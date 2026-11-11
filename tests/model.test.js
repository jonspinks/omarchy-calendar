// Model.js under node: the date, draft, reminder and "next up" logic.
//   TZ=America/Toronto node tests/model.test.js
const fs = require("fs")
const path = require("path")
const src = fs.readFileSync(path.join(__dirname, "..", "Model.js"), "utf8")
const M = new Function(src + "; return { parseClock, parseDateText, eventDraft, newDraft, draftArgs," +
  " nextUp, dueSnoozes, reminderText, keyForDate, addDays, dueReminders, claimName," +
  " parseAddresses, guestEdit, guestRemove, guestRows, guestSummary, indexEvents," +
  " formatDayField, formatDayLong, viewDays, stepAnchor, rangeTitle, daysCount, notesHtml, meetingNotes," +
  " draftSnapshot, draftUnchanged, VIEWS, knownGuests, guestSuggestions, guestQuery, applyGuestPick, slotStart," +
  " parseMeetingLinks, timeSlots, clockText, lengthLabel, draftLength, moveStart, draggable, dragTimes, dragArgs }")()

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
eq(M.formatDayField("2026-10-02"), "Fri 2 Oct 2026", "formatDayField")
eq(M.formatDayLong("2026-10-02"), "Friday, 2 October 2026", "formatDayLong")
eq([M.formatDayField("2026-02-31"), M.formatDayLong(""), M.formatDayField("nope")], ["", "", ""], "formatDay: blank when it isn't a day")

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
let noted = M.newDraft("2026-10-02", new Date(2026, 8, 27, 21, 10), "Google/c")
noted.notes = "Agenda\n--bring this"
let notedArgs = M.draftArgs(noted).args
eq(notedArgs.slice(notedArgs.indexOf("--notes"), notedArgs.indexOf("--notes") + 2),
   ["--notes", "Agenda\n--bring this"], "create: notes stay a value")
noted.notes = " \n "
eq(M.draftArgs(noted).args.indexOf("--notes"), -1, "create: blank notes are left off")

// Dismissing the popup keeps a new event only once it differs from the start.
let fresh = M.newDraft("2026-10-02", new Date(2026, 8, 27, 21, 10), "Google/c")
let base = M.draftSnapshot(fresh)
eq(M.draftUnchanged(base, M.draftSnapshot(fresh)), true, "draft: untouched is dropped")
eq(M.draftUnchanged(null, base), true, "draft: no baseline is dropped")
eq(M.draftUnchanged(base, null), true, "draft: no current copy is dropped")
fresh.title = "Standup"
eq(base.title, "", "draft: the baseline is a copy")
eq(M.draftUnchanged(base, M.draftSnapshot(fresh)), false, "draft: a title keeps it")
fresh.title = ""
fresh.invite = "a@b.co"
eq(M.draftUnchanged(base, M.draftSnapshot(fresh)), false, "draft: an address keeps it")
fresh.invite = ""
fresh.location = "Room 2"
eq(M.draftUnchanged(base, M.draftSnapshot(fresh)), false, "draft: a place keeps it")
fresh.location = ""
fresh.from = "15:00"
eq(M.draftUnchanged(base, M.draftSnapshot(fresh)), false, "draft: a time keeps it")
fresh.from = base.from
fresh.allDay = true
eq(M.draftUnchanged(base, M.draftSnapshot(fresh)), false, "draft: all day keeps it")
fresh.allDay = false
fresh.busy = false
eq(M.draftUnchanged(base, M.draftSnapshot(fresh)), false, "draft: free keeps it")
fresh.busy = true
fresh.calendar = "Plan2/c"
eq(M.draftUnchanged(base, M.draftSnapshot(fresh)), false, "draft: another calendar keeps it")
fresh.calendar = "Google/c"
fresh.date = "2026-10-03"
eq(M.draftUnchanged(base, M.draftSnapshot(fresh)), false, "draft: another day keeps it")
fresh.date = base.date
fresh.notes = "Bring the doc"
eq(M.draftUnchanged(base, M.draftSnapshot(fresh)), false, "draft: notes keep it")

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


