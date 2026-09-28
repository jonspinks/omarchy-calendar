"""Every file this tool writes, reads back, or locks, and every provider reply.

Nothing here trusts a path to be what its name says:

- Directories are created 0700 and must be real directories owned by this
  account (never a symlink); a group- or world-readable one is tightened.
- Writes go to a fresh private file made exclusively (mkstemp: O_EXCL, 0600)
  in the destination directory, are flushed to disk, then renamed over the
  target. No predictable temporary name is ever opened, so nothing planted at
  one can be followed or truncated.
- Reads open with O_NOFOLLOW and O_NONBLOCK, accept only a regular file, and
  stop at a size cap, so a symlink, FIFO or huge file can't hang or exhaust
  the sync.
- The lockfile is opened without truncating (O_RDWR | O_CREAT, never O_TRUNC)
  and without following a link, and must be a regular file owned by us.
- Provider replies are read to a byte cap, within an overall deadline, before
  any JSON parsing.
"""

import json
import os
import stat
import tempfile
import time

# Our own files are small: an account list, calendar choices, a few months of
# events. 64 MB is far past any real one and still safe to hold in memory.
MAX_FILE = 64 * 1024 * 1024
# One API reply: a page of up to 250 events (Google) or 100 (Graph), bodies
# included. Real pages are well under 5 MB.
MAX_REPLY = 32 * 1024 * 1024
REPLY_DEADLINE = 90  # seconds for a whole reply, however slowly it trickles


class UnsafePath(OSError):
    """A path that isn't the plain, private file or directory we expect."""


def private_dir(path):
    """Make path a 0700 directory of ours, or refuse; returns path."""
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        pass
    except FileNotFoundError:
        private_dir(os.path.dirname(path))
        return private_dir(path)
    st = os.lstat(path)
    if not stat.S_ISDIR(st.st_mode):
        raise UnsafePath("%s is not a plain directory (a symlink or a file?)" % path)
    if st.st_uid != os.getuid():
        raise UnsafePath("%s belongs to another account" % path)
    if st.st_mode & 0o077:
        os.chmod(path, 0o700)
    return path


def write_private(path, data, indent=None):
    """Write data as JSON to path, atomically, readable only by us."""
    d = private_dir(os.path.dirname(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix="." + os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=indent, separators=None if indent else (",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def read_json(path, default, limit=MAX_FILE):
    """Our own JSON file, or default if it's missing or unreadable as JSON.

    A path that is a symlink, a FIFO or anything but a regular file raises
    UnsafePath instead of being followed or waited on.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except FileNotFoundError:
        return default
    except OSError as e:
        if e.errno == 40:  # ELOOP: the final component is a symlink
            raise UnsafePath("%s is a symlink" % path)
        raise
    with os.fdopen(fd, "rb") as f:
        st = os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode):
            raise UnsafePath("%s is not a regular file" % path)
        raw = f.read(limit + 1)
    if len(raw) > limit:
        raise UnsafePath("%s is larger than %d bytes" % (path, limit))
    try:
        return json.loads(raw)
    except ValueError:
        return default


def open_lock(path):
    """The lockfile, opened for flock: never truncated, never a link or FIFO."""
    private_dir(os.path.dirname(path))
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, 0o600)
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
        os.close(fd)
        raise UnsafePath("%s is not a regular file of ours" % path)
    return os.fdopen(fd, "r+b", buffering=0)


def read_reply(resp, limit=MAX_REPLY, deadline=REPLY_DEADLINE):
    """A provider's reply body, capped in size and in total time."""
    end = time.monotonic() + deadline
    chunks, size = [], 0
    while True:
        if time.monotonic() > end:
            raise ReplyTooLarge("the reply took longer than %d s" % deadline)
        chunk = resp.read(min(65536, limit + 1 - size))
        if not chunk:
            return b"".join(chunks)
        size += len(chunk)
        if size > limit:
            raise ReplyTooLarge("the reply was larger than %d bytes" % limit)
        chunks.append(chunk)


def reply_json(resp, limit=MAX_REPLY):
    raw = read_reply(resp, limit)
    return json.loads(raw) if raw.strip() else None


class ReplyTooLarge(OSError):
    """A reply past the size or time cap: treated like a network failure."""
