"""Changes made from Omarchy, written straight to the provider.

Every write names the event by its uid (as in events.json) and is checked
against the local copy first: an unknown uid, or an event the account can't
change, stops before anything is sent. A write that succeeds is applied to the
local copy at once, so the widget shows it without waiting, and a sync then
brings back the provider's own version.

Writes that replace a field wholesale carry the provider's version stamp
(Google's etag as If-Match), so a change made elsewhere since the event was
read is never overwritten: the write fails with Conflict instead.
"""

import os
import urllib.parse

from . import auth, sync

GOOGLE = "https://www.googleapis.com/calendar/v3"
GRAPH = "https://graph.microsoft.com/v1.0"

ANSWERS = {"accept": "accepted", "tentative": "tentative", "decline": "declined"}
GRAPH_ACTIONS = {"accept": "accept", "tentative": "tentativelyAccept", "decline": "decline"}


class EditError(RuntimeError):
    """A change that can't be made, said in plain words."""


def q(part):
    return urllib.parse.quote(part, safe="")


def locate(uid):
    """(account entry, state path, state, event, provider event id) for a uid."""
    name = uid.split("/", 1)[0]
    a = next((x for x in auth.load_accounts() if x["name"] == name), None)
    if not a:
        raise EditError("no account called %r" % name)
    path = os.path.join(sync.CACHE, "state-%s.json" % name)
    st = sync.read_json(path, {"events": {}})
    e = st.get("events", {}).get(uid)
    if not e:
        raise EditError("that event isn't in the local copy any more; sync and try again")
    prefix = "%s/%s/" % (name, e["calendar"])
    return a, path, st, e, uid[len(prefix):]


def token(a):
    return auth.google_access(a) if a["provider"] == "google" else auth.ms_access(a)


def respond(uid, answer, series=False):
    """Accept, tentatively accept or decline an invitation, and tell the organiser.

    series answers for every occurrence of a recurring event; otherwise only
    this one.
    """
    if answer not in ANSWERS:
        raise EditError("the answer is accept, tentative or decline")
    a, path, st, e, eid = locate(uid)
    if e.get("organizer"):
        raise EditError("this is your own event: there is no invitation to answer")
    if series and not e.get("seriesId"):
        series = False
    target = e["seriesId"] if series else eid
    tok = token(a)
    if a["provider"] == "google":
        _google_respond(tok, e["calendar"], target, ANSWERS[answer])
    else:
        auth.send_json("POST", GRAPH + "/me/calendars/%s/events/%s/%s" % (q(e["calendar"]), q(target), GRAPH_ACTIONS[answer]),
                       tok, {"sendResponse": True})
    _apply(a["name"], lambda x: x["uid"] == uid or series and x.get("seriesId") == e["seriesId"],
           {"response": ANSWERS[answer]})


def _google_respond(tok, cal, eid, status):
    # Google has no "respond" call: the answer is this account's entry in the
    # guest list, and the list is written back whole. The etag of the copy
    # just read guards it, so a guest added meanwhile is never dropped; on a
    # conflict it is read and tried once more.
    url = GOOGLE + "/calendars/%s/events/%s" % (q(cal), q(eid))
    for attempt in (1, 2):
        ev = auth.get_json(url, tok)
        guests = ev.get("attendees") or []
        me = next((g for g in guests if g.get("self")), None)
        if not me:
            raise EditError("you aren't on this event's guest list (a group invitation?): answer it in Google Calendar")
        me["responseStatus"] = status
        try:
            auth.send_json("PATCH", url + "?sendUpdates=all", tok, {"attendees": guests},
                           {"If-Match": ev["etag"]})
            return
        except auth.Conflict:
            if attempt == 2:
                raise


def _apply(account, match, fields):
    """Patch the local copy (under the sync lock) and republish events.json."""
    with sync.locked():
        path = os.path.join(sync.CACHE, "state-%s.json" % account)
        st = sync.read_json(path, {"events": {}})
        for x in st.get("events", {}).values():
            if match(x):
                x.update(fields)
        sync.write_private(path, st)
        sync.republish()


# ------------------------------------------------------------ create, delete