// One reminder per reminder, however many monitors run the widget.
const uid = "Work/AAMkAGFlM2I3MzQ2LWIyY2YtNDk1OC05OWNlLTlkNmM1ZWEzNjVjOABGAAAAAABrWEN4QHQSQZkyyBZHFxZPBwAwQ5yla4kITqFX-eujOloEAADLjJ_0AAA=/x"
const a = M.claimName(uid + "@1790000000000")
eq(a, M.claimName(uid + "@1790000000000"), "claim: the same reminder, the same name")
eq(a === M.claimName(uid + "@1790000600000"), false, "claim: another reminder time, another name")
eq(M.claimName("snooze:" + uid + "@1") === M.claimName("snooze:" + uid + "@2"), false, "claim: each snooze is its own")
eq(/^r[0-9a-f]{16}$/.test(a), true, "claim: short and file-safe")
// The snooze id carries its time, so a second snooze of one event claims afresh.
const snz = M.dueSnoozes({ events: [{ uid: "u1", start: "2026-10-25T14:00:00Z", end: "2026-10-25T15:00:00Z", allDay: false }] },
                       { "snooze:u1": Date.parse("2026-10-25T14:10:00Z") }, Date.parse("2026-10-25T14:11:00Z"))
eq(snz.map(r => r.id), ["snooze:u1@" + Date.parse("2026-10-25T14:10:00Z")], "claim: snooze ids carry their time")


// The days view: the next few days from the selected one (#4).
const ww = ["2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13"]
eq(M.viewDays("workweek", "2026-11-11", 1), ww, "work week: a Wednesday shows its own week")
eq(M.viewDays("workweek", "2026-11-09", 0), ww, "work week: a Monday, Sunday-start setting")
eq(M.viewDays("workweek", "2026-11-13", 1), ww, "work week: a Friday shows its own week")
eq(M.viewDays("workweek", "2026-11-08", 1), ww, "work week: a Sunday shows the week ahead")
eq(M.viewDays("workweek", "2026-11-08", 0), ww, "work week: a Sunday shows the week ahead, Sunday-start too")
eq(M.viewDays("workweek", "2026-11-07", 1), ww, "work week: a Saturday shows the week ahead")
eq(M.viewDays("workweek", M.stepAnchor("workweek", "2026-11-08", 1), 1)[0], "2026-11-16", "work week: Next from a Sunday goes on a week")
eq(M.viewDays("workweek", M.stepAnchor("workweek", "2026-11-08", -1), 1)[0], "2026-11-02", "work week: Previous from a Sunday goes back to last week")
eq(M.viewDays("days", "2026-10-25", 1, 4), ["2026-10-25", "2026-10-26", "2026-10-27", "2026-10-28"], "days: from the selected day, no past days")
eq(M.viewDays("days", "2026-10-30", 1, 3), ["2026-10-30", "2026-10-31", "2026-11-01"], "days: across a month end")
eq(M.viewDays("days", "2026-10-25", 1).length, 4, "days: four when unset")
eq([M.daysCount("2"), M.daysCount(9), M.daysCount(1), M.daysCount("x"), M.daysCount(undefined)], [2, 7, 2, 4, 4], "days: 2 to 7, else 4")
eq([M.stepAnchor("days", "2026-10-25", 1, 4), M.stepAnchor("days", "2026-10-25", -1, 3)], ["2026-10-29", "2026-10-22"], "days: steps by the days shown")
eq(M.rangeTitle("days", "2026-10-25", 1, 4), "25 Oct – 28 Oct", "days: title")
eq(M.VIEWS.slice(0, 5), ["day", "week", "workweek", "month", "year"], "days: keys 1 to 5 keep their views")
eq(M.VIEWS[5], "days", "days: key 6")
// CalDAV is two-way: its events are editable where the event and calendar
// both say so, and its invitations are answered like any other.
const idx = M.indexEvents({
  accounts: [{ name: "G", provider: "google" }, { name: "F", provider: "caldav" }],
  calendars: [{ account: "G", id: "c", name: "C", editable: true }, { account: "F", id: "w", name: "W", editable: true }],
  events: ["G/c", "F/w"].map(function(ref) {
    return { uid: ref + "/1", account: ref[0], calendar: ref.slice(2), title: "Mine", allDay: true,
             start: "2026-10-02", end: "2026-10-03", status: "confirmed", response: "organizer",
             organizer: true, editable: true }
  })
}, true)
eq(idx.byDay["2026-10-02"].map(function(r) { return [r.account, r.editable, "answerable" in r] }).sort(),
   [["F", true, false], ["G", true, false]], "indexEvents: caldav events edit like the others")

