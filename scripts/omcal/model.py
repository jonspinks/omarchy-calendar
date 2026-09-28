"""One event shape for every provider, and the join links inside them.

A normalised event:

    uid          "<account>/<calendar id>/<event id>": stable, and unique across accounts
    account      account name, as in accounts.json
    calendar     provider calendar id
    title        "(no title)" when there is none
    allDay       True for date-only events
    start, end   all-day: "YYYY-MM-DD", end exclusive (the day after the last)
                 timed:   ISO 8601 in UTC, "YYYY-MM-DDTHH:MM:SSZ"
    location     free text, or ""
    join         {"url", "kind"} with kind teams | zoom | meet | webex | other,
                 or None
    response     accepted | tentative | declined | needsAction | organizer | none
    organizer    True when the account owns the event
    status       confirmed | tentative | cancelled
    busy         False when the event is marked free/transparent
    recurring    True for an occurrence of a series
    seriesId     the series' id, for "edit all" later, or None
    editable     True when this account can change the event
    webLink      the event in the provider's own web app, or ""
    etag         the provider's version stamp, for safe edits later
    remind       minutes before the start to pop up a reminder, e.g. [10]; [] for none
    guests       the guest list, organiser first, as
                 {"email", "name", "response", "optional", "organizer", "me", "room"}
                 with response accepted | tentative | declined | needsAction;
                 [] when nobody else is invited. At most GUEST_CAP are kept.
    guestTotal   how many guests there are, kept or not
    guestsHidden True when the organiser has hidden the list from guests, so
                 it holds only you

Both providers are asked for end-exclusive all-day dates, and timed events are
kept as UTC instants: local time is applied only when something is displayed,
so a time-zone change never rewrites the cache.
"""

import re
from datetime import datetime, timezone

# Meeting links, most specific first. Only https, and only these hosts: a
# "join" button should never open an arbitrary link found in an invitation.
JOIN_PATTERNS = [
    ("teams", re.compile(r"https://teams\.(?:microsoft|live)\.com/(?:l/meetup-join|meet)/[^\s\"'<>]+", re.I)),
    ("zoom", re.compile(r"https://(?:[\w-]+\.)?zoom\.us/(?:j|my|w|s)/[^\s\"'<>]+", re.I)),
    ("meet", re.compile(r"https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}(?:\?[^\s\"'<>]*)?", re.I)),
    ("webex", re.compile(r"https://[\w-]+\.webex\.com/[^\s\"'<>]+", re.I)),
]

TAGS = re.compile(r"<[^>]+>")


def find_join(*texts):
    """The first meeting link in these texts, as {"url", "kind"}, or None."""
    for text in texts:
        if not text:
            continue
        # Link targets first (an Outlook invitation keeps the Teams link in an
        # href, often behind "Click here to join"), then the visible text.
        hrefs = " ".join(re.findall(r"""href\s*=\s*["']([^"']+)["']""", text, re.I))
        plain = (hrefs + " " + TAGS.sub(" ", text)).replace("&amp;", "&")
        for kind, rx in JOIN_PATTERNS:
            m = rx.search(plain)
            if m:
                return {"url": m.group(0).rstrip(".,);>"), "kind": kind}
    return None


def join_kind(url):
    for kind, rx in JOIN_PATTERNS:
        if rx.match(url or ""):
            return kind
    return "other"


GUEST_CAP = 100
GUEST_ANSWERS = ("accepted", "tentative", "declined", "needsAction")
# The order a guest list reads in: who's coming first, who said no last.
_ANSWER_RANK = {"accepted": 0, "tentative": 1, "needsAction": 2, "declined": 3}
EMAIL = re.compile(r"^[^@\s,;<>\"']+@[^@\s,;<>\"']+\.[^@\s,;<>\"']+$")


def guest(email, name="", response="needsAction", optional=False, organizer=False, me=False, room=False):
    """One guest. The organiser is going to their own meeting, whatever the
    provider says (Graph can list them among the guests as not answering)."""
    if organizer:
        response = "accepted"
    return {"email": email or "", "name": (name or "").strip(),
            "response": response if response in GUEST_ANSWERS else "needsAction",
            "optional": bool(optional), "organizer": bool(organizer), "me": bool(me), "room": bool(room)}


def guest_fields(guests, hidden=False):
    """The event's guest fields: the list in reading order, capped, and its size.

    A list of one is only ever the organiser or you, so it isn't a guest list.
    """
    if len(guests) < 2:
        guests = []

    def rank(g):
        return (not g["organizer"], g["room"], _ANSWER_RANK[g["response"]], g["optional"],
                (g["name"] or g["email"]).lower())

    guests = sorted(guests, key=rank)
    return {"guests": guests[:GUEST_CAP], "guestTotal": len(guests), "guestsHidden": bool(hidden)}


def utc_iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_instant(text, assume_utc=False):
    """An ISO 8601 date-time, with or without an offset, as an aware datetime.

    Graph writes seven fractional digits and no offset ("...T14:00:00.0000000")
    when asked for UTC; Python's parser takes at most six.
    """
    t = text.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    m = re.match(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d+)?(.*)$", t)
    if m:
        # "." plus at most six digits: Python's limit.
        t = m.group(1) + (m.group(2) or "")[:7] + m.group(3)
    dt = datetime.fromisoformat(t)
    if dt.tzinfo is None:
        if not assume_utc:
            raise ValueError("no time zone in %r" % text)
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def sort_key(e):
    """All-day events first on their day, then by start time."""
    s = e["start"]
    return (s[:10], 0 if e["allDay"] else 1, s, e["title"].lower())
