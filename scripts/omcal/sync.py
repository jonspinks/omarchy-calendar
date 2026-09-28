"""Keep a private local copy of every account's events, and one file for the widget.

    python3 -m omcal.sync [--full] [--quiet]

Each account keeps its own state file, and each calendar in it its own cursor:
a Graph deltaLink, or the time of the last Google fetch. A pass fetches only
what changed, and a full refresh runs when the window moves on to a new day,
when a cursor has expired, or every six hours for Google. An account that
fails (signed out, keyring locked, offline) keeps its last good events and
reports why, and never stops the other accounts syncing.

Files, all 0600 in a 0700 directory under $XDG_CACHE_HOME/blacksheep.calendar:
    state-<account>.json   calendars, cursors and events for one account
    events.json            what the widget reads: accounts, calendars, events
"""

import contextlib
import fcntl
import json
import os
import sys
import time
import urllib.error
from datetime import datetime, timedelta, timezone

from . import auth, files, google, graph
from .model import sort_key

APP = "blacksheep.calendar"
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), APP)
RUNTIME = os.environ.get("XDG_RUNTIME_DIR") or CACHE
DAYS_BACK, DAYS_AHEAD = 35, 120
GOOGLE_FULL_EVERY = 6 * 3600


# The private write, read and lock helpers live in files.py (see there).
write_private = files.write_private
read_json = files.read_json
LOCK = os.path.join(RUNTIME, APP + ".lock")


def window_now():
    day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return day.strftime("%Y-%m-%d"), ((day - timedelta(days=DAYS_BACK)).strftime(fmt),
                                      (day + timedelta(days=DAYS_AHEAD)).strftime(fmt))


def sync_account(a, full, log):
    path = os.path.join(CACHE, "state-%s.json" % a["name"])
    st = read_json(path, {"calendars": {}, "events": {}})
    day, window = window_now()
    moved = st.get("windowDay") != day
    now = time.time()
    status, error = "ok", ""
    try:
        if a["provider"] == "google":
            tok, prov = auth.google_access(a), google
        else:
            tok, prov = auth.ms_access(a), graph
        # Hidden calendars are not fetched at all; their cached events go too,
        # so a shown-again calendar starts with a full fetch.
        hidden = auth.hidden_calendars().get(a["name"], set())
        listed = prov.calendars(tok)
        st["known"] = [dict(c, shown=c["id"] not in hidden) for c in listed]
        cals = [c for c in listed if c["id"] not in hidden]
        keep = {c["id"] for c in cals}
        # A calendar that was removed or hidden takes its events with it.
        for cid in list(st["calendars"]):
            if cid not in keep:
                del st["calendars"][cid]
        st["events"] = {u: e for u, e in st["events"].items() if e["calendar"] in keep}
        for cal in cals:
            prev = st["calendars"].get(cal["id"], {})
            cursor = prev.get("cursor")
            stale = a["provider"] == "google" and now - prev.get("fullAt", 0) > GOOGLE_FULL_EVERY
            whole = full or moved or not cursor or stale
            try:
                events, removed, cursor = _fetch(a, prov, tok, cal, window, None if whole else cursor)
            except (graph.DeltaExpired, auth.HttpError) as e:
                if whole or (isinstance(e, auth.HttpError) and e.code != 410):
                    raise
                whole = True
                events, removed, cursor = _fetch(a, prov, tok, cal, window, None)
            if whole:
                st["events"] = {u: e for u, e in st["events"].items() if e["calendar"] != cal["id"]}
            for u in removed:
                st["events"].pop(u, None)
            for e in events:
                st["events"][e["uid"]] = e
            st["calendars"][cal["id"]] = dict(cal, cursor=cursor,
                                              fullAt=now if whole else prev.get("fullAt", now))
            log("  %s / %s: %s, %d changed, %d removed" % (a["name"], cal["name"] or cal["id"],
                "full" if whole else "delta", len(events), len(removed)))
        st["windowDay"], st["window"] = day, window
        st["lastSync"] = now
    except auth.AuthError as e:
        status, error = "signin", str(e)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        status, error = "offline", str(getattr(e, "reason", e))
    except auth.HttpError as e:
        status, error = "error", str(e)
    st["status"], st["error"] = status, error
    write_private(path, st)
    return st


