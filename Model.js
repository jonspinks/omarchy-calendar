// Pure date and format math for the clock widget and its calendar panel.
// Everything here is locale- and Qt-free so it can be unit tested under node
// (test/shell.d/clock-test.sh); the QML owns month/weekday naming through
// Qt.locale().

var MS_PER_DAY = 86400000

// Weekday indices match both JS Date.getDay() and QML's Locale.Sunday…
// Locale.Saturday, so a locale's firstDayOfWeek can be passed straight in.
var WEEKDAY_NAMES = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]

// ---- Bar label formats. Right-clicking the clock walks these in order and
//      writes the result back to shell.json, so the label the bar shows and
//      the format the config stores are always the same thing.
//
// The locale-shaped time presets are each followed by their 12-hour twin, so
// the walk from a 24-hour label to the same label in AM/PM is a single right
// click rather than a lap of the ring. The ISO preset is deliberately left
// without one: ISO 8601 writes time on a 24-hour clock, so an AM/PM variant
// would contradict the only thing that format is for.
var CLOCK_FORMATS = [
  "dddd HH:mm",
  "dddd h:mm AP",
  "HH:mm",
  "h:mm AP",
  "ddd d MMM HH:mm",
  "ddd d MMM h:mm AP",
  "d MMMM 'W'ww yyyy",
  "yyyy-MM-dd HH:mm"
]

// Vertical bars have room for a few stacked lines and nothing else, so the
// ring stays short. AM/PM costs a fourth line, which is why only the plain
// time carries it here.
var VERTICAL_CLOCK_FORMATS = [
  "HH\n—\nmm",
  "h\n—\nmm\nAP",
  "dd\nMMM\n'W'ww\n''yy",
  "HH\nmm"
]

function clockFormats(vertical) {
  return vertical ? VERTICAL_CLOCK_FORMATS.slice() : CLOCK_FORMATS.slice()
}

// The presets in a fixed order, plus the configured alternate and current
// format when they are something else. The order must not depend on which
// entry is current: cycling writes the result back to shell.json, and a ring
// that reshuffled itself around the current value would bounce between two
// entries instead of walking.
function clockFormatRing(configured, configuredAlt, presets) {
  var ring = []
  var candidates = (presets || []).concat([configuredAlt, configured])
  for (var i = 0; i < candidates.length; i++) {
    var format = String(candidates[i] === undefined || candidates[i] === null ? "" : candidates[i])
    if (format === "" || ring.indexOf(format) !== -1) continue
    ring.push(format)
  }
  return ring.length > 0 ? ring : ["HH:mm"]
}

// Next entry after `current`. An unknown current format (a hand-written one
// that is not in the ring) starts the walk at the top.
function nextClockFormat(ring, current) {
  if (!ring || ring.length === 0) return ""
  var index = ring.indexOf(String(current === undefined || current === null ? "" : current))
  return ring[(index + 1) % ring.length]
}

// Two-digit ISO week, substituted into a format's 'ww' token before Qt
// formats it -- Qt has no ISO week specifier of its own.
function isoWeekLiteral(year, month, day) {
  return pad2(isoWeek(year, month, day))
}

function pad2(value) {
  var n = Number(value)
  return (n < 10 ? "0" : "") + n
}

// Stable "yyyy-MM-dd" identity for a day, so a grid cell can be compared
// against today without dragging Date objects through bindings.
function dateKey(year, month, day) {
  return year + "-" + pad2(Number(month) + 1) + "-" + pad2(day)
}

function keyForDate(date) {
  return dateKey(date.getFullYear(), date.getMonth(), date.getDate())
}

function coerceWeekStart(value) {
  if (value === undefined || value === null) return null
  if (typeof value === "number")
    return isFinite(value) ? ((Math.round(value) % 7) + 7) % 7 : null

  var text = String(value).replace(/^\s+|\s+$/g, "").toLowerCase()
  if (text === "") return null

  for (var i = 0; i < WEEKDAY_NAMES.length; i++)
    if (WEEKDAY_NAMES[i] === text || WEEKDAY_NAMES[i].substr(0, 3) === text) return i

  var parsed = parseInt(text, 10)
  return isFinite(parsed) ? ((parsed % 7) + 7) % 7 : null
}

// Configured week start, falling back to the locale's own first day when
// the setting is missing or nonsense.
function normalizedWeekStart(value, fallback) {
  var configured = coerceWeekStart(value)
  if (configured !== null) return configured
  var fallbackStart = coerceWeekStart(fallback)
  return fallbackStart === null ? 1 : fallbackStart
}

function weekStartSettingName(index) {
  return WEEKDAY_NAMES[normalizedWeekStart(index, 1)]
}

// The toggle flips between the two conventions people actually switch
// between. A calendar configured to any other start (Saturday, say) is
// shown as-is and lands on Monday the first time it is toggled.
function toggledWeekStart(index) {
  return normalizedWeekStart(index, 1) === 1 ? 0 : 1
}

