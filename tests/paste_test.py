"""The bounded paste helper (scripts/omcal/paste.py) against fake wl-paste
programs: an ordinary offer, one that never ends, one that holds the pipe
open from a forked child (as wl-paste's own `cat` can), and the helper
killed outright part way through. No real clipboard is touched."""

import os
import signal
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "omcal", "paste.py")
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

from omcal import paste  # noqa: E402

FAKES = {
    # An ordinary clipboard.
    "plain": 'printf "Team lunch"',
    # A clipboard that never stops sending.
    "endless": "exec yes 0123456789abcdef",
    # wl-paste forks a reader that keeps the pipe open and sends nothing,
    # then waits for it: the case where only a group kill ends it.
    "withhold": textwrap.dedent("""\
        sleep 600 &
        echo $! >> "$PIDS"
        echo $$ >> "$PIDS"
        wait
        """),
    # A little, then nothing more, with the pipe left open.
    "trickle": textwrap.dedent("""\
        echo $$ >> "$PIDS"
        printf "half"
        exec sleep 600
        """),
}


def alive(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split(")")[-1].split()[0] != "Z"
    except FileNotFoundError:
        return False


class PasteTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.pids = os.path.join(self.dir, "pids")
        self.env = dict(os.environ, PATH=self.dir + ":" + os.environ["PATH"], PIDS=self.pids)

    def fake(self, kind):
        path = os.path.join(self.dir, "wl-paste")
        with open(path, "w") as f:
            f.write("#!/bin/sh\n" + FAKES[kind] + "\n")
        os.chmod(path, stat.S_IRWXU)

    def readers(self):
        try:
            with open(self.pids) as f:
                return [int(line) for line in f if line.strip()]
        except FileNotFoundError:
            return []

    def run_helper(self, *args):
        start = time.monotonic()
        out = subprocess.run([sys.executable, "-B", SCRIPT, *args], env=self.env,
                             capture_output=True, timeout=10)
        return out, time.monotonic() - start

    def test_an_ordinary_paste_comes_back_whole(self):
        self.fake("plain")
        out, took = self.run_helper()
        self.assertEqual((out.returncode, out.stdout), (0, b"Team lunch"))
        self.assertLess(took, 1.0)

    def test_an_endless_offer_stops_at_the_byte_limit(self):
        self.fake("endless")
        out, took = self.run_helper()
        self.assertEqual(len(out.stdout), paste.LIMIT)
        self.assertLess(took, paste.DEADLINE + 0.5)

    def test_a_withheld_offer_ends_at_the_deadline_and_its_readers_die(self):
        self.fake("withhold")
        out, took = self.run_helper()
        self.assertEqual(out.stdout, b"")
        self.assertLess(took, paste.DEADLINE + 1.0)
        time.sleep(0.2)
        self.assertTrue(self.readers())
        self.assertEqual([p for p in self.readers() if alive(p)], [])

    def test_a_trickle_keeps_what_came_before_the_deadline(self):
        self.fake("trickle")
        out, took = self.run_helper()
        self.assertEqual(out.stdout, b"half")
        self.assertLess(took, paste.DEADLINE + 1.0)

    def test_killing_the_helper_still_ends_its_readers(self):
        # The shell can SIGKILL the helper (an unload, a reload). The deadline
        # lives in `timeout`, not in the helper, so the readers still die.
        self.fake("withhold")
        helper = subprocess.Popen([sys.executable, "-B", SCRIPT], env=self.env,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        for _ in range(50):
            if len(self.readers()) >= 2:
                break
            time.sleep(0.05)
        self.assertGreaterEqual(len(self.readers()), 2)
        helper.send_signal(signal.SIGKILL)
        helper.wait()
        helper.stdout.close()
        deadline = time.monotonic() + float(paste.BACKSTOP) + 1.5
        while time.monotonic() < deadline and any(alive(p) for p in self.readers()):
            time.sleep(0.1)
        self.assertEqual([p for p in self.readers() if alive(p)], [])

    def test_primary_selection_is_asked_for_by_flag(self):
        self.assertIn("--primary", paste.reader_command(True))
        self.assertNotIn("--primary", paste.reader_command(False))
        self.assertEqual(paste.reader_command(False)[:3], ["timeout", "--signal=KILL", paste.BACKSTOP])

    def test_no_wl_paste_gives_nothing(self):
        self.env["PATH"] = self.dir
        out, _ = self.run_helper()
        self.assertEqual(out.stdout, b"")

    def test_half_a_character_at_the_limit_is_dropped(self):
        self.assertEqual(paste.text_of("é".encode() + b"\xc3"), "é")


if __name__ == "__main__":
    unittest.main()
