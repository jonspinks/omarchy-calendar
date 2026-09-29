"""Changes to CalDAV events: read the resource, patch it, put it back.

An event on a CalDAV server is one iCalendar file (a resource), and for a
series that one file holds the rule and every changed occurrence together. So
every change here takes the same three steps: GET the resource with its ETag,
patch its text (icalwrite.Doc: only the lines being changed are touched; time
zones, alarms and other apps' X- properties go back byte for byte), and PUT it
back with If-Match. A copy changed elsewhere meanwhile is never overwritten:
the server answers 412, nothing is written, and auth.Conflict says so. Nothing
is retried: the next sync shows what changed, and you decide again.

One occurrence of a series is changed through its override: a VEVENT with the
same UID and a RECURRENCE-ID naming the occurrence, made from the series the
first time it's needed. Deleting one occurrence adds an EXDATE to the series.

Invitations, answers and cancellations are the server's job, not this code's.
Fastmail (Cyrus) and most servers do implicit scheduling (RFC 6638): a PUT that
changes an event you organise sends its guests the update or cancellation, and
one that changes your own PARTSTAT on someone else's event sends the organiser
your reply. Nothing here sends mail.

Each function returns the resource as the server now holds it, (text, etag),
or None when it's gone, for edit.py to put into the local copy.
"""

import copy
import urllib.parse
import uuid
from datetime import datetime, timezone

from . import auth, ical, icalwrite
from .caldav import _addr
from .edit import EditError, merge_guests
from .icalwrite import line, time_value, utc_stamp

PRODID = "-//blacksheep.calendar//Datebook for Omarchy//EN"
ICS = "text/calendar; charset=utf-8"
PARTSTAT = {"accept": "ACCEPTED", "tentative": "TENTATIVE", "decline": "DECLINED"}


# ------------------------------------------------------------------- HTTP

def _read(session, href):
    """The resource as it stands: (Doc, etag). One that's gone is a conflict too."""
    try:
        _, headers, raw = session.send("GET", href)
    except auth.HttpError as e:
        if e.code in (404, 410):
            raise auth.Conflict("the event is no longer on the server; sync and try again")
        raise
    try:
        return icalwrite.Doc(raw.decode("utf-8")), headers.get("etag", "")
    except (UnicodeDecodeError, ValueError) as e:
        raise EditError("the server's copy of this event can't be read (%s); change it in its own app" % e)


def _check(e):
    if not e.get("href"):
        raise EditError("the local copy of this event predates editing; sync and try again")


def _same(a, b):
    """Two ETags for the same version? A weak one (W/"x") matches its strong
    twin, and a quoted one its unquoted twin: a server may write getetag in a
    REPORT differently from the ETag header of a GET."""
    def strip(t):
        t = (t or "").strip()
        return (t[2:] if t.startswith("W/") else t).strip('"')
    return strip(a) == strip(b)


def _unchanged(etag, e):
    """Stop if the server's copy isn't the one the local copy was made from."""
    if not _same(etag, e.get("etag")):
        raise auth.Conflict("the event was changed elsewhere; sync and try again")


def _put(session, href, text, guard):
    """Write the resource; (text, etag) as the server now holds it.

    A server that changes what it stores (scheduling adds SCHEDULE-STATUS to
    each guest, say) sends no ETag back, as RFC 4791 5.3.4 requires; then the
    stored copy is read again, so the local copy matches it exactly.
    """
    _, headers, _ = session.send("PUT", href, text.encode("utf-8"), dict(guard, **{"Content-Type": ICS}))
    if headers.get("etag"):
        return text, headers["etag"]
    doc, etag = _read(session, href)
    return doc.text(), etag


def _delete(session, href, etag, mine):
    headers = {"If-Match": etag}
    if not mine:
        # Your copy of someone else's invitation: take it off your calendar
        # without the server declining on your behalf (RFC 6638 8.1), as the
        # other providers do. Declining is what respond() is for.
        headers["Schedule-Reply"] = "F"
    try:
        session.send("DELETE", href, None, headers)
    except auth.HttpError as e:
        if e.code not in (404, 410):   # already gone is what was wanted
            raise


