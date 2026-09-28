// Model.js under node: the date, draft, reminder and "next up" logic.
//   TZ=America/Toronto node tests/model.test.js
const fs = require("fs")
const path = require("path")
const src = fs.readFileSync(path.join(__dirname, "..", "Model.js"), "utf8")
const M = new Function(src + "; return { parseClock, parseDateText, eventDraft, newDraft, draftArgs," +
  " nextUp, dueSnoozes, reminderText, keyForDate, addDays, dueReminders," +
  " parseAddresses, guestEdit, guestRemove, guestRows, guestSummary }")()

let failed = 0
function eq(got, want, name) {
  const ok = JSON.stringify(got) === JSON.stringify(want)
  if (!ok) failed++
  console.log((ok ? "ok   " : "FAIL ") + name + (ok ? "" : "\n     got  " + JSON.stringify(got) + "\n     want " + JSON.stringify(want)))
}

// Times and dates as typed.
eq(["9", "9:30", "0930", "14:30", "2pm", "2:30 pm", "12am", "12pm", "24:00", "13pm", "9:75"].map(M.parseClock),
   [540, 570, 570, 870, 840, 870, 0, 720, -1, -1, -1], "parseClock")
eq(["2026-10-02", "2026-10-2", "2026-2-30", "x"].map(M.parseDateText), ["2026-10-02", "2026-10-02", "", ""], "parseDateText")

// New events: options can't be smuggled in through a title.
let d = M.newDraft("2026-10-02", new Date(2026, 8, 27, 21, 10), "Google/c")
d.title = "--all-day"
eq(M.draftArgs(d).args, ["create", "Google/c", "--title", "--all-day", "--start", "2026-10-02 09:00",
                         "--end", "2026-10-02 10:00", "--busy"], "create: title stays a value")
d.from = "23:00"; d.to = "1am"
eq(M.draftArgs(d).args.slice(5, 8), ["2026-10-02 23:00", "--end", "2026-10-03 01:00"], "create: past midnight")
d.allDay = true; d.endDate = "2026-10-03"; d.busy = false
eq(M.draftArgs(d).args.slice(5, 10), ["2026-10-02", "--end", "2026-10-04", "--all-day", "--free"], "create: all-day ends the day after")
d.invite = "a@b.co, bad"
eq(M.draftArgs(d).error, "bad isn't an email address.", "create: bad guest")

// Editing sends only what changed.
const ev = { uid: "P/c/1", account: "P", calendar: "c", title: "T", location: "", busy: true, recurring: true,
             start: "2026-09-29T02:45:00Z", end: "2026-09-29T03:15:00Z" }
let e = M.eventDraft(ev)
eq([e.date, e.from, e.to], ["2026-09-28", "22:45", "23:15"], "edit: shown in local time")
eq(M.draftArgs(e).args, [], "edit: nothing changed")
e.title = "New"
eq(M.draftArgs(e).args, ["update", "P/c/1", "--title", "New"], "edit: title only")
e.series = true
eq(M.draftArgs(e).args, ["update", "P/c/1", "--title", "New", "--series"], "edit: series title")
e.from = "22:00"
eq(!!M.draftArgs(e).error, true, "edit: a series isn't moved")
e.series = false; e.busy = false
eq(M.draftArgs(e).args.slice(2), ["--title", "New", "--free", "--start", "2026-09-28 22:00",
                                  "--end", "2026-09-28 23:15", "--timed"], "edit: move one, and free")
const ad = M.eventDraft(Object.assign({}, ev, { start: "2026-10-05", end: "2026-10-07" }))
eq([ad.allDay, ad.date, ad.endDate], [true, "2026-10-05", "2026-10-06"], "edit: all-day shows its last day")

// Next up.
const now = new Date(2026, 8, 28, 9, 50), k = M.keyForDate(now)
const at = (h, m, dd) => new Date(2026, 8, 28 + (dd || 0), h, m).toISOString()
const by = {}
by[k] = [{ title: "past", start: at(8, 0), end: at(9, 0) },
         { title: "allday", start: k, end: M.addDays(k, 1), allDay: true },
         { title: "declined", start: at(10, 0), end: at(11, 0), declined: true },
         { title: "live", start: at(9, 30), end: at(10, 15) },
         { title: "soon", start: at(10, 0), end: at(10, 30) }]
let n = M.nextUp(by, now, false)
eq([n.event.title, n.when, n.live], ["live", "Now · 25 min left", true], "nextUp: on now")
by[k].splice(3, 1); n = M.nextUp(by, now, false)
eq([n.event.title, n.when, n.soon], ["soon", "In 10 min", true], "nextUp: soon")
by[k] = []; by[M.addDays(k, 1)] = [{ title: "t", start: at(14, 30, 1), end: at(15, 0, 1) }]
eq(M.nextUp(by, now, false).when, "Tomorrow · 2:30pm", "nextUp: tomorrow")
eq(M.nextUp({}, now, false), null, "nextUp: nothing")