function weekdayOrder(weekStart) {
  var start = normalizedWeekStart(weekStart, 1)
  var out = []
  for (var i = 0; i < 7; i++) out.push((start + i) % 7)
  return out
}

// ISO-8601 week number: the week owning the Thursday of that date's
// Monday-based week. Mirrors the clock widget's 'ww' format token.
function isoWeek(year, month, day) {
  var date = new Date(Date.UTC(year, month, day))
  var weekday = date.getUTCDay() || 7
  date.setUTCDate(date.getUTCDate() + 4 - weekday)
  var yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1))
  return Math.ceil(((date.getTime() - yearStart.getTime()) / MS_PER_DAY + 1) / 7)
}

function dayOfYear(year, month, day) {
  return Math.round((Date.UTC(year, month, day) - Date.UTC(year, 0, 1)) / MS_PER_DAY) + 1
}

function daysInYear(year) {
  return dayOfYear(year, 11, 31)
}

// Share of the year already behind you: whole days completed over days in
// the year, so January 1 reads 0% and December 31 reads 100%.
function yearProgress(year, month, day) {
  var total = daysInYear(year)
  if (total <= 0) return 0
  return Math.max(0, Math.min(1, (dayOfYear(year, month, day) - 1) / total))
}

function yearProgressPercent(year, month, day) {
  return Math.round(yearProgress(year, month, day) * 100)
}

// Memento mori. The default span is a round number rather than anything from
// an actuarial table: the point of the bar is the reminder, not the
// arithmetic, and whoever wants a different number can say so.
var DEFAULT_LIFE_EXPECTANCY = 90

// A birth year rather than an age, so the bar keeps counting on its own
// instead of going stale the moment it is entered. 0 means "not set", which
// is also what a blank, malformed, future, or implausibly distant year means.
function parseBirthYear(value, currentYear) {
  var now = Math.round(Number(currentYear))
  if (!isFinite(now)) return 0
  var text = String(value === undefined || value === null ? "" : value).replace(/^\s+|\s+$/g, "")
  if (!/^\d{4}$/.test(text)) return 0
  var year = parseInt(text, 10)
  if (!isFinite(year) || year > now || year < now - 120) return 0
  return year
}

// Whole years, the way people say their age: born in 1979 makes you 47 for
// all of 2026, whichever side of your birthday today falls.
function ageFromBirthYear(birthYear, currentYear) {
  var born = parseBirthYear(birthYear, currentYear)
  if (born <= 0) return 0
  return Math.round(Number(currentYear)) - born
}

// 0 means "not set", which is also what a blank, negative, fractional, or
// absurd entry means — the life bar simply stays hidden.
function parseAge(value) {
  var text = String(value === undefined || value === null ? "" : value).replace(/^\s+|\s+$/g, "")
  if (!/^\d+$/.test(text)) return 0
  var years = parseInt(text, 10)
  if (!isFinite(years) || years <= 0 || years > 120) return 0
  return years
}

// Unset or nonsense falls back to the default rather than to zero, so the
// bar always has something to measure against.
function parseLifeExpectancy(value) {
  var text = String(value === undefined || value === null ? "" : value).replace(/^\s+|\s+$/g, "")
  if (!/^\d+$/.test(text)) return DEFAULT_LIFE_EXPECTANCY
  var years = parseInt(text, 10)
  if (!isFinite(years) || years <= 0 || years > 150) return DEFAULT_LIFE_EXPECTANCY
  return years
}

function lifeProgress(age, expectancy) {
  var years = parseAge(age)
  var span = parseLifeExpectancy(expectancy)
  if (years <= 0 || span <= 0) return 0
  return Math.max(0, Math.min(1, years / span))
}

function lifeProgressPercent(age, expectancy) {
  return Math.round(lifeProgress(age, expectancy) * 100)
}

// Always six rows of seven days. A fixed grid keeps the popup exactly the
// same height in every month, so stepping through the year never makes the
// panel jump under the pointer.
function monthGrid(year, month, weekStart, todayKey) {
  var start = normalizedWeekStart(weekStart, 1)
  var leading = (new Date(year, month, 1).getDay() - start + 7) % 7
  var cursor = new Date(year, month, 1 - leading)
  var today = String(todayKey || "")
  var weeks = []

  for (var w = 0; w < 6; w++) {
    var days = []
    var thursday = null
    for (var d = 0; d < 7; d++) {
      var cellYear = cursor.getFullYear()
      var cellMonth = cursor.getMonth()
      var cellDay = cursor.getDate()
      var weekday = cursor.getDay()
      var key = dateKey(cellYear, cellMonth, cellDay)
      if (weekday === 4) thursday = { year: cellYear, month: cellMonth, day: cellDay }
      days.push({
        key: key,
        year: cellYear,
        month: cellMonth,
        day: cellDay,
        weekday: weekday,
        inMonth: cellMonth === month && cellYear === year,
        weekend: weekday === 0 || weekday === 6,
        today: key === today
      })
      cursor.setDate(cursor.getDate() + 1)
    }
    // Number every row by the ISO week owning its Thursday. That is the
    // definition itself for Monday-start weeks, and the only answer that
    // stays stable for the other starts, where a row straddles two ISO
    // weeks but shares all of Monday through Thursday with one of them.
    var anchor = thursday || days[0]
    weeks.push({
      week: isoWeek(anchor.year, anchor.month, anchor.day),
      days: days
    })
  }
  return weeks
}