def local_zone():
    """The IANA name of this machine's zone, in its current spelling.

    /etc/localtime often points at an old alias ("Canada/Eastern"), which
    Microsoft may not know; tzdata's own link table gives the name it is now.
    """
    try:
        name = os.path.realpath("/etc/localtime").split("/zoneinfo/", 1)[1]
    except IndexError:
        return "UTC"
    try:
        with open("/usr/share/zoneinfo/tzdata.zi") as f:
            for line in f:
                if line.startswith("L ") and line.split()[2:3] == [name]:
                    return line.split()[1]
    except OSError:
        pass
    return name


def when(text, all_day):
    """A date ("2026-10-02") or a local or zoned time ("2026-10-02 14:30")."""
    from datetime import date, datetime
    t = text.strip()
    if all_day:
        return date.fromisoformat(t[:10])
    dt = datetime.fromisoformat(t.replace(" ", "T"))
    return dt if dt.tzinfo else dt.astimezone()


def calendar_of(ref):
    """(account entry, calendar entry) for "<account>/<calendar id>"."""
    name, _, cid = ref.partition("/")
    a = next((x for x in auth.load_accounts() if x["name"] == name), None)
    st = sync.read_json(os.path.join(sync.CACHE, "state-%s.json" % name), {})
    cal = (st.get("calendars") or {}).get(cid)
    if not a or not cal:
        raise EditError("no shown calendar %r (calendar-ctl calendars)" % ref)
    if not cal.get("editable"):
        raise EditError("%s is read-only" % (cal.get("name") or cid))
    return a, cal


def create(ref, title, start, end=None, all_day=False, location="", invite=()):
    """A new event, and invitations to anyone named in invite. Returns its uid."""
    from datetime import timedelta
    from . import google, graph
    from .model import utc_iso
    a, cal = calendar_of(ref)
    all_day = bool(all_day)
    s, e = when(start, all_day), when(end, all_day) if end else None
    if all_day:
        e = e or s + timedelta(days=1)   # end is exclusive: the day after the last
    else:
        e = e or s + timedelta(hours=1)
    if e <= s:
        raise EditError("the end has to be after the start")
    title = title.strip() or "(no title)"
    tok = token(a)
    if a["provider"] == "google":
        body = {"summary": title, "location": location,
                "start": {"date": s.isoformat()} if all_day else {"dateTime": utc_iso(s)},
                "end": {"date": e.isoformat()} if all_day else {"dateTime": utc_iso(e)},
                "attendees": [{"email": m} for m in invite]}
        ev = auth.send_json("POST", GOOGLE + "/calendars/%s/events?sendUpdates=all" % q(cal["id"]), tok, body)
        new = google.normalise(a["name"], cal, ev)
    else:
        zone = local_zone() if all_day else "UTC"
        stamp = (lambda d: d.isoformat() + "T00:00:00") if all_day else (lambda d: utc_iso(d)[:-1])
        body = {"subject": title, "isAllDay": all_day,
                "start": {"dateTime": stamp(s), "timeZone": zone},
                "end": {"dateTime": stamp(e), "timeZone": zone},
                "location": {"displayName": location},
                "attendees": [{"emailAddress": {"address": m}, "type": "required"} for m in invite]}
        ev = auth.send_json("POST", GRAPH + "/me/calendars/%s/events" % q(cal["id"]), tok, body,
                            {"Prefer": 'outlook.timezone="UTC"'})
        new = graph.normalise(a["name"], cal, ev)
    _add(a["name"], new)
    return new["uid"]


def delete(uid, series=False):
    """Delete an event (guests get a cancellation), or its whole series.

    Deleting an invitation you didn't organise only takes it off your
    calendar; decline it instead to tell the organiser.
    """
    a, path, st, e, eid = locate(uid)
    if not (st.get("calendars") or {}).get(e["calendar"], {}).get("editable"):
        raise EditError("this calendar is read-only")
    if series and not e.get("seriesId"):
        series = False
    target = e["seriesId"] if series else eid
    tok = token(a)
    # Only this copy's own etag guards it; a series master has its own, which
    # the local copy doesn't hold, so a series delete goes unguarded.
    guard = {} if series or not e.get("etag") else {"If-Match": e["etag"]}
    if a["provider"] == "google":
        auth.send_json("DELETE", GOOGLE + "/calendars/%s/events/%s?sendUpdates=all" % (q(e["calendar"]), q(target)),
                       tok, None, guard)
    else:
        auth.send_json("DELETE", GRAPH + "/me/calendars/%s/events/%s" % (q(e["calendar"]), q(target)),
                       tok, None, guard)
    with sync.locked():
        st = sync.read_json(path, {"events": {}})
        st["events"] = {u: x for u, x in st.get("events", {}).items()
                        if not (u == uid or series and x.get("seriesId") == e["seriesId"])}
        sync.write_private(path, st)
        sync.republish()


