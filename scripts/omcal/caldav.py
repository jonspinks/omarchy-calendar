"""CalDAV (RFC 4791): Fastmail, and any other server that speaks it.

Signing in is HTTP Basic with an app password, kept in the keyring like the
other providers' refresh tokens. The account's calendar home (Fastmail's is
https://caldav.fastmail.com/dav/calendars/user/<email>/) is listed with one
PROPFIND; each calendar in it is fetched with a calendar-query REPORT that asks
the server to expand series into occurrences inside the window, the same
shape Google's singleEvents and Graph's calendarView hand back.

There is no delta here. Each calendar carries a ctag (or a sync-token) that
changes whenever anything in it does; sync.py keeps the one it last fetched
as the calendar's cursor, and a calendar whose tag hasn't moved isn't fetched
at all. One that has moved is fetched whole: a few months of one calendar is
a single small request, and it can't drift.

A server that ignores the expand request sends each series as its rule, and
ical.occurrences() expands it here instead.

XML is read by namespace, never by prefix: servers pick their own prefixes
(Fastmail's replies don't use "d:").

Each event keeps the address of the resource (the .ics file) it came from, so
that davedit.py can read it whole, patch it and put it back.
"""

import base64
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

from . import auth, files, ical
from .model import find_join, guest, guest_fields, utc_iso

FASTMAIL = "https://caldav.fastmail.com/dav/calendars/user/%s/"

DAV, CAL = "DAV:", "urn:ietf:params:xml:ns:caldav"
CS, APPLE = "http://calendarserver.org/ns/", "http://apple.com/ns/ical/"

PARTSTAT = {"ACCEPTED": "accepted", "TENTATIVE": "tentative", "DECLINED": "declined",
            "NEEDS-ACTION": "needsAction"}


def fastmail_home(email):
    return FASTMAIL % urllib.parse.quote(email, safe="@")


def _t(ns, name):
    return "{%s}%s" % (ns, name)


# ------------------------------------------------------------------- HTTP

class Session:
    """What a CalDAV account signs in with: its home URL, user name and password.

    Stands where the other providers pass an access token, so sync.py can
    hand it to calendars() and fetch() the same way.
    """

    def __init__(self, url, user, password):
        self.url, self.user, self.password = url, user, password

    def __repr__(self):   # never the password, in a traceback or a log
        return "Session(%r, %r)" % (self.url, self.user)

    def send(self, method, url, body=None, headers=None):
        """One request: (status, {lower-case header: value}, reply bytes).

        401 is a sign-in problem; 412 is a conflict (an If-Match or
        If-None-Match didn't hold, so nothing was written); any other error
        status is an HttpError with its code.
        """
        check_url(url)
        cred = base64.b64encode(("%s:%s" % (self.user, self.password)).encode()).decode()
        h = {"Authorization": "Basic " + cred}
        h.update(headers or {})
        req = urllib.request.Request(url, data=body, method=method, headers=h)
        host = urllib.parse.urlsplit(url).netloc
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, {k.lower(): v for k, v in r.headers.items()}, files.read_reply(r)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                e.close()
                raise auth.AuthError("%s refused the saved password (a revoked app password?)" % host)
            if e.code == 412:
                e.close()
                raise auth.Conflict("the event was changed elsewhere; sync and try again")
            raise auth.HttpError(host, e.code, auth.error_text(e))


def login(a):
    """The saved sign-in for a caldav account, as a Session."""
    s = auth.secret_load(a["name"])
    return Session(a["url"], a.get("user") or a.get("email", ""), s["password"])


def check_url(url):
    """The password goes with every request, so only over https (or to this machine)."""
    u = urllib.parse.urlsplit(url)
    if u.scheme == "https" or u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1", "::1"):
        return
    # Raised as a sign-in problem: the account has to be added again, properly.
    raise auth.AuthError("a CalDAV address has to start with https://, not %r" % url)


def _request(session, method, url, body, depth):
    """One WebDAV request; the reply's raw bytes (a 207 multistatus, usually)."""
    return session.send(method, url, body.encode(), {
        "Depth": str(depth), "Content-Type": "application/xml; charset=utf-8"})[2]


def dav(session, method, url, body, depth):
    """A request, and its multistatus as [(absolute href, {prop tag: element})].

    Only properties the server found (a 200 propstat) are kept; the rest come
    back as empty 404 elements, which would read as blank values.
    """
    raw = _request(session, method, url, body, depth)
    try:
        return multistatus(raw, url)
    except ET.ParseError as e:
        raise auth.HttpError(urllib.parse.urlsplit(url).netloc, 207, "unreadable XML (%s)" % e)