// Snoozes come back while the event runs, and say so.
const t = Date.now(), iso = ms => new Date(ms).toISOString().replace(/\.\d+Z/, "Z")
const se = { uid: "a/c/1", account: "a", calendar: "c", title: "T", allDay: false, start: iso(t - 60000),
             end: iso(t + 1800000), status: "confirmed", join: { url: "https://x" }, remind: [5], response: "organizer" }
eq(M.dueSnoozes({ events: [se] }, { "snooze:a/c/1": t + 1000 }, t).length, 0, "snooze: not yet")
const back = M.dueSnoozes({ events: [se] }, { "snooze:a/c/1": t - 1 }, t)
eq(back.length, 1, "snooze: due")
eq(M.reminderText(back[0], "Work", false).body.indexOf("snoozed · "), 0, "snooze: labelled")
eq(M.dueSnoozes({ events: [Object.assign({}, se, { end: iso(t - 1) })] }, { "snooze:a/c/1": t - 1 }, t).length, 0, "snooze: not after the end")


// Guests.
const guests = [
  { email: "olive@x.co", name: "Olive", response: "accepted", organizer: true, me: false, optional: false, room: false },
  { email: "me@x.co", name: "", response: "tentative", organizer: false, me: true, optional: false, room: false },
  { email: "Bob@x.co", name: "Bob@x.co", response: "needsAction", organizer: false, me: false, optional: true, room: false },
  { email: "zed@x.co", name: "Zed", response: "declined", organizer: false, me: false, optional: false, room: false }
]
eq(M.guestSummary(guests, 4), "3 guests · 1 maybe, 1 no, 1 waiting", "guests: summary leaves the organiser out")
eq(M.guestSummary(guests.slice(1, 2), 150), "150 guests · 1 maybe", "guests: summary counts the whole list")
eq(M.parseAddresses("A@b.co; c@d.co  a@b.co"), { list: ["a@b.co", "c@d.co"] }, "guests: addresses split and deduped")
eq(M.parseAddresses("a@b.co, <x@y.co>").error, "<x@y.co> isn't an email address.", "guests: bad address")
eq(M.guestEdit(guests, [], [], "new@x.co"), { invited: ["new@x.co"], uninvited: [] }, "guests: add")
eq(M.guestEdit(guests, [], [], "BOB@x.co").error, "bob@x.co is already invited.", "guests: already on the list")
eq(M.guestEdit(guests, ["new@x.co"], [], "new@x.co").error, "new@x.co is already invited.", "guests: already added")
eq(M.guestEdit(guests, [], ["bob@x.co"], "bob@x.co"), { invited: [], uninvited: [] }, "guests: typing back undoes a removal")
eq(M.guestRemove([], [], "Bob@x.co"), { invited: [], uninvited: ["bob@x.co"] }, "guests: remove")
eq(M.guestRemove(["new@x.co"], [], "new@x.co"), { invited: [], uninvited: [] }, "guests: removing one just added forgets them")
const rows = M.guestRows(guests, ["new@x.co"], ["bob@x.co"])
eq(rows.map(r => [r.title, r.detail, r.answer, r.tags, r.fixed, r.pending]), [
  ["Olive", "olive@x.co", "", "organiser", true, ""],
  ["me@x.co", "", "Maybe", "you", true, ""],
  ["Bob@x.co", "", "Waiting", "optional", false, "remove"],
  ["Zed", "zed@x.co", "No", "", false, ""],
  ["new@x.co", "", "Invite", "", false, "add"]], "guests: rows")

e = M.eventDraft(Object.assign({}, ev, { guests: guests }))
eq(M.draftArgs(e).args, [], "guests: untouched, nothing to send")
e.invited = ["new@x.co"]; e.uninvited = ["bob@x.co"]
eq(M.draftArgs(e).args, ["update", "P/c/1", "--invite", "new@x.co", "--uninvite", "bob@x.co"], "guests: changes sent")
e.invited = []; e.uninvited = []; e.guestText = "typed@x.co"
eq(M.draftArgs(e).args, ["update", "P/c/1", "--invite", "typed@x.co"], "guests: typed but not added still counts")
e.guestText = "oops"
eq(M.draftArgs(e).error, "oops isn't an email address.", "guests: typed nonsense stops the save")
e.guestText = ""; e.title = "New"; e.invited = ["new@x.co"]; e.series = true
eq(M.draftArgs(e).args, ["update", "P/c/1", "--title", "New", "--invite", "new@x.co", "--series"], "guests: with a title, for the series")

if (failed) { console.log(failed + " failed"); process.exit(1) }
console.log("all passed")