# ------------------------------------------------------------ components

def _rid(block):
    got = block.get("RECURRENCE-ID")
    return ical.instant_key(ical.value_time(got)) if got else None


def _master(doc):
    """The series itself (or the one event of a resource that doesn't repeat)."""
    return next((b for b in doc.events() if not b.get("RECURRENCE-ID")), None)


def _override(doc, rid):
    return next((b for b in doc.events() if _rid(b) == rid), None)


def _occurrence(doc, rid):
    """The override for one occurrence, made from the series if it has none yet."""
    got = _override(doc, rid)
    if got is not None:
        return got
    master = _master(doc)
    if master is None or not master.get("RRULE") and not master.get("RDATE"):
        raise EditError("that occurrence isn't in the server's copy any more; sync and try again")
    return _split(doc, master, rid)


def _split(doc, master, rid):
    """A copy of the series for one occurrence, placed with it: every line kept
    (alarms, guests, X- properties), less the rule, and moved to that date."""
    o = copy.deepcopy(master)
    for name in ("RRULE", "RDATE", "EXDATE", "EXRULE"):
        o.drop(name)
    start = ical.parse_time(rid)
    old_start = master.get("DTSTART")
    params, value = time_value(start, old_start)
    o.set("DTSTART", line("DTSTART", value, params))
    o.add(line("RECURRENCE-ID", value, params), after="UID")
    old_end = master.get("DTEND")
    if old_end:
        end = start + (ical.value_time(old_end) - ical.value_time(old_start))
        o.set("DTEND", line("DTEND", *reversed(time_value(end, old_end))))
    # After the series' last copy, so the ones already there keep their places.
    cal = doc.calendar
    last = [b for b in doc.events() if b.value("UID") == master.value("UID")][-1]
    cal.items.insert(cal.items.index(last) + 1, o)
    return o


def _only(doc):
    """The event of a resource that doesn't repeat."""
    events = doc.events()
    if not events:
        raise EditError("the server's copy of this event has no event in it; sync and try again")
    return _master(doc) or events[0]


def _start_key(e):
    """The event's start as a RECURRENCE-ID key (what ical.instant_key gives)."""
    return e["start"].replace("-", "").replace(":", "")


def _as_occurrence(doc, e):
    """e itself, or e as one occurrence when the server's copy is a series.

    The local copy can call an occurrence a one-off (a series with only one
    occurrence in the window, or a first occurrence a server sent without its
    RECURRENCE-ID). Acting on it as a one-off would change or delete the
    whole series, so the server's copy decides.
    """
    if e.get("recurrenceId"):
        return e
    master = _master(doc)
    if master is not None and (master.get("RRULE") or master.get("RDATE")):
        return dict(e, recurrenceId=_start_key(e))
    return e


def _targets(doc, e, series):
    """The VEVENTs a change goes to: the series and its overrides, one
    occurrence's override, or the single event."""
    if series:
        master = _master(doc)
        if master is None:
            raise EditError("only some occurrences of this series are on your calendar; "
                            "change them one at a time")
        return [master] + [b for b in doc.events() if b is not master]
    e = _as_occurrence(doc, e)
    if e.get("recurrenceId"):
        return [_occurrence(doc, e["recurrenceId"])]
    return [_only(doc)]


def _touch(block, sequence=False):
    """Stamp a changed VEVENT; a change guests must hear about bumps SEQUENCE,
    so their calendars take it over the copy they have."""
    now = utc_stamp(datetime.now(timezone.utc))
    block.set("DTSTAMP", "DTSTAMP:" + now)
    block.set("LAST-MODIFIED", "LAST-MODIFIED:" + now)
    if sequence:
        try:
            n = int(block.value("SEQUENCE", "0").strip() or 0)
        except ValueError:
            n = 0
        block.set("SEQUENCE", "SEQUENCE:%d" % (n + 1))


