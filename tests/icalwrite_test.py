"""The iCalendar writer: lines, folding, escaping, and patches that keep every other byte.

    python3 -B -m unittest discover -s tests -p '*_test.py'
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from omcal import ical, icalwrite  # noqa: E402

ALARM_TEXT = """BEGIN:VALARM
X-WR-ALARMUID:5A1B-alarm
ACTION:DISPLAY
TRIGGER:-PT15M
END:VALARM"""

# Folded lines, a quoted parameter holding ":" and ";", a time zone, an alarm.
SINGLE = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//macOS 15//EN
BEGIN:VTIMEZONE
TZID:America/Chicago
BEGIN:STANDARD
TZOFFSETFROM:-0500
TZOFFSETTO:-0600
DTSTART:19701101T020000
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:single-1@example.com
SUMMARY:Planning
DESCRIPTION:A long description that goes on and on past the seventy-five o
 ctet limit\\, folded where the other app folded it.
X-APPLE-TRAVEL-ADVISORY-BEHAVIOR;X-ODD="a:b;c":AUTOMATIC
ORGANIZER;CN=Me:mailto:me@example.com
ATTENDEE;CN=Me;PARTSTAT=ACCEPTED:mailto:me@example.com
ATTENDEE;CN=Bob;PARTSTAT=NEEDS-ACTION:mailto:bob@example.com
%s
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n") % ALARM_TEXT.replace("\n", "\r\n")


class Writer(unittest.TestCase):
    def test_every_byte_survives_a_parse(self):
        for text in (SINGLE, SINGLE.replace("\r\n", "\n"), "BEGIN:VCALENDAR\r\nEND:VEVENT\r\nX:1"):
            self.assertEqual(icalwrite.Doc(text).text(), text)

    def test_fold_counts_octets_and_never_splits_a_character(self):
        title = "Café meeting ☕ with Zoë and 東京 office: " * 5
        folded = icalwrite.fold(icalwrite.line("SUMMARY", title, text=True))
        for phys in folded.split("\r\n"):
            self.assertLessEqual(len(phys.encode("utf-8")), 75)
            phys.encode("utf-8").decode("utf-8")   # whole characters only
        self.assertTrue(all(p.startswith(" ") for p in folded.split("\r\n")[1:]))
        [v] = ical.parse("BEGIN:VEVENT\r\n" + folded + "\r\nEND:VEVENT\r\n").find("VEVENT")
        self.assertEqual(v.value("SUMMARY"), title)

    def test_text_escapes(self):
        self.assertEqual(icalwrite.line("LOCATION", "Room 4; B, 2\\3\nUp", text=True),
                         "LOCATION:Room 4\\; B\\, 2\\\\3\\nUp")
        self.assertEqual(icalwrite.line("ATTENDEE", "mailto:a@b.c", [("CN", 'Smith, "Jo"')]),
                         "ATTENDEE;CN=\"Smith, 'Jo'\":mailto:a@b.c")

    def test_with_param_keeps_the_rest_of_the_line(self):
        line = 'ATTENDEE;CN="Smith; Amy: PhD";PARTSTAT=NEEDS-ACTION;X-Y=1:mailto:amy@example.com'
        self.assertEqual(icalwrite.with_param(line, "PARTSTAT", "ACCEPTED"),
                         'ATTENDEE;CN="Smith; Amy: PhD";PARTSTAT=ACCEPTED;X-Y=1:mailto:amy@example.com')
        self.assertEqual(icalwrite.with_param("ATTENDEE:mailto:a@b.c", "PARTSTAT", "DECLINED"),
                         "ATTENDEE;PARTSTAT=DECLINED:mailto:a@b.c")

    def test_block_set_add_drop(self):
        doc = icalwrite.Doc(SINGLE)
        [v] = doc.events()
        v.set("SUMMARY", "SUMMARY:New")
        v.drop("ATTENDEE", keep=lambda value, p: "bob" not in value)
        v.add("ATTENDEE:mailto:carol@example.com")
        v.add("X-NEW:1")   # no X-NEW yet: after the last property, before the VALARM_TEXT
        text = doc.text()
        self.assertIn("SUMMARY:New\r\n", text)
        self.assertNotIn("bob@example.com", text)
        self.assertIn("mailto:me@example.com\r\nATTENDEE:mailto:carol@example.com\r\n", text)
        self.assertIn("X-NEW:1\r\n" + ALARM_TEXT.replace("\n", "\r\n"), text)


if __name__ == "__main__":
    unittest.main()
