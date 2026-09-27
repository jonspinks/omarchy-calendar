# omarchy-calendar

Google Calendar and Microsoft 365 in Omarchy's calendar: your events on the
month grid, a day agenda, reminders with a Join button, and two-way editing.
Work in progress.

## Phase 0: sign in

`bin/calendar-ctl` signs each account in and proves it can read the calendar.
Refresh tokens go in the GNOME keyring (`secret-tool`), never on disk; the
config at `~/.config/blacksheep.calendar/accounts.json` (0600) holds only
names, tenant IDs and client IDs.

```bash
bin/calendar-ctl add-google Google ~/Downloads/client_secret_*.json
bin/calendar-ctl add-microsoft Work     --tenant <tenant-id> --client-id <app-id>
bin/calendar-ctl add-microsoft Client   --tenant <tenant-id> --client-id <app-id>
bin/calendar-ctl test Work
```

### Registering the apps

**Google:** Google Cloud Console → a project → enable **Google Calendar API** →
OAuth consent screen with scope `.../auth/calendar`, publishing status **In
production** (Testing mode expires refresh tokens every 7 days) → Credentials →
OAuth client ID → **Desktop app** → download the JSON.

**Microsoft, once per tenant:** Entra admin centre → App registrations → New
(single tenant) → Authentication: **Allow public client flows** on →
API permissions, Microsoft Graph, delegated: `Calendars.ReadWrite`, `User.Read`,
`offline_access` → note the application (client) ID and directory (tenant) ID.

## License

MIT — see [LICENSE](LICENSE).