def _mailto(address):
    return "mailto:" + address


# ---------------------------------------------------------------- answer

def respond(a, session, e, answer, series):
    """Set your PARTSTAT on the organiser's invitation; the server sends the reply.

    For the whole series, your answer goes on the series and on every
    occurrence that has its own copy of the guest list.
    """
    _check(e)
    me = (a.get("email") or "").lower()
    doc, etag = _read(session, e["href"])
    changed = [b for b in _targets(doc, e, series) if _set_partstat(b, me, PARTSTAT[answer])]
    if not changed:
        raise EditError("you (%s) aren't on this event's guest list (a group invitation?): "
                        "answer it in your calendar's own app" % (me or "no address"))
    for b in changed:
        _touch(b)
    # The copy just read is the guard: an answer needs no more than that.
    return _put(session, e["href"], doc.text(), {"If-Match": etag})


def _set_partstat(block, me, partstat):
    found = False
    for k, value, _ in block.props("ATTENDEE"):
        if me and _addr(value).lower() == me:
            block.replace(k, icalwrite.with_param(block.content(k), "PARTSTAT", partstat))
            found = True
    return found


# ---------------------------------------------------------------- create

def create(a, session, cal, title, s, e, all_day, location, invite, busy):
    """A new resource in the calendar; returns (href, uid, text, etag).

    PUT with If-None-Match: *, so an existing resource is never replaced.
    """
    me = (a.get("email") or "").lower()
    if invite and not me:
        raise EditError("this account has no email address of its own, so it can't send invitations")
    uid = "%s@omacal" % uuid.uuid4()
    now = utc_stamp(datetime.now(timezone.utc))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:" + PRODID, "CALSCALE:GREGORIAN", "BEGIN:VEVENT",
             "UID:" + uid, "DTSTAMP:" + now, "CREATED:" + now, "LAST-MODIFIED:" + now, "SEQUENCE:0",
             line("DTSTART", *reversed(time_value(s))), line("DTEND", *reversed(time_value(e))),
             line("SUMMARY", title, text=True)]
    if location:
        lines.append(line("LOCATION", location, text=True))
    lines.append("TRANSP:" + ("OPAQUE" if busy else "TRANSPARENT"))
    if invite:
        lines.append(line("ORGANIZER", _mailto(me)))
        lines.extend(_invitation(m) for m in invite)
    lines += ["END:VEVENT", "END:VCALENDAR"]
    text = "".join(icalwrite.fold(x) + "\r\n" for x in lines)
    href = cal["href"] + urllib.parse.quote(uid, safe="@") + ".ics"
    return (href, uid) + _put(session, href, text, {"If-None-Match": "*"})


def _invitation(address):
    return line("ATTENDEE", _mailto(address), [("PARTSTAT", "NEEDS-ACTION"), ("RSVP", "TRUE")])


# ---------------------------------------------------------------- update

def update(a, session, e, title, location, busy, timing, invite, uninvite, series):
    """Change the fields given (None leaves one alone) and the guest list.

    Field changes are guarded by the local copy's ETag, as they are for the
    other providers; a guests-only change is applied to the server's current
    list, so a guest someone else added meanwhile is kept.

    For a series, a field changes on the series and on each occurrence that
    still had the series' old value; one that was changed on its own keeps
    its own. Guests are added to and taken off every copy of the list.
    """
    _check(e)
    doc, etag = _read(session, e["href"])
    fields = title is not None or location is not None or busy is not None or timing
    if fields:
        _unchanged(etag, e)
    me = (a.get("email") or "").lower()
    blocks = _targets(doc, e, series)
    first = blocks[0]
    old = {n: first.value(n) for n in ("SUMMARY", "LOCATION", "TRANSP")}
    for i, b in enumerate(blocks):
        strict = i == 0
        changed = _fields(b, old if not strict else None, title, location, busy)
        if timing and strict:
            _times(b, *timing)
        guests = (invite or uninvite) and _guests(b, me, invite, uninvite, strict)
        if changed or guests or timing and strict:
            _touch(b, sequence=bool(timing and strict or "LOCATION" in changed))
    return _put(session, e["href"], doc.text(), {"If-Match": etag})


