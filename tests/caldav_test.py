"""CalDAV: listing calendars, reading iCalendar, series, and the ctag cursor.

    python3 -B -m unittest discover -s tests -p '*_test.py'

Every reply here is made up; nothing talks to a server.
"""
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from unittest import mock
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from omcal import auth, caldav, edit, ical, sync  # noqa: E402

HOME = "https://caldav.example.com/dav/calendars/user/me@example.com/"
CAL = {"id": "work", "href": HOME + "work/", "editable": False, "ctag": "c1"}
WINDOW = ("2026-09-01T00:00:00Z", "2026-11-01T00:00:00Z")
ME = "me@example.com"

# Odd prefixes on purpose: nothing may assume "d:".
PROPFIND = """<?xml version="1.0" encoding="UTF-8"?>
<multistatus xmlns="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav"
             xmlns:x1="http://calendarserver.org/ns/" xmlns:ap="http://apple.com/ns/ical/">
 <response><href>/dav/calendars/user/me@example.com/</href>
  <propstat><prop><resourcetype><collection/></resourcetype><displayname>me</displayname></prop>
   <status>HTTP/1.1 200 OK</status></propstat></response>
 <response><href>/dav/calendars/user/me@example.com/Inbox/</href>
  <propstat><prop><resourcetype><collection/><C:schedule-inbox/></resourcetype>
   <C:schedule-default-calendar-URL><href>/dav/calendars/user/me@example.com/work/</href></C:schedule-default-calendar-URL>
  </prop><status>HTTP/1.1 200 OK</status></propstat></response>
 <response><href>/dav/calendars/user/me@example.com/Outbox/</href>
  <propstat><prop><resourcetype><collection/><C:schedule-outbox/></resourcetype></prop>
   <status>HTTP/1.1 200 OK</status></propstat></response>
 <response><href>/dav/calendars/user/me@example.com/Default/</href>
  <propstat><prop><resourcetype><collection/><C:calendar/></resourcetype>
   <displayname>Personal</displayname><ap:calendar-color>#3A429CFF</ap:calendar-color>
   <x1:getctag>ctag-1</x1:getctag>
   <C:supported-calendar-component-set><C:comp name="VEVENT"/><C:comp name="VTODO"/></C:supported-calendar-component-set>
   <current-user-privilege-set><privilege><read/></privilege><privilege><write/></privilege></current-user-privilege-set>
  </prop><status>HTTP/1.1 200 OK</status></propstat>
  <propstat><prop><sync-token/></prop><status>HTTP/1.1 404 Not Found</status></propstat></response>
 <response><href>/dav/calendars/user/me@example.com/work/</href>
  <propstat><prop><resourcetype><collection/><C:calendar/></resourcetype>
   <displayname>Work</displayname><ap:calendar-color>#00aa00</ap:calendar-color>
   <sync-token>https://example.com/sync/7</sync-token>
   <current-user-privilege-set><privilege><read/></privilege></current-user-privilege-set>
  </prop><status>HTTP/1.1 200 OK</status></propstat></response>
 <response><href>/dav/calendars/user/me@example.com/tasks/</href>
  <propstat><prop><resourcetype><collection/><C:calendar/></resourcetype><displayname>Tasks</displayname>
   <C:supported-calendar-component-set><C:comp name="VTODO"/></C:supported-calendar-component-set>
  </prop><status>HTTP/1.1 200 OK</status></propstat></response>
</multistatus>"""


def ics(*vevents, extra=""):
    return "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//test//EN", extra.strip()]
                       + [v.strip().replace("\n", "\r\n") for v in vevents] + ["END:VCALENDAR", ""])


