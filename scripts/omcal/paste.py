"""Paste for Datebook's text fields, bounded in size and time.

Usage: python3 -B paste.py [--primary]

Prints the clipboard's text (or the primary selection's), at most LIMIT
bytes, read within DEADLINE seconds, and exits 0. Nothing on the clipboard,
no text type, or no wl-paste: prints nothing.

The fields never let Qt read the clipboard (see Typing.js): Qt's own read
has no size or time limit. Here the shell only ever receives this script's
output, and that is capped.

`wl-paste` forks `cat` to copy the offer, and a hostile clipboard owner can
keep that pipe open forever. So the reader runs under GNU `timeout` in a
session of its own: `timeout` holds the deadline and, when it passes, kills
its whole process group (`wl-paste` and `cat` with it). That does not depend
on this script still running: if the shell kills it part way through, the
readers still die at the deadline. This script also kills the group as soon
as it has what it needs, or at its own, shorter deadline.
"""

import os
import select
import signal
import subprocess
import sys
import time

LIMIT = 8192            # bytes handed back to the shell
DEADLINE = 1.5          # seconds this script waits for the offer
BACKSTOP = "2"          # seconds before `timeout` kills the readers itself
CHUNK = 4096


def reader_command(primary):
    cmd = ["timeout", "--signal=KILL", BACKSTOP, "wl-paste", "--no-newline", "--type", "text"]
    if primary:
        cmd.insert(4, "--primary")
    return cmd


def kill_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass


def read_bounded(cmd, limit=LIMIT, deadline=DEADLINE):
    """At most `limit` bytes of `cmd`'s output, within `deadline` seconds."""
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError:
        return b""
    out = bytearray()
    end = time.monotonic() + deadline
    try:
        fd = proc.stdout.fileno()
        while len(out) < limit:
            left = end - time.monotonic()
            if left <= 0:
                break
            ready, _, _ = select.select([fd], [], [], left)
            if not ready:
                break
            chunk = os.read(fd, min(CHUNK, limit - len(out)))
            if not chunk:
                break
            out += chunk
    finally:
        proc.stdout.close()
        kill_group(proc)
    return bytes(out)


def text_of(data):
    """UTF-8 text, never ending in half a character cut at the limit."""
    return data.decode("utf-8", errors="ignore")


def main(argv):
    primary = "--primary" in argv[1:]
    sys.stdout.write(text_of(read_bounded(reader_command(primary))))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