function stepMonth(year, month, delta) {
  var target = new Date(year, Number(month) + Number(delta), 1)
  return { year: target.getFullYear(), month: target.getMonth() }
}

// ---- Events, from the sync's events.json (see scripts/omcal/model.py).
//
// Timed events arrive as UTC instants and all-day events as plain dates with
// an exclusive end. Local time is applied only here, at display time, so the
// cache never depends on the time zone the laptop is in today.

// Fallback colours for calendars that don't bring one (Graph often doesn't),
// picked per account so each account still reads as one family.
var FALLBACK_COLORS = ["#7aa2f7", "#9ece6a", "#e0af68", "#bb9af7", "#7dcfff", "#f7768e"]

function colorFor(calendar, accountIndex) {
  var c = calendar && calendar.color ? String(calendar.color) : ""
  if (/^#[0-9a-fA-F]{6}$/.test(c)) return c
  return FALLBACK_COLORS[Math.max(0, accountIndex) % FALLBACK_COLORS.length]
}

function addDays(key, n) {
  var p = key.split("-")
  var d = new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]) + n)
  return keyForDate(d)
}

function pad(n) { return (n < 10 ? "0" : "") + n }

function clockLabel(date, use24h) {
  if (use24h) return pad(date.getHours()) + ":" + pad(date.getMinutes())
  var h = date.getHours() % 12 || 12
  return h + (date.getMinutes() ? ":" + pad(date.getMinutes()) : "") + (date.getHours() < 12 ? "am" : "pm")
}

// Every local day an event covers, with the label it shows on that day.
function eventDays(e, use24h) {
  var out = []
  if (e.allDay) {
    var last = addDays(e.end > e.start ? e.end : addDays(e.start, 1), -1)
    for (var k = e.start; k <= last; k = addDays(k, 1))
      out.push({ key: k, label: "All day", sort: "0" })
    return out
  }
  var start = new Date(e.start), end = new Date(e.end)
  if (!(end > start)) end = new Date(start.getTime() + 60000)
  // The last moment inside the event: an event ending at midnight belongs to
  // the day before, not to the day it ends on.
  var lastKey = keyForDate(new Date(end.getTime() - 1))
  var firstKey = keyForDate(start)
  for (var d = firstKey; d <= lastKey; d = addDays(d, 1)) {
    var label
    if (firstKey === lastKey) label = clockLabel(start, use24h) + " – " + clockLabel(end, use24h)
    else if (d === firstKey) label = "from " + clockLabel(start, use24h)
    else if (d === lastKey) label = "until " + clockLabel(end, use24h)
    else label = "All day"
    out.push({ key: d, label: label, sort: d === firstKey ? "1" + e.start : "0" })
  }
  return out
}

