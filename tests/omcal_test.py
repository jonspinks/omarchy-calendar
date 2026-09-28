"""The sync side: join links, Graph's timestamps, and de-duplication.

    python3 -B -m unittest discover -s tests -p '*_test.py'
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from omcal.model import find_join, parse_instant, utc_iso  # noqa: E402
from omcal.sync import dedupe  # noqa: E402
from omcal import files  # noqa: E402
import io  # noqa: E402
import tempfile  # noqa: E402


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


class Files(unittest.TestCase):
    """What a reviewer asked for: nothing predictable is followed, truncated or waited on."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.victim = os.path.join(self.dir, "victim")
        with open(self.victim, "w") as f:
            f.write("keep me")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir)

    def test_write_ignores_a_planted_tmp_link(self):
        # The old code wrote <name>.tmp: a link planted there was followed and truncated.
        target = os.path.join(self.dir, "state.json")
        os.symlink(self.victim, target + ".tmp")
        files.write_private(target, {"a": 1})
        self.assertEqual(open(self.victim).read(), "keep me")
        self.assertEqual(files.read_json(target, None), {"a": 1})
        self.assertEqual(os.stat(target).st_mode & 0o777, 0o600)
        self.assertFalse([n for n in os.listdir(self.dir) if n.startswith(".state.json.")])

    def test_read_refuses_links_and_fifos(self):
        link = os.path.join(self.dir, "link.json")
        os.symlink(self.victim, link)
        with self.assertRaises(files.UnsafePath):
            files.read_json(link, None)
        fifo = os.path.join(self.dir, "fifo.json")
        os.mkfifo(fifo)
        with self.assertRaises(files.UnsafePath):   # refused at once, not waited on
            files.read_json(fifo, None)
        self.assertEqual(files.read_json(os.path.join(self.dir, "missing"), "d"), "d")

    def test_read_caps_size(self):
        big = os.path.join(self.dir, "big.json")
        with open(big, "w") as f:
            f.write("[" + "1," * 2000 + "1]")
        with self.assertRaises(files.UnsafePath):
            files.read_json(big, None, limit=1000)

    def test_lock_is_not_truncated_or_followed(self):
        lock = os.path.join(self.dir, "x.lock")
        with open(lock, "w") as f:
            f.write("data")
        files.open_lock(lock).close()
        self.assertEqual(open(lock).read(), "data")
        os.unlink(lock)
        os.symlink(self.victim, lock)
        with self.assertRaises(OSError):
            files.open_lock(lock)
        self.assertEqual(open(self.victim).read(), "keep me")
        os.unlink(lock)
        os.mkfifo(lock)
        with self.assertRaises(files.UnsafePath):
            files.open_lock(lock)

    def test_private_dir_refuses_a_link(self):
        real = os.path.join(self.dir, "real")
        os.mkdir(real)
        os.symlink(real, os.path.join(self.dir, "cache"))
        with self.assertRaises(files.UnsafePath):
            files.private_dir(os.path.join(self.dir, "cache"))
        open_dir = os.path.join(self.dir, "open")
        os.mkdir(open_dir, 0o755)
        files.private_dir(open_dir)
        self.assertEqual(os.stat(open_dir).st_mode & 0o777, 0o700)

    def test_reply_is_capped(self):
        self.assertEqual(files.reply_json(io.BytesIO(b'{"ok": true}')), {"ok": True})
        self.assertIsNone(files.reply_json(io.BytesIO(b"  ")))
        with self.assertRaises(files.ReplyTooLarge):
            files.reply_json(io.BytesIO(b"x" * 5000), limit=1000)

    def test_reply_has_a_deadline(self):
        class Trickle:
            def read(self, n):
                import time
                time.sleep(0.05)
                return b" "
        with self.assertRaises(files.ReplyTooLarge):
            files.read_reply(Trickle(), limit=10 ** 9, deadline=0.2)


if __name__ == "__main__":
    unittest.main()
