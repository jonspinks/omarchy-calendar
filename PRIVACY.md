# Privacy policy: Datebook

*Last updated: 28 September 2026*

Datebook (Omarchy Calendar) is a desktop calendar for the Omarchy Linux desktop. It shows
your Google Calendar, Microsoft 365 and Fastmail (or other CalDAV) events in the desktop's calendar, sends
meeting reminders, and lets you create, edit, delete and respond to events, and see and change who
is invited.
It is open source: everything it does is in this repository.

## What it accesses

When you sign in, you grant access to your calendars through Google's or
Microsoft's own sign-in page:

- **Google:** the Google Calendar scope (`https://www.googleapis.com/auth/calendar`),
  plus your email address, to show which account is signed in.
- **Microsoft 365:** `Calendars.ReadWrite` and `User.Read`, plus
  `offline_access`, so it can stay signed in.
- **Fastmail and other CalDAV servers:** an app password you create for it,
  with calendar (CalDAV) access only. Changes you make are written back to
  your calendars there; the server itself (Fastmail's, or yours) sends any
  invitations, updates, cancellations or replies those changes call for, to
  the people on the event. Datebook sends no email.

It uses that access only to show your events, remind you about them, and make
the changes you ask it to make. It doesn't read email, contacts, files or
anything else.

## Where your data goes

Nowhere but your own computer. Datebook has no server, and no one
operates a service behind it: it runs entirely on your machine and talks
directly to Google's and Microsoft's calendar APIs, and for Fastmail to
`caldav.fastmail.com` only (or to the CalDAV address you give it).

- **Sign-in tokens**, and a CalDAV account's app password, are stored in your
  system keyring (the GNOME keyring, through `secret-tool`), never in a plain
  file.
- **Account settings** that aren't secret (account names, the IDs of the
  Google or Microsoft app you signed in through, and a CalDAV account's
  address and user name) are kept in
  `~/.config/blacksheep.calendar/`, readable only by you.
- **A copy of your events** is kept in your user cache, readable only by you,
  so the calendar can show them instantly and work offline. It includes each
  event's guest list (names, email addresses and whether they've answered),
  exactly as your calendar already shows it to you.

Your calendar data is never sent to the developer, never shared with or sold
to anyone, and never used for advertising, analytics or training.

## Removing your data

- `calendar-ctl remove <account>` deletes that account's settings and its
  keyring entry. Do this for each account **before** removing the plugin:
  removing the plugin alone leaves the keyring entries in place.
- Removing the plugin doesn't delete its files outside the plugin folder.
  The account list in `~/.config/blacksheep.calendar/` and the copy of your
  events in `~/.cache/blacksheep.calendar/` stay until you delete them; both
  are safe to delete.
- You can revoke its access at any time: for Google at
  <https://myaccount.google.com/permissions>, and for Microsoft at
  <https://myaccount.microsoft.com> under *App permissions*, and for Fastmail
  by revoking the app password under Settings → Privacy & Security.

## Use of Google user data

Datebook's use and transfer of information received from Google APIs
adheres to the
[Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy),
including the Limited Use requirements.

## Contact

Questions or concerns: open an issue at
<https://github.com/jonspinks/omarchy-calendar/issues>.
