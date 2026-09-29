"""Writing iCalendar: new events whole, and small patches to ones a server holds.

    line(name, value, params)   one content line, its TEXT escaped
    fold(line)                  that line cut into 75-octet physical lines
    Doc(text)                   a resource as blocks of raw lines, to patch
    time_value(t, like)         a date or instant, written as another property writes its own

A server's copy of an event carries far more than this plugin reads: time
zone definitions, alarms, X- properties from other apps, parameters nobody
here knows. Rebuilding it from the parsed model would lose all of that, so an
edit patches the text instead. Doc keeps every line exactly as it came, folds
and line endings included; only a property being changed is written afresh,
and everything else goes back byte for byte.
"""

import re
from datetime import datetime, timezone

from . import ical

FOLD = 75   # octets per physical line, not counting the line break (RFC 5545 3.1)


# ------------------------------------------------------------------ lines

def escape(text):
    """TEXT as iCalendar writes it: backslash, ";" and "," escaped, newlines as \\n."""
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n"))


def param(value):
    """A parameter value, quoted when it holds ":", ";" or ",".

    A parameter can't hold a double quote or a line break at all, quoted or
    not, so those are replaced rather than risk breaking the line.
    """
    v = re.sub(r"[\r\n]+", " ", value).replace('"', "'")
    return '"%s"' % v if re.search(r"[:;,]", v) else v


def line(name, value, params=(), text=False):
    """One content line, unfolded. params is [(name, value)], in order; text
    escapes the value, for SUMMARY, LOCATION and the like."""
    head = name + "".join(";%s=%s" % (k, param(v)) for k, v in params)
    return head + ":" + (escape(value) if text else value)


def fold(content, nl="\r\n"):
    """A content line as physical lines of at most 75 octets each.

    Counted in UTF-8 octets, as the RFC says, and never cut inside a
    character: a split multi-byte character is garbage to every reader.
    """
    out, cur, size = [], "", 0
    for ch in content:
        n = len(ch.encode("utf-8"))
        if size + n > FOLD:
            out.append(cur)
            cur, size = " ", 1   # a continuation starts with one space, which counts
        cur += ch
        size += n
    out.append(cur)
    return nl.join(out)


def _unfold(raw):
    """A logical line as it came (folds and break included) as one line of text."""
    return re.sub(r"(?:\r\n|\n|\r)[ \t]", "", raw).rstrip("\r\n")


def param_spans(content):
    """Where each parameter sits in an unfolded line: ([(NAME, start, end)], colon).

    start..end covers ";NAME=value" including any quotes, so a parameter can
    be replaced without disturbing its neighbours. Scans like ical.split_line,
    since a quoted value may hold ":" or ";".
    """
    i, n, spans = 0, len(content), []
    while i < n and content[i] not in ";:":
        i += 1
    while i < n and content[i] == ";":
        start, j = i, i + 1
        while j < n and content[j] not in "=;:":
            j += 1
        key, i = content[start + 1:j].upper(), j
        if i < n and content[i] == "=":
            i += 1
            while True:
                if i < n and content[i] == '"':
                    end = content.find('"', i + 1)
                    i = n if end < 0 else end + 1
                else:
                    while i < n and content[i] not in ",;:":
                        i += 1
                if i < n and content[i] == ",":
                    i += 1
                    continue
                break
        spans.append((key, start, i))
    return spans, i


def with_param(content, key, value):
    """The same line with one parameter set (replaced in place, or added last)."""
    spans, colon = param_spans(content)
    new = ";%s=%s" % (key, param(value))
    for k, s, e in spans:
        if k == key.upper():
            return content[:s] + new + content[e:]
    return content[:colon] + new + content[colon:]


# ------------------------------------------------------------------ times

def utc_stamp(dt):
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def time_value(t, like=None):
    """t (a date, or an aware datetime) as (params, value).

    like is an existing (value, params) property to match: a time goes back in
    its TZID if it had one, in UTC if it ended in Z, or as floating local time
    if it had neither. Without one, a time is UTC. A date is always VALUE=DATE.
    """
    if not isinstance(t, datetime):
        return [("VALUE", "DATE")], t.strftime("%Y%m%d")
    if like:
        value, params = like
        is_date = params.get("VALUE", "").upper() == "DATE" or len(value.strip()) == 8
        if not is_date and params.get("TZID"):
            return [("TZID", params["TZID"])], t.astimezone(ical.zone(params["TZID"])).strftime("%Y%m%dT%H%M%S")
        if not is_date and not value.strip().endswith("Z"):
            # Floating: ical reads it in this machine's zone, so write it in that.
            return [], t.astimezone().strftime("%Y%m%dT%H%M%S")
    return [], utc_stamp(t)


