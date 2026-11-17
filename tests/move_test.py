"""Moving an event to another calendar: Google's own move, or a copy and delete.

    python3 -B -m unittest discover -s tests -p '*_test.py'
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from omcal import auth, edit, sync  # noqa: E402

GOOGLE = {"name": "P", "provider": "google", "email": "me@example.com"}
MS = {"name": "E", "provider": "microsoft", "email": "me@corp.example"}
GCALS = {"primary": {"id": "primary", "name": "Me", "editable": True, "defaultRemind": []},
         "family": {"id": "family", "name": "Family", "editable": True, "defaultRemind": []},
         "holidays": {"id": "holidays", "name": "Holidays", "editable": False, "defaultRemind": []}}
MCALS = {"cal": {"id": "cal", "name": "Calendar", "editable": True}}


def event(account, cal, eid, **kw):
    e = {"uid": "%s/%s/%s" % (account, cal, eid), "account": account, "calendar": cal, "title": "Plan",
         "allDay": False, "start": "2026-10-02T14:00:00Z", "end": "2026-10-02T15:00:00Z",
         "location": "Room 4", "notes": "Agenda", "busy": True, "organizer": True, "editable": True,
         "recurring": False, "seriesId": None, "etag": '"1"', "guests": [], "guestTotal": 0,
         "status": "confirmed"}
    e.update(kw)
    return e


class Move(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.calls = []
        self.patches = [mock.patch.object(sync, "CACHE", self.dir),
                        mock.patch.object(sync, "LOCK", os.path.join(self.dir, "lock")),
                        mock.patch.object(auth, "load_accounts", return_value=[GOOGLE, MS]),
                        mock.patch.object(auth, "hidden_calendars", return_value={}),
                        mock.patch.object(auth, "google_access", return_value="g-token"),
                        mock.patch.object(auth, "ms_access", return_value="m-token"),
                        mock.patch.object(auth, "send_json", side_effect=self.send)]
        for p in self.patches:
            p.start()
        self.write("P", GCALS, [event("P", "primary", "ev1")])
        self.write("E", MCALS, [])

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.dir)

    def write(self, name, cals, events):
        sync.write_private(os.path.join(self.dir, "state-%s.json" % name),
                           {"calendars": cals, "events": {e["uid"]: e for e in events}})

    def state(self, name):
        with open(os.path.join(self.dir, "state-%s.json" % name)) as f:
            return json.load(f)["events"]

    def send(self, method, url, tok, body, headers=None):
        self.calls.append((method, url, body))
        if "/move?" in url:
            return {"id": "ev1", "summary": "Plan", "etag": '"2"', "status": "confirmed",
                    "organizer": {"email": "me@example.com", "self": True},
                    "start": {"dateTime": "2026-10-02T14:00:00Z"}, "end": {"dateTime": "2026-10-02T15:00:00Z"}}
        if method == "POST" and "graph.microsoft.com" in url:
            return {"id": "new1", "subject": body["subject"], "isOrganizer": True, "@odata.etag": 'W/"1"',
                    "start": {"dateTime": "2026-10-02T14:00:00.0000000"},
                    "end": {"dateTime": "2026-10-02T15:00:00.0000000"},
                    "responseStatus": {"response": "organizer"}}
        return None

    def test_within_a_google_account_is_googles_move(self):
        uid = edit.move("P/primary/ev1", "P/family")
        self.assertEqual(uid, "P/family/ev1")
        self.assertEqual(len(self.calls), 1)
        method, url, _ = self.calls[0]
        self.assertEqual(method, "POST")
        self.assertIn("/calendars/primary/events/ev1/move?destination=family&sendUpdates=none", url)
        self.assertEqual(sorted(self.state("P")), ["P/family/ev1"])

    def test_to_another_account_is_a_copy_then_a_delete(self):
        guests = [{"email": "me@example.com", "organizer": True, "me": True},
                  {"email": "amy@example.com"}, {"email": "room@resource.example", "room": True}]
        self.write("P", GCALS, [event("P", "primary", "ev1", guests=guests, guestTotal=3)])
        uid = edit.move("P/primary/ev1", "E/cal")
        self.assertEqual(uid, "E/cal/new1")
        (m1, u1, b1), (m2, u2, _) = self.calls
        self.assertEqual((m1, m2), ("POST", "DELETE"))
        self.assertIn("/me/calendars/cal/events", u1)
        self.assertEqual(b1["subject"], "Plan")
        self.assertEqual(b1["location"], {"displayName": "Room 4"})
        self.assertEqual(b1["body"]["content"], "Agenda")
        self.assertEqual([x["emailAddress"]["address"] for x in b1["attendees"]], ["amy@example.com"])
        self.assertEqual(b1["start"]["dateTime"], "2026-10-02T14:00:00")
        self.assertIn("/calendars/primary/events/ev1?sendUpdates=all", u2)
        self.assertEqual(self.state("P"), {})
        self.assertIn("E/cal/new1", self.state("E"))

    def test_same_calendar_does_nothing(self):
        self.assertEqual(edit.move("P/primary/ev1", "P/primary"), "P/primary/ev1")
        self.assertEqual(self.calls, [])

    def test_refused_without_sending_anything(self):
        cases = [
            (dict(organizer=False), "only an event you organise"),
            (dict(recurring=True, seriesId="s1"), "repeating"),
            (dict(guests=[{"email": "amy@example.com"}], guestTotal=40), "guest list"),
        ]
        for fields, words in cases:
            self.write("P", GCALS, [event("P", "primary", "ev1", **fields)])
            with self.assertRaises(edit.EditError) as cm:
                edit.move("P/primary/ev1", "E/cal")
            self.assertIn(words, str(cm.exception))
        with self.assertRaises(edit.EditError):
            edit.move("P/primary/ev1", "P/holidays")   # read-only
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
