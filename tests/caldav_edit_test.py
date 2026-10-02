"""CalDAV writes: every edit.py call on a caldav account, against a fake server.

    python3 -B -m unittest discover -s tests -p '*_test.py'

The server here is a dict of resources in memory: it answers GET, PUT and
DELETE, honours If-Match and If-None-Match as a real one does, and records
every request. Nothing talks to a network or the keyring.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from omcal import auth, caldav, edit, ical, icalwrite, sync  # noqa: E402

HOME = "https://caldav.example.com/dav/calendars/user/me@example.com/"
ME = "me@example.com"
WINDOW = ("2026-09-01T00:00:00Z", "2026-12-01T00:00:00Z")
ACCOUNT = {"name": "F", "provider": "caldav", "email": ME, "url": HOME}
CAL = {"id": "work", "href": HOME + "work/", "name": "Work", "color": "", "primary": True,
       "editable": True, "ctag": "c1"}


def crlf(text):
    return text.strip().replace("\n", "\r\n") + "\r\n"


ZONE = """BEGIN:VTIMEZONE
TZID:America/Chicago
X-LIC-LOCATION:America/Chicago
BEGIN:DAYLIGHT
TZOFFSETFROM:-0600
TZOFFSETTO:-0500
TZNAME:CDT
DTSTART:19700308T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0500
TZOFFSETTO:-0600
TZNAME:CST
DTSTART:19701101T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
END:VTIMEZONE"""

ALARM = """BEGIN:VALARM
X-WR-ALARMUID:5A1B-alarm
ACTION:DISPLAY
TRIGGER:-PT15M
DESCRIPTION:Reminder
END:VALARM"""

# Mine, with a guest, and plenty this plugin never reads: all of it has to
# come back exactly as it was.
SINGLE = crlf("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//macOS 15//EN
CALSCALE:GREGORIAN
%s
BEGIN:VEVENT
UID:single-1@example.com
DTSTAMP:20260901T000000Z
CREATED:20260901T000000Z
SEQUENCE:2
DTSTART;TZID=America/Chicago:20261002T090000
DTEND;TZID=America/Chicago:20261002T100000
SUMMARY:Planning
LOCATION:Room 4
DESCRIPTION:A long description that goes on and on past the seventy-five o
 ctet limit\\, folded where the other app folded it.
X-APPLE-TRAVEL-ADVISORY-BEHAVIOR;X-ODD="a:b;c":AUTOMATIC
ORGANIZER;CN=Me:mailto:me@example.com
ATTENDEE;CN=Me;PARTSTAT=ACCEPTED;ROLE=CHAIR:mailto:me@example.com
ATTENDEE;CN=Bob;PARTSTAT=NEEDS-ACTION;RSVP=TRUE;X-NUM-GUESTS=0:mailto:bob@example.com
%s
END:VEVENT
END:VCALENDAR""" % (ZONE, ALARM))

# A weekly series of mine; the 12 October one was already moved.
SERIES = crlf("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
%s
BEGIN:VEVENT
UID:standup@example.com
DTSTAMP:20260901T000000Z
SEQUENCE:0
DTSTART;TZID=America/Chicago:20261005T090000
DTEND;TZID=America/Chicago:20261005T091500
RRULE:FREQ=WEEKLY;BYDAY=MO;COUNT=6
SUMMARY:Standup
X-MOZ-GENERATION:3
%s
END:VEVENT
BEGIN:VEVENT
UID:standup@example.com
RECURRENCE-ID;TZID=America/Chicago:20261012T090000
DTSTAMP:20260901T000000Z
DTSTART;TZID=America/Chicago:20261012T100000
DTEND;TZID=America/Chicago:20261012T101500
SUMMARY:Standup (late)
END:VEVENT
END:VCALENDAR""" % (ZONE, ALARM))

# Someone else's invitation, to me by a differently-cased mailto.
INVITE = crlf("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Google Inc//Google Calendar 70.9054//EN
METHOD:REQUEST
BEGIN:VEVENT
UID:invite-1@google.com
DTSTAMP:20260901T000000Z
DTSTART:20261003T150000Z
DTEND:20261003T160000Z
SUMMARY:Review
ORGANIZER;CN=Olive:mailto:olive@example.com
ATTENDEE;CN="Smith; Amy";PARTSTAT=ACCEPTED:mailto:amy@example.com
ATTENDEE;CN=Me;CUTYPE=INDIVIDUAL;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:MAILTO:Me@Example.com
X-GOOGLE-CONFERENCE:https://meet.google.com/abc-defg-hij
END:VEVENT
END:VCALENDAR""")