def multistatus(raw, base):
    out = []
    root = ET.fromstring(raw)
    for resp in root.iter(_t(DAV, "response")):
        href = (resp.findtext(_t(DAV, "href")) or "").strip()
        props = {}
        for ps in resp.findall(_t(DAV, "propstat")):
            # "HTTP/1.1 200 OK"; a propstat without a status is taken as found.
            if (ps.findtext(_t(DAV, "status")) or "").split()[1:2] not in ([], ["200"]):
                continue
            for prop in ps.findall(_t(DAV, "prop")):
                for p in prop:
                    props[p.tag] = p
        out.append((urllib.parse.urljoin(base, href), props))
    return out


# -------------------------------------------------------------- calendars

LIST = """<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"
            xmlns:cs="http://calendarserver.org/ns/" xmlns:a="http://apple.com/ns/ical/">
  <d:prop>
    <d:resourcetype/><d:displayname/><d:current-user-privilege-set/><d:sync-token/>
    <c:supported-calendar-component-set/><c:schedule-default-calendar-URL/>
    <cs:getctag/><a:calendar-color/>
  </d:prop>
</d:propfind>"""


def calendars(session):
    """The calendars in the account's home that hold events, with their colours and tags.

    Scheduling Inbox and Outbox, task lists and address books are left out.
    The default calendar for new invitations (named on the scheduling Inbox)
    is the primary one; failing that, the first.
    """
    out, default = [], None
    for href, props in dav(session, "PROPFIND", session.url, LIST, 1):
        dflt = props.get(_t(CAL, "schedule-default-calendar-URL"))
        if dflt is not None and (dflt.findtext(_t(DAV, "href")) or "").strip():
            default = urllib.parse.urljoin(href, dflt.findtext(_t(DAV, "href")).strip())
        rt = props.get(_t(DAV, "resourcetype"))
        if rt is None or rt.find(_t(CAL, "calendar")) is None:
            continue
        comps = props.get(_t(CAL, "supported-calendar-component-set"))
        # No component set means the collection takes every kind (RFC 4791 5.2.3).
        if comps is not None and len(comps) and not any(c.get("name", "").upper() == "VEVENT" for c in comps):
            continue
        privs = props.get(_t(DAV, "current-user-privilege-set"))
        writable = privs is not None and any(
            privs.find(".//" + _t(DAV, p)) is not None for p in ("write", "write-content", "all"))
        seg = urllib.parse.unquote(urllib.parse.urlsplit(href).path.rstrip("/").rsplit("/", 1)[-1])
        out.append({"id": seg, "href": href,
                    "name": (_text(props, DAV, "displayname") or seg),
                    "color": colour(_text(props, APPLE, "calendar-color")),
                    "primary": False, "editable": writable,
                    "ctag": _text(props, CS, "getctag"), "syncToken": _text(props, DAV, "sync-token")})
    if out:
        pick = next((c for c in out if default and c["href"].rstrip("/") == default.rstrip("/")), out[0])
        pick["primary"] = True
    return out


def _text(props, ns, name):
    el = props.get(_t(ns, name))
    return (el.text or "").strip() if el is not None else ""


def colour(text):
    """Apple's calendar-color, "#RRGGBBAA" or "#RRGGBB", as "#RRGGBB"."""
    t = (text or "").strip()
    if len(t) == 9 and t.startswith("#"):
        return t[:7]
    return t if len(t) == 7 and t.startswith("#") else ""


# The shape of the events a cursor was fetched with. Bumped when they gain a
# field (2: href and recurrenceId, for writing back) or read one differently
# (3: a series' bare first occurrence), so every calendar is fetched again
# once, not left as it was until something in it changes.
SHAPE = 3


def cursor(cal):
    """The tag that changes whenever anything in the calendar does, or None.

    A server that offers neither has no cursor, so its calendars are fetched
    whole on every pass.
    """
    tag = cal.get("ctag") or cal.get("syncToken")
    return "%d:%s" % (SHAPE, tag) if tag else None


# ----------------------------------------------------------------- events

QUERY = """<?xml version="1.0" encoding="utf-8"?>
<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <d:getetag/>
    <c:calendar-data><c:expand start="%(start)s" end="%(end)s"/></c:calendar-data>
  </d:prop>
  <c:filter>
    <c:comp-filter name="VCALENDAR">
      <c:comp-filter name="VEVENT"><c:time-range start="%(start)s" end="%(end)s"/></c:comp-filter>
    </c:comp-filter>
  </c:filter>
</c:calendar-query>"""