// {calendars, byDay, accounts} for the panel: hidden calendars dropped, each
// event carrying its colour and calendar name, each day's list in order.
function indexEvents(data, use24h) {
  var calendars = {}, accounts = []
  var accountIndex = {}
  var list = (data && data.accounts) || []
  for (var i = 0; i < list.length; i++) {
    accountIndex[list[i].name] = i
    accounts.push(list[i])
  }
  var cals = (data && data.calendars) || []
  var calendarList = []
  for (var c = 0; c < cals.length; c++) {
    var cal = cals[c]
    calendars[cal.account + "/" + cal.id] = {
      name: cal.name, shown: cal.shown !== false, editable: !!cal.editable,
      color: colorFor(cal, accountIndex[cal.account] || 0)
    }
    calendarList.push({ account: cal.account, id: cal.id, ref: cal.account + "/" + cal.id,
                        name: cal.name || cal.id, primary: !!cal.primary, shown: cal.shown !== false,
                        color: calendars[cal.account + "/" + cal.id].color })
  }
  // The rail's list: by account in their own order, each one's main calendar first.
  calendarList.sort(function(a, b) {
    var ai = accountIndex[a.account] || 0, bi = accountIndex[b.account] || 0
    if (ai !== bi) return ai - bi
    if (a.primary !== b.primary) return a.primary ? -1 : 1
    return a.name.toLowerCase() < b.name.toLowerCase() ? -1 : 1
  })
  var byDay = {}
  var evs = (data && data.events) || []
  for (var j = 0; j < evs.length; j++) {
    var e = evs[j]
    var cinfo = calendars[e.account + "/" + e.calendar]
    if (!cinfo || !cinfo.shown || e.status === "cancelled") continue
    var days = eventDays(e, use24h)
    for (var n = 0; n < days.length; n++) {
      var day = days[n]
      if (!byDay[day.key]) byDay[day.key] = []
      byDay[day.key].push({
        uid: e.uid, title: e.title, label: day.label, sort: day.sort,
        color: cinfo.color, calendarName: cinfo.name, account: e.account,
        location: e.location || "", join: e.join || null, webLink: e.webLink || "",
        response: e.response, declined: e.response === "declined",
        allDay: e.allDay || day.label === "All day", start: e.start, end: e.end,
        organizer: !!e.organizer, recurring: !!e.recurring,
        calendar: e.calendar, editable: !!e.editable && !!cinfo.editable,
        busy: e.busy !== false,
        guests: e.guests || [], guestTotal: e.guestTotal || 0, guestsHidden: !!e.guestsHidden
      })
    }
  }
  for (var key in byDay)
    byDay[key].sort(function(a, b) { return a.sort < b.sort ? -1 : a.sort > b.sort ? 1 : (a.title < b.title ? -1 : 1) })
  return { calendars: calendars, calendarList: calendarList, byDay: byDay, accounts: accounts }
}

// Up to `max` distinct colours for a day's dots, in the day's own order.
function dayColors(events, max) {
  var seen = {}, out = []
  for (var i = 0; events && i < events.length && out.length < max; i++) {
    if (events[i].declined || seen[events[i].color]) continue
    seen[events[i].color] = true
    out.push(events[i].color)
  }
  return out
}

function dayTitle(key, todayKey) {
  if (key === todayKey) return "Today"
  if (key === addDays(todayKey, 1)) return "Tomorrow"
  if (key === addDays(todayKey, -1)) return "Yesterday"
  var p = key.split("-")
  return Qt.formatDate(new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2])), "dddd d MMMM")
}


// ---- Views: which days each shows, and where Previous and Next go.

var VIEWS = ["day", "week", "workweek", "month", "year"]

function keyToDate(key) {
  var p = String(key).split("-")
  return new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]))
}

function weekStartKey(key, weekStart) {
  var d = keyToDate(key)
  var back = (d.getDay() - normalizedWeekStart(weekStart, 1) + 7) % 7
  return addDays(key, -back)
}

function viewDays(view, anchorKey, weekStart) {
  var days = []
  if (view === "day") {
    days = [anchorKey]
  } else if (view === "week") {
    var first = weekStartKey(anchorKey, weekStart)
    for (var i = 0; i < 7; i++) days.push(addDays(first, i))
  } else if (view === "workweek") {
    // Monday to Friday of the week holding the anchor, whatever the week-start
    // setting: a working week is a working week.
    var d = keyToDate(anchorKey)
    var monday = addDays(anchorKey, -((d.getDay() + 6) % 7))
    for (var j = 0; j < 5; j++) days.push(addDays(monday, j))
  }
  return days
}

function stepAnchor(view, anchorKey, delta) {
  var d = keyToDate(anchorKey)
  if (view === "day") return addDays(anchorKey, delta)
  if (view === "week" || view === "workweek") return addDays(anchorKey, 7 * delta)
  if (view === "month") {
    var m = new Date(d.getFullYear(), d.getMonth() + delta, 1)
    return keyForDate(m)
  }
  return keyForDate(new Date(d.getFullYear() + delta, 0, 1))
}

var MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

function shortDay(key) {
  var d = keyToDate(key)
  return d.getDate() + " " + MONTHS_SHORT[d.getMonth()]
}

function rangeTitle(view, anchorKey, weekStart) {
  var d = keyToDate(anchorKey)
  if (view === "day") {
    var names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    return names[d.getDay()] + " " + shortDay(anchorKey) + " " + d.getFullYear()
  }
  if (view === "week" || view === "workweek") {
    var days = viewDays(view, anchorKey, weekStart)
    // Numbered like the month grid's rows: by the ISO week owning Thursday.
    var a = keyToDate(days[0])
    for (var t = 0; t < days.length; t++)
      if (keyToDate(days[t]).getDay() === 4) { a = keyToDate(days[t]); break }
    return "Week " + isoWeek(a.getFullYear(), a.getMonth(), a.getDate()) + " · "
      + shortDay(days[0]) + " – " + shortDay(days[days.length - 1])
  }
  if (view === "month") return ""
  return String(d.getFullYear())
}