INVITE_SERIES = crlf("""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:weekly-olive
DTSTAMP:20260901T000000Z
DTSTART;VALUE=DATE:20261006
DTEND;VALUE=DATE:20261007
RRULE:FREQ=WEEKLY;COUNT=4
SUMMARY:Olive's day
ORGANIZER:mailto:olive@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:olive@example.com
ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:me@example.com
END:VEVENT
END:VCALENDAR""")

FILES = {"single.ics": SINGLE, "series.ics": SERIES, "invite.ics": INVITE, "invite-series.ics": INVITE_SERIES}


class Server(caldav.Session):
    """A CalDAV server in a dict. Each PUT gives the resource a new ETag."""

    def __init__(self, files):
        super().__init__(HOME, ME, "pw")
        self.files = {HOME + "work/" + name: (text, '"1"') for name, text in files.items()}
        self.calls, self.version = [], 1
        self.etag_on_put = True   # a server that alters what it stores sends none
        self.race = False         # someone else writes between our GET and PUT

    def send(self, method, url, body=None, headers=None):
        headers = dict(headers or {})
        self.calls.append((method, url, headers, body.decode("utf-8") if body else None))
        have = self.files.get(url)
        if method == "GET":
            if not have:
                raise auth.HttpError("caldav.example.com", 404)
            if self.race:
                self._store(url, have[0])
            return 200, {"etag": have[1]}, have[0].encode("utf-8")
        if "If-Match" in headers and (not have or have[1] != headers["If-Match"]):
            raise auth.Conflict("the event was changed elsewhere; sync and try again")
        if headers.get("If-None-Match") == "*" and have:
            raise auth.Conflict("the event was changed elsewhere; sync and try again")
        if method == "PUT":
            etag = self._store(url, body.decode("utf-8"))
            return 201, {"etag": etag} if self.etag_on_put else {}, b""
        if method == "DELETE":
            del self.files[url]
            return 204, {}, b""
        raise AssertionError(method)

    def _store(self, url, text):
        self.version += 1
        self.files[url] = (text, '"%d"' % self.version)
        return self.files[url][1]

    def text(self, name):
        return self.files[HOME + "work/" + name][0]

    def writes(self):
        return [c for c in self.calls if c[0] != "GET"]


