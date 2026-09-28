"""Microsoft 365 through Graph: every calendar, kept current with delta queries.

/me/calendars/{id}/calendarView/delta with a start and end expands series into
occurrences for that window, and hands back a deltaLink. Calling the deltaLink
later returns only what changed: new or updated events, and "@removed" stubs
for deletions. The window is fixed when the delta starts, so a new delta is
begun whenever the window moves on (once a day).

Times are left in UTC, Graph's default: timed events are exact instants, and
all-day events come back as midnight-to-midnight, whose date part is the
all-day date with an exclusive end, the same convention as Google.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from .model import find_join, join_kind, parse_instant, utc_iso

API = "https://graph.microsoft.com/v1.0"
RESPONSES = {"accepted": "accepted", "tentativelyAccepted": "tentative", "declined": "declined",
             "notResponded": "needsAction", "organizer": "organizer", "none": "none"}


class DeltaExpired(Exception):
    """Graph no longer honours this deltaLink (HTTP 410): start a new delta."""


def _get(url, tok):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + tok,
                                               "Prefer": "odata.maxpagesize=100"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 410:
            raise DeltaExpired()
        from .auth import HttpError
        raise HttpError("graph.microsoft.com", e.code, e.read().decode(errors="replace")[:300])


def calendars(tok):
    out, url = [], API + "/me/calendars?$select=id,name,hexColor,canEdit,isDefaultCalendar&$top=100"
    while url:
        r = _get(url, tok)
        for c in r.get("value", []):
            out.append({"id": c["id"], "name": c.get("name", ""), "color": c.get("hexColor") or "",
                        "primary": bool(c.get("isDefaultCalendar")), "editable": bool(c.get("canEdit"))})
        url = r.get("@odata.nextLink")
    return out


def normalise(account, cal, e):
    all_day = bool(e.get("isAllDay"))
    s, en = e["start"]["dateTime"], e["end"]["dateTime"]
    if all_day:
        start, end = s[:10], en[:10]
    else:
        start = utc_iso(parse_instant(s, assume_utc=True))
        end = utc_iso(parse_instant(en, assume_utc=True))
    organizer = bool(e.get("isOrganizer"))
    response = RESPONSES.get((e.get("responseStatus") or {}).get("response", "none"), "none")
    if organizer:
        response = "organizer"
    join = None
    url = (e.get("onlineMeeting") or {}).get("joinUrl")
    if url and url.startswith("https://"):
        join = {"url": url, "kind": join_kind(url)}
    if not join:
        join = find_join((e.get("location") or {}).get("displayName"), (e.get("body") or {}).get("content"))
    status = "cancelled" if e.get("isCancelled") else ("tentative" if e.get("showAs") == "tentative" else "confirmed")
    return {
        "uid": "%s/%s/%s" % (account, cal["id"], e["id"]),
        "account": account, "calendar": cal["id"],
        "title": e.get("subject") or "(no title)",
        "allDay": all_day, "start": start, "end": end,
        "location": (e.get("location") or {}).get("displayName", ""),
        "join": join,
        "response": response,
        "organizer": organizer,
        "status": status,
        "busy": e.get("showAs") not in ("free", "workingElsewhere"),
        "recurring": e.get("type") in ("occurrence", "exception"),
        "seriesId": e.get("seriesMasterId"),
        # An attendee's copy can be changed in Outlook, but the change stays
        # in that one mailbox: only the organiser's edits reach anyone.
        "editable": cal["editable"] and organizer,
        "webLink": e.get("webLink", ""),
        "etag": e.get("@odata.etag") or e.get("changeKey", ""),
        # Outlook's reminder: on or off, and how long before the start.
        "remind": [int(e.get("reminderMinutesBeforeStart") or 0)] if e.get("isReminderOn") else [],
    }


def fetch(account, tok, cal, window, delta_link=None):
    """Returns (events, removed_ids, next_delta_link).

    With no delta_link this is a full fetch of the window, and starts a delta.
    """
    if delta_link:
        url = delta_link
    else:
        url = API + "/me/calendars/%s/calendarView/delta?%s" % (
            urllib.parse.quote(cal["id"], safe=""),
            urllib.parse.urlencode({"startDateTime": window[0], "endDateTime": window[1]}))
    events, removed = [], []
    while True:
        r = _get(url, tok)
        for e in r.get("value", []):
            uid = "%s/%s/%s" % (account, cal["id"], e["id"])
            if "@removed" in e or e.get("isCancelled"):
                removed.append(uid)
            elif "start" in e:
                events.append(normalise(account, cal, e))
        if r.get("@odata.nextLink"):
            url = r["@odata.nextLink"]
            continue
        return events, removed, r.get("@odata.deltaLink")