def _fields(b, old, title, location, busy):
    """Set title, place and free/busy on one VEVENT; returns the names changed.

    With old (the series' values before the change), an override is only
    changed where it still had the series' value.
    """
    new = {}
    if title is not None:
        new["SUMMARY"] = title
    if location is not None:
        new["LOCATION"] = location
    if busy is not None:
        new["TRANSP"] = "OPAQUE" if busy else "TRANSPARENT"
    changed = []
    for name, value in new.items():
        if old is not None and b.value(name) != old[name]:
            continue
        if name == "LOCATION" and not value:
            b.drop(name)
        else:
            b.set(name, line(name, value, text=name != "TRANSP"))
        changed.append(name)
    return changed


def _times(b, s, en, all_day):
    """New start and end; each keeps its zone when the kind (timed or all-day) stays."""
    for name, t in (("DTSTART", s), ("DTEND", en)):
        like = b.get(name) or b.get("DTSTART")
        was_date = like is not None and not isinstance(ical.value_time(like), datetime)
        params, value = time_value(t, like if was_date == all_day else None)
        b.set(name, line(name, value, params))
    b.drop("DURATION")   # DTEND now says it


def _guests(b, me, invite, uninvite, strict):
    """Add and take off guests on one VEVENT; True if its list changed.

    strict (the event itself) raises for a change that can't be made, as the
    other providers do; the series' overrides take what applies to them.
    """
    org = _addr(b.value("ORGANIZER")).lower()
    have = [{"email": _addr(v).lower()} for _, v, _ in b.props("ATTENDEE")]
    if not strict:
        emails = {x["email"] for x in have}
        invite = [m for m in invite if m not in emails and m != org]
        uninvite = [m for m in uninvite if m in emails and m not in (org, me)]
        if not invite and not uninvite:
            return False
    merge_guests("caldav", have, invite, uninvite, me, org)
    if uninvite:
        b.drop("ATTENDEE", keep=lambda v, p: _addr(v).lower() not in uninvite)
    if invite and not org:
        # Your own event, with nobody on it till now: you organise it.
        if not me:
            raise EditError("this account has no email address of its own, so it can't send invitations")
        b.add(line("ORGANIZER", _mailto(me)), after="SUMMARY")
    for m in invite:
        b.add(_invitation(m), after="ATTENDEE" if b.get("ATTENDEE") else "ORGANIZER")
    return True


# ---------------------------------------------------------------- delete

def delete(a, session, e, series):
    """The whole resource, or one occurrence of a series (an EXDATE on it).

    Returns None when the resource is gone, or its new (text, etag).
    """
    _check(e)
    mine = bool(e.get("organizer"))
    if series:
        _delete(session, e["href"], e.get("etag", ""), mine)
        return None
    doc, etag = _read(session, e["href"])
    _unchanged(etag, e)
    e = _as_occurrence(doc, e)
    if not e.get("recurrenceId"):
        _delete(session, e["href"], etag, mine)
        return None
    rid = e["recurrenceId"]
    master = _master(doc)
    override = _override(doc, rid)
    if override is not None:
        doc.calendar.items.remove(override)
    if master is None:
        if not doc.events():   # that was the only occurrence you had
            _delete(session, e["href"], etag, mine)
            return None
    else:
        start = master.get("DTSTART")
        params, value = time_value(ical.parse_time(rid), start)
        master.add(line("EXDATE", value, params))
        _touch(master, sequence=True)
    return _put(session, e["href"], doc.text(), {"If-Match": etag})