class Case(unittest.TestCase):
    """edit.py's calls on a caldav account, over a fake server and a temporary cache."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.server = Server(FILES)
        self.patches = [mock.patch.object(sync, "CACHE", self.dir),
                        mock.patch.object(sync, "LOCK", os.path.join(self.dir, "lock")),
                        mock.patch.object(sync, "window_now", return_value=("2026-09-28", WINDOW)),
                        mock.patch.object(auth, "load_accounts", return_value=[ACCOUNT]),
                        mock.patch.object(auth, "hidden_calendars", return_value={}),
                        mock.patch.object(caldav, "login", return_value=self.server)]
        for p in self.patches:
            p.start()
        events = {}
        for href, (text, etag) in self.server.files.items():
            for e in caldav.resource_events("F", CAL, text, etag, WINDOW, ME, href):
                events[e["uid"]] = e
        sync.write_private(self.state_path(), {"calendars": {"work": dict(CAL, cursor="3:c1")}, "known": [CAL],
                                               "events": events, "window": list(WINDOW)})

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.dir)

    def state_path(self):
        return os.path.join(self.dir, "state-F.json")

    def state(self, whole=False):
        with open(self.state_path()) as f:
            st = json.load(f)
        return st if whole else st["events"]

    def published(self):
        with open(os.path.join(self.dir, "events.json")) as f:
            return {e["uid"]: e for e in json.load(f)["events"]}

    def vevents(self, name):
        return ical.parse(self.server.text(name)).find("VEVENT")

    def changed_lines(self, before, after):
        """The (unfolded) lines only one side has, as (removed, added)."""
        a, b = (re.sub(r"\r\n[ \t]", "", t).split("\r\n") for t in (before, after))
        return [x for x in a if x not in b], [x for x in b if x not in a]


# ------------------------------------------------------------------ create

class Create(Case):
    def test_a_new_event_with_guests(self):
        uid = edit.create("F/work", "Lunch, then “coffee”", "2026-10-06T12:00:00+00:00", "2026-10-06T13:00:00+00:00",
                          location="Café", invite=["Bob@Example.com"])
        [(method, url, headers, body)] = self.server.writes()
        ical_uid = uid.split("/", 2)[2]
        self.assertTrue(ical_uid.endswith("@omacal"))
        self.assertEqual((method, url), ("PUT", HOME + "work/" + ical_uid + ".ics"))
        self.assertEqual(headers["If-None-Match"], "*")
        self.assertNotIn("If-Match", headers)
        self.assertTrue(headers["Content-Type"].startswith("text/calendar"))
        self.assertTrue(body.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:"))
        [v] = ical.parse(body).find("VEVENT")
        self.assertEqual((v.value("UID"), v.value("SEQUENCE"), v.value("TRANSP")), (ical_uid, "0", "OPAQUE"))
        self.assertEqual((v.value("DTSTART"), v.value("DTEND")), ("20261006T120000Z", "20261006T130000Z"))
        self.assertEqual((v.value("SUMMARY"), v.value("LOCATION")), ("Lunch, then “coffee”", "Café"))
        for name in ("DTSTAMP", "CREATED", "LAST-MODIFIED"):
            self.assertRegex(v.value(name), r"^\d{8}T\d{6}Z$")
        self.assertEqual(v.value("ORGANIZER"), "mailto:me@example.com")
        [(addr, params)] = v.all("ATTENDEE")
        self.assertEqual((addr, params["PARTSTAT"], params["RSVP"]), ("mailto:bob@example.com", "NEEDS-ACTION", "TRUE"))
        # In the local copy at once, as caldav reads it.
        e = self.published()[uid]
        self.assertEqual((e["title"], e["start"], e["organizer"], e["editable"]),
                         ("Lunch, then “coffee”", "2026-10-06T12:00:00Z", True, True))
        self.assertEqual((e["href"], e["etag"]), (url, self.server.files[url][1]))

    def test_all_day_and_free_and_alone(self):
        uid = edit.create("F/work", "Trip", "2026-10-10", all_day=True)
        [v] = ical.parse(self.server.writes()[0][3]).find("VEVENT")
        self.assertEqual(v.get("DTSTART"), ("20261010", {"VALUE": "DATE"}))
        self.assertEqual(v.value("DTEND"), "20261011")
        self.assertEqual(v.value("TRANSP"), "TRANSPARENT")
        self.assertIsNone(v.get("ORGANIZER"))   # nobody invited: no scheduling
        self.assertIsNone(v.get("LOCATION"))
        self.assertEqual(self.state()[uid]["allDay"], True)

    def test_a_read_only_calendar(self):
        st = self.state(whole=True)
        st["calendars"]["work"]["editable"] = False
        sync.write_private(self.state_path(), st)
        with self.assertRaisesRegex(edit.EditError, "read-only"):
            edit.create("F/work", "x", "2026-10-06 12:00")
        self.assertEqual(self.server.calls, [])


# ------------------------------------------------------------------ update

class Update(Case):
    UID = "F/work/single-1@example.com"

    def test_title_time_and_place_touch_only_their_lines(self):
        edit.update(self.UID, title="Planning, round two", start="2026-10-02T16:00:00+00:00", location="Room 5")
        [(method, url, headers, body)] = self.server.writes()
        self.assertEqual((method, url, headers["If-Match"]), ("PUT", HOME + "work/single.ics", '"1"'))
        # The zone, the alarm, the other app's X- line (odd parameter and all)
        # and the folded description come back byte for byte.
        for kept in (ZONE, ALARM):
            self.assertIn(kept.replace("\n", "\r\n"), body)
        self.assertIn('X-APPLE-TRAVEL-ADVISORY-BEHAVIOR;X-ODD="a:b;c":AUTOMATIC\r\n', body)
        self.assertIn("DESCRIPTION:A long description that goes on and on past the seventy-five o\r\n ctet", body)
        removed, added = self.changed_lines(SINGLE, body)
        self.assertEqual({re.split("[;:]", x)[0] for x in removed + added},
                         {"SUMMARY", "DTSTART", "DTEND", "LOCATION", "SEQUENCE", "DTSTAMP", "LAST-MODIFIED"})
        [v] = self.vevents("single.ics")
        self.assertEqual(v.value("SUMMARY"), "Planning, round two")
        # Still in its own zone, an hour long: 16:00Z is 11:00 in Chicago.
        self.assertEqual(v.get("DTSTART"), ("20261002T110000", {"TZID": "America/Chicago"}))
        self.assertEqual(v.get("DTEND"), ("20261002T120000", {"TZID": "America/Chicago"}))
        self.assertEqual(v.value("SEQUENCE"), "3")
        self.assertNotEqual(v.value("DTSTAMP"), "20260901T000000Z")
        e = self.state()[self.UID]
        self.assertEqual((e["title"], e["start"], e["location"], e["etag"]),
                         ("Planning, round two", "2026-10-02T16:00:00Z", "Room 5", '"2"'))

    def test_a_title_alone_keeps_the_sequence(self):
        edit.update(self.UID, title="Renamed")
        [v] = self.vevents("single.ics")
        self.assertEqual((v.value("SUMMARY"), v.value("SEQUENCE")), ("Renamed", "2"))
        self.assertIsNotNone(v.get("LAST-MODIFIED"))

    def test_clearing_the_place_and_marking_free(self):
        edit.update(self.UID, location="", busy=False)
        [v] = self.vevents("single.ics")
        self.assertIsNone(v.get("LOCATION"))
        self.assertEqual(v.value("TRANSP"), "TRANSPARENT")

    def test_changed_elsewhere_since_the_sync(self):
        url = HOME + "work/single.ics"
        self.server.files[url] = (SINGLE.replace("Planning", "Theirs"), '"7"')
        with self.assertRaises(auth.Conflict):
            edit.update(self.UID, title="Mine")
        self.assertEqual(self.server.writes(), [])
        self.assertIn("Theirs", self.server.text("single.ics"))

    def test_changed_between_read_and_write_is_a_412(self):
        self.server.race = True
        with self.assertRaises(auth.Conflict):
            edit.respond("F/work/invite-1@google.com", "accept")
        self.assertEqual(len(self.server.writes()), 1)   # tried once, not again
        self.assertIn("PARTSTAT=NEEDS-ACTION", self.server.text("invite.ics"))

    def test_one_occurrence_becomes_an_override(self):
        uid = "F/work/standup@example.com@20261019T140000Z"
        self.assertTrue(self.state()[uid]["editable"])
        edit.update(uid, title="Standup (demo)", start="2026-10-19T15:00:00+00:00")
        body = self.server.writes()[0][3]
        master, moved, new = self.vevents("series.ics")
        # The series and the earlier override are untouched, byte for byte.
        blocks = icalwrite.Doc(body).events()
        self.assertEqual(blocks[0].text(), icalwrite.Doc(SERIES).events()[0].text())
        self.assertEqual(blocks[1].text(), icalwrite.Doc(SERIES).events()[1].text())
        self.assertEqual(new.get("RECURRENCE-ID"), ("20261019T090000", {"TZID": "America/Chicago"}))
        self.assertEqual(new.get("DTSTART"), ("20261019T100000", {"TZID": "America/Chicago"}))
        self.assertEqual(new.get("DTEND"), ("20261019T101500", {"TZID": "America/Chicago"}))
        self.assertEqual((new.value("SUMMARY"), new.value("SEQUENCE"), new.value("X-MOZ-GENERATION")),
                         ("Standup (demo)", "1", "3"))
        self.assertIsNone(new.get("RRULE"))
        self.assertEqual([s.name for s in new.subs], ["VALARM"])
        st = self.state()
        self.assertEqual((st[uid]["title"], st[uid]["start"]), ("Standup (demo)", "2026-10-19T15:00:00Z"))
        self.assertEqual(st["F/work/standup@example.com@20261026T140000Z"]["title"], "Standup")
        self.assertEqual(len([e for e in st.values() if e.get("seriesId") == "standup@example.com"]), 6)

    def test_an_occurrence_already_moved_changes_in_place(self):
        edit.update("F/work/standup@example.com@20261012T140000Z", title="Standup (later)")
        events = self.vevents("series.ics")
        self.assertEqual([v.value("SUMMARY") for v in events], ["Standup", "Standup (later)"])

    def test_the_series(self):
        edit.update("F/work/standup@example.com@20261019T140000Z", title="Daily-ish", location="Hall", series=True)
        master, moved = self.vevents("series.ics")
        self.assertEqual((master.value("SUMMARY"), master.value("LOCATION")), ("Daily-ish", "Hall"))
        self.assertEqual(master.value("RRULE"), "FREQ=WEEKLY;BYDAY=MO;COUNT=6")
        # The moved one had its own title, so keeps it; it had the series' (no)
        # place, so takes the new one.
        self.assertEqual((moved.value("SUMMARY"), moved.value("LOCATION")), ("Standup (late)", "Hall"))
        titles = {e["start"][:10]: e["title"] for e in self.state().values() if e.get("seriesId")}
        self.assertEqual((titles["2026-10-19"], titles["2026-10-12"]), ("Daily-ish", "Standup (late)"))

    def test_a_series_time_moves_one_at_a_time(self):
        with self.assertRaisesRegex(edit.EditError, "move one occurrence"):
            edit.update("F/work/standup@example.com@20261019T140000Z", start="2026-10-19 11:00", series=True)
        self.assertEqual(self.server.calls, [])

    def test_someone_elses_event_isnt_edited(self):
        with self.assertRaisesRegex(edit.EditError, "can't change this event"):
            edit.update("F/work/invite-1@google.com", title="Mine now")
        self.assertEqual(self.server.calls, [])


# ------------------------------------------------------------------ guests

class Guests(Case):
    def test_invite_and_uninvite(self):
        edit.update("F/work/single-1@example.com", invite=["Carol@Example.com"], uninvite=["bob@example.com"])
        [(method, _, headers, body)] = self.server.writes()
        self.assertEqual(headers["If-Match"], '"1"')
        removed, added = self.changed_lines(SINGLE, body)
        self.assertEqual([x for x in removed if x.startswith("ATTENDEE")],
                         ["ATTENDEE;CN=Bob;PARTSTAT=NEEDS-ACTION;RSVP=TRUE;X-NUM-GUESTS=0:mailto:bob@example.com"])
        self.assertIn("ATTENDEE;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:carol@example.com", added)
        self.assertIn("ORGANIZER;CN=Me:mailto:me@example.com\r\n", body)
        guests = {g["email"] for g in self.state()["F/work/single-1@example.com"]["guests"]}
        self.assertEqual(guests, {"me@example.com", "carol@example.com"})

    def test_the_same_rules_as_the_other_providers(self):
        for invite, uninvite, why in ((["bob@example.com"], [], "already invited"),
                                      ([], ["nobody@example.com"], "isn't on the guest list"),
                                      ([], ["me@example.com"], "organiser")):
            with self.assertRaisesRegex(edit.EditError, why):
                edit.update("F/work/single-1@example.com", invite=invite, uninvite=uninvite)
        self.assertEqual(self.server.writes(), [])

    def test_inviting_to_an_event_of_your_own_makes_you_organiser(self):
        uid = edit.create("F/work", "Solo", "2026-10-06T12:00:00+00:00")
        edit.update(uid, invite=["dan@example.com"])
        [v] = ical.parse(self.server.writes()[-1][3]).find("VEVENT")
        self.assertEqual(v.value("ORGANIZER"), "mailto:me@example.com")
        self.assertEqual([a for a, _ in v.all("ATTENDEE")], ["mailto:dan@example.com"])


# ------------------------------------------------------------------ answer

class Respond(Case):
    def test_accept_changes_only_your_partstat(self):
        edit.respond("F/work/invite-1@google.com", "accept")
        [(method, _, headers, body)] = self.server.writes()
        self.assertEqual((method, headers["If-Match"]), ("PUT", '"1"'))
        removed, added = self.changed_lines(INVITE, body)
        self.assertEqual([x for x in removed if not x.startswith("DTSTAMP")],
                         ["ATTENDEE;CN=Me;CUTYPE=INDIVIDUAL;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:MAILTO:Me@Example.com"])
        self.assertIn("ATTENDEE;CN=Me;CUTYPE=INDIVIDUAL;PARTSTAT=ACCEPTED;RSVP=TRUE:MAILTO:Me@Example.com", added)
        self.assertIn('ATTENDEE;CN="Smith; Amy";PARTSTAT=ACCEPTED:mailto:amy@example.com\r\n', body)
        self.assertNotIn("SEQUENCE", body)   # an answer never bumps the organiser's sequence
        self.assertEqual(self.published()["F/work/invite-1@google.com"]["response"], "accepted")

    def test_decline_one_occurrence(self):
        uid = "F/work/weekly-olive@20261013"
        edit.respond(uid, "decline")
        master, one = self.vevents("invite-series.ics")
        self.assertEqual(master.all("ATTENDEE")[1][1]["PARTSTAT"], "NEEDS-ACTION")
        self.assertEqual(one.get("RECURRENCE-ID"), ("20261013", {"VALUE": "DATE"}))
        self.assertEqual(one.value("DTSTART"), "20261013")
        self.assertEqual([p["PARTSTAT"] for _, p in one.all("ATTENDEE")], ["ACCEPTED", "DECLINED"])
        st = self.state()
        self.assertEqual((st[uid]["response"], st["F/work/weekly-olive@20261020"]["response"]),
                         ("declined", "needsAction"))

    def test_the_whole_series(self):
        edit.respond("F/work/weekly-olive@20261013", "tentative", series=True)
        [master] = self.vevents("invite-series.ics")
        self.assertEqual(master.all("ATTENDEE")[1][1]["PARTSTAT"], "TENTATIVE")
        self.assertEqual({e["response"] for e in self.state().values() if e.get("seriesId") == "weekly-olive"},
                         {"tentative"})

    def test_your_own_event_has_nothing_to_answer(self):
        with self.assertRaisesRegex(edit.EditError, "your own event"):
            edit.respond("F/work/single-1@example.com", "accept")


# ------------------------------------------------------------------ delete

class Delete(Case):
    def test_an_event(self):
        edit.delete("F/work/single-1@example.com")
        [(method, url, headers, _)] = self.server.writes()
        self.assertEqual((method, url, headers), ("DELETE", HOME + "work/single.ics", {"If-Match": '"1"'}))
        self.assertNotIn("F/work/single-1@example.com", self.published())

    def test_an_invitation_goes_quietly(self):
        edit.delete("F/work/invite-1@google.com")
        self.assertEqual(self.server.writes()[0][2], {"If-Match": '"1"', "Schedule-Reply": "F"})

    def test_one_occurrence(self):
        edit.delete("F/work/standup@example.com@20261019T140000Z")
        [(method, _, headers, body)] = self.server.writes()
        self.assertEqual((method, headers["If-Match"]), ("PUT", '"1"'))
        master, moved = self.vevents("series.ics")
        self.assertEqual(master.get("EXDATE"), ("20261019T090000", {"TZID": "America/Chicago"}))
        self.assertEqual(master.value("SEQUENCE"), "1")
        self.assertIn(ALARM.replace("\n", "\r\n"), body)
        left = sorted(e["start"][:10] for e in self.state().values() if e.get("seriesId") == "standup@example.com")
        self.assertEqual(left, ["2026-10-05", "2026-10-12", "2026-10-26", "2026-11-02", "2026-11-09"])

    def bare_occurrence(self):
        """The 19th as a server might send a first occurrence: looking like a
        one-off, with no recurrenceId, though its resource is a series."""
        st = self.state(whole=True)
        e = dict(st["events"].pop("F/work/standup@example.com@20261019T140000Z"),
                 uid="F/work/standup@example.com", recurrenceId=None, recurring=False, seriesId=None)
        st["events"][e["uid"]] = e
        sync.write_private(self.state_path(), st)
        return e["uid"]

    def test_a_series_occurrence_that_looks_like_a_one_off(self):
        # Deleting the resource here would take the whole series with it.
        edit.delete(self.bare_occurrence())
        writes = self.server.writes()
        self.assertEqual([w[0] for w in writes], ["PUT"])
        master = self.vevents("series.ics")[0]
        self.assertEqual(master.get("EXDATE"), ("20261019T090000", {"TZID": "America/Chicago"}))

    def test_renaming_it_changes_only_that_occurrence(self):
        edit.update(self.bare_occurrence(), title="Just this one")
        blocks = self.vevents("series.ics")
        self.assertEqual(blocks[0].value("SUMMARY"), "Standup")
        self.assertIn(("Just this one", "20261019T090000"),
                      [(b.value("SUMMARY"), b.value("RECURRENCE-ID")) for b in blocks[1:]])

    def test_an_occurrence_that_had_been_moved(self):
        edit.delete("F/work/standup@example.com@20261012T140000Z")
        [master] = self.vevents("series.ics")
        self.assertEqual(master.value("EXDATE"), "20261012T090000")
        self.assertNotIn("Standup (late)", self.server.text("series.ics"))

    def test_the_series(self):
        edit.delete("F/work/standup@example.com@20261019T140000Z", series=True)
        [(method, url, _, _)] = self.server.writes()
        self.assertEqual((method, url), ("DELETE", HOME + "work/series.ics"))
        self.assertFalse(any(e.get("seriesId") == "standup@example.com" for e in self.state().values()))


# -------------------------------------------------------------- the wire

class Wire(Case):
    def test_no_etag_back_means_read_it_again(self):
        # Scheduling makes the server alter what it stores, so it sends no
        # ETag; the stored copy is read back to learn the real one.
        self.server.etag_on_put = False
        edit.update("F/work/single-1@example.com", title="Again")
        self.assertEqual([c[0] for c in self.server.calls], ["GET", "PUT", "GET"])
        self.assertEqual(self.state()["F/work/single-1@example.com"]["etag"], '"2"')

    def test_a_412_is_a_conflict(self):
        import io
        import urllib.error
        err = urllib.error.HTTPError(HOME, 412, "Precondition Failed", {}, io.BytesIO(b""))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaisesRegex(auth.Conflict, "changed elsewhere"):
                caldav.Session(HOME, ME, "pw").send("PUT", HOME + "work/x.ics", b"x", {"If-Match": '"1"'})

    def test_gone_from_the_server(self):
        del self.server.files[HOME + "work/single.ics"]
        with self.assertRaisesRegex(auth.Conflict, "no longer on the server"):
            edit.update("F/work/single-1@example.com", title="x")

    def test_a_local_copy_from_before_editing(self):
        st = self.state(whole=True)
        del st["events"]["F/work/single-1@example.com"]["href"]
        sync.write_private(self.state_path(), st)
        with self.assertRaisesRegex(edit.EditError, "sync and try again"):
            edit.update("F/work/single-1@example.com", title="x")
        self.assertEqual(self.server.calls, [])


if __name__ == "__main__":
    unittest.main()