// A day's timed events as blocks on an hour grid: minutes from midnight, and
// a column when meetings overlap, so they sit side by side, not on top.
function dayLayout(events, dayKey) {
  var dayStart = keyToDate(dayKey).getTime()
  var dayEnd = keyToDate(addDays(dayKey, 1)).getTime()
  var blocks = []
  for (var i = 0; events && i < events.length; i++) {
    var e = events[i]
    if (e.allDay) continue
    var s = Math.max(new Date(e.start).getTime(), dayStart)
    var en = Math.min(new Date(e.end).getTime(), dayEnd)
    if (!(en > s)) en = s + 15 * 60000
    blocks.push({ event: e, top: (s - dayStart) / 60000, bottom: (en - dayStart) / 60000 })
  }
  blocks.sort(function(a, b) { return a.top - b.top || b.bottom - a.bottom })
  // Greedy columns within each cluster of overlapping events.
  var cluster = [], clusterEnd = -1
  function flush() {
    var cols = 0
    for (var k = 0; k < cluster.length; k++) cols = Math.max(cols, cluster[k].column + 1)
    for (var m = 0; m < cluster.length; m++) cluster[m].columns = cols
    cluster = []
  }
  for (var j = 0; j < blocks.length; j++) {
    var b = blocks[j]
    if (b.top >= clusterEnd) { flush(); clusterEnd = -1 }
    var used = {}
    for (var c = 0; c < cluster.length; c++) if (cluster[c].bottom > b.top) used[cluster[c].column] = true
    var col = 0
    while (used[col]) col++
    b.column = col
    cluster.push(b)
    clusterEnd = Math.max(clusterEnd, b.bottom)
  }
  flush()
  return blocks
}

// The hours a time grid shows: at least 7am to 8pm, widened to fit any event.
function hourRange(dayKeys, byDay) {
  var first = 7, last = 20
  for (var i = 0; i < dayKeys.length; i++) {
    var blocks = dayLayout(byDay[dayKeys[i]] || [], dayKeys[i])
    for (var j = 0; j < blocks.length; j++) {
      first = Math.min(first, Math.floor(blocks[j].top / 60))
      last = Math.max(last, Math.ceil(blocks[j].bottom / 60))
    }
  }
  return { first: first, last: last }
}

// How busy a day is, 0-3, for the year view's shading.
function busyLevel(events) {
  var n = 0
  for (var i = 0; events && i < events.length; i++) if (!events[i].declined) n++
  return n === 0 ? 0 : n < 3 ? 1 : n < 6 ? 2 : 3
}


// ---- Reminders.
//
// An event's own reminder wins (Google's popup reminders, Outlook's "remind me
// N minutes before"). Many work meetings arrive with Outlook's reminder
// switched off, so a timed meeting with a Join link and no reminder of its own
// still gets one, FALLBACK_REMIND minutes before. A reminder the laptop slept
// through still fires, but only until LATE_LIMIT minutes after the start.

var FALLBACK_REMIND = 5
var LATE_LIMIT = 10

function reminderTimes(e) {
  var r = (e.remind || []).slice()
  if (r.length === 0 && !e.allDay && e.join) r = [FALLBACK_REMIND]
  return r
}

function startMs(e) {
  return e.allDay ? keyToDate(e.start).getTime() : new Date(e.start).getTime()
}

// Reminders that are due now and haven't fired: [{id, event, minutes}], where
// minutes is how long until the start (negative once it has begun).
function dueReminders(data, calendars, nowMs, fired) {
  var due = []
  var evs = (data && data.events) || []
  for (var i = 0; i < evs.length; i++) {
    var e = evs[i]
    var cal = calendars[e.account + "/" + e.calendar]
    if (!cal || !cal.shown || e.status === "cancelled" || e.response === "declined") continue
    var start = startMs(e)
    if (nowMs > start + LATE_LIMIT * 60000) continue
    var times = reminderTimes(e)
    // The latest reminder already due is the one worth showing; earlier ones
    // for the same event are marked as fired alongside it.
    var best = null
    for (var t = 0; t < times.length; t++) {
      var at = start - times[t] * 60000
      var id = e.uid + "@" + at
      if (nowMs >= at && !fired[id] && (best === null || at > best.at)) best = { id: id, at: at }
    }
    if (best) due.push({ id: best.id, event: e, minutes: Math.round((start - nowMs) / 60000),
                         also: times.map(function(m) { return e.uid + "@" + (start - m * 60000) }) })
  }
  return due
}

// Snoozed reminders whose time has come, while their event hasn't ended.
// fired["snooze:<uid>"] holds when each should come back.
function dueSnoozes(data, fired, nowMs) {
  var out = []
  var evs = (data && data.events) || []
  for (var i = 0; i < evs.length; i++) {
    var e = evs[i]
    var at = fired["snooze:" + e.uid]
    if (!at || nowMs < at) continue
    var end = e.allDay ? keyToDate(e.end).getTime() : new Date(e.end).getTime()
    if (nowMs >= end || e.status === "cancelled") continue
    out.push({ id: "snooze:" + e.uid, event: e, minutes: Math.round((startMs(e) - nowMs) / 60000), also: [] })
  }
  return out
}