def _fetch(a, prov, tok, cal, window, cursor):
    if prov is google:
        events, removed, at = google.fetch(a["name"], tok, cal, window, cursor)
        return events, removed, google.since(at)
    return graph.fetch(a["name"], tok, cal, window, cursor)


def publish(accounts, states):
    out = {"schema": 1, "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "window": window_now()[1], "accounts": [], "calendars": [], "events": []}
    for a in accounts:
        st = states[a["name"]]
        out["accounts"].append({"name": a["name"], "provider": a["provider"], "email": a.get("email", ""),
                                "status": st.get("status", "ok"), "error": st.get("error", ""),
                                "lastSync": st.get("lastSync")})
        # Every calendar the account has, shown or not, so the widget can offer
        # the same choice as calendar-ctl hide/show.
        for c in st.get("known", []):
            out["calendars"].append({"account": a["name"], "id": c["id"], "name": c.get("name", ""),
                                     "color": c.get("color", ""), "primary": c.get("primary", False),
                                     "editable": c.get("editable", False), "shown": c.get("shown", True)})
        out["events"].extend(e for e in st.get("events", {}).values() if e["status"] != "cancelled")
    out["events"] = dedupe(out["events"], out["calendars"])
    out["events"].sort(key=sort_key)
    write_private(os.path.join(CACHE, "events.json"), out)
    return out


def dedupe(events, calendars):
    """One copy of an event that appears in several calendars.

    Subscribed calendars mirror others (a read-only copy of a calendar that is
    also shared in full), and every account brings its own holiday calendar, so
    the same event can arrive many times. The copy kept is the one that can be
    edited, then the one on a primary calendar; the rest are listed in alsoIn.
    The state files keep every copy: this only shapes what is displayed.
    """
    cals = {(c["account"], c["id"]): c for c in calendars}

    def rank(e):
        c = cals.get((e["account"], e["calendar"]), {})
        return (not e["editable"], not c.get("primary", False), e["account"], c.get("name", ""))

    groups = {}
    for e in events:
        groups.setdefault((e["title"].strip().lower(), e["start"], e["end"], e["allDay"]), []).append(e)
    out = []
    for group in groups.values():
        group.sort(key=rank)
        keep = dict(group[0])
        keep["alsoIn"] = ["%s: %s" % (e["account"], cals.get((e["account"], e["calendar"]), {}).get("name", ""))
                          for e in group[1:]]
        out.append(keep)
    return out


@contextlib.contextmanager
def locked():
    """Wait for any running sync, and hold the lock meanwhile."""
    with files.open_lock(LOCK) as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def republish():
    """events.json again from the state files as they are, without fetching."""
    accounts = auth.load_accounts()
    states = {a["name"]: read_json(os.path.join(CACHE, "state-%s.json" % a["name"]), {}) for a in accounts}
    return publish(accounts, states)


def main(argv):
    full = "--full" in argv
    quiet = "--quiet" in argv
    log = (lambda *_: None) if quiet else print
    lock = files.open_lock(LOCK)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("another sync is running")
        return 0
    accounts = auth.load_accounts()
    states = {a["name"]: sync_account(a, full, log) for a in accounts}
    out = publish(accounts, states)
    for acc in out["accounts"]:
        log("%-12s %-8s %s" % (acc["name"], acc["status"], acc["error"]))
    log("%d events from %d calendars" % (len(out["events"]), len(out["calendars"])))
    return 0 if all(a["status"] == "ok" for a in out["accounts"]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