MEETING = """BEGIN:VEVENT
UID:meet-1@example.com
DTSTAMP:20260901T000000Z
DTSTART;TZID=America/Chicago:20261002T090000
DTEND;TZID=America/Chicago:20261002T100000
SUMMARY:Plan\\, review\\; and ship
LOCATION:Room 4
DESCRIPTION:Agenda:\\nOne\\nJoin: https://acme.zoom.us/j/123456789?p
 wd=abc
ORGANIZER;CN=Olive:mailto:olive@example.com
ATTENDEE;CN="Smith; Amy";PARTSTAT=ACCEPTED;ROLE=OPT-PARTICIPANT:mailto:amy@example.com
ATTENDEE;PARTSTAT=TENTATIVE;RSVP=TRUE:MAILTO:Me@Example.com
ATTENDEE;CUTYPE=ROOM;PARTSTAT=ACCEPTED;CN=Room 4:mailto:room4@example.com
TRANSP:OPAQUE
STATUS:CONFIRMED
BEGIN:VALARM
ACTION:DISPLAY
TRIGGER:-PT15M
DESCRIPTION:x
END:VALARM
BEGIN:VALARM
ACTION:EMAIL
TRIGGER:-PT1H
END:VALARM
BEGIN:VALARM
ACTION:AUDIO
TRIGGER;VALUE=DATE-TIME:20261002T130000Z
END:VALARM
END:VEVENT"""

CHICAGO = """BEGIN:VTIMEZONE
TZID:America/Chicago
BEGIN:DAYLIGHT
TZOFFSETFROM:-0600
TZOFFSETTO:-0500
DTSTART:19700308T020000
SUMMARY:should never be read
END:DAYLIGHT
END:VTIMEZONE"""


def events(data, window=WINDOW, cal=CAL):
    return caldav.resource_events("F", cal, ics(*data) if isinstance(data, list) else data, '"e1"', window, ME)


class Listing(unittest.TestCase):
    def test_calendars_from_a_multistatus(self):
        with mock.patch.object(caldav, "_request", return_value=PROPFIND.encode()):
            cals = caldav.calendars(caldav.Session(HOME, ME, "pw"))
        self.assertEqual([c["id"] for c in cals], ["Default", "work"])   # no Inbox, Outbox or task list
        personal, work = cals
        self.assertEqual((personal["name"], personal["color"], personal["ctag"]), ("Personal", "#3A429C", "ctag-1"))
        self.assertEqual(personal["syncToken"], "")   # a 404 propstat is not a blank value
        self.assertEqual(personal["href"], HOME + "Default/")
        # Editable where the server grants write; Work grants only read.
        self.assertEqual([c["editable"] for c in cals], [True, False])
        # The default calendar, named on the Inbox, is the primary one.
        self.assertEqual([c["primary"] for c in cals], [False, True])
        self.assertEqual(caldav.cursor(work), "3:https://example.com/sync/7")

    def test_401_is_a_sign_in_problem(self):
        import io
        import urllib.error
        err = urllib.error.HTTPError(HOME, 401, "Unauthorized", {}, io.BytesIO(b""))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(auth.AuthError):
                caldav.calendars(caldav.Session(HOME, ME, "wrong"))

    def test_over_real_http(self):
        # A stub server on this machine: the method, Depth and Basic
        # credentials really go over the wire, and a 207 is a success.
        import base64
        import http.server
        import threading
        seen = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_PROPFIND(self):
                seen.update(method=self.command, depth=self.headers["Depth"], auth=self.headers["Authorization"],
                            body=self.rfile.read(int(self.headers["Content-Length"])))
                self.send_response(207)
                self.send_header("Content-Type", "application/xml")
                self.end_headers()
                self.wfile.write(PROPFIND.encode())

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.handle_request, daemon=True).start()
        try:
            cals = caldav.calendars(caldav.Session("http://127.0.0.1:%d/home/" % srv.server_port, ME, "s3cret"))
        finally:
            srv.server_close()
        self.assertEqual(len(cals), 2)
        self.assertEqual((seen["method"], seen["depth"]), ("PROPFIND", "1"))
        self.assertEqual(seen["auth"], "Basic " + base64.b64encode(b"me@example.com:s3cret").decode())
        self.assertIn(b"getctag", seen["body"])
        self.assertEqual(cals[0]["href"], "http://127.0.0.1:%d/dav/calendars/user/me@example.com/Default/" % srv.server_port)

    def test_only_https(self):
        with self.assertRaises(auth.AuthError):
            caldav.check_url("http://caldav.example.com/")
        caldav.check_url("http://localhost:5232/me/")

    def test_fastmail_home(self):
        self.assertEqual(caldav.fastmail_home("kyle@example.com"),
                         "https://caldav.fastmail.com/dav/calendars/user/kyle@example.com/")