// Notes: links clickable, everything else escaped.
eq(M.notesHtml("Join:\nhttps://teams.microsoft.com/meet/1?p=a&b=c.\n<https://aka.ms/x> <b>", "#abc"),
   'Join:<br><a href="https://teams.microsoft.com/meet/1?p=a&amp;b=c" style="color:#abc">https://teams.microsoft.com/meet/1?p=a&amp;b=c</a>.<br>' +
   '&lt;<a href="https://aka.ms/x" style="color:#abc">https://aka.ms/x</a>&gt; &lt;b&gt;', "notesHtml: links, escapes, line breaks")
eq(M.notesHtml('http://plain.example "https://" javascript:alert(1)', "#abc"),
   'http://plain.example &quot;https://&quot; javascript:alert(1)', "notesHtml: only https becomes a link")
eq(M.notesHtml("____________\n\n\nTeams\nsnake_case_name\n\n____________\n", "#abc"), "<hr>Teams<br>snake_case_name<hr>",
   "notesHtml: an underscore line is a rule, without the blank lines around it")
eq(M.notesHtml("Agenda\n\nItem one", "#abc"), "Agenda<br><br>Item one", "notesHtml: other blank lines stay")

eq([M.meetingNotes("____\n\n____"), M.meetingNotes("  \n"), M.meetingNotes(null), M.meetingNotes("\n____\nHi\n")],
   ["", "", "", "____\nHi"], "meetingNotes: only divider lines is no notes")

// A double-clicked hour, and the hour the pointer is in.
let atTwo = M.newDraft("2026-10-02", new Date(2026, 9, 2, 11, 15), "Google/c", 14 * 60)
eq([atTwo.date, atTwo.endDate, atTwo.from, atTwo.to], ["2026-10-02", "2026-10-02", "14:00", "15:00"], "create: a double-clicked hour")
let noon = M.newDraft("2026-10-02", new Date(2026, 9, 2, 11, 15), "Google/c")
eq([noon.from, noon.to], ["12:00", "13:00"], "create: today, with no hour, is the next hour")
eq(M.newDraft("2026-10-02", new Date(2026, 8, 27, 21, 10), "Google/c", "14:00").from, "09:00", "create: a start that isn't a number is ignored")
eq(M.newDraft("2026-10-02", new Date(2026, 9, 2, 11, 15), "Google/c", 23 * 60).to, "23:59", "create: a late hour still ends the same day")
eq([M.slotStart(0, 40, 7, 20), M.slotStart(41, 40, 7, 20), M.slotStart(40 * 12, 40, 7, 20)],
   [420, 480, 19 * 60], "slot: the hour the pointer is in")
eq([M.slotStart(-1, 40, 7, 20), M.slotStart(40 * 13, 40, 7, 20), M.slotStart(0, 0, 7, 20)],
   [-1, -1, -1], "slot: outside the grid is no hour")

// People to offer while an address is typed: from events already cached.
const book = M.knownGuests({
  "2026-10-01": [
    { uid: "a", guests: [
      { email: "Me@x.co", name: "Me", me: true },
      { email: "room@x.co", name: "Board room", room: true },
      { email: "maya@x.co", name: "Maya" },
      { email: "nope", name: "Nope" },
      { email: "", name: "Blank" },
      { email: "owen@x.co", name: "Owen" }
    ]},
    { uid: "b", guests: [{ email: "leah@x.co", name: "Leah Okonkwo" }] }
  ],
  "2026-10-02": [
    { uid: "a", guests: [{ email: "maya@x.co", name: "Maya Chen" }, { email: "owen@x.co", name: "O" }] },
    { uid: "c", guests: [{ email: "maya@x.co", name: "M" }, { email: "leah@x.co", name: "leah@x.co" }] }
  ]
})
eq(book.map(function(p) { return [p.email, p.name, p.count] }), [
  ["leah@x.co", "Leah Okonkwo", 2],
  ["maya@x.co", "Maya Chen", 2],
  ["owen@x.co", "Owen", 1]
], "knownGuests: skip you, rooms and bad addresses; one count per event; longest name")
const names = [
  { email: "ann@x.co", name: "Anna", count: 4 },
  { email: "amy@x.co", name: "Anya", count: 1 },
  { email: "zoe@x.co", name: "Zoe Ann", count: 9 },
  { email: "lee@x.co", name: "Lee", count: 3 }
]
eq(M.guestSuggestions(names, "an", [], 6).map(function(p) { return [p.email, p.name, p.detail, p.rank] }), [
  ["ann@x.co", "Anna", "ann@x.co", 0],
  ["amy@x.co", "Anya", "amy@x.co", 0],
  ["zoe@x.co", "Zoe Ann", "zoe@x.co", 1]
], "suggest: a prefix beats a middle, then whoever you meet more often")
eq(M.guestSuggestions(names, "a", [], 6), [], "suggest: one letter stays quiet")
eq(M.guestSuggestions(names, "ann@x.co", [], 6), [], "suggest: a finished address is not offered again")
eq(M.guestSuggestions(names, "lee@x.co, an", ["amy@x.co"], 6).map(function(p) { return p.email }),
   ["ann@x.co", "zoe@x.co"], "suggest: skip anyone already invited")
