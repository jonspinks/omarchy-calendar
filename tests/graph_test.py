"""Graph delta items that carry only what changed.

    python3 -B -m unittest discover -s tests -p '*_test.py'
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from omcal import graph  # noqa: E402

CAL = {"id": "cal", "editable": True}
WINDOW = ("2026-09-01T00:00:00Z", "2026-12-01T00:00:00Z")


def full(eid, subject="ThreeOaks Fire Inspection", organizer=True):
    return {"id": eid, "subject": subject, "isOrganizer": organizer, "type": "occurrence",
            "seriesMasterId": "master", "start": {"dateTime": "2026-10-13T12:30:00.0000000"},
            "end": {"dateTime": "2026-10-13T13:30:00.0000000"},
            "responseStatus": {"response": "organizer"}, "showAs": "free", "@odata.etag": 'W/"2"'}


class PartialDeltaItems(unittest.TestCase):
    def run_fetch(self, items, events_by_id):
        calls = []

        def fake_get(url, tok, prefer="odata.maxpagesize=100"):
            if "/calendarView/delta" in url:
                return {"value": items, "@odata.deltaLink": "next"}
            calls.append((url, prefer))
            eid = url.rsplit("/", 1)[1]
            if eid not in events_by_id:
                raise graph.DeltaExpired()   # any failure to read it
            return events_by_id[eid]

        with mock.patch.object(graph, "_get", fake_get):
            events, removed, link = graph.fetch("Plan2", "tok", CAL, WINDOW, None, "me@plan2.example")
        return events, calls

    def test_a_partial_item_is_read_in_full(self):
        partial = {"id": "occ1", "start": {"dateTime": "2026-10-13T12:30:00.0000000"},
                   "end": {"dateTime": "2026-10-13T13:30:00.0000000"}, "@odata.etag": 'W/"2"'}
        events, calls = self.run_fetch([partial], {"occ1": full("occ1")})
        self.assertEqual([(e["title"], e["organizer"], e["editable"], e["response"]) for e in events],
                         [("ThreeOaks Fire Inspection", True, True, "organizer")])
        self.assertEqual(calls, [(graph.API + "/me/events/occ1", 'outlook.timezone="UTC"')])

    def test_a_complete_item_is_not_read_again(self):
        events, calls = self.run_fetch([full("occ2")], {})
        self.assertEqual(calls, [])
        self.assertEqual(events[0]["title"], "ThreeOaks Fire Inspection")

    def test_an_untitled_event_is_not_mistaken_for_a_partial_one(self):
        events, calls = self.run_fetch([full("occ3", subject="")], {})
        self.assertEqual(calls, [])
        self.assertEqual(events[0]["title"], "(no title)")

    def test_a_partial_item_that_cant_be_read_is_skipped(self):
        partial = {"id": "gone", "start": {"dateTime": "2026-10-13T12:30:00.0000000"},
                   "end": {"dateTime": "2026-10-13T13:30:00.0000000"}}
        events, calls = self.run_fetch([partial], {})
        self.assertEqual(events, [])
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