class Parsing(unittest.TestCase):
    def test_folded_lines_params_and_escapes(self):
        cal = ical.parse(ics(MEETING)).find("VEVENT")[0]
        self.assertEqual(cal.value("SUMMARY"), "Plan, review; and ship")
        self.assertEqual(cal.value("DESCRIPTION"), "Agenda:\nOne\nJoin: https://acme.zoom.us/j/123456789?pwd=abc")
        amy = cal.all("ATTENDEE")[0]
        self.assertEqual((amy[1]["CN"], amy[1]["PARTSTAT"], amy[0]), ("Smith; Amy", "ACCEPTED", "mailto:amy@example.com"))

    def test_a_meeting_in_the_model(self):
        [e] = events(ics(MEETING, extra=CHICAGO))
        self.assertEqual(e["uid"], "F/work/meet-1@example.com")
        self.assertEqual((e["start"], e["end"], e["allDay"]), ("2026-10-02T14:00:00Z", "2026-10-02T15:00:00Z", False))
        self.assertEqual(e["title"], "Plan, review; and ship")
        self.assertEqual(e["join"], {"url": "https://acme.zoom.us/j/123456789?pwd=abc", "kind": "zoom"})
        self.assertEqual((e["response"], e["organizer"]), ("tentative", False))
        self.assertEqual(e["remind"], [15])   # not the email alarm, nor the fixed-time one
        self.assertEqual((e["busy"], e["status"], e["recurring"], e["seriesId"]), (True, "confirmed", False, None))
        self.assertEqual((e["editable"], e["webLink"], e["etag"]), (False, "", '"e1"'))
        g = {x["email"].lower(): x for x in e["guests"]}
        self.assertEqual(e["guests"][0]["email"], "olive@example.com")   # the organiser, added and first
        self.assertTrue(g["olive@example.com"]["organizer"])
        self.assertTrue(g["amy@example.com"]["optional"])
        self.assertEqual(g["amy@example.com"]["name"], "Smith; Amy")
        self.assertTrue(g["me@example.com"]["me"])
        self.assertEqual(g["me@example.com"]["response"], "tentative")
        self.assertTrue(g["room4@example.com"]["room"])
        self.assertEqual(e["guestTotal"], 4)

    def test_all_day_duration_and_defaults(self):
        got = events([
            "BEGIN:VEVENT\nUID:a\nDTSTART;VALUE=DATE:20261005\nDTEND;VALUE=DATE:20261007\nSUMMARY:Trip\nTRANSP:TRANSPARENT\nEND:VEVENT",
            "BEGIN:VEVENT\nUID:b\nDTSTART;VALUE=DATE:20261010\nEND:VEVENT",
            "BEGIN:VEVENT\nUID:c\nDTSTART:20261003T120000Z\nDURATION:PT1H30M\nSTATUS:TENTATIVE\nEND:VEVENT",
            "BEGIN:VEVENT\nUID:d\nDTSTART:20261004T120000Z\nEND:VEVENT",
        ])
        by = {e["uid"].rsplit("/", 1)[1]: e for e in got}
        self.assertEqual((by["a"]["start"], by["a"]["end"], by["a"]["allDay"], by["a"]["busy"]),
                         ("2026-10-05", "2026-10-07", True, False))
        self.assertEqual((by["b"]["end"], by["b"]["title"]), ("2026-10-11", "(no title)"))
        self.assertEqual((by["c"]["end"], by["c"]["status"]), ("2026-10-03T13:30:00Z", "tentative"))
        self.assertEqual(by["d"]["end"], by["d"]["start"])
        # Your own event: no organiser, no guests.
        self.assertEqual((by["a"]["response"], by["a"]["organizer"], by["a"]["guests"]), ("organizer", True, []))

    def test_organised_by_me(self):
        [e] = events(["BEGIN:VEVENT\nUID:o\nDTSTART:20261003T120000Z\nORGANIZER:mailto:me@example.com\n"
                      "ATTENDEE;PARTSTAT=ACCEPTED:mailto:me@example.com\nATTENDEE:mailto:bob@example.com\nEND:VEVENT"])
        self.assertEqual((e["response"], e["organizer"]), ("organizer", True))
        self.assertEqual(e["guests"][0]["email"], "me@example.com")
        self.assertEqual(e["guests"][1]["response"], "needsAction")

    def test_invited_but_not_by_this_address(self):
        [e] = events(["BEGIN:VEVENT\nUID:n\nDTSTART:20261003T120000Z\nORGANIZER:mailto:olive@example.com\n"
                      "ATTENDEE:mailto:alias@example.com\nEND:VEVENT"])
        self.assertEqual((e["response"], e["organizer"]), ("none", False))

    def test_unknown_zone_falls_back_to_local(self):
        t = ical.parse_time("20261002T090000", "Central Standard Time")
        self.assertEqual(t.utcoffset(), datetime(2026, 10, 2, 9).astimezone().utcoffset())
        self.assertEqual(ical.parse_time("20261002T090000", "/mozilla.org/20050126_1/America/Chicago").tzinfo,
                         ZoneInfo("America/Chicago"))

    def test_outside_the_window_is_dropped(self):
        self.assertEqual(events(["BEGIN:VEVENT\nUID:x\nDTSTART:20270101T120000Z\nEND:VEVENT"]), [])