function reminderText(r, calName, use24h) {
  var e = r.event
  var when = e.allDay && r.minutes <= 0 ? "today"
           : r.minutes > 1 ? "in " + r.minutes + " min"
           : r.minutes >= -1 ? "starting now"
           : "started " + (-r.minutes) + " min ago"
  if (String(r.id).indexOf("snooze:") === 0) when = "snoozed · " + when
  var time = e.allDay ? "All day" : clockLabel(new Date(e.start), use24h) + " – " + clockLabel(new Date(e.end), use24h)
  var how = e.join ? " · click to join " + ({teams: "Teams", zoom: "Zoom", meet: "Meet", webex: "Webex"}[e.join.kind] || "the meeting")
                   : (e.webLink ? " · click to open" : "")
  return { headline: e.title, body: when + " · " + time + " · " + calName + how }
}


// ---- Next up: the meeting on now, or the next one within a week. All-day
//      and declined events don't count; a meeting counts until it ends.
function nextUp(byDay, now, use24h) {
  var nowMs = now.getTime()
  var key = keyForDate(now)
  for (var d = 0; d < 8; d++) {
    var rows = byDay[addDays(key, d)] || []
    var best = null
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i]
      if (r.allDay || r.declined || String(r.start).length === 10) continue
      var s = new Date(r.start).getTime(), e = new Date(r.end).getTime()
      if (e <= nowMs) continue
      if (!best || s < best.s) best = { row: r, s: s, e: e }
    }
    if (best) return { event: best.row, when: nextUpWhen(best.s, best.e, now, use24h), live: best.s <= nowMs,
                       soon: best.s > nowMs && best.s - nowMs <= 15 * 60000 }
  }
  return null
}

function nextUpWhen(s, e, now, use24h) {
  var nowMs = now.getTime()
  var mins = Math.round((s - nowMs) / 60000)
  if (s <= nowMs) {
    var left = Math.max(1, Math.round((e - nowMs) / 60000))
    return "Now · " + (left < 60 ? left + " min left" : "until " + clockLabel(new Date(e), use24h))
  }
  if (mins < 60) return "In " + Math.max(1, mins) + " min"
  var start = new Date(s), dk = keyForDate(start), today = keyForDate(now)
  var at = clockLabel(start, use24h)
  if (dk === today) return (mins < 180 ? "In " + Math.floor(mins / 60) + " h " + (mins % 60) + " min · " : "Today · ") + at
  if (dk === addDays(today, 1)) return "Tomorrow · " + at
  return ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][start.getDay()] + " · " + at
}

// ---- The event editor. A draft is plain fields, as typed; draftArgs turns
//      it into calendar-ctl arguments, sending only what changed.

// "9", "9:30", "0930", "14:30", "2pm", "2:30 pm" -> minutes after midnight, or -1.
function parseClock(text) {
  var m = String(text || "").trim().toLowerCase().match(/^(\d{1,2})(?::?(\d{2}))?\s*(am|pm|a|p)?$/)
  if (!m) return -1
  var h = Number(m[1]), min = m[2] ? Number(m[2]) : 0
  if (min > 59) return -1
  if (m[3]) {
    if (h < 1 || h > 12) return -1
    h = h % 12 + (m[3].charAt(0) === "p" ? 12 : 0)
  } else if (h > 23) return -1
  return h * 60 + min
}

// "2026-10-02" (or "2026-10-2") -> "2026-10-02", or "" when it isn't a real date.
function parseDateText(text) {
  var m = String(text || "").trim().match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/)
  if (!m) return ""
  var d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  if (d.getMonth() !== Number(m[2]) - 1 || d.getDate() !== Number(m[3])) return ""
  return keyForDate(d)
}

function clockInput(minutes) {
  return pad(Math.floor(minutes / 60)) + ":" + pad(minutes % 60)
}

function minutesOf(date) { return date.getHours() * 60 + date.getMinutes() }

// A draft from an agenda/grid row (see indexEvents).
function eventDraft(ev) {
  var d = {
    mode: "edit", uid: ev.uid, calendar: ev.account + "/" + ev.calendar,
    title: ev.title === "(no title)" ? "" : ev.title, location: ev.location || "",
    allDay: String(ev.start).length === 10, invite: "", series: false, recurring: !!ev.recurring,
    busy: ev.busy !== false, guests: ev.guests || [], invited: [], uninvited: [], guestText: ""
  }
  if (d.allDay) {
    d.date = ev.start; d.endDate = addDays(ev.end, -1); d.from = "09:00"; d.to = "10:00"
  } else {
    var s = new Date(ev.start), e = new Date(ev.end)
    d.date = keyForDate(s); d.endDate = keyForDate(e)
    d.from = clockInput(minutesOf(s)); d.to = clockInput(minutesOf(e))
  }
  d.original = { title: d.title, location: d.location, allDay: d.allDay, busy: d.busy,
                 date: d.date, endDate: d.endDate, from: d.from, to: d.to }
  return d
}

