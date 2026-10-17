"""Just enough iCalendar (RFC 5545) to read events from a CalDAV server.

    parse(text)            the components, nested: VCALENDAR > VEVENT > VALARM
    value_time(prop)       DTSTART and friends as a date or an aware datetime
    duration(text)         "-PT15M" as a timedelta
    occurrences(ev, ...)   a series' starts inside a window, when the server
                           handed back a rule instead of expanding it

Only what the calendar shows is read. VTIMEZONE bodies are skipped: a TZID is
looked up in the system's zoneinfo instead, which is what Fastmail and most
servers write (IANA names like "America/Chicago"). A TZID zoneinfo doesn't
know (Outlook's "Central Standard Time", or a made-up one) falls back to this
machine's own zone: right for most invitations you'd see, and never a crash.
"""

import re
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Properties whose values are TEXT, and so carry backslash escapes.
TEXT = {"SUMMARY", "LOCATION", "DESCRIPTION", "COMMENT", "CATEGORIES"}


def warn(msg):
    print("calendar: " + msg, file=sys.stderr)


# ------------------------------------------------------------------ parse

class Component:
    """One BEGIN..END block: its properties in order, and the blocks inside."""

    def __init__(self, name):
        self.name, self.props, self.subs = name, [], []

    def get(self, name):
        """The first property called name, as (value, params), or None."""
        return next(((v, p) for n, p, v in self.props if n == name), None)

    def value(self, name, default=""):
        got = self.get(name)
        return got[0] if got else default

    def all(self, name):
        return [(v, p) for n, p, v in self.props if n == name]

    def find(self, name):
        """Every component called name, at any depth below this one."""
        out = []
        for s in self.subs:
            if s.name == name:
                out.append(s)
            out.extend(s.find(name))
        return out


def unfold(text):
    """Logical lines: a line that starts with a space or tab continues the last."""
    out = []
    for line in re.split(r"\r\n|\n|\r", text):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        elif line:
            out.append(line)
    return out


def split_line(line):
    """ "DTSTART;TZID=America/Chicago:20261002T090000" as (name, params, value).

    Parameter values may be quoted, and a quoted one may hold ":" or ";"
    (CN="Smith; Jo"), so this scans rather than splits.
    """
    i, n = 0, len(line)
    while i < n and line[i] not in ";:":
        i += 1
    name, params = line[:i].upper(), {}
    while i < n and line[i] == ";":
        j = i + 1
        while j < n and line[j] not in "=;:":
            j += 1
        key = line[i + 1:j].upper()
        vals, i = [], j
        if i < n and line[i] == "=":
            i += 1
            while True:
                if i < n and line[i] == '"':
                    end = line.find('"', i + 1)
                    end = n if end < 0 else end
                    vals.append(line[i + 1:end])
                    i = end + 1
                else:
                    j = i
                    while j < n and line[j] not in ",;:":
                        j += 1
                    vals.append(line[i:j])
                    i = j
                if i < n and line[i] == ",":
                    i += 1
                    continue
                break
        params[key] = ",".join(vals)
    return name, params, line[i + 1:] if i < n else ""