def _stamp(iso):
    """ "2026-08-24T00:00:00Z" as CalDAV writes it: "20260824T000000Z"."""
    return iso.replace("-", "").replace(":", "")


def fetch(account, session, cal, window, since=None, me=""):
    """Returns (events, removed_ids, cursor), like the other providers.

    since is the calendar's cursor from the last fetch. sync.py passes one
    only when it still matches the calendar's tag, so there is nothing new
    to read; otherwise (None) the whole window is fetched, and sync.py
    replaces every event it had for this calendar.
    """
    if since:
        return [], [], since
    body = QUERY % {"start": _stamp(window[0]), "end": _stamp(window[1])}
    events = []
    for href, props in dav(session, "REPORT", cal["href"], body, 1):
        data = _text(props, CAL, "calendar-data")
        if not data:
            continue
        try:
            events.extend(resource_events(account, cal, data, _text(props, DAV, "getetag"), window, me, href))
        except (ValueError, IndexError, KeyError) as e:
            # One unreadable event (a mangled date, say) is skipped, not
            # allowed to stop the calendar, or every other account, syncing.
            ical.warn("skipped %s: %s" % (href, e))
    return events, [], cursor(cal)


def resource_events(account, cal, data, etag, window, me="", href=""):
    """Every event in one calendar object resource that overlaps the window.

    href is the resource's own address, kept on each event for writing back.

    An expanded series arrives as one VEVENT per occurrence, each with its
    RECURRENCE-ID. One still carrying its RRULE is expanded here, with its
    EXDATEs skipped and any modified occurrence (a VEVENT of the same UID
    with a RECURRENCE-ID) taking the place of the one it replaces.
    """
    lo = datetime.fromisoformat(window[0].replace("Z", "+00:00"))
    hi = datetime.fromisoformat(window[1].replace("Z", "+00:00"))
    vevents = ical.parse(data).find("VEVENT")
    overridden = {ical.instant_key(ical.value_time(v.get("RECURRENCE-ID")))
                  for v in vevents if v.get("RECURRENCE-ID")}
    # Fastmail's expand leaves the RECURRENCE-ID off a series' first
    # occurrence (and its RRULE with it), so on its own it looks like a
    # one-off. Its siblings give it away: they share its UID.
    in_series = {v.value("UID") for v in vevents if v.get("RECURRENCE-ID")}
    out = []
    for v in vevents:
        start = ical.value_time(v.get("DTSTART"))
        if start is None:
            continue
        span = _length(v, start)
        rrule = v.value("RRULE")
        if rrule and not v.get("RECURRENCE-ID"):
            skip = {ical.instant_key(t) for t in ical.value_times(v.all("EXDATE"))} | overridden
            starts = [t for t in ical.occurrences(start, rrule, hi, v.value("UID"))
                      if ical.instant_key(t) not in skip]
            series = True
        elif not v.get("RECURRENCE-ID") and v.value("UID") in in_series:
            starts, series = [start], True
        else:
            starts, series = [start], False
        for s in starts:
            if _overlaps(s, s + span, lo, hi):
                out.append(normalise(account, cal, v, s, s + span, etag, me,
                                     occurrence=s if series else None, href=href))
    return out


def _length(v, start):
    """How long the event lasts: DTEND - DTSTART, or DURATION, or the defaults
    (a day for an all-day event, no time at all for a timed one)."""
    end = ical.value_time(v.get("DTEND"))
    if end is not None and type(end) is type(start):
        return end - start
    dur = ical.duration(v.value("DURATION"))
    if dur is not None:
        if not isinstance(start, datetime):
            return timedelta(days=max(1, dur.days))
        return dur
    return timedelta(days=1) if not isinstance(start, datetime) else timedelta(0)


def _overlaps(s, e, lo, hi):
    if isinstance(s, datetime):
        return s < hi and (e > lo or s >= lo)
    return s < hi.date() and e > lo.date()


def _addr(value):
    v = (value or "").strip()
    return v[7:] if v.lower().startswith("mailto:") else v