// A new event on dayKey: the next whole hour today, 9am on any other day.
function newDraft(dayKey, now, calendarRef) {
  var start = dayKey === keyForDate(now) ? Math.min(23 * 60, (now.getHours() + 1) * 60) : 9 * 60
  return { mode: "create", uid: "", calendar: calendarRef || "", title: "", location: "",
           allDay: false, date: dayKey, endDate: dayKey,
           from: clockInput(start), to: clockInput(Math.min(start + 60, 23 * 60 + 59)),
           invite: "", series: false, recurring: false, busy: true, original: null,
           guests: [], invited: [], uninvited: [], guestText: "" }
}

// { args: [...] } for calendar-ctl, or { error: "what to fix" }.
function draftArgs(d) {
  var date = parseDateText(d.date), endDate = parseDateText(d.endDate || d.date)
  if (!date) return { error: "The start date should look like 2026-10-02." }
  if (!endDate) return { error: "The end date should look like 2026-10-02." }
  var start, end
  if (d.allDay) {
    if (endDate < date) return { error: "The last day can't be before the first." }
    start = date; end = addDays(endDate, 1)
  } else {
    var f = parseClock(d.from), t = parseClock(d.to)
    if (f < 0) return { error: "The start time should look like 14:30 or 2:30pm." }
    if (t < 0) return { error: "The end time should look like 15:30 or 3:30pm." }
    // An end at or before the start on the same day means it runs past midnight.
    if (endDate === date && t <= f) endDate = addDays(date, 1)
    if (endDate < date) return { error: "The end can't be before the start." }
    start = date + " " + clockInput(f); end = endDate + " " + clockInput(t)
  }
  var args
  if (d.mode === "create") {
    if (!d.calendar) return { error: "Pick a calendar." }
    args = ["create", d.calendar, "--title", d.title, "--start", start, "--end", end]
    if (d.allDay) args.push("--all-day")
    args.push(d.busy === false ? "--free" : "--busy")
    if (d.location) args.push("--location", d.location)
    var people = parseAddresses(d.invite)
    if (people.error) return people
    for (var i = 0; i < people.list.length; i++) args.push("--invite", people.list[i])
    return { args: args }
  }
  var o = d.original || {}
  args = ["update", d.uid]
  if (d.title !== o.title) args.push("--title", d.title)
  if (d.location !== o.location) args.push("--location", d.location)
  if (d.busy !== o.busy) args.push(d.busy ? "--busy" : "--free")
  var timesChanged = d.allDay !== o.allDay || d.date !== o.date || d.endDate !== o.endDate
                     || (!d.allDay && (d.from !== o.from || d.to !== o.to))
  if (timesChanged) {
    if (d.series) return { error: "A whole series can't be moved from here: untick it to move this one." }
    args.push("--start", start, "--end", end, d.allDay ? "--all-day" : "--timed")
  }
  // Guests: the ones added and taken off, and any still typed in the box.
  var g = guestEdit(d.guests, d.invited, d.uninvited, d.guestText)
  if (g.error) return g
  for (var n = 0; n < g.invited.length; n++) args.push("--invite", g.invited[n])
  for (var m = 0; m < g.uninvited.length; m++) args.push("--uninvite", g.uninvited[m])
  if (args.length === 2) return { args: [] }   // nothing changed
  if (d.series) args.push("--series")
  return { args: args }
}

// ---- Guests

var EMAIL = /^[^@\s,;<>"']+@[^@\s,;<>"']+\.[^@\s,;<>"']+$/

// Addresses typed into one box, split on spaces, commas or semicolons:
// { list } lower-cased and each once, or { error }.
function parseAddresses(text) {
  var parts = String(text || "").split(/[\s,;]+/).filter(function(x) { return x })
  var list = []
  for (var i = 0; i < parts.length; i++) {
    if (!EMAIL.test(parts[i])) return { error: parts[i] + " isn't an email address." }
    var a = parts[i].toLowerCase()
    if (list.indexOf(a) < 0) list.push(a)
  }
  return { list: list }
}

// The guest changes so far, with text typed in the box added to them:
// { invited, uninvited } or { error }. Typing back someone just taken off
// undoes that instead.
function guestEdit(guests, invited, uninvited, text) {
  var parsed = parseAddresses(text)
  if (parsed.error) return parsed
  var have = {}
  for (var i = 0; i < (guests || []).length; i++) have[String(guests[i].email).toLowerCase()] = true
  var add = (invited || []).slice(), drop = (uninvited || []).slice()
  for (var j = 0; j < parsed.list.length; j++) {
    var a = parsed.list[j], k = drop.indexOf(a)
    if (k >= 0) drop.splice(k, 1)
    else if (have[a] || add.indexOf(a) >= 0) return { error: a + " is already invited." }
    else add.push(a)
  }
  return { invited: add, uninvited: drop }
}

