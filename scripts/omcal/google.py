"""Google Calendar: every calendar the account has switched on, kept current.

Each calendar is fetched in full once (singleEvents=true, so the server
expands recurring series into occurrences inside the window), then kept
current with updatedMin + showDeleted: only what changed since the last
sync comes back, deletions included (as status "cancelled"). Google's
syncToken would be tidier, but it cannot be combined with a time window, and
the window is what keeps the cache small. A full refresh runs a few times a
day anyway, so nothing drifts for long.
"""

import urllib.parse
from datetime import datetime, timedelta, timezone

from . import auth
from .model import find_join, join_kind, parse_instant, utc_iso

API = "https://www.googleapis.com/calendar/v3"


def _get(url, tok):
    return auth.get_json(url, tok)


def calendars(tok):
    """The calendars shown in Google Calendar, with their colours and roles."""
    out, page = [], None
    while True:
        q = {"maxResults": 250, "minAccessRole": "reader"}
        if page:
            q["pageToken"] = page
        r = _get(API + "/users/me/calendarList?" + urllib.parse.urlencode(q), tok)
        for c in r.get("items", []):
            if c.get("selected") is False or c.get("deleted"):
                continue
            out.append({"id": c["id"], "name": c.get("summaryOverride") or c.get("summary", ""),
                        "color": c.get("backgroundColor", ""), "primary": bool(c.get("primary")),
                        "editable": c.get("accessRole") in ("owner", "writer")})
        page = r.get("nextPageToken")
        if not page:
            return out


def normalise(account, cal, e):
    s, en = e.get("start", {}), e.get("end", {})
    all_day = "date" in s
    if all_day:
        start, end = s["date"], en.get("date", s["date"])
    else:
        start = utc_iso(parse_instant(s["dateTime"]))
        end = utc_iso(parse_instant(en.get("dateTime", s["dateTime"])))
    me = next((a for a in e.get("attendees", []) if a.get("self")), None)
    organizer = bool((e.get("organizer") or {}).get("self")) or me is None and not e.get("attendees")
    response = "organizer" if organizer else (me or {}).get("responseStatus", "none")
    join = None
    for ep in (e.get("conferenceData") or {}).get("entryPoints", []):
        if ep.get("entryPointType") == "video" and ep.get("uri", "").startswith("https://"):
            join = {"url": ep["uri"], "kind": join_kind(ep["uri"])}
            break
    if not join and e.get("hangoutLink"):
        join = {"url": e["hangoutLink"], "kind": "meet"}
    if not join:
        join = find_join(e.get("location"), e.get("description"))
    return {
        "uid": "%s/%s/%s" % (account, cal["id"], e["id"]),
        "account": account, "calendar": cal["id"],
        "title": e.get("summary") or "(no title)",
        "allDay": all_day, "start": start, "end": end,
        "location": e.get("location", ""),
        "join": join,
        "response": response,
        "organizer": organizer,
        "status": e.get("status", "confirmed"),
        "busy": e.get("transparency") != "transparent",
        "recurring": bool(e.get("recurringEventId")),
        "seriesId": e.get("recurringEventId"),
        "editable": cal["editable"] and (organizer or bool(e.get("guestsCanModify"))),
        "webLink": e.get("htmlLink", ""),
        "etag": e.get("etag", ""),
    }


def fetch(account, tok, cal, window, updated_min=None):
    """Events in the window: all of them, or only those changed since updated_min.

    Returns (events, removed_ids, fetched_at). Cancelled events are removals.
    """
    fetched_at = datetime.now(timezone.utc)
    q = {"timeMin": window[0], "timeMax": window[1], "singleEvents": "true", "maxResults": 250}
    if updated_min:
        q["updatedMin"] = updated_min
        q["showDeleted"] = "true"
    events, removed, page = [], [], None
    base = API + "/calendars/%s/events?" % urllib.parse.quote(cal["id"], safe="")
    while True:
        if page:
            q["pageToken"] = page
        r = _get(base + urllib.parse.urlencode(q), tok)
        for e in r.get("items", []):
            if e.get("status") == "cancelled":
                removed.append("%s/%s/%s" % (account, cal["id"], e["id"]))
            else:
                events.append(normalise(account, cal, e))
        page = r.get("nextPageToken")
        if not page:
            return events, removed, fetched_at


def since(fetched_at):
    """updatedMin for the next incremental pass, with a margin for clock skew."""
    return (fetched_at - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
