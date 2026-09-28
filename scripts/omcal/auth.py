"""Accounts, the keyring, and signing in to Google and Microsoft 365.

Secrets never touch disk here. Each account's refresh token (and, for Google,
the OAuth client secret) is stored in the GNOME keyring through secret-tool,
under service=blacksheep.calendar account=<name>. The config file holds only
what is not secret: names, providers, tenant and client IDs.
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


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
    try:
        with open(ACCOUNTS) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_accounts(accounts):
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
    tmp = ACCOUNTS + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(accounts, f, indent=2)
    os.replace(tmp, ACCOUNTS)


CHOICES = os.path.join(CONFIG_DIR, "calendars.json")


def hidden_calendars():
    """{account: set of calendar ids you've chosen not to see}. Not secret."""
    try:
        with open(CHOICES) as f:
            return {k: set(v) for k, v in json.load(f).get("hidden", {}).items()}
    except (FileNotFoundError, ValueError):
        return {}


def save_hidden(hidden):
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
    tmp = CHOICES + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"hidden": {k: sorted(v) for k, v in hidden.items() if v}}, f, indent=2)
    os.replace(tmp, CHOICES)


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
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return json.load(e)
        except Exception:
            raise HttpError(urllib.parse.urlsplit(url).netloc, e.code)


def get_json(url, token):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise HttpError(urllib.parse.urlsplit(url).netloc, e.code, e.read().decode(errors="replace")[:300])


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
            raw = r.read()
            return json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as e:
        if e.code == 412:
            raise Conflict("the event was changed elsewhere; sync and try again")
        raise HttpError(urllib.parse.urlsplit(url).netloc, e.code, e.read().decode(errors="replace")[:300])


def token_error(t):
    return "%s: %s" % (t.get("error", "error"), t.get("error_description", "").splitlines()[0] if t.get("error_description") else "")


# ---------------------------------------------------------------- Google

def add_google(name, client_file):
    check_name(name)
    try:
        with open(client_file) as f:
            c = json.load(f)
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
    threading.Thread(target=srv.handle_request, daemon=True).start()
    deadline = time.time() + 300
    while "code" not in got and time.time() < deadline:
        time.sleep(0.2)
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