def guests(v, me):
    """The guest list's fields, and this account's own ATTENDEE entry (or None)."""
    org_value, org_params = v.get("ORGANIZER") or ("", {})
    org = _addr(org_value).lower()
    out, mine = [], None
    for value, params in v.all("ATTENDEE"):
        addr = _addr(value)
        is_me = bool(me) and addr.lower() == me
        if is_me:
            mine = params
        out.append(guest(addr, params.get("CN"), PARTSTAT.get(params.get("PARTSTAT", "").upper(), "needsAction"),
                         optional=params.get("ROLE", "").upper() == "OPT-PARTICIPANT",
                         organizer=bool(org) and addr.lower() == org, me=is_me,
                         room=params.get("CUTYPE", "").upper() in ("ROOM", "RESOURCE")))
    if out and org and not any(g["organizer"] for g in out):
        out.append(guest(_addr(org_value), org_params.get("CN"), "accepted", organizer=True,
                         me=bool(me) and org == me))
    return guest_fields(out), mine


def normalise(account, cal, v, start, end, etag="", me="", occurrence=None, href=""):
    """One VEVENT, at one of its occurrences, in the model's shape.

    occurrence is set when the start came from expanding a rule here; an
    occurrence the server expanded carries its own RECURRENCE-ID instead.
    It can be changed from here when the calendar can be written and the
    event is yours: organised by you, or with nobody else on it. Someone
    else's invitation is answered, not edited.
    """
    me = (me or "").lower()
    uid = v.value("UID")
    rid = v.get("RECURRENCE-ID")
    rid_key = ical.instant_key(ical.value_time(rid)) if rid else (
        ical.instant_key(occurrence) if occurrence is not None else None)
    all_day = not isinstance(start, datetime)
    org = _addr(v.value("ORGANIZER")).lower()
    fields, mine = guests(v, me)
    organizer = bool(me) and org == me or not org and not v.get("ATTENDEE")
    if organizer:
        response = "organizer"
    elif mine is not None:
        response = PARTSTAT.get(mine.get("PARTSTAT", "NEEDS-ACTION").upper(), "needsAction")
    else:
        response = "none"
    # A CONFERENCE link comes from whoever sent the invitation, so it goes
    # through the same known-hosts check as a link in the description.
    conf = [x for n in ("CONFERENCE", "X-GOOGLE-CONFERENCE", "X-MICROSOFT-SKYPETEAMSMEETINGURL",
                        "X-MICROSOFT-ONLINEMEETINGCONFLINK") for x, _ in v.all(n)]
    status = v.value("STATUS", "CONFIRMED").lower()
    return {
        "uid": "%s/%s/%s%s" % (account, cal["id"], uid, "@" + rid_key if rid_key else ""),
        "account": account, "calendar": cal["id"],
        "title": v.value("SUMMARY").strip() or "(no title)",
        "allDay": all_day,
        "start": start.isoformat() if all_day else utc_iso(start),
        "end": end.isoformat() if all_day else utc_iso(end),
        "location": v.value("LOCATION"),
        "join": find_join(*conf, v.value("URL"), v.value("LOCATION"), v.value("DESCRIPTION")),
        "response": response,
        "organizer": organizer,
        "status": status if status in ("confirmed", "tentative", "cancelled") else "confirmed",
        "busy": v.value("TRANSP").upper() != "TRANSPARENT",
        "recurring": rid_key is not None or bool(v.value("RRULE")),
        "seriesId": uid if rid_key is not None or v.value("RRULE") else None,
        "editable": bool(cal.get("editable")) and organizer,
        "webLink": "",
        "etag": etag,
        "href": href,
        "recurrenceId": rid_key,
        "remind": reminders(v),
        **fields,
    }


def reminders(v):
    """Minutes before the start of each pop-up (DISPLAY) or sound (AUDIO) alarm.

    Only alarms set relative to the start count; one at a fixed time, or
    after the start, isn't a "minutes before" reminder.
    """
    out = set()
    for alarm in v.subs:
        if alarm.name != "VALARM" or alarm.value("ACTION").upper() not in ("DISPLAY", "AUDIO"):
            continue
        trig = alarm.get("TRIGGER")
        if not trig or trig[1].get("VALUE", "").upper() == "DATE-TIME" or trig[1].get("RELATED", "START").upper() != "START":
            continue
        d = ical.duration(trig[0])
        if d is not None and d <= timedelta(0):
            out.add(int(-d.total_seconds() // 60))
    return sorted(out)


def upcoming(session, me="", days=30, limit=5):
    """The next few events across every calendar, for calendar-ctl test."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    window = (utc_iso(now), utc_iso(now + timedelta(days=days)))
    events = []
    for cal in calendars(session):
        events.extend(fetch("test", session, cal, window, None, me)[0])
    today = date.today().isoformat()
    events = [e for e in events if e["status"] != "cancelled" and (e["allDay"] and e["end"] > today or e["end"] > window[0])]
    return sorted(events, key=lambda e: e["start"])[:limit]
