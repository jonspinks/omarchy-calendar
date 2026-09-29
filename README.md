# Datebook — Google Calendar, Microsoft 365 and Fastmail in Omarchy's clock

Click the clock and your actual week is there: every Google, Microsoft 365
and Fastmail calendar you have, in one place, with a Join button when a meeting's about to
start.

![Datebook: your week, what's next, and a reminder you can join from](preview.png)

## What you get

Omarchy's clock opens a lovely month grid, but none of your appointments are
in it. So you keep a browser tab open for Google Calendar, another for
Outlook, and still miss the 2pm because neither one told you. This plugin
replaces the clock with a real calendar that knows about all of them.

**Everything in one view.** Sign in to a Google account and as many Microsoft
365 accounts as you have (work, a client's tenant, your own business), plus
Fastmail or any other CalDAV server, and every calendar in them shows up
together, each in its own colour. Tick the
ones you care about and hide the rest.

![The month, with every calendar in it and what's next on the left](screenshots/1-month.png)

**Day, week, working week, month and year.** Switch with the buttons or
keys 1 to 5. The week shows meetings side by side when they overlap, and a
line for right now.

![A week, with the next meeting and its Join button in the corner](screenshots/2-week.png)

**It's two-way** (for Google and Microsoft; Fastmail and CalDAV are
read-only for now). Answer invitations with Accept, Maybe or Decline, and the
organiser gets your reply. Create events (with guests if you like), move
them, rename them, set them busy or free, delete them. Recurring meetings
work too: answer or rename the whole series, or just this one. If someone
changed the event since you last synced, it tells you instead of
overwriting their change.

**See who's coming.** Open any meeting and the guest list is there: who
said yes, maybe or no, and who hasn't answered yet, with the organiser
first. On your own meetings, add people or take them off right there; they
get the invitation or the cancellation when you save.

![An invitation, answered from the calendar](screenshots/3-invitation.png)

**Reminders you can join from.** A few minutes before a meeting, a
notification pops up. Click it and you're in the Teams, Zoom, Meet or Webex
call. Busy? Snooze it for five minutes from the calendar.

![A reminder: click it to join](screenshots/5-reminder.png)

**Still Omarchy's clock when you want it.** One button folds it back to
Omarchy's own month, with just the day's appointments under it. One more
brings the full calendar back.

![Compact: Omarchy's month, and today's appointments](screenshots/4-compact.png)

**Private.** It talks straight to Google, Microsoft and Fastmail from your machine.
There's no server in the middle, your sign-ins live in the system keyring,
and your events stay in your own cache. See [PRIVACY.md](PRIVACY.md).

**Works with** Google Calendar (personal or Workspace), Microsoft 365 work
or school accounts, Fastmail, and other CalDAV servers. Personal Outlook.com
accounts aren't supported yet. You register your own (free) Google and
Microsoft app to sign in with: it takes about ten minutes, once, and the
steps are below. Fastmail needs only an app password.

## Install

```bash
omarchy plugin add https://github.com/jonspinks/omarchy-calendar
# Put it where the clock is, then take the clock off the bar.
omarchy plugin enable blacksheep.calendar --before omarchy.clock
omarchy plugin disable omarchy.clock
```

If the clock was your bar's centre anchor (Omarchy's default), make the
calendar the anchor instead, so the centre of the bar stays centred:

```bash
t=$(mktemp ~/.config/omarchy/shell.json.XXXXXX) \
  && jq '.bar.centerAnchor = "blacksheep.calendar"' ~/.config/omarchy/shell.json > "$t" \
  && mv "$t" ~/.config/omarchy/shell.json
```

Then sign in to your accounts (next section). Until you do, it's the clock
you had, with an empty calendar.

## Sign in

Everything goes through `calendar-ctl`, in the plugin's `scripts/` folder:

```bash
C=~/.config/omarchy/plugins/blacksheep.calendar/scripts/calendar-ctl
$C add-google Personal ~/Downloads/client_secret_*.json
$C add-microsoft Work --tenant <tenant-id> --client-id <app-id>
$C add-microsoft Client --tenant <tenant-id> --client-id <app-id>
$C add-fastmail Home you@fastmail.com
$C sync
```

Google opens your browser to sign in. Microsoft shows a short code to enter
at microsoft.com/devicelogin. Fastmail asks for an app password. The names
(`Personal`, `Work`, ...) are yours to choose; they're how accounts are
labelled in the calendar. Refresh tokens and passwords go in the GNOME
keyring (`secret-tool`), never on disk.

### Fastmail and other CalDAV servers

Fastmail signs in with an app password, not your real one: Fastmail
Settings → Privacy & Security → Manage app passwords → New app password,
with access to **Calendars (CalDAV)**. `add-fastmail` asks for it (it isn't
echoed, and never goes on the command line), checks it, and saves it.

Any other CalDAV server works the same way, given its calendar home:

```bash
$C add-caldav Nextcloud --url https://cloud.example.com/remote.php/dav/calendars/me/ --user me
```

These accounts are read-only for now: their events show, remind and join
like any other, but answering, creating, editing and deleting are for
Google and Microsoft accounts until a later version. Make those changes in
Fastmail itself, and they arrive with the next sync.

### Registering the apps

Google and Microsoft only let an app read your calendar if it's registered
with them, so you register your own. Nobody else's app ever sees your data.

**Google** (once): in the Google Cloud Console, make a project, enable the
**Google Calendar API**, and set up the OAuth consent screen with the scope
`https://www.googleapis.com/auth/calendar`. Set its publishing status to
**In production** (Testing mode signs you out every 7 days; you don't need
Google's verification for your own use). Then Credentials → Create OAuth
client ID → **Desktop app**, and download the JSON.

**Microsoft** (once per organisation you sign in to): in the Entra admin
centre, Entra ID → App registrations → New registration (single tenant). Under
Authentication, turn on **Allow public client flows**. Under API permissions
add Microsoft Graph, delegated: `Calendars.ReadWrite`, `User.Read` and
`offline_access`. Note the application (client) ID and the directory (tenant)
ID. If the organisation requires admin consent, an admin has to grant it once.

## Using it

- **Click an event** to open it: edit it, delete it, answer it, open it in
  Google Calendar or Outlook, or join it. **New** (or `n`) starts one on the
  selected day.
- **Guests:** an event lists everyone invited and their answers. On one you
  can edit, **−** takes a guest off and the box below adds addresses (type
  several, or press Enter after each). Nothing is sent until **Save**. From
  a terminal: `calendar-ctl guests <uid>`, and `calendar-ctl update <uid>
  --invite <email> --uninvite <email>`.
- **Calendars:** click one in the list on the left to show or hide it. A
  hidden calendar isn't downloaded at all. `calendar-ctl choose` does the
  same in a checklist.
- **Keys:** `1`–`5` views, `[` `]` or the arrow keys to step, `t` today,
  `n` new event, `w` to flip the first day of the week.
- **Sync** runs every three minutes while the shell runs, and when you open
  the calendar. `calendar-ctl sync` runs one by hand.

**Settings** (in the widget's entry in `shell.json`, all optional):
`"layout": "classic"` starts in compact mode; `"reminders": false` turns
reminders off; `"view"` is the view it opens in; `"format"` is the clock's
own format, and its 12- or 24-hour choice carries into the calendar.

**Key bindings:** the calendar answers IPC, so you can bind keys to it, e.g.

```bash
qs ipc -p /usr/share/omarchy/shell call blacksheep.calendar newEvent
qs ipc -p /usr/share/omarchy/shell call blacksheep.calendar view week   # day, week, workweek, month, year
qs ipc -p /usr/share/omarchy/shell call blacksheep.calendar toggle      # also compact, expand
```

## Remove

Sign out of each account first, while the tool is still there. That deletes
its tokens from the keyring:

```bash
C=~/.config/omarchy/plugins/blacksheep.calendar/scripts/calendar-ctl
$C list                 # the account names
$C remove Personal      # and so on, for each one
omarchy plugin remove blacksheep.calendar
omarchy plugin enable omarchy.clock --section center
```

What's left afterwards is the non-secret account list in
`~/.config/blacksheep.calendar/`, and the event copy in
`~/.cache/blacksheep.calendar/`. Both are safe to delete. To revoke access on
the providers' side as well, remove the app at
myaccount.google.com/permissions, delete the app registration in Entra, and
revoke the app password in Fastmail's settings.

## Requirements

Omarchy (it's built on the shell's own clock and notifications), `python3`,
and `secret-tool` with a running keyring (Omarchy has both). `gum`, which
Omarchy ships, is used only by `calendar-ctl choose`. No sudo, no system
files, and no services: sync and reminders run inside the shell.

## How it works

`scripts/omcal/` does the talking. Google is fetched per calendar with
`singleEvents` and kept current with `updatedMin`; Microsoft uses Graph's
`calendarView/delta`; CalDAV asks the server to expand each calendar's
series in the window, and fetches a calendar again only when its ctag has
changed. A copy of the next four months (and the last five weeks)
lives in `~/.cache/blacksheep.calendar/`, and the widget reads one file from
it. Every change you make is written straight to the provider, guarded by the
event's etag, then applied to the local copy at once, before the next sync
confirms it. Times are kept in UTC, and only turned into local time on screen.

`tests/run.sh` runs the tests: the widget's date, editing, reminder and
"next up" logic under node, and the sync's link-finding, time parsing,
de-duplication, iCalendar and CalDAV reading under Python.

## License

MIT — see [LICENSE](LICENSE). Parts of the panel are derived from Omarchy's
own clock (MIT).