eq(M.guestSuggestions([{ email: "maya@x.co", name: "Maya Chen", count: 2 }], "x.co", [], 6),
   [{ email: "maya@x.co", name: "Maya Chen", detail: "maya@x.co", rank: 1, count: 2 }], "suggest: part of an address")
eq(M.guestQuery("a@b.co, may"), "may", "guestQuery")
eq(M.guestQuery("a@b.co;may"), "may", "guestQuery: a semicolon")
eq(M.applyGuestPick("a@b.co, may", "maya@x.co"), "a@b.co, maya@x.co", "applyGuestPick")
eq(M.applyGuestPick("may", "maya@x.co"), "maya@x.co", "applyGuestPick: the only address")

// Personal rooms: a name, then an https link. No file is an empty list.
eq(M.parseMeetingLinks(""), [], "rooms: nothing")
eq(M.parseMeetingLinks(null), [], "rooms: no text")
eq(M.parseMeetingLinks(" \n# a note\n\nnot a link\nOffice http://example.com/room\n"), [], "rooms: comments, blanks and http are skipped")
eq(M.parseMeetingLinks("Work room  https://teams.microsoft.com/l/meetup-join/abc.\r\nhttps://us02web.zoom.us/my/steven\n"), [
  { name: "Work room", url: "https://teams.microsoft.com/l/meetup-join/abc" },
  { name: "https://us02web.zoom.us/my/steven", url: "https://us02web.zoom.us/my/steven" }
], "rooms: a name with spaces, a bare link, and a trailing period")
eq(M.parseMeetingLinks("Steven https://meet.proton.me/join/abc#xyz"), [
  { name: "Steven", url: "https://meet.proton.me/join/abc#xyz" }
], "rooms: a fragment stays")
eq(M.parseMeetingLinks('Room <img src="https://evil.test/x"> https://meet.google.com/abc-defg-hij'), [
  { name: 'Room <img src="https://evil.test/x">', url: "https://meet.google.com/abc-defg-hij" }
], "rooms: the last link is the room, and the name stays plain text")
eq(M.parseMeetingLinks("Work https://zoom.example/j/1\nAgain https://zoom.example/j/1\n"), [
  { name: "Work", url: "https://zoom.example/j/1" }
], "rooms: the same link once")
eq(M.parseMeetingLinks("HTTPS://teams.microsoft.com/meet/AbC"), [
  { name: "https://teams.microsoft.com/meet/AbC", url: "https://teams.microsoft.com/meet/AbC" }
], "rooms: the scheme is written https")
let many = []
for (let n = 0; n < 13; n++) many.push("Room " + n + " https://meet.example/r/" + n)
eq(M.parseMeetingLinks(many.join("\n")).length, 12, "rooms: twelve is enough")
eq(M.parseMeetingLinks("A".repeat(90) + " https://meet.example/room")[0].name,
   "A".repeat(79) + "…", "rooms: a long name is shortened")
eq(M.parseMeetingLinks("x".repeat(17000) + "\nKept https://meet.example/kept"), [], "rooms: text past the cap is not read")