class Series(unittest.TestCase):
    def test_server_expanded_occurrences(self):
        # What calendar-data with <expand> looks like: one VEVENT per
        # occurrence, each with its RECURRENCE-ID, in UTC, and no RRULE.
        occ = ("BEGIN:VEVENT\nUID:standup\nRECURRENCE-ID:{d}T140000Z\nDTSTART:{d}T140000Z\n"
               "DTEND:{d}T141500Z\nSUMMARY:{t}\nEND:VEVENT")
        data = [occ.format(d="20261005", t="Standup"), occ.format(d="20261006", t="Standup (moved room)")]
        first = events(data)
        self.assertEqual([e["uid"] for e in first],
                         ["F/work/standup@20261005T140000Z", "F/work/standup@20261006T140000Z"])
        self.assertTrue(all(e["recurring"] and e["seriesId"] == "standup" for e in first))
        self.assertEqual([e["uid"] for e in events(data)], [e["uid"] for e in first])   # stable

    def test_expanded_first_occurrence_without_its_recurrence_id(self):
        # Fastmail sends a series' first occurrence bare: no RECURRENCE-ID and
        # no RRULE. Its siblings' UID is what marks it as part of the series.
        bare = "BEGIN:VEVENT\nUID:s\nDTSTART:20261005T140000Z\nDTEND:20261005T143000Z\nSUMMARY:S\nEND:VEVENT"
        occ = ("BEGIN:VEVENT\nUID:s\nRECURRENCE-ID:20261012T140000Z\nDTSTART:20261012T140000Z\n"
               "DTEND:20261012T143000Z\nSUMMARY:S\nEND:VEVENT")
        got = sorted(events([bare, occ]), key=lambda e: e["start"])
        self.assertEqual([e["uid"] for e in got], ["F/work/s@20261005T140000Z", "F/work/s@20261012T140000Z"])
        self.assertTrue(all(e["recurring"] and e["seriesId"] == "s" for e in got))
        self.assertEqual(got[0]["recurrenceId"], "20261005T140000Z")

    def test_weekly_byday_count_with_exdate_and_an_override(self):
        master = ("BEGIN:VEVENT\nUID:w\nDTSTART;TZID=America/Chicago:20260928T090000\n"
                  "DTEND;TZID=America/Chicago:20260928T093000\nSUMMARY:Sync\n"
                  "RRULE:FREQ=WEEKLY;BYDAY=MO,WE;COUNT=6\n"
                  "EXDATE;TZID=America/Chicago:20261005T090000\nEND:VEVENT")
        moved = ("BEGIN:VEVENT\nUID:w\nRECURRENCE-ID;TZID=America/Chicago:20260930T090000\n"
                 "DTSTART;TZID=America/Chicago:20260930T110000\nDTEND;TZID=America/Chicago:20260930T113000\n"
                 "SUMMARY:Sync (moved)\nEND:VEVENT")
        got = sorted(events([master, moved]), key=lambda e: e["start"])
        # Six from the rule (Sep 28, 30; Oct 5, 7, 12, 14), less the EXDATE,
        # with the 30th replaced by its override. November's DST change
        # doesn't reach them: all at 9:00 CDT = 14:00Z.
        self.assertEqual([(e["start"], e["title"]) for e in got], [
            ("2026-09-28T14:00:00Z", "Sync"), ("2026-09-30T16:00:00Z", "Sync (moved)"),
            ("2026-10-07T14:00:00Z", "Sync"), ("2026-10-12T14:00:00Z", "Sync"), ("2026-10-14T14:00:00Z", "Sync")])
        self.assertEqual(got[1]["uid"], "F/work/w@20260930T140000Z")   # keyed by the occurrence it replaces
        self.assertEqual(len({e["uid"] for e in got}), 5)
        self.assertTrue(all(e["seriesId"] == "w" for e in got))

    def test_daily_until_across_dst_in_the_window(self):
        master = ("BEGIN:VEVENT\nUID:d\nDTSTART;TZID=America/Chicago:20261029T080000\nDURATION:PT1H\n"
                  "RRULE:FREQ=DAILY;UNTIL=20261102T140000Z\nEND:VEVENT")
        got = sorted(events([master]), key=lambda e: e["start"])
        # 8:00 local every day: 13:00Z until DST ends on 1 November, then 14:00Z.
        self.assertEqual([e["start"] for e in got], ["2026-10-29T13:00:00Z", "2026-10-30T13:00:00Z",
                                                     "2026-10-31T13:00:00Z"])  # Nov 1 is past the window end
        wide = ("2026-10-01T00:00:00Z", "2026-12-01T00:00:00Z")
        got = sorted(events([master], window=wide), key=lambda e: e["start"])
        self.assertEqual([e["start"] for e in got][-2:], ["2026-11-01T14:00:00Z", "2026-11-02T14:00:00Z"])

    def test_monthly_and_all_day_yearly(self):
        self.assertEqual(ical.occurrences(date(2026, 1, 31), "FREQ=MONTHLY;COUNT=3", datetime(2027, 1, 1, tzinfo=timezone.utc)),
                         [date(2026, 1, 31), date(2026, 3, 31), date(2026, 5, 31)])   # no 31st in Feb or April
        self.assertEqual(ical.occurrences(date(2026, 9, 1), "FREQ=MONTHLY;BYDAY=-1FR;COUNT=2", date(2027, 1, 1)),
                         [date(2026, 9, 25), date(2026, 10, 30)])
        self.assertEqual(ical.occurrences(date(2024, 2, 29), "FREQ=YEARLY", date(2028, 12, 31)),
                         [date(2024, 2, 29), date(2028, 2, 29)])

    def test_unsupported_rule_gives_the_first_and_says_so(self):
        start = datetime(2026, 10, 1, 9, tzinfo=timezone.utc)
        with mock.patch.object(ical, "warn") as warn:
            got = ical.occurrences(start, "FREQ=MONTHLY;BYDAY=MO;BYSETPOS=1", datetime(2027, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(got, [start])
        warn.assert_called_once()

    def test_endless_rule_stops(self):
        start = datetime(2000, 1, 1, tzinfo=timezone.utc)
        got = ical.occurrences(start, "FREQ=DAILY", datetime(2100, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(len(got), ical.MAX_STEPS)


class Syncing(unittest.TestCase):
    """A caldav account through sync_account and publish, with the server stubbed."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.patches = [mock.patch.object(sync, "CACHE", self.dir),
                        mock.patch.object(auth, "hidden_calendars", return_value={}),
                        mock.patch.object(caldav, "login", return_value=caldav.Session(HOME, ME, "pw"))]
        for p in self.patches:
            p.start()
        self.account = {"name": "F", "provider": "caldav", "email": ME, "url": HOME}
        self.cal = dict(CAL, name="Work", color="#00aa00", primary=True)
        self.reports = 0

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.dir)

    def run_sync(self, ctag, data, full=False):
        def report(session, method, url, body, depth):
            self.reports += 1
            return ('<d:multistatus xmlns:d="DAV:" xmlns:cal="urn:ietf:params:xml:ns:caldav"><d:response>'
                    '<d:href>/dav/work/x.ics</d:href><d:propstat><d:prop><d:getetag>"e9"</d:getetag>'
                    '<cal:calendar-data>%s</cal:calendar-data></d:prop><d:status>HTTP/1.1 200 OK</d:status>'
                    '</d:propstat></d:response></d:multistatus>' % ics(*data).replace("&", "&amp;")).encode()
        with mock.patch.object(caldav, "calendars", return_value=[dict(self.cal, ctag=ctag)]), \
                mock.patch.object(caldav, "_request", side_effect=report):
            return sync.sync_account(self.account, full, lambda *_: None)

    def test_ctag_unchanged_is_not_fetched(self):
        one = ["BEGIN:VEVENT\nUID:u1\nDTSTART:20261003T120000Z\nDTEND:20261003T130000Z\nSUMMARY:One\nEND:VEVENT"]
        st = self.run_sync("c1", one)
        self.assertEqual((st["status"], self.reports), ("ok", 1))
        self.assertEqual(list(st["events"]), ["F/work/u1"])
        self.assertEqual(st["calendars"]["work"]["cursor"], "3:c1")
        st = self.run_sync("c1", [])   # the server would say nothing is there: never asked
        self.assertEqual((self.reports, list(st["events"])), (1, ["F/work/u1"]))
        # A moved ctag refetches the calendar whole: what's gone is gone.
        two = ["BEGIN:VEVENT\nUID:u2\nDTSTART:20261004T120000Z\nSUMMARY:Two\nEND:VEVENT"]
        st = self.run_sync("c2", two)
        self.assertEqual((self.reports, list(st["events"])), (2, ["F/work/u2"]))
        self.assertEqual(st["calendars"]["work"]["cursor"], "3:c2")
        st = self.run_sync("c2", two, full=True)   # --full always fetches
        self.assertEqual(self.reports, 3)

    def test_into_events_json(self):
        with mock.patch.object(sync, "window_now", return_value=("2026-09-28", WINDOW)):
            st = self.run_sync("c1", [MEETING])
            out = sync.publish([self.account], {"F": st})
        self.assertEqual(out["accounts"][0]["provider"], "caldav")
        self.assertEqual(out["accounts"][0]["status"], "ok")
        self.assertEqual(out["calendars"][0], {"account": "F", "id": "work", "name": "Work", "color": "#00aa00",
                                               "primary": True, "editable": False, "shown": True})
        [e] = out["events"]
        self.assertEqual((e["uid"], e["etag"], e["alsoIn"]), ("F/work/meet-1@example.com", '"e9"', []))
        self.assertEqual(e["href"], "https://caldav.example.com/dav/work/x.ics")
        self.assertIsNone(e["recurrenceId"])
        # The model's shape, plus the two fields only CalDAV needs for writing back.
        self.assertEqual(set(e) - {"alsoIn", "href", "recurrenceId"}, set(_google_shape()))
        self.assertTrue(os.path.exists(os.path.join(self.dir, "events.json")))

    def test_a_broken_event_is_skipped(self):
        bad = ["BEGIN:VEVENT\nUID:bad\nDTSTART:2026-10-03\nEND:VEVENT"]
        with mock.patch.object(caldav.ical, "warn") as warn:
            st = self.run_sync("c1", bad)
        self.assertEqual((st["status"], st["events"]), ("ok", {}))
        warn.assert_called_once()

    def test_signed_out(self):
        with mock.patch.object(caldav, "calendars", side_effect=auth.AuthError("refused")):
            st = sync.sync_account(self.account, False, lambda *_: None)
        self.assertEqual(st["status"], "signin")


def _google_shape():
    from omcal import google
    return google.normalise("G", {"id": "p", "editable": True, "defaultRemind": []},
                            {"id": "1", "start": {"date": "2026-10-01"}, "end": {"date": "2026-10-02"}})


class Upgrade(unittest.TestCase):
    def test_a_phase_1_cursor_fetches_once_more(self):
        # State saved before events had an href holds the bare ctag; it no
        # longer matches, so each calendar is read again and gains them.
        self.assertNotEqual(caldav.cursor({"ctag": "c1"}), "c1")
        self.assertIsNone(caldav.cursor({}))


if __name__ == "__main__":
    unittest.main()
