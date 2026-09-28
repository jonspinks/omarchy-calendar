"""The sync side: join links, Graph's timestamps, and de-duplication.

    python3 -B -m unittest discover -s tests -p '*_test.py'
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from omcal.model import find_join, parse_instant, utc_iso  # noqa: E402
from omcal.sync import dedupe  # noqa: E402


class JoinLinks(unittest.TestCase):
    def test_teams_behind_an_href(self):
        html = '<a href="https://teams.microsoft.com/l/meetup-join/19%3ameeting_x/0?context=1">Click here to join</a>'
        self.assertEqual(find_join(html)["kind"], "teams")

    def test_zoom_and_meet_in_text(self):
        self.assertEqual(find_join("Join: https://acme.zoom.us/j/123456789?pwd=x.")["url"],
                         "https://acme.zoom.us/j/123456789?pwd=x")
        self.assertEqual(find_join("meet https://meet.google.com/abc-defg-hij")["kind"], "meet")

    def test_only_https_and_known_hosts(self):
        self.assertIsNone(find_join("http://teams.microsoft.com/l/meetup-join/x"))
        self.assertIsNone(find_join("https://evil.example/zoom.us/j/1"))


class Instants(unittest.TestCase):
    def test_graph_seven_digit_fraction(self):
        self.assertEqual(utc_iso(parse_instant("2026-09-28T14:00:00.0000000", assume_utc=True)), "2026-09-28T14:00:00Z")

    def test_offset(self):
        self.assertEqual(utc_iso(parse_instant("2026-09-28T10:00:00-04:00")), "2026-09-28T14:00:00Z")

    def test_no_zone_refused(self):
        with self.assertRaises(ValueError):
            parse_instant("2026-09-28T10:00:00")


class Dedupe(unittest.TestCase):
    def test_keeps_the_editable_copy(self):
        cals = [{"account": "G", "id": "mirror", "name": "Mirror", "primary": False},
                {"account": "G", "id": "main", "name": "Main", "primary": True}]
        ev = {"title": "Standup", "start": "2026-09-28T13:30:00Z", "end": "2026-09-28T13:45:00Z", "allDay": False}
        out = dedupe([dict(ev, account="G", calendar="mirror", editable=False),
                      dict(ev, account="G", calendar="main", editable=True)], cals)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["calendar"], "main")
        self.assertEqual(out[0]["alsoIn"], ["G: Mirror"])


if __name__ == "__main__":
    unittest.main()
