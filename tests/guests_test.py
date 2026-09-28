"""Guest lists: read from each provider, and changed without losing anyone.

    python3 -B -m unittest discover -s tests -p '*_test.py'
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from omcal import auth, edit, google, graph  # noqa: E402
from omcal.model import GUEST_CAP, guest, guest_fields  # noqa: E402

GCAL = {"id": "primary", "editable": True, "defaultRemind": []}
MCAL = {"id": "cal", "editable": True}


def g_event(**kw):
    e = {"id": "ev1", "summary": "Plan", "etag": '"1"', "status": "confirmed",
         "start": {"dateTime": "2026-10-02T14:00:00Z"}, "end": {"dateTime": "2026-10-02T15:00:00Z"}}
    e.update(kw)
    return e


def m_event(**kw):
    e = {"id": "ev1", "subject": "Plan", "@odata.etag": 'W/"1"', "isOrganizer": False,
         "start": {"dateTime": "2026-10-02T14:00:00.0000000"}, "end": {"dateTime": "2026-10-02T15:00:00.0000000"},
         "responseStatus": {"response": "tentativelyAccepted"},
         "organizer": {"emailAddress": {"name": "Olive Organiser", "address": "olive@corp.example"}}}
    e.update(kw)
    return e


def m_att(addr, response="none", type_="required", name=""):
    return {"type": type_, "status": {"response": response, "time": "0001-01-01T00:00:00Z"},
            "emailAddress": {"name": name or addr, "address": addr}}


class ReadingGoogle(unittest.TestCase):
    def test_guests_with_answers_in_reading_order(self):
        e = g_event(organizer={"email": "olive@example.com"}, attendees=[
            {"email": "zed@example.com", "responseStatus": "declined"},
            {"email": "me@example.com", "self": True, "responseStatus": "needsAction"},
            {"email": "amy@example.com", "displayName": "Amy", "responseStatus": "accepted", "optional": True},
            {"email": "olive@example.com", "organizer": True, "responseStatus": "accepted"},
            {"email": "room@resource.example", "resource": True, "responseStatus": "accepted"},
            {"email": "bob@example.com", "responseStatus": "tentative"},
        ])
        n = google.normalise("P", GCAL, e)
        self.assertEqual([g["email"] for g in n["guests"]],
                         ["olive@example.com", "amy@example.com", "bob@example.com", "me@example.com",
                          "zed@example.com", "room@resource.example"])
        self.assertEqual(n["guestTotal"], 6)
        self.assertFalse(n["guestsHidden"])
        amy = n["guests"][1]
        self.assertEqual((amy["name"], amy["response"], amy["optional"]), ("Amy", "accepted", True))
        self.assertTrue(n["guests"][3]["me"])
        self.assertTrue(n["guests"][-1]["room"])

    def test_no_guests_is_an_empty_list(self):
        n = google.normalise("P", GCAL, g_event(organizer={"email": "me@example.com", "self": True}))
        self.assertEqual((n["guests"], n["guestTotal"]), ([], 0))

    def test_hidden_list(self):
        e = g_event(organizer={"email": "olive@example.com"}, guestsCanSeeOtherGuests=False,
                    attendees=[{"email": "me@example.com", "self": True, "responseStatus": "accepted"}])
        n = google.normalise("P", GCAL, e)
        # What's left is the organiser and you, and a note that there's more.
        self.assertEqual([g["email"] for g in n["guests"]], ["olive@example.com", "me@example.com"])
        self.assertTrue(n["guestsHidden"])

    def test_organiser_missing_from_the_list_is_added(self):
        e = g_event(organizer={"email": "olive@example.com", "displayName": "Olive"},
                    attendees=[{"email": "me@example.com", "self": True, "responseStatus": "accepted"},
                               {"email": "bob@example.com", "responseStatus": "needsAction"}])
        n = google.normalise("P", GCAL, e)
        self.assertEqual(n["guests"][0]["email"], "olive@example.com")
        self.assertTrue(n["guests"][0]["organizer"])


class ReadingGraph(unittest.TestCase):
    def test_organiser_added_and_you_found_by_address(self):
        e = m_event(attendees=[m_att("Me@Corp.example", "none"), m_att("bob@corp.example", "accepted"),
                               m_att("cat@corp.example", "declined", "optional"),
                               m_att("room1@corp.example", "accepted", "resource")])
        n = graph.normalise("W", MCAL, e, "me@corp.example")
        self.assertEqual([(g["email"], g["response"]) for g in n["guests"]],
                         [("olive@corp.example", "accepted"), ("bob@corp.example", "accepted"),
                          # Your own answer is the event's, which Graph keeps current.
                          ("Me@Corp.example", "tentative"),
                          ("cat@corp.example", "declined"), ("room1@corp.example", "accepted")])
        self.assertTrue(n["guests"][0]["organizer"])
        self.assertEqual(n["guests"][0]["name"], "Olive Organiser")
        self.assertTrue(n["guests"][2]["me"])
        self.assertTrue(n["guests"][3]["optional"])
        self.assertTrue(n["guests"][4]["room"])

    def test_organisers_own_event(self):
        e = m_event(isOrganizer=True, organizer={"emailAddress": {"name": "Me", "address": "me@corp.example"}},
                    attendees=[m_att("bob@corp.example", "none")])
        n = graph.normalise("W", MCAL, e, "me@corp.example")
        self.assertEqual([(g["email"], g["me"], g["organizer"]) for g in n["guests"]],
                         [("me@corp.example", True, True), ("bob@corp.example", False, False)])
        self.assertEqual(n["guests"][1]["response"], "needsAction")

    def test_no_attendees_no_list(self):
        n = graph.normalise("W", MCAL, m_event(isOrganizer=True, attendees=[]), "me@corp.example")
        self.assertEqual(n["guests"], [])

    def test_hidden_list(self):
        n = graph.normalise("W", MCAL, m_event(hideAttendees=True, attendees=[m_att("me@corp.example")]),
                            "me@corp.example")
        self.assertTrue(n["guestsHidden"])


class Fields(unittest.TestCase):
    def test_capped_but_counted(self):
        many = [guest("g%03d@example.com" % i) for i in range(GUEST_CAP + 20)]
        f = guest_fields(many)
        self.assertEqual((len(f["guests"]), f["guestTotal"]), (GUEST_CAP, GUEST_CAP + 20))

    def test_unknown_answer_is_no_answer_yet(self):
        self.assertEqual(guest("a@b.co", response="organizer")["response"], "needsAction")


class Merging(unittest.TestCase):
    G = [{"email": "olive@example.com", "organizer": True, "responseStatus": "accepted"},
         {"email": "me@example.com", "self": True, "responseStatus": "accepted"},
         {"email": "bob@example.com", "responseStatus": "declined", "comment": "away"}]

    def test_google_keeps_answers_and_adds(self):
        out = edit.merge_guests("google", self.G, ["new@example.com"], ["bob@example.com"],
                                "me@example.com", "olive@example.com")
        self.assertEqual(out, self.G[:2] + [{"email": "new@example.com"}])

    def test_graph_sends_address_and_type_only(self):
        out = edit.merge_guests("microsoft", [m_att("bob@corp.example", "accepted", "optional"),
                                              m_att("cat@corp.example")],
                                ["new@corp.example"], ["cat@corp.example"], "me@corp.example", "me@corp.example")
        self.assertEqual(out, [{"emailAddress": {"name": "bob@corp.example", "address": "bob@corp.example"},
                                "type": "optional"},
                               {"emailAddress": {"address": "new@corp.example"}, "type": "required"}])

    def test_addresses_match_whatever_their_case(self):
        out = edit.merge_guests("microsoft", [m_att("Bob@Corp.example")], [], ["bob@corp.example"])
        self.assertEqual(out, [])

    def test_refusals(self):
        cases = [
            (["bob@example.com"], [], "already invited"),
            (["olive@example.com"], [], "already invited"),
            ([], ["nobody@example.com"], "isn't on the guest list"),
            ([], ["olive@example.com"], "organiser"),
            ([], ["me@example.com"], "yourself"),
        ]
        for invite, uninvite, says in cases:
            with self.assertRaises(edit.EditError) as c:
                edit.merge_guests("google", self.G, invite, uninvite, "me@example.com", "olive@example.com")
            self.assertIn(says, str(c.exception))

    def test_remove_then_add_back_is_allowed(self):
        out = edit.merge_guests("google", self.G, ["bob@example.com"], ["bob@example.com"],
                                "me@example.com", "olive@example.com")
        self.assertEqual(out[-1], {"email": "bob@example.com"})

    def test_addresses_are_checked(self):
        self.assertEqual(edit._addresses([" A@B.co ", "a@b.co"]), ["a@b.co"])
        for bad in ["nope", "a@b", "a b@c.co", "a@b.co,c@d.co", "<a@b.co>"]:
            with self.assertRaises(edit.EditError):
                edit._addresses([bad])


class Provider:
    """A fake provider: GET returns the event as it stands, PATCH applies the
    body if the If-Match etag is current, else answers 412."""

    def __init__(self, kind, event, etag_key):
        self.kind, self.event, self.key = kind, dict(event), etag_key
        self.version, self.writes, self.reads = 1, [], 0
        self.before_write = None

    def etag(self):
        return 'W/"%d"' % self.version if self.kind == "microsoft" else '"%d"' % self.version

    def get_json(self, url, tok):
        self.reads += 1
        return dict(self.event, **{self.key: self.etag()})

    def send_json(self, method, url, tok, body=None, headers=None):
        if self.before_write:
            self.before_write(self)
            self.before_write = None
        if (headers or {}).get("If-Match") not in (None, self.etag()):
            raise auth.Conflict("the event was changed elsewhere; sync and try again")
        self.writes.append((method, url, body, headers))
        self.event.update(body)
        self.version += 1
        return dict(self.event, **{self.key: self.etag()})


class Writing(unittest.TestCase):
    def setUp(self):
        self.saved = []
        patches = [mock.patch.object(edit, "token", lambda a: "tok"),
                   mock.patch.object(edit, "_add", lambda acc, ev: self.saved.append(("add", ev))),
                   mock.patch.object(edit, "_apply", lambda acc, match, f: self.saved.append(("apply", f)))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def use(self, provider, local):
        acc = {"name": "A", "provider": provider.kind, "email": "me@example.com"}
        st = {"calendars": {"c": dict(GCAL if provider.kind == "google" else MCAL, id="c")},
              "events": {local["uid"]: local}}
        for target, fn in ((edit, "locate"),):
            p = mock.patch.object(target, fn, lambda uid: (acc, "/dev/null", st, local, "ev1"))
            p.start()
            self.addCleanup(p.stop)
        for fn in ("get_json", "send_json"):
            p = mock.patch.object(auth, fn, getattr(provider, fn))
            p.start()
            self.addCleanup(p.stop)

    def google(self, **local):
        p = Provider("google", g_event(organizer={"email": "me@example.com", "self": True}, attendees=[
            {"email": "me@example.com", "self": True, "organizer": True, "responseStatus": "accepted"},
            {"email": "bob@example.com", "responseStatus": "accepted"}]), "etag")
        self.use(p, dict({"uid": "A/c/ev1", "calendar": "c", "editable": True, "etag": '"1"',
                          "seriesId": None, "allDay": False}, **local))
        return p

    def test_google_add_and_remove_in_one_write(self):
        p = self.google()
        edit.update("A/c/ev1", invite=["New@Example.com"], uninvite=["bob@example.com"])
        method, url, body, headers = p.writes[0]
        self.assertEqual(method, "PATCH")
        self.assertTrue(url.endswith("?sendUpdates=all"))
        self.assertEqual([x["email"] for x in body["attendees"]], ["me@example.com", "new@example.com"])
        self.assertEqual(headers["If-Match"], '"1"')
        kind, ev = self.saved[0]
        self.assertEqual(kind, "add")
        self.assertEqual([g["email"] for g in ev["guests"]], ["me@example.com", "new@example.com"])

    def test_someone_added_meanwhile_is_kept(self):
        p = self.google()

        def someone_else(prov):
            prov.event["attendees"] = prov.event["attendees"] + [{"email": "late@example.com"}]
            prov.version += 1
        p.before_write = someone_else
        edit.update("A/c/ev1", invite=["new@example.com"])
        self.assertEqual(p.reads, 2)
        self.assertEqual([x["email"] for x in p.writes[0][2]["attendees"]],
                         ["me@example.com", "bob@example.com", "late@example.com", "new@example.com"])

    def test_stale_copy_with_other_changes_is_a_conflict(self):
        p = self.google(etag='"0"')
        with self.assertRaises(auth.Conflict):
            edit.update("A/c/ev1", title="Renamed", invite=["new@example.com"])
        self.assertEqual(p.writes, [])

    def test_stale_copy_guests_only_goes_ahead(self):
        p = self.google(etag='"0"')
        edit.update("A/c/ev1", invite=["new@example.com"])
        self.assertEqual(len(p.writes), 1)

    def test_title_and_guests_together(self):
        p = self.google()
        edit.update("A/c/ev1", title=" Renamed ", invite=["new@example.com"])
        body = p.writes[0][2]
        self.assertEqual(body["summary"], "Renamed")
        self.assertIn({"email": "new@example.com"}, body["attendees"])

    def test_series_updates_every_occurrence_here(self):
        p = self.google(seriesId="ser")
        edit.update("A/c/ev1", uninvite=["bob@example.com"], series=True)
        self.assertIn("/events/ser", p.writes[0][1])
        kind, fields = self.saved[0]
        self.assertEqual(kind, "apply")
        self.assertEqual([g["email"] for g in fields["guests"]], [])   # only you left: no list

    def test_graph(self):
        p = Provider("microsoft", m_event(isOrganizer=True,
                                          organizer={"emailAddress": {"address": "me@example.com"}},
                                          attendees=[m_att("bob@example.com", "accepted")]), "@odata.etag")
        self.use(p, {"uid": "A/c/ev1", "calendar": "c", "editable": True, "etag": 'W/"1"',
                     "seriesId": None, "allDay": False})
        edit.update("A/c/ev1", invite=["cat@example.com"])
        method, url, body, headers = p.writes[0]
        self.assertEqual(body["attendees"][-1], {"emailAddress": {"address": "cat@example.com"}, "type": "required"})
        self.assertEqual(headers["If-Match"], 'W/"1"')
        self.assertEqual(headers["Prefer"], 'outlook.timezone="UTC"')
        guests = self.saved[0][1]["guests"]
        self.assertEqual([(g["email"], g["organizer"]) for g in guests],
                         [("me@example.com", True), ("bob@example.com", False), ("cat@example.com", False)])

    def test_not_yours_is_refused_before_anything_is_sent(self):
        p = self.google(editable=False)
        with self.assertRaises(edit.EditError):
            edit.update("A/c/ev1", invite=["new@example.com"])
        self.assertEqual((p.reads, p.writes), (0, []))


if __name__ == "__main__":
    unittest.main()
