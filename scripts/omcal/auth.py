"""Accounts, the keyring, and signing in to Google, Microsoft 365 and CalDAV.

Secrets never touch disk here. Each account's refresh token (and, for Google,
the OAuth client secret; for CalDAV, the app password) is stored in the GNOME
keyring through secret-tool, under service=blacksheep.calendar account=<name>.
The config file holds only what is not secret: names, providers, tenant and
client IDs, CalDAV addresses and user names.
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from . import files


class AuthError(Exception):
    """A saved sign-in no longer works: the account needs adding again."""


class HttpError(RuntimeError):
    """An API answered with an HTTP error; .code is the status."""

    def __init__(self, host, code, detail=""):
        super().__init__("%s answered HTTP %s%s" % (host, code, ": " + detail if detail else ""))
        self.code = code


APP = "blacksheep.calendar"
CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), APP)
ACCOUNTS = os.path.join(CONFIG_DIR, "accounts.json")

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPES = "openid email https://www.googleapis.com/auth/calendar"
MS_SCOPES = "offline_access openid email User.Read Calendars.ReadWrite"


def die(msg):
    print("calendar-ctl: " + msg, file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- config

def load_accounts():
    return files.read_json(ACCOUNTS, [])


def save_accounts(accounts):
    files.write_private(ACCOUNTS, accounts, indent=2)


CHOICES = os.path.join(CONFIG_DIR, "calendars.json")


def hidden_calendars():
    """{account: set of calendar ids you've chosen not to see}. Not secret."""
    data = files.read_json(CHOICES, {})
    return {k: set(v) for k, v in (data.get("hidden", {}) if isinstance(data, dict) else {}).items()}


def save_hidden(hidden):
    files.write_private(CHOICES, {"hidden": {k: sorted(v) for k, v in hidden.items() if v}}, indent=2)


def account(name):
    for a in load_accounts():
        if a["name"] == name:
            return a
    die("no account called %r (calendar-ctl list)" % name)


def check_name(name):
    if not name or not all(c.isalnum() or c in "-_." for c in name):
        die("an account name is letters, digits, '-', '_' or '.'")


# ---------------------------------------------------------------- keyring

def secret_store(name, data):
    p = subprocess.run(
        ["secret-tool", "store", "--label", "Omarchy Calendar: " + name,
         "service", APP, "account", name],
        input=json.dumps(data), text=True, capture_output=True)
    if p.returncode != 0:
        # Raised, not fatal: the sync saves Microsoft's rotated tokens with nobody
        # at the keyboard, and a locked keyring must fail that account alone.
        raise AuthError("could not save to the keyring: " + (p.stderr.strip() or "secret-tool failed"))


def secret_load(name):
    p = subprocess.run(["secret-tool", "lookup", "service", APP, "account", name],
                       text=True, capture_output=True)
    if p.returncode != 0 or not p.stdout:
        raise AuthError("no saved sign-in for %r" % name)
    return json.loads(p.stdout)


def secret_clear(name):
    subprocess.run(["secret-tool", "clear", "service", APP, "account", name],
                   capture_output=True)


# ------------------------------------------------------------------ HTTP

def save_account(entry):
    accounts = [a for a in load_accounts() if a["name"] != entry["name"]]
    accounts.append(entry)
    save_accounts(accounts)


def post_form(url, fields):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return files.reply_json(r)
    except urllib.error.HTTPError as e:
        # A token endpoint says why in a small JSON error body.
        try:
            return files.reply_json(e, limit=64 * 1024)
        except Exception:
            raise HttpError(urllib.parse.urlsplit(url).netloc, e.code)


def get_json(url, token):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return files.reply_json(r)
    except urllib.error.HTTPError as e:
        raise HttpError(urllib.parse.urlsplit(url).netloc, e.code, error_text(e))


class Conflict(RuntimeError):
    """The event changed elsewhere since it was read (HTTP 412): nothing was written."""


def send_json(method, url, token, body=None, headers=None):
    """A write to an API. Returns the reply's JSON, or None for an empty reply."""
    h = {"Authorization": "Bearer " + token}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return files.reply_json(r)
    except urllib.error.HTTPError as e:
        if e.code == 412:
            raise Conflict("the event was changed elsewhere; sync and try again")
        raise HttpError(urllib.parse.urlsplit(url).netloc, e.code, error_text(e))


def error_text(e):
    """The start of an error reply, for the message: read no more than that."""
    try:
        return e.read(4096).decode(errors="replace")[:300]
    except Exception:
        return ""


def token_error(t):
    return "%s: %s" % (t.get("error", "error"), t.get("error_description", "").splitlines()[0] if t.get("error_description") else "")


# ---------------------------------------------------------------- Google

def add_google(name, client_file):
    check_name(name)
    try:
        # The file you downloaded, so it may be a link; it is still only ever
        # a few hundred bytes, and read no further than that allows.
        with open(client_file, "rb") as f:
            raw = f.read(64 * 1024 + 1)
        if len(raw) > 64 * 1024:
            die("%s is far too large to be a Google client file" % client_file)
        c = json.loads(raw)
    except (OSError, ValueError) as e:
        die("cannot read %s: %s" % (client_file, e))
    c = c.get("installed") or c.get("web") or {}
    cid, csecret = c.get("client_id"), c.get("client_secret")
    if not cid or not csecret:
        die("that is not a Google OAuth client file (want a Desktop app client)")

    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    got = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        timeout = 10  # a connection that sends nothing is dropped, not waited on

        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            if q.get("state", [""])[0] != state:
                self.send_response(400); self.end_headers(); return
            got["code"] = q.get("code", [""])[0]
            got["error"] = q.get("error", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<p>Signed in. You can close this tab and go back to the terminal.</p>".encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    redirect = "http://127.0.0.1:%d/" % srv.server_port
    url = GOOGLE_AUTH + "?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code",
        "scope": GOOGLE_SCOPES, "access_type": "offline", "prompt": "consent",
        "code_challenge": challenge, "code_challenge_method": "S256", "state": state})
    print("Opening your browser to sign in to Google. If it doesn't open, visit:\n\n  %s\n" % url)
    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Serve until the real redirect arrives: a stray request (a favicon, or
    # another local account poking the port) gets a 400 and doesn't end it.
    srv.timeout = 1
    deadline = time.time() + 300
    while "code" not in got and time.time() < deadline:
        srv.handle_request()
    srv.server_close()
    if got.get("error") or not got.get("code"):
        die("Google sign-in did not finish: %s" % (got.get("error") or "timed out"))

    t = post_form(GOOGLE_TOKEN, {
        "client_id": cid, "client_secret": csecret, "code": got["code"],
        "code_verifier": verifier, "redirect_uri": redirect, "grant_type": "authorization_code"})
    if "refresh_token" not in t:
        die("Google gave no refresh token (%s)" % token_error(t))
    secret_store(name, {"refresh_token": t["refresh_token"], "client_secret": csecret})
    who = get_json("https://openidconnect.googleapis.com/v1/userinfo", t["access_token"]).get("email", "")
    save_account({"name": name, "provider": "google", "clientId": cid, "email": who})
    print("Added %s (%s)." % (name, who))


def google_access(a):
    s = secret_load(a["name"])
    t = post_form(GOOGLE_TOKEN, {"client_id": a["clientId"], "client_secret": s["client_secret"],
                                 "refresh_token": s["refresh_token"], "grant_type": "refresh_token"})
    if "access_token" not in t:
        raise AuthError("Google refused the saved sign-in (%s)" % token_error(t))
    return t["access_token"]


# ------------------------------------------------------------- Microsoft

def ms_base(tenant):
    return "https://login.microsoftonline.com/%s/oauth2/v2.0" % urllib.parse.quote(tenant, safe="")


def add_microsoft(name, tenant, client_id):
    check_name(name)
    d = post_form(ms_base(tenant) + "/devicecode", {"client_id": client_id, "scope": MS_SCOPES})
    if "device_code" not in d:
        die("Microsoft refused to start sign-in (%s)" % token_error(d))
    print(d.get("message") or "Visit %s and enter %s" % (d["verification_uri"], d["user_code"]))
    interval = int(d.get("interval", 5))
    deadline = time.time() + int(d.get("expires_in", 900))
    while time.time() < deadline:
        time.sleep(interval)
        t = post_form(ms_base(tenant) + "/token", {
            "client_id": client_id, "device_code": d["device_code"],
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
        if "access_token" in t:
            break
        err = t.get("error")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        die("Microsoft sign-in failed (%s)" % token_error(t))
    else:
        die("the sign-in code expired; run the command again")
    if "refresh_token" not in t:
        die("Microsoft gave no refresh token: is offline_access granted?")
    secret_store(name, {"refresh_token": t["refresh_token"]})
    me = get_json("https://graph.microsoft.com/v1.0/me?$select=userPrincipalName", t["access_token"])
    save_account({"name": name, "provider": "microsoft", "tenant": tenant, "clientId": client_id,
                  "email": me.get("userPrincipalName", "")})
    print("Added %s (%s)." % (name, me.get("userPrincipalName", "")))


def ms_access(a):
    s = secret_load(a["name"])
    t = post_form(ms_base(a["tenant"]) + "/token", {
        "client_id": a["clientId"], "refresh_token": s["refresh_token"],
        "grant_type": "refresh_token", "scope": MS_SCOPES})
    if "access_token" not in t:
        raise AuthError("Microsoft refused the saved sign-in (%s)" % token_error(t))
    # Microsoft rotates refresh tokens: keep the newest one.
    if t.get("refresh_token") and t["refresh_token"] != s["refresh_token"]:
        s["refresh_token"] = t["refresh_token"]
        secret_store(a["name"], s)
    return t["access_token"]


# ---------------------------------------------------------------- CalDAV

def add_fastmail(name, email):
    """Fastmail: the calendar home is known from the address alone."""
    from .caldav import fastmail_home
    if "@" not in email:
        die("that doesn't look like a Fastmail address")
    add_caldav(name, fastmail_home(email), email, what="Fastmail")


def add_caldav(name, url, user, what="the server"):
    """Any CalDAV server, signed in with a user name and an (app) password.

    The password is asked for without echoing it, or read from stdin when
    that isn't a terminal (so a password manager can pipe it in), never taken
    from the command line (where ps and the shell history would see it), and
    checked against the server before anything is saved.
    """
    import getpass
    from . import caldav
    check_name(name)
    if not url.endswith("/"):
        url += "/"
    try:
        caldav.check_url(url)
    except AuthError as e:
        die(str(e))
    interactive = sys.stdin.isatty()
    if what == "Fastmail" and interactive:
        print("Make an app password for this at Fastmail: Settings > Privacy & Security >\n"
              "Manage app passwords > New app password, with access to Calendars (CalDAV).\n")
    password = (getpass.getpass("App password for %s: " % user) if interactive
                else sys.stdin.readline().rstrip("\r\n"))
    if not password:
        die("no password given; nothing saved")
    try:
        found = caldav.calendars(caldav.Session(url, user, password))
    except AuthError:
        die("%s refused that password. Check the user name (%s), and that the app\n"
            "password has CalDAV access." % (what, user))
    except HttpError as e:
        die("%s answered, but not as a CalDAV calendar home: %s" % (what, e))
    except (urllib.error.URLError, OSError) as e:
        die("couldn't reach %s: %s" % (url, getattr(e, "reason", e)))
    secret_store(name, {"password": password})
    save_account({"name": name, "provider": "caldav", "url": url, "user": user,
                  "email": user if "@" in user else ""})
    print("Added %s (%s): %d calendar%s." % (name, user, len(found), "" if len(found) == 1 else "s"))