def unescape(text):
    return re.sub(r"\\([\\;,nN])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), text)


def parse(text):
    """The whole iCalendar text as a root Component holding its VCALENDARs.

    Lenient: an unmatched END is ignored and an unclosed BEGIN is closed at
    the end, so one broken event can't hide the rest.
    """
    root = Component("")
    stack = [root]
    for line in unfold(text):
        name, params, value = split_line(line)
        if name == "BEGIN":
            c = Component(value.strip().upper())
            stack[-1].subs.append(c)
            stack.append(c)
        elif name == "END":
            if len(stack) > 1 and stack[-1].name == value.strip().upper():
                stack.pop()
        elif not _in_zone(stack):
            stack[-1].props.append((name, params, unescape(value) if name in TEXT else value))
    return root


def _in_zone(stack):
    # A VTIMEZONE's STANDARD/DAYLIGHT blocks are never read: see the docstring.
    return any(c.name == "VTIMEZONE" for c in stack)


# ------------------------------------------------------------------ times

def zone(tzid):
    """A TZID as a tzinfo; this machine's zone when zoneinfo doesn't know it."""
    if tzid:
        # Some writers prefix the IANA name ("/mozilla.org/20050126_1/America/Chicago").
        parts = tzid.strip("/").split("/")
        for k in range(len(parts)):
            try:
                return ZoneInfo("/".join(parts[k:]))
            except (ZoneInfoNotFoundError, ValueError):
                continue
    return datetime.now().astimezone().tzinfo


def parse_time(text, tzid=None, is_date=False):
    """One DATE or DATE-TIME value: a date, or an aware datetime.

    "...Z" is UTC; a TZID is that zone; neither is "floating", the same wall
    time wherever you are, so it's taken in this machine's zone.
    """
    t = text.strip()
    if is_date or len(t) == 8:
        return date(int(t[:4]), int(t[4:6]), int(t[6:8]))
    dt = datetime(int(t[:4]), int(t[4:6]), int(t[6:8]), int(t[9:11]), int(t[11:13]), int(t[13:15] or 0))
    if t.endswith("Z"):
        return dt.replace(tzinfo=timezone.utc)
    return dt.replace(tzinfo=zone(tzid))


def value_time(prop):
    """A (value, params) property as a date or datetime, or None."""
    if not prop or not prop[0].strip():
        return None
    value, params = prop
    return parse_time(value.split(",")[0], params.get("TZID"), params.get("VALUE", "").upper() == "DATE")


def value_times(props):
    """Every value of properties that may list several (EXDATE, RDATE)."""
    out = []
    for value, params in props:
        for v in value.split(","):
            if v.strip():
                out.append(parse_time(v, params.get("TZID"), params.get("VALUE", "").upper() == "DATE"))
    return out


def duration(text):
    """An iCalendar duration ("P1D", "-PT15M", "P1W") as a timedelta, or None."""
    m = re.match(r"^([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$", (text or "").strip())
    if not m or not any(m.groups()[1:]):
        return None
    w, d, h, mi, s = (int(x or 0) for x in m.groups()[1:])
    td = timedelta(weeks=w, days=d, hours=h, minutes=mi, seconds=s)
    return -td if m.group(1) == "-" else td


def instant_key(t):
    """A start as a comparable key: the date for all-day, the UTC instant otherwise."""
    if isinstance(t, datetime):
        return t.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return t.strftime("%Y%m%d")


# ------------------------------------------------------------- recurrence

DAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
FREQS = {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"}
# The rule parts this expander understands, per frequency. Anything else
# (BYSETPOS, BYMONTH, BYWEEKNO, HOURLY...) gets the first occurrence only.
UNDERSTOOD = {"DAILY": {"FREQ", "INTERVAL", "COUNT", "UNTIL", "WKST"},
              "WEEKLY": {"FREQ", "INTERVAL", "COUNT", "UNTIL", "WKST", "BYDAY"},
              "MONTHLY": {"FREQ", "INTERVAL", "COUNT", "UNTIL", "WKST", "BYDAY", "BYMONTHDAY"},
              "YEARLY": {"FREQ", "INTERVAL", "COUNT", "UNTIL", "WKST"}}
# However odd the rule, the expander stops after this many periods.
MAX_STEPS = 5000


def rule(text):
    """ "FREQ=WEEKLY;BYDAY=MO,WE" as {"FREQ": "WEEKLY", "BYDAY": "MO,WE"}."""
    out = {}
    for part in text.split(";"):
        k, _, v = part.partition("=")
        if k.strip():
            out[k.strip().upper()] = v.strip().upper()
    return out


def occurrences(start, rrule, window_end, uid=""):
    """A series' occurrence starts, from its first through window_end.

    start is the series' DTSTART (a date or an aware datetime); occurrences
    keep its wall-clock time in its own zone, so a 9:00 meeting stays at 9:00
    across a DST change. COUNT counts from the first occurrence, wherever the
    window starts. A rule this can't follow yields just the first occurrence,
    with a warning: a calendar with one event too few beats a wrong one.
    """
    r = rule(rrule)
    freq = r.get("FREQ")
    if freq not in FREQS or set(r) - UNDERSTOOD[freq] or (freq == "MONTHLY" and "BYDAY" in r and "BYMONTHDAY" in r):
        warn("can't follow the rule %r of %s; showing only its first occurrence" % (rrule, uid or "an event"))
        return [start]
    try:
        interval = max(1, int(r.get("INTERVAL", "1")))
        count = int(r["COUNT"]) if "COUNT" in r else None
        until = _until(r.get("UNTIL"), start)
        days = [_byday(x) for x in r["BYDAY"].split(",")] if "BYDAY" in r else []
        monthdays = [int(x) for x in r["BYMONTHDAY"].split(",")] if "BYMONTHDAY" in r else []
    except (ValueError, KeyError):
        warn("can't read the rule %r of %s; showing only its first occurrence" % (rrule, uid or "an event"))
        return [start]
    if freq == "WEEKLY" and any(n for n, _ in days):
        warn("a weekly rule with numbered days (%r) in %s; showing only its first occurrence" % (rrule, uid))
        return [start]
    if not isinstance(start, datetime) and isinstance(window_end, datetime):
        window_end = window_end.date()
    out = []
    for step in range(MAX_STEPS):
        for t in sorted(_period(freq, start, step * interval, days, monthdays, DAYS.get(r.get("WKST"), 0))):
            if t < start:
                continue
            if (until is not None and t > until) or (count is not None and len(out) >= count) or t > window_end:
                return out
            out.append(t)
    return out


def _byday(text):
    """ "2TU" as (2, 1), "-1FR" as (-1, 4), "MO" as (0, 0)."""
    m = re.match(r"^([+-]?\d{1,2})?(MO|TU|WE|TH|FR|SA|SU)$", text.strip())
    if not m:
        raise ValueError(text)
    return int(m.group(1) or 0), DAYS[m.group(2)]


def _until(text, start):
    """UNTIL in start's own terms: a date for an all-day series, else an instant."""
    if not text:
        return None
    t = parse_time(text)
    if isinstance(start, datetime):
        if not isinstance(t, datetime):
            # A date-only UNTIL on a timed series: through the end of that day.
            t = datetime(t.year, t.month, t.day, 23, 59, 59, tzinfo=start.tzinfo)
        elif t.tzinfo is None:
            t = t.replace(tzinfo=start.tzinfo)
        return t
    return t.date() if isinstance(t, datetime) else t


def _at(start, day):
    """start's time of day (and zone) on another date."""
    if isinstance(start, datetime):
        return start.replace(year=day.year, month=day.month, day=day.day)
    return day


def _period(freq, start, n, days, monthdays, wkst):
    """Every candidate start in the n-th period (day, week, month, year) after start's."""
    d0 = start.date() if isinstance(start, datetime) else start
    if freq == "DAILY":
        return [_at(start, d0 + timedelta(days=n))]
    if freq == "WEEKLY":
        week = d0 - timedelta(days=(d0.weekday() - wkst) % 7) + timedelta(weeks=n)
        wanted = [wd for _, wd in days] or [d0.weekday()]
        return [_at(start, week + timedelta(days=(wd - wkst) % 7)) for wd in set(wanted)]
    if freq == "MONTHLY":
        y, m = d0.year + (d0.month - 1 + n) // 12, (d0.month - 1 + n) % 12 + 1
        return [_at(start, d) for d in _month_days(y, m, days, monthdays or ([] if days else [d0.day]))]
    y = d0.year + n
    try:
        return [_at(start, d0.replace(year=y))]
    except ValueError:   # 29 February in a year without one
        return []


def _month_days(y, m, days, monthdays):
    last = (date(y + m // 12, m % 12 + 1, 1) - timedelta(days=1)).day
    out = []
    for md in monthdays:
        d = md if md > 0 else last + 1 + md
        if 1 <= d <= last:   # the 31st is skipped in a shorter month, as RFC 5545 says
            out.append(date(y, m, d))
    for nth, wd in days:
        all_wd = [date(y, m, d) for d in range(1, last + 1) if date(y, m, d).weekday() == wd]
        if nth == 0:
            out.extend(all_wd)
        elif -len(all_wd) <= nth <= len(all_wd):
            out.append(all_wd[nth - 1] if nth > 0 else all_wd[nth])
    return out