// Take a guest off (or, for one added in this edit, just forget them).
function guestRemove(invited, uninvited, email) {
  var a = String(email).toLowerCase()
  var add = (invited || []).filter(function(x) { return x !== a })
  if (add.length !== (invited || []).length) return { invited: add, uninvited: (uninvited || []).slice() }
  var drop = (uninvited || []).slice()
  if (drop.indexOf(a) < 0) drop.push(a)
  return { invited: add, uninvited: drop }
}

var ANSWER_LABELS = { accepted: "Yes", tentative: "Maybe", declined: "No", needsAction: "Waiting" }

// The rows the editor lists: each guest, with what this edit will do to them.
// The organiser has no answer to show: it's their meeting.
function guestRows(guests, invited, uninvited) {
  var rows = []
  for (var i = 0; i < (guests || []).length; i++) {
    var g = guests[i], email = String(g.email || "")
    var named = !!g.name && g.name.toLowerCase() !== email.toLowerCase()
    var tags = []
    if (g.organizer) tags.push("organiser")
    if (g.me) tags.push("you")
    if (g.optional) tags.push("optional")
    if (g.room) tags.push("room")
    rows.push({ email: email, title: named ? g.name : email, detail: named ? email : "",
                response: g.organizer ? "" : g.response,
                answer: g.organizer ? "" : ANSWER_LABELS[g.response] || "Waiting", tags: tags.join(", "),
                fixed: !!g.organizer || !!g.me,
                pending: (uninvited || []).indexOf(email.toLowerCase()) >= 0 ? "remove" : "" })
  }
  for (var j = 0; j < (invited || []).length; j++)
    rows.push({ email: invited[j], title: invited[j], detail: "", response: "", answer: "Invite",
                tags: "", fixed: false, pending: "add" })
  return rows
}

// "5 guests · 3 yes, 1 maybe, 1 waiting": the people invited, so not the
// organiser, who has nothing to answer.
function guestSummary(guests, total) {
  var n = { accepted: 0, tentative: 0, declined: 0, needsAction: 0 }, hosts = 0
  for (var i = 0; i < (guests || []).length; i++) {
    if (guests[i].organizer) { hosts++; continue }
    n[guests[i].response in n ? guests[i].response : "needsAction"]++
  }
  var count = Math.max(total || 0, (guests || []).length) - hosts
  var parts = []
  if (n.accepted) parts.push(n.accepted + " yes")
  if (n.tentative) parts.push(n.tentative + " maybe")
  if (n.declined) parts.push(n.declined + " no")
  if (n.needsAction) parts.push(n.needsAction + " waiting")
  return count + (count === 1 ? " guest" : " guests") + (parts.length ? " · " + parts.join(", ") : "")
}

if (typeof module !== "undefined") {
  module.exports = {
    dateKey: dateKey,
    keyForDate: keyForDate,
    normalizedWeekStart: normalizedWeekStart,
    weekStartSettingName: weekStartSettingName,
    toggledWeekStart: toggledWeekStart,
    weekdayOrder: weekdayOrder,
    isoWeek: isoWeek,
    dayOfYear: dayOfYear,
    daysInYear: daysInYear,
    yearProgress: yearProgress,
    yearProgressPercent: yearProgressPercent,
    parseAge: parseAge,
    parseBirthYear: parseBirthYear,
    ageFromBirthYear: ageFromBirthYear,
    parseLifeExpectancy: parseLifeExpectancy,
    lifeProgress: lifeProgress,
    lifeProgressPercent: lifeProgressPercent,
    monthGrid: monthGrid,
    stepMonth: stepMonth,
    clockFormats: clockFormats,
    clockFormatRing: clockFormatRing,
    nextClockFormat: nextClockFormat,
    isoWeekLiteral: isoWeekLiteral,
    colorFor: colorFor,
    addDays: addDays,
    eventDays: eventDays,
    indexEvents: indexEvents,
    dayColors: dayColors,
    viewDays: viewDays,
    stepAnchor: stepAnchor,
    rangeTitle: rangeTitle,
    dayLayout: dayLayout,
    hourRange: hourRange,
    busyLevel: busyLevel,
    reminderTimes: reminderTimes,
    dueReminders: dueReminders,
    dueSnoozes: dueSnoozes,
    reminderText: reminderText,
    parseAddresses: parseAddresses,
    guestEdit: guestEdit,
    guestRemove: guestRemove,
    guestRows: guestRows,
    guestSummary: guestSummary
  }
}