// The time picker and moving an event's start.
eq([M.timeSlots(15).length, M.timeSlots(15)[1], M.timeSlots(15, 550).indexOf(550), M.timeSlots(15, 540).length], [96, 15, 37, 96], "timeSlots: 15-minute steps, keeps an odd time")
eq([M.clockText(870, true), M.clockText(870, false), M.clockText(0, false), M.clockText(720, false), M.clockText(-1, true)], ["14:30", "2:30 pm", "12:00 am", "12:00 pm", ""], "clockText")
eq([30, 60, 90, 140, 1440, 2880].map(M.lengthLabel), ["30 min", "1 h", "1.5 h", "2 h 20 min", "1 day", "2 days"], "lengthLabel")
const moveEv = { allDay: false, date: "2026-11-12", endDate: "2026-11-12", from: "09:00", to: "10:30" }
eq(M.draftLength(moveEv), 90, "draftLength")
eq(M.draftLength({ allDay: false, date: "2026-11-12", endDate: "2026-11-12", from: "23:00", to: "00:30" }), 90, "draftLength: past midnight")
eq(M.moveStart(moveEv, "2026-11-12", "14:00"), { date: "2026-11-12", endDate: "2026-11-12", from: "14:00", to: "15:30" }, "moveStart: new time keeps the length")
eq(M.moveStart(moveEv, "2026-11-20", "09:00"), { date: "2026-11-20", endDate: "2026-11-20", from: "09:00", to: "10:30" }, "moveStart: new day moves the end day too")
eq(M.moveStart(moveEv, "2026-11-12", "23:30"), { date: "2026-11-12", endDate: "2026-11-13", from: "23:30", to: "01:00" }, "moveStart: runs past midnight")
eq(M.moveStart({ allDay: false, date: "2026-11-12", endDate: "2026-11-14", from: "09:00", to: "17:00" }, "2026-11-20", "09:00"),
   { date: "2026-11-20", endDate: "2026-11-22", from: "09:00", to: "17:00" }, "moveStart: a multi-day event keeps its days")
eq(M.moveStart({ allDay: true, date: "2026-11-12", endDate: "2026-11-13", from: "09:00", to: "10:00" }, "2026-12-01", ""),
   { date: "2026-12-01", endDate: "2026-12-02", from: "09:00", to: "10:00" }, "moveStart: all-day moves by whole days")
eq(M.moveStart({ allDay: false, date: "2026-11-12", endDate: "2026-11-12", from: "09:00", to: "x" }, "2026-11-12", "10:00").to, "11:00", "moveStart: unreadable end -> an hour")

// Dragging in the hour grid.
const when = (y, mo, d, h, mi) => new Date(y, mo - 1, d, h, mi).getTime()
const hhmm = (ms) => { const x = new Date(ms); return x.getDate() + " " + String(x.getHours()).padStart(2, "0") + ":" + String(x.getMinutes()).padStart(2, "0") }
let dt = M.dragTimes(when(2026, 11, 12, 9, 0), when(2026, 11, 12, 10, 30), 67, 0, "move")
eq([hhmm(dt.start), hhmm(dt.end)], ["12 10:00", "12 11:30"], "dragTimes: move snaps the start, keeps the length")
dt = M.dragTimes(when(2026, 11, 12, 9, 0), when(2026, 11, 12, 10, 0), 0, 2, "move")
eq([hhmm(dt.start), hhmm(dt.end)], ["14 09:00", "14 10:00"], "dragTimes: across columns moves whole days")
dt = M.dragTimes(when(2026, 10, 31, 9, 0), when(2026, 10, 31, 10, 0), 0, 1, "move")
eq([hhmm(dt.start), hhmm(dt.end)], ["1 09:00", "1 10:00"], "dragTimes: a day across the clock change stays 9:00")
dt = M.dragTimes(when(2026, 11, 12, 9, 0), when(2026, 11, 12, 10, 0), -80, 0, "resize")
eq([hhmm(dt.start), hhmm(dt.end)], ["12 09:00", "12 09:15"], "dragTimes: resize never below 15 minutes")
dt = M.dragTimes(when(2026, 11, 12, 9, 0), when(2026, 11, 12, 10, 0), 55, 0, "resize")
eq(hhmm(dt.end), "12 11:00", "dragTimes: resize snaps the end")
eq([M.draggable({ editable: true, organizer: true }), M.draggable({ editable: true, organizer: false }),
    M.draggable({ editable: false, organizer: true }), M.draggable({ editable: true, organizer: true, allDay: true })],
   [true, false, false, false], "draggable: your own timed events only")
const dragEv = { uid: "Google/c/abc", account: "Google", calendar: "c", title: "Standup", location: "",
                 start: "2026-11-12T09:00:00-05:00", end: "2026-11-12T09:30:00-05:00", busy: true, guests: [] }
eq(M.dragArgs(dragEv, when(2026, 11, 13, 14, 0), when(2026, 11, 13, 14, 30)).args,
   ["update", "Google/c/abc", "--start", "2026-11-13 14:00", "--end", "2026-11-13 14:30", "--timed"], "dragArgs: update with the new times only")
eq(M.dragArgs(dragEv, when(2026, 11, 12, 23, 30), when(2026, 11, 13, 0, 0)).args.slice(2, 6),
   ["--start", "2026-11-12 23:30", "--end", "2026-11-13 00:00"], "dragArgs: ending at midnight")

if (failed) { console.log(failed + " failed"); process.exit(1) }
console.log("all passed")