# ------------------------------------------------------------------- Doc

class Block:
    """One BEGIN..END component as raw text: its BEGIN and END lines, and
    between them, in order, property lines (raw strings, break included) and
    the components inside (Blocks)."""

    def __init__(self, name, nl, head="", tail=""):
        self.name, self.nl, self.head, self.tail, self.items = name, nl, head, tail, []

    def text(self):
        return self.head + "".join(i if isinstance(i, str) else i.text() for i in self.items) + self.tail

    def blocks(self, name):
        return [i for i in self.items if isinstance(i, Block) and i.name == name]

    def props(self, name):
        """[(item index, value, params)] for each property called name."""
        out = []
        for k, item in enumerate(self.items):
            if isinstance(item, str):
                n, p, v = ical.split_line(_unfold(item))
                if n == name:
                    out.append((k, ical.unescape(v) if n in ical.TEXT else v, p))
        return out

    def get(self, name):
        got = self.props(name)
        return (got[0][1], got[0][2]) if got else None

    def value(self, name, default=""):
        got = self.get(name)
        return got[0] if got else default

    def content(self, k):
        """Item k's line, unfolded."""
        return _unfold(self.items[k])

    def replace(self, k, content):
        self.items[k] = fold(content, self.nl) + self.nl

    def set(self, name, content):
        """This property, once: in the first copy's place, or after the last property."""
        found = self.props(name)
        if not found:
            return self.add(content)
        self.replace(found[0][0], content)
        for k, _, _ in reversed(found[1:]):
            del self.items[k]

    def add(self, content, after=None):
        """A new property: after the last one called after (or of its own name),
        otherwise after the last property, before any component inside."""
        name = after or ical.split_line(content)[0]
        same = self.props(name)
        if same:
            at = same[-1][0] + 1
        else:
            at = next((k for k, i in enumerate(self.items) if isinstance(i, Block)), len(self.items))
        self.items.insert(at, fold(content, self.nl) + self.nl)

    def drop(self, name, keep=None):
        """Remove every property called name, or only those keep(value, params) turns down."""
        for k, v, p in reversed(self.props(name)):
            if keep is None or not keep(v, p):
                del self.items[k]


PHYSICAL = re.compile(r"[^\r\n]*(?:\r\n|\n|\r)|[^\r\n]+$")


class Doc:
    """A whole iCalendar resource, parsed into Blocks without changing a byte.

    Lenient like ical.parse: an END that doesn't match is kept as a plain line,
    and an unclosed BEGIN just has no END line of its own.
    """

    def __init__(self, text):
        self.nl = "\r\n" if "\r\n" in text or "\n" not in text else "\n"
        self.root = Block("", self.nl)
        stack = [self.root]
        for raw in _logical(text):
            name, _, value = ical.split_line(_unfold(raw))
            if name == "BEGIN":
                b = Block(value.strip().upper(), self.nl, head=raw)
                stack[-1].items.append(b)
                stack.append(b)
            elif name == "END" and len(stack) > 1 and stack[-1].name == value.strip().upper():
                stack.pop().tail = raw
            else:
                stack[-1].items.append(raw)

    def text(self):
        return self.root.text()

    @property
    def calendar(self):
        cals = self.root.blocks("VCALENDAR")
        if not cals:
            raise ValueError("no VCALENDAR in the resource")
        return cals[0]

    def events(self):
        return self.calendar.blocks("VEVENT")


def _logical(text):
    """The raw logical lines: a physical line starting with a space or tab
    belongs to the one before it, and stays joined to it exactly as it was."""
    out = []
    for phys in PHYSICAL.findall(text):
        if phys[:1] in (" ", "\t") and out:
            out[-1] += phys
        else:
            out.append(phys)
    return out