def _add(account, event):
    with sync.locked():
        path = os.path.join(sync.CACHE, "state-%s.json" % account)
        st = sync.read_json(path, {"events": {}})
        st.setdefault("events", {})[event["uid"]] = event
        sync.write_private(path, st)
        sync.republish()


# ------------------------------------------------------------------ edit

def update(uid, title=None, start=None, end=None, all_day=None, location=None, series=False):
    """Change an event's title, times or place; None leaves a field as it is.

    Guarded by the local copy's etag: if the event changed anywhere else since
    the last sync, nothing is written and Conflict says so. With series, the
    title and place change for every occurrence; times can only be moved one
    occurrence at a time (a series' own start is its first occurrence, not
    this one, so moving it from here would shift every date by surprise).
    """
    from datetime import timedelta
    from . import google, graph
    from .model import utc_iso
    a, path, st, e, eid = locate(uid)
    if not e.get("editable"):
        raise EditError("you can't change this event: it isn't yours, or the calendar is read-only")
    series = bool(series and e.get("seriesId"))
    if series and (start or end or all_day is not None):
        raise EditError("a whole series can change its title and place here, not its times; "
                        "move one occurrence, or the series in the provider's app")
    cal = (st.get("calendars") or {}).get(e["calendar"])
    if not cal:
        raise EditError("that calendar isn't shown any more; sync and try again")
    timing = start is not None or end is not None or all_day is not None
    if timing:
        ad = e["allDay"] if all_day is None else all_day
        s = when(start if start else e["start"], ad)
        if end:
            en = when(end, ad)
        elif all_day is None:
            en = when(e["end"], ad)   # an unchanged kind keeps its end...
        else:
            en = s + (timedelta(days=1) if ad else timedelta(hours=1))   # ...a new kind gets a fresh one
        if not end and start and all_day is None:
            # A new start alone moves the event, keeping its length.
            en = s + (when(e["end"], ad) - when(e["start"], ad))
        if en <= s:
            raise EditError("the end has to be after the start")
    target = e["seriesId"] if series else eid
    guard = {} if series else {"If-Match": e["etag"]} if e.get("etag") else {}
    tok = token(a)
    if a["provider"] == "google":
        body = {}
        if title is not None:
            body["summary"] = title.strip() or "(no title)"
        if location is not None:
            body["location"] = location
        if timing:
            body["start"] = {"date": s.isoformat(), "dateTime": None} if ad else {"dateTime": utc_iso(s), "date": None}
            body["end"] = {"date": en.isoformat(), "dateTime": None} if ad else {"dateTime": utc_iso(en), "date": None}
        ev = auth.send_json("PATCH", GOOGLE + "/calendars/%s/events/%s?sendUpdates=all" % (q(e["calendar"]), q(target)),
                            tok, body, guard)
    else:
        body = {}
        if title is not None:
            body["subject"] = title.strip() or "(no title)"
        if location is not None:
            body["location"] = {"displayName": location}
        if timing:
            zone = local_zone() if ad else "UTC"
            stamp = (lambda d: d.isoformat() + "T00:00:00") if ad else (lambda d: utc_iso(d)[:-1])
            body.update({"isAllDay": ad, "start": {"dateTime": stamp(s), "timeZone": zone},
                         "end": {"dateTime": stamp(en), "timeZone": zone}})
        ev = auth.send_json("PATCH", GRAPH + "/me/calendars/%s/events/%s" % (q(e["calendar"]), q(target)),
                            tok, body, dict(guard, Prefer='outlook.timezone="UTC"'))
    if series:
        # The reply is the series itself; its occurrences come back with the sync.
        fields = {k: v for k, v in (("title", body.get("summary") or body.get("subject")),
                                    ("location", location)) if v is not None}
        _apply(a["name"], lambda x: x.get("seriesId") == e["seriesId"], fields)
    else:
        new = (google if a["provider"] == "google" else graph).normalise(a["name"], cal, ev)
        _add(a["name"], new)
