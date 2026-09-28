import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

// The clock's calendar popup: a month grid with ISO week numbers, built to
// sit beside the weather panel — same hero-over-detail composition, same
// spacing scale, same small-caps labels.
//
// The grid is a read-out rather than a picker: today is the only marked
// day, and the only thing that moves is which month is on screen —
// chevrons, the scroll wheel, and the arrow keys all step it.
//
// BarWidget.qml owns the bar label and hands this panel the button to
// anchor against.
Panel {
  id: root
  moduleName: "blacksheep.calendar"
  ipcTarget: "blacksheep.calendar"
  manageIpc: false

  property var anchorItem: null

  // The bar tracks the widget mounted in its slot — BarWidget.qml — not this
  // nested panel. Everything the bar identifies a panel by has to be that
  // widget: the popout coordinator (and with it the open-panel dot under the
  // pill) compares against `slot.activeItem`, and switchPanelFrom looks the
  // slot up the same way.
  property var hostWidget: null
  readonly property var barIdentity: hostWidget || root

  // ---- Today. SystemClock keeps this honest across midnight so the
  //      highlight rolls over without the panel being reopened.
  property date today: new Date()
  readonly property string todayKey: Model.keyForDate(today)

  // The month on screen. Stepping moves this and nothing else: the grid is
  // a read-out, not a picker, so there is no per-day cursor to keep in sync.
  property int viewYear: today.getFullYear()
  property int viewMonth: today.getMonth()

  readonly property date viewDate: new Date(viewYear, viewMonth, 1)
  readonly property bool viewingCurrentMonth: viewYear === today.getFullYear() && viewMonth === today.getMonth()

  // Pinned to today, not to the month being browsed — stepping through the
  // calendar does not change how much of the year is gone.
  readonly property real yearDone: Model.yearProgress(today.getFullYear(), today.getMonth(), today.getDate())
  readonly property int yearDonePercent: Model.yearProgressPercent(today.getFullYear(), today.getMonth(), today.getDate())

  // Memento mori, for anyone who goes looking: double-tapping the year bar
  // asks for a birth year and a life expectancy, and a second bar tracks one
  // against the other. A birth year rather than an age, so it keeps counting
  // on its own. Without one the bar stays hidden.
  readonly property int birthYear: Model.parseBirthYear(setting("birthYear", 0), today.getFullYear())
  readonly property int age: Model.ageFromBirthYear(birthYear, today.getFullYear())
  readonly property int lifeExpectancy: Model.parseLifeExpectancy(setting("lifeExpectancy", 0))
  readonly property real lifeDone: Model.lifeProgress(age, lifeExpectancy)
  readonly property int lifeDonePercent: Model.lifeProgressPercent(age, lifeExpectancy)
  property bool editingLife: false

  // Unset falls through to the locale's own first day, so a fresh install
  // starts out matching the rest of the desktop rather than a hardcoded
  // convention. Clicking the grid's "W" heading writes the choice back to
  // shell.json.
  readonly property int weekStart: Model.normalizedWeekStart(setting("weekStartDay", null), Qt.locale().firstDayOfWeek)
  // The interface is English throughout, so day names are not taken from the
  // system locale. Where the week starts still is: that is a regional
  // convention rather than a translation, and it stays overridable above.
  readonly property var labelLocale: Qt.locale("en_US")
  readonly property string nextWeekStartLabel: labelLocale.dayName(Model.toggledWeekStart(weekStart), Locale.LongFormat)
  readonly property var weekdays: Model.weekdayOrder(weekStart)
  readonly property var weeks: Model.monthGrid(viewYear, viewMonth, weekStart, todayKey)


  // Guarded so the widget renders before the bar is injected (the bar-widget
  // contract instantiates it bare).
  readonly property color contentForeground: bar ? bar.foreground : Color.foreground
  readonly property string contentFontFamily: bar ? bar.fontFamily : Style.font.family

  readonly property int cellWidth: Style.space(52)
  readonly property int cellHeight: Style.space(34)
  readonly property int cellSpacing: Style.space(2)
  readonly property int weekColumnWidth: Style.space(32)
  readonly property int gutterWidth: Style.space(14)

  // ---- Events. scripts/calendar-sync keeps a private copy of every
  //      calendar in events.json; this panel only ever reads it, and runs
  //      the sync on a timer so the file stays fresh.
  readonly property string home: Quickshell.env("HOME")
  readonly property string pluginDir: home + "/.config/omarchy/plugins/blacksheep.calendar"
  readonly property string eventsPath: home + "/.cache/blacksheep.calendar/events.json"
  // Times follow the bar's own clock: a format with AP or ap is 12-hour.
  readonly property bool use24h: !/ap/i.test(String(setting("format", "HH:mm")))
  property var eventIndex: Model.indexEvents(null, root.use24h)
  property string selectedKey: root.todayKey
  readonly property var selectedEvents: root.eventIndex.byDay[root.selectedKey] || []
  readonly property var problemAccounts: root.eventIndex.accounts.filter(function(a) { return a.status !== "ok" })
  property real lastSyncAt: 0

  // ---- Views. Month is the stock grid; day, week and working week are time
  //      grids; year is twelve small months. Remembered in shell.json.
  readonly property var viewOptions: [
    { label: "Day", value: "day", tooltip: "One day (1)" },
    { label: "Week", value: "week", tooltip: "Seven days (2)" },
    { label: "Work week", value: "workweek", tooltip: "Monday to Friday (3)" },
    { label: "Month", value: "month", tooltip: "The month grid (4)" },
    { label: "Year", value: "year", tooltip: "Twelve months (5)" }
  ]
  property string viewMode: Model.VIEWS.indexOf(String(setting("view", "month"))) >= 0 ? String(setting("view", "month")) : "month"
  readonly property bool isTimeView: viewMode === "day" || viewMode === "week" || viewMode === "workweek"

  function setView(v) {
    if (Model.VIEWS.indexOf(v) < 0 || v === root.viewMode) return
    root.viewMode = v
    root.showSelectedMonth()
    persistSettings({ view: v })
  }

  // Previous and Next: a month in the month view, otherwise the view's own unit.
  function step(delta) {
    if (root.viewMode === "month") { root.moveMonth(delta); return }
    root.selectedKey = Model.stepAnchor(root.viewMode, root.selectedKey, delta)
    root.showSelectedMonth()
  }

  function showSelectedMonth() {
    var d = Model.keyToDate(root.selectedKey)
    root.viewYear = d.getFullYear()
    root.viewMonth = d.getMonth()
  }

  // The app layout (ModernLayout.qml) unless the setting asks for the stock one.
  readonly property bool modern: String(setting("layout", "modern")) !== "classic"
  readonly property bool syncing: syncProc.running

  function pickDay(key) {
    root.selectedKey = key
    root.showSelectedMonth()
  }

  // Show or hide a calendar from the rail. The ctl saves the choice and syncs
  // (a calendar shown again is fetched in full), and events.json follows.
  function toggleCalendar(c) {
    root.runWrite("cal:" + c.ref, [c.shown ? "hide" : "show", c.account, c.id])
  }

  function removeDraftEvent(series) {
    root.runWrite(root.draftEvent.uid, ["delete", root.draftEvent.uid].concat(series ? ["--series"] : []))
  }

  function respondFromEditor(answer, series) {
    root.runWrite(root.draftEvent.uid, ["respond", root.draftEvent.uid, answer].concat(series ? ["--series"] : []))
  }

  // From the year: the month, on today if it's in it, else on its first day.
  function openMonth(month) {
    var y = Model.keyToDate(root.selectedKey).getFullYear()
    var t = Model.keyToDate(root.todayKey)
    root.selectedKey = t.getFullYear() === y && t.getMonth() === month ? root.todayKey : Model.dateKey(y, month, 1)
    root.viewMode === "month" ? root.showSelectedMonth() : root.setView("month")
  }

  function openDay(key) {
    root.selectedKey = key
    root.setView("day")
    root.showSelectedMonth()
  }

  property var eventData: null

  function ingest(text) {
    try {
      root.eventData = JSON.parse(text)
      root.eventIndex = Model.indexEvents(root.eventData, root.use24h)
    } catch (e) {
      // A half-written file can't happen (the sync renames into place), so a
      // parse error means a damaged cache: keep what is on screen.
    }
  }

  function syncNow() {
    if (syncProc.running) return
    root.lastSyncAt = Date.now()
    syncProc.running = true
  }

  function openUrl(url) {
    // Only ever a link the sync vetted: https, and for joins a known host.
    if (!/^https:\/\//.test(String(url || ""))) return
    urlProc.command = ["xdg-open", String(url)]
    urlProc.running = true
  }

  // ---- Writes (calendar-ctl, one at a time). The ctl patches the local copy
  //      and syncs, so events.json changes and the panel follows by itself.
  property string writingUid: ""

  function respond(ev, answer, series) {
    root.runWrite(ev.uid, ["respond", ev.uid, answer].concat(series ? ["--series"] : []))
  }

  // A write from the editor closes it when it lands; a failure is said in the
  // editor if it is open, and in a notification otherwise.
  function runWrite(uid, args) {
    if (writeProc.running || !args.length) return
    root.writingUid = uid || "new"
    root.editorError = ""
    writeProc.fromEditor = root.editorOpen
    writeProc.command = [root.pluginDir + "/scripts/calendar-ctl"].concat(args)
    writeProc.running = true
  }

  Process {
    id: writeProc
    property bool fromEditor: false
    stderr: StdioCollector { id: writeErr; waitForEnd: true }
    onExited: function(code) {
      root.writingUid = ""
      if (code === 0) {
        if (fromEditor) root.closeEditor()
        return
      }
      var msg = String(writeErr.text || "").trim().replace(/^calendar-ctl: /, "") || "the change wasn't made"
      msg = msg.charAt(0).toUpperCase() + msg.slice(1)
      if (fromEditor && root.editorOpen) {
        root.editorError = msg
        return
      }
      failProc.command = ["omarchy-notification-send", "-g", "󰃭", "-u", "normal", "--app-name", "Calendar",
                          "Calendar: not saved", msg]
      failProc.running = true
    }
  }

  // ---- The event editor (EventEditor.qml). Open, the panel's own keys step
  //      aside so typing goes into the fields.
  property var draft: null
  property var draftEvent: null
  property string editorError: ""
  readonly property bool editorOpen: draft !== null

  readonly property var editableCalendars: {
    var out = []
    var cals = (root.eventData && root.eventData.calendars) || []
    for (var i = 0; i < cals.length; i++) {
      var c = cals[i]
      if (c.shown && c.editable) out.push({ value: c.account + "/" + c.id, label: c.account + ": " + (c.name || c.id), primary: c.primary })
    }
    return out
  }

  function defaultCalendar() {
    var saved = String(setting("defaultCalendar", "") || "")
    var list = root.editableCalendars
    for (var i = 0; i < list.length; i++) if (list[i].value === saved) return saved
    for (var j = 0; j < list.length; j++) if (list[j].primary) return list[j].value
    return list.length ? list[0].value : ""
  }

  function openEditor(ev) {
    if (!ev || !ev.uid) return
    root.editorError = ""
    root.draftEvent = ev
    root.draft = Model.eventDraft(ev)
  }

  function newEvent() {
    root.editorError = ""
    root.draftEvent = null
    root.draft = Model.newDraft(root.selectedKey, new Date(), root.defaultCalendar())
  }

  function closeEditor() {
    root.draft = null
    root.draftEvent = null
    root.editorError = ""
    Qt.callLater(function() { if (keyCatcher) keyCatcher.forceActiveFocus() })
  }

  function saveDraft(d) {
    var out = Model.draftArgs(d)
    if (out.error) { root.editorError = out.error; return }
    if (!out.args.length) { root.closeEditor(); return }
    if (d.mode === "create" && d.calendar !== setting("defaultCalendar", "")) persistSettings({ defaultCalendar: d.calendar })
    root.runWrite(d.uid, out.args)
  }

  Process { id: failProc }

  function chooseCalendars() {
    termProc.command = ["omarchy-launch-floating-terminal-with-presentation",
                        root.pluginDir + "/scripts/calendar-ctl choose"]
    termProc.running = true
    root.close()
  }

  function selectDay(cell) {
    root.selectedKey = cell.key
    // Clicking a leading or trailing day from a neighbouring month goes there.
    if (!cell.inMonth) {
      root.viewYear = cell.year
      root.viewMonth = cell.month
    }
  }

  FileView {
    id: eventsFile
    path: root.eventsPath
    watchChanges: true
    onFileChanged: reload()
    onLoaded: root.ingest(text())
  }

  Process {
    id: syncProc
    command: [root.pluginDir + "/scripts/calendar-sync", "--quiet"]
  }

  // ---- Reminders (see Model.dueReminders). What has fired is kept in the
  //      runtime directory, so a shell reload never repeats a reminder, and a
  //      reboot starts clean.
  readonly property bool remindersOn: setting("reminders", true) !== false
  property var fired: ({})
  property bool firedLoaded: false

  FileView {
    id: firedFile
    path: (Quickshell.env("XDG_RUNTIME_DIR") || (root.home + "/.cache")) + "/blacksheep.calendar-reminded.json"
    printErrors: false
    onLoaded: {
      try { root.fired = JSON.parse(text()) || {} } catch (e) { root.fired = {} }
      root.firedLoaded = true
    }
    onLoadFailed: root.firedLoaded = true
  }

  readonly property int snoozeMinutes: 5
  property date clockNow: new Date()

  function checkReminders() {
    if (!root.remindersOn || !root.eventData || !root.firedLoaded) return
    var now = Date.now()
    var fired = root.fired
    var due = Model.dueReminders(root.eventData, root.eventIndex.calendars, now, fired)
    for (var i = 0; i < due.length; i++) {
      for (var j = 0; j < due[i].also.length; j++) fired[due[i].also[j]] = now
      fired["shown:" + due[i].event.uid] = now
      root.notify(due[i])
    }
    // Snoozed reminders come back once their time is up, while the event runs.
    var snoozed = Model.dueSnoozes(root.eventData, fired, now)
    for (var k = 0; k < snoozed.length; k++) {
      delete fired["snooze:" + snoozed[k].event.uid]
      fired["shown:" + snoozed[k].event.uid] = now
      root.notify(snoozed[k])
    }
    if (!due.length && !snoozed.length) return
    // Forget anything over a day old: the file stays small.
    // (A pending snooze is in the future, so it always stays.)
    for (var id in fired) if (now - fired[id] > 86400000) delete fired[id]
    root.saveFired(fired)
  }

  function saveFired(fired) {
    root.fired = Object.assign({}, fired)
    firedFile.setText(JSON.stringify(fired))
  }

  // One process per reminder: notify-send -A waits for the button pressed,
  // and one reminder waiting must never hold up the next.
  //
  // The title and body come from invitations anyone can send, so "--" ends
  // notify-send's options before them: a title like "--hint=..." or "-u" is
  // then only ever text (the reason omarchy-notification-send avoids
  // notify-send altogether). The glyph is a hint, as Omarchy sends it.
  function notify(r) {
    var e = r.event
    var cal = root.eventIndex.calendars[e.account + "/" + e.calendar] || {}
    var text = Model.reminderText(r, cal.name || e.account, root.use24h)
    var url = e.join ? e.join.url : e.webLink
    var args = ["notify-send", "--app-name=Calendar", "--urgency=normal",
                "--hint=string:omarchy-glyph:󰃭",
                "--action=snooze=Snooze " + root.snoozeMinutes + " min"]
    if (/^https:\/\//.test(String(url || "")))
      // The exec hint is what Omarchy runs on a click, and it survives into
      // the notification history; "default" is for other servers.
      args = args.concat(["--hint=string:omarchy-exec-argv:" + JSON.stringify(["xdg-open", String(url)]),
                          "--action=default=" + (e.join ? "Join" : "Open")])
    args = args.concat(["--", text.headline, text.body])
    var p = Qt.createQmlObject('import Quickshell.Io; Process { stdout: StdioCollector { waitForEnd: true } }', root)
    p.stdout.streamFinished.connect(function() {
      var action = String(p.stdout.text || "").trim()
      if (action === "snooze") root.snooze(e)
      else if (action === "default") root.openUrl(url)
      p.destroy()
    })
    p.command = args
    p.running = true
  }

  function snooze(e) {
    var fired = Object.assign({}, root.fired)
    fired["snooze:" + e.uid] = Date.now() + root.snoozeMinutes * 60000
    delete fired["shown:" + e.uid]
    root.saveFired(fired)
  }

  // Snooze is offered for 15 minutes after a reminder pops up, until the
  // event ends; not while a snooze is already pending.
  function canSnooze(e, fired, now) {
    var at = fired["shown:" + e.uid]
    if (!at || fired["snooze:" + e.uid]) return false
    var t = now.getTime()
    var end = String(e.end).length === 10 ? Model.keyToDate(e.end).getTime() : new Date(e.end).getTime()
    return t - at < 15 * 60000 && t < end
  }

  Timer {
    interval: 20000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: {
      root.clockNow = new Date()
      root.checkReminders()
    }
  }

  Process { id: urlProc }
  Process { id: termProc }

  // Every three minutes, whether or not the panel is open: reminders and the
  // bar need fresh data too, and a pass that finds nothing new costs a few
  // small requests.
  Timer {
    interval: 180000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.syncNow()
  }

  function open() {
    refresh()
    root.controller.show()
    // Set after showing, not before: showing hands the popout coordinator
    // over, which closes whichever panel was open, and that close clears the
    // shared flag. Deferring means the panel taking over always wins, while
    // a handoff to a panel that does not manage the flag still leaves it
    // cleared rather than stuck on.
    Qt.callLater(function() {
      if (root.opened) setCenterHoverRevealSuppressed(true)
    })
  }

  function close() {
    setCenterHoverRevealSuppressed(false)
    // Dismissing the panel mid-edit would otherwise leave the inputs up,
    // waiting behind a closed popup for the next time it opens.
    if (root.editingLife) root.cancelEditingLife()
    if (root.editorOpen && !writeProc.running) root.closeEditor()
    root.controller.hide()
  }

  function toggle() {
    if (root.opened) root.close()
    else root.open()
  }

  function switchPanel(direction) {
    if (root.bar && typeof root.bar.switchPanelFrom === "function")
      return root.bar.switchPanelFrom(root.barIdentity, direction)
    return false
  }

  // Summoning by hotkey moves no pointer, so a hover the bar was still
  // holding must not keep the center indicators revealed behind the panel.
  function setCenterHoverRevealSuppressed(value) {
    if (root.bar && typeof root.bar.setCenterHoverRevealSuppressed === "function")
      root.bar.setCenterHoverRevealSuppressed(value)
    else if (root.bar && "centerHoverRevealSuppressed" in root.bar)
      root.bar.centerHoverRevealSuppressed = value
  }

  function refresh() {
    root.today = new Date()
    root.goToToday()
    root.selectedKey = root.todayKey
    // Opening the panel is when stale data shows; a minute is fresh enough.
    if (Date.now() - root.lastSyncAt > 60000) root.syncNow()
  }

  function goToToday() {
    root.viewYear = today.getFullYear()
    root.viewMonth = today.getMonth()
    root.selectedKey = root.todayKey
  }

  function moveMonth(delta) {
    var next = Model.stepMonth(viewYear, viewMonth, delta)
    root.viewYear = next.year
    root.viewMonth = next.month
  }

  function moveYear(delta) {
    moveMonth(delta * 12)
  }

  // Applied locally first so the panel redraws on the click itself; the
  // shell.json write comes back through the bar as the same value. With no
  // writable entry (the widget is not in the layout) it stays a session-only
  // preference rather than doing nothing. The host widget builds its own
  // entry when the label format is cycled, so it has to be kept in step or
  // it would write this key straight back out from a stale copy.
  function persistSettings(values) {
    var entry = { id: root.moduleName }
    for (var existing in root.settings) if (existing !== "id") entry[existing] = root.settings[existing]
    for (var key in values) entry[key] = values[key]

    root.settings = entry
    if (root.hostWidget && "settings" in root.hostWidget) root.hostWidget.settings = entry
    if (root.bar && root.bar.shell && typeof root.bar.shell.updateEntryInline === "function")
      root.bar.shell.updateEntryInline(root.moduleName, entry)
  }

  function setWeekStart(day) {
    var next = Model.normalizedWeekStart(day, root.weekStart)
    if (next === root.weekStart) return
    persistSettings({ weekStartDay: Model.weekStartSettingName(next) })
  }

  function startEditingLife() {
    root.editingLife = true
    Qt.callLater(function() {
      bornField.text = root.birthYear > 0 ? String(root.birthYear) : ""
      expectancyField.text = String(root.lifeExpectancy)
      bornField.selectAll()
      bornField.forceActiveFocus()
    })
  }

  function cancelEditingLife() {
    root.editingLife = false
    Qt.callLater(function() { if (keyCatcher) keyCatcher.forceActiveFocus() })
  }

  // Shared by both fields: Tab hops to the other one, Enter commits the pair,
  // Escape drops the lot.
  function handleLifeKey(event, other) {
    if (event.key === Qt.Key_Escape) {
      root.cancelEditingLife()
      event.accepted = true
    } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
      root.commitLife()
      event.accepted = true
    } else if (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) {
      other.selectAll()
      other.forceActiveFocus()
      event.accepted = true
    }
  }

  // Double-tapping the life bar puts it away again. The expectancy stays in
  // the config so setting a birth year again brings your own number back
  // rather than the default.
  function clearLife() {
    if (root.birthYear <= 0) return
    persistSettings({ birthYear: 0 })
  }

  function commitLife() {
    var born = Model.parseBirthYear(bornField.text, today.getFullYear())
    var span = Model.parseLifeExpectancy(expectancyField.text)
    if (born !== root.birthYear || span !== root.lifeExpectancy)
      persistSettings({ birthYear: born, lifeExpectancy: span })
    cancelEditingLife()
  }

  function toggleWeekStart() {
    setWeekStart(Model.toggledWeekStart(root.weekStart))
  }

  // English short day names, matching the rest of the interface.
  function weekdayLabel(weekday) {
    return String(labelLocale.dayName(weekday, Locale.ShortFormat)).toUpperCase()
  }

  SystemClock {
    id: clock
    precision: SystemClock.Minutes
    onDateChanged: {
      if (Model.keyForDate(clock.date) === String(root.todayKey)) return
      var followToday = root.viewingCurrentMonth
      root.today = clock.date
      if (followToday) root.goToToday()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    centerOnBar: true
    focusTarget: keyCatcher
    // Wider for a week of columns; the other views keep the stock width.
    // The app layout takes what the screen allows, up to a comfortable size;
    // the stock one is sized by its content.
    contentWidth: root.modern ? panel.fittedContentWidth(Style.space(1240))
                : panel.fittedContentWidth(Style.space(root.viewMode === "week" || root.viewMode === "workweek" ? 900 : 560))
    contentHeight: root.modern ? panel.fittedContentHeight(Style.space(780))
                 : panel.fittedContentHeight(calendarColumn.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: root.editingLife || root.editorOpen
      onMoveRequested: function(dx, dy) {
        if (dx !== 0) root.step(dx)
        if (dy !== 0 && root.viewMode === "month") root.moveYear(dy)
      }
      onActivateRequested: root.goToToday()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) {
        if (t >= "1" && t <= "5") root.setView(Model.VIEWS[Number(t) - 1])
        else if (t === "[") root.step(-1)
        else if (t === "]") root.step(1)
        else if (t === "{") root.moveYear(-1)
        else if (t === "}") root.moveYear(1)
        else if (t === "t" || t === "T") root.goToToday()
        else if (t === "w" || t === "W") root.toggleWeekStart()
        else if (t === "n" || t === "N") root.newEvent()
      }

      ModernLayout {
        visible: root.modern
        anchors.fill: parent
        p: root
      }

      Flickable {
        id: calendarScroll
        visible: !root.modern
        anchors.fill: parent
        contentWidth: calendarColumn.width
        contentHeight: calendarColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height || contentWidth > width

        Column {
          id: calendarColumn
          // Never narrower than the grid. The popup width is capped to what
          // the screen allows, and a fixed seven-column grid would otherwise
          // lose its last days off the edge instead of scrolling.
          width: Math.max(calendarScroll.width, gridColumn.width)
          spacing: Style.space(8)

          // ---- Hero: today, centered. Once the view has stepped back
          //      it is also the way home — clicking the date you are
          //      looking for beats hunting for a reset button.
          Item {
            width: parent.width
            height: heroRow.height

            Row {
              id: heroRow
              anchors.horizontalCenter: parent.horizontalCenter
              spacing: Style.space(22)

              Text {
                // Baseline-aligned, not center-aligned: "July 26" carries a
                // descender, so centering the two boxes leaves the icon
                // sitting visibly low against the digits.
                anchors.baseline: heroDate.baseline
                text: "󰃭"
                color: heroMouse.containsMouse
                  ? Style.hoverStateColor(root.contentForeground, Color.accent)
                  : root.contentForeground
                font.family: root.contentFontFamily
                // Decorative, and deliberately outside the Style.font.*
                // scale. Sized so the glyph reads at the cap height of the
                // date beside it rather than towering over it.
                font.pixelSize: 48
              }

              Text {
                id: heroDate
                textFormat: Text.PlainText
                anchors.verticalCenter: parent.verticalCenter
                text: Qt.formatDate(root.today, "MMMM d")
                color: heroMouse.containsMouse
                  ? Style.hoverStateColor(root.contentForeground, Color.accent)
                  : root.contentForeground
                font.family: root.contentFontFamily
                font.pixelSize: 52
                font.bold: true
              }
            }

            MouseArea {
              id: heroMouse
              x: heroRow.x
              y: heroRow.y
              width: heroRow.width
              height: heroRow.height
              enabled: !root.viewingCurrentMonth
              hoverEnabled: enabled
              cursorShape: Qt.PointingHandCursor
              onClicked: root.goToToday()

              PanelToolTip {
                visible: heroMouse.containsMouse
                text: "Back to today"
                fontFamily: root.contentFontFamily
              }
            }
          }

          // ---- Year progress, doubling as the rule under the hero:
          //      a plain hairline said nothing, and whole days done
          //      over days in the year says the same thing louder.
          Item {
            width: parent.width
            height: yearBlock.y + yearBlock.height

            Item {
              id: yearBlock
              y: Style.space(6)
              anchors.horizontalCenter: parent.horizontalCenter
              width: gridColumn.width
              height: Math.max(yearLabel.implicitHeight, Style.space(10))

              TapHandler {
                enabled: !root.editingLife
                onDoubleTapped: root.startEditingLife()
              }

              Row {
                visible: root.editingLife
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.verticalCenter: parent.verticalCenter
                spacing: Style.space(10)

                Text {
                  anchors.verticalCenter: parent.verticalCenter
                  text: "BORN"
                  color: Qt.darker(root.contentForeground, 1.5)
                  font.family: root.contentFontFamily
                  font.pixelSize: Style.font.bodySmall
                  font.letterSpacing: 1
                }

                TextField {
                  id: bornField
                  width: Style.space(70)
                  anchors.verticalCenter: parent.verticalCenter
                  placeholderText: "year"
                  foreground: root.contentForeground
                  font.family: root.contentFontFamily
                  inputMethodHints: Qt.ImhDigitsOnly

                  Keys.onPressed: function(event) { root.handleLifeKey(event, expectancyField) }
                }

                Text {
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.verticalCenterOffset: 0
                  leftPadding: Style.space(6)
                  text: "LIVE TO"
                  color: Qt.darker(root.contentForeground, 1.5)
                  font.family: root.contentFontFamily
                  font.pixelSize: Style.font.bodySmall
                  font.letterSpacing: 1
                }

                TextField {
                  id: expectancyField
                  width: Style.space(60)
                  anchors.verticalCenter: parent.verticalCenter
                  placeholderText: "90"
                  foreground: root.contentForeground
                  font.family: root.contentFontFamily
                  inputMethodHints: Qt.ImhDigitsOnly

                  Keys.onPressed: function(event) { root.handleLifeKey(event, bornField) }
                }
              }

              Text {
                id: yearLabel
                textFormat: Text.PlainText
                visible: !root.editingLife
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                text: root.today.getFullYear()
                color: Qt.darker(root.contentForeground, 1.5)
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.bodySmall
                font.letterSpacing: 1
              }

              Text {
                id: yearPercent
                textFormat: Text.PlainText
                visible: !root.editingLife
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                text: root.yearDonePercent + "%"
                color: root.contentForeground
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.bodySmall
              }

              Rectangle {
                id: yearTrack
                visible: !root.editingLife
                anchors.left: yearLabel.right
                anchors.right: yearPercent.left
                anchors.leftMargin: Style.space(12)
                anchors.rightMargin: Style.space(12)
                anchors.verticalCenter: parent.verticalCenter
                height: Style.space(6)
                radius: Style.cornerRadius > 0 ? height / 2 : 0
                color: Qt.rgba(root.contentForeground.r, root.contentForeground.g, root.contentForeground.b, 0.12)

                Rectangle {
                  width: Math.round(parent.width * root.yearDone)
                  height: parent.height
                  radius: parent.radius
                  color: Style.selectedStateColor(root.contentForeground, Color.accent)

                  Behavior on width { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
                }
              }
            }
          }

          // ---- Memento mori. Only here once someone has gone looking and
          //      given an age; the same rail as the year above it, measured
          //      against a nominal lifetime.
          Item {
            visible: root.birthYear > 0
            width: parent.width
            height: visible ? lifeBlock.height : 0

            Item {
              id: lifeBlock
              anchors.horizontalCenter: parent.horizontalCenter
              width: gridColumn.width
              height: Math.max(lifeLabel.implicitHeight, Style.space(10))

              Text {
                id: lifeLabel
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                text: "LIFE"
                color: Qt.darker(root.contentForeground, 1.5)
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.bodySmall
                font.letterSpacing: 1
              }

              Text {
                id: lifePercent
                textFormat: Text.PlainText
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                text: root.lifeDonePercent + "%"
                color: root.contentForeground
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.bodySmall
              }

              Rectangle {
                anchors.left: lifeLabel.right
                anchors.right: lifePercent.left
                anchors.leftMargin: Style.space(12)
                anchors.rightMargin: Style.space(12)
                anchors.verticalCenter: parent.verticalCenter
                height: Style.space(6)
                radius: Style.cornerRadius > 0 ? height / 2 : 0
                color: Qt.rgba(root.contentForeground.r, root.contentForeground.g, root.contentForeground.b, 0.12)

                Rectangle {
                  width: Math.round(parent.width * root.lifeDone)
                  height: parent.height
                  radius: parent.radius
                  color: Style.selectedStateColor(root.contentForeground, Color.accent)

                  Behavior on width { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
                }
              }

              TapHandler {
                onDoubleTapped: root.clearLife()
              }

              MouseArea {
                id: lifeMouse
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.NoButton

                PanelToolTip {
                  visible: lifeMouse.containsMouse
                  text: "Memento Mori"
                  fontFamily: root.contentFontFamily
                }
              }
            }
          }

          // ---- One event, over the views while it is open.
          EventEditor {
            visible: root.editorOpen
            width: Math.min(parent.width, Style.space(520))
            anchors.horizontalCenter: parent.horizontalCenter
            height: visible ? implicitHeight : 0
            draft: root.modern ? null : root.draft
            event: root.draftEvent
            calendars: root.editableCalendars
            saving: root.writingUid !== ""
            error: root.editorError
            foreground: root.contentForeground
            fontFamily: root.contentFontFamily
            onSave: function(d) { root.saveDraft(d) }
            onCancel: root.closeEditor()
            onRemove: function(series) { root.removeDraftEvent(series) }
            onRespond: function(answer, series) { root.respondFromEditor(answer, series) }
            onOpenLink: function(url) { root.openUrl(url) }
          }

          // ---- Which view. Keys 1 to 5 do the same.
          Item {
            visible: !root.editorOpen
            width: parent.width
            height: viewSwitch.implicitHeight

            ButtonGroup {
              id: viewSwitch
              anchors.horizontalCenter: parent.horizontalCenter
              options: root.viewOptions
              value: root.viewMode
              focusable: false
              foreground: root.contentForeground
              fontFamily: root.contentFontFamily
              fontSize: Style.font.bodySmall
              onChanged: function(v) { root.setView(v) }
            }
          }

          // ---- Day, week and working week.
          TimeGrid {
            visible: root.isTimeView && !root.editorOpen
            width: Math.min(parent.width, Style.space(root.viewMode === "day" ? 520 : 880))
            anchors.horizontalCenter: parent.horizontalCenter
            height: implicitHeight
            days: Model.viewDays(root.viewMode, root.selectedKey, root.weekStart)
            byDay: root.eventIndex.byDay
            todayKey: root.todayKey
            use24h: root.use24h
            foreground: root.contentForeground
            fontFamily: root.contentFontFamily
            onOpenEvent: function(ev) { root.openEditor(ev) }
            onJoinEvent: function(url) { root.openUrl(url) }
            onPickDay: function(key) { root.openDay(key) }
          }

          // ---- The year.
          YearView {
            visible: root.viewMode === "year" && !root.editorOpen
            width: parent.width
            height: implicitHeight
            yearNumber: Model.keyToDate(root.selectedKey).getFullYear()
            byDay: root.eventIndex.byDay
            todayKey: root.todayKey
            selectedKey: root.selectedKey
            weekStart: root.weekStart
            foreground: root.contentForeground
            fontFamily: root.contentFontFamily
            onPickDay: function(key) { root.openDay(key) }
            onOpenMonth: function(m) { root.openMonth(m) }
          }

          // ---- Month grid: week numbers down a gutter on the left, then
          //      the seven day columns. Always six rows, so the popup is
          //      exactly as tall in February as it is in August.
          Item {
            visible: root.viewMode === "month" && !root.editorOpen
            width: parent.width
            height: gridColumn.y + gridColumn.height

            WheelHandler {
              onWheel: function(event) {
                // Horizontal wheels and touchpad side-scrolls report y === 0;
                // without this they would every one read as "next month".
                if (event.angleDelta.y === 0) return
                root.moveMonth(event.angleDelta.y > 0 ? -1 : 1)
              }
            }

            Column {
              id: gridColumn
              // The meter above is a solid rule; the grid needs room to
              // read as its own block rather than hanging off it.
              y: Style.space(18)
              anchors.horizontalCenter: parent.horizontalCenter
              spacing: Style.space(3)

              Row {
                id: headerRow
                spacing: root.cellSpacing

                // The week-number heading doubles as the week-start toggle.
                // It is the one control in the panel whose meaning is not
                // self-evident, so it carries a tooltip naming the day the
                // click will switch to.
                Rectangle {
                  width: root.weekColumnWidth
                  height: Style.space(16)
                  radius: Style.cornerRadius
                  color: weekStartMouse.containsMouse
                    ? Style.hoverFillFor(root.contentForeground, Color.accent)
                    : "transparent"

                  Text {
                    anchors.centerIn: parent
                    text: "W"
                    color: weekStartMouse.containsMouse
                      ? Style.hoverStateColor(root.contentForeground, Color.accent)
                      : Qt.darker(root.contentForeground, 1.9)
                    font.family: root.contentFontFamily
                    font.pixelSize: Style.font.caption
                    font.letterSpacing: 1
                    font.bold: true
                  }

                  MouseArea {
                    id: weekStartMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.toggleWeekStart()
                  }

                  PanelToolTip {
                    visible: weekStartMouse.containsMouse
                    text: "Start weeks on " + root.nextWeekStartLabel
                    fontFamily: root.contentFontFamily
                  }
                }

                Item {
                  width: root.gutterWidth
                  height: Style.space(16)
                }

                Repeater {
                  model: root.weekdays

                  Text {
                    textFormat: Text.PlainText
                    required property var modelData
                    width: root.cellWidth
                    height: Style.space(16)
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    text: root.weekdayLabel(modelData)
                    color: Qt.darker(root.contentForeground, 1.5)
                    font.family: root.contentFontFamily
                    font.pixelSize: Style.font.caption
                    font.letterSpacing: 1
                    font.bold: true
                  }
                }
              }

              Repeater {
                model: root.weeks

                Row {
                  required property var modelData
                  spacing: root.cellSpacing

                  Text {
                    textFormat: Text.PlainText
                    width: root.weekColumnWidth
                    height: root.cellHeight
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    text: modelData.week
                    color: Qt.darker(root.contentForeground, 1.9)
                    font.family: root.contentFontFamily
                    font.pixelSize: Style.font.caption
                  }

                  Item {
                    width: root.gutterWidth
                    height: root.cellHeight
                  }

                  Repeater {
                    model: modelData.days

                    Rectangle {
                      id: dayCell
                      required property var modelData
                      readonly property var dayEvents: root.eventIndex.byDay[modelData.key] || []
                      readonly property var dots: Model.dayColors(dayEvents, 3)
                      readonly property bool selected: modelData.key === root.selectedKey

                      width: root.cellWidth
                      height: root.cellHeight
                      radius: Style.cornerRadius
                      // Today is outlined, not filled: a lit-up block shouts
                      // over a grid this quiet. The selected day, when it
                      // isn't today, gets a quieter fill.
                      color: dayMouse.containsMouse
                        ? Style.hoverFillFor(root.contentForeground, Color.accent)
                        : (selected && !modelData.today
                          ? Qt.rgba(root.contentForeground.r, root.contentForeground.g, root.contentForeground.b, 0.08)
                          : "transparent")
                      border.width: modelData.today || selected ? Style.spacing.hairline : 0
                      border.color: modelData.today
                        ? Style.normalBorderFor(root.contentForeground, Color.accent)
                        : Qt.rgba(root.contentForeground.r, root.contentForeground.g, root.contentForeground.b, 0.25)

                      MouseArea {
                        id: dayMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.selectDay(dayCell.modelData)
                      }

                      // One dot per calendar with something on this day.
                      Row {
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: Style.space(4)
                        spacing: Style.space(3)
                        Repeater {
                          model: dayCell.dots
                          Rectangle {
                            required property var modelData
                            width: Style.space(4)
                            height: width
                            radius: width / 2
                            color: modelData
                            opacity: dayCell.modelData.inMonth ? 0.95 : 0.4
                          }
                        }
                      }

                      Text {
                        textFormat: Text.PlainText
                        anchors.centerIn: parent
                        anchors.verticalCenterOffset: dayCell.dots.length ? -Style.space(3) : 0
                        text: modelData.day
                        color: modelData.inMonth
                          ? (modelData.weekend ? Qt.darker(root.contentForeground, 1.45) : root.contentForeground)
                          : Qt.darker(root.contentForeground, 2.2)
                        font.family: root.contentFontFamily
                        font.pixelSize: Style.font.body
                        font.bold: modelData.today
                      }
                    }
                  }
                }
              }
            }

            // Hairline down the week-number gutter, drawn only beside the
            // day rows so it does not cut through the header band.
            Rectangle {
              x: gridColumn.x + root.weekColumnWidth + root.cellSpacing + Math.round((root.gutterWidth - width) / 2)
              y: gridColumn.y + headerRow.height + gridColumn.spacing
              width: Style.spacing.hairline
              height: gridColumn.height - headerRow.height - gridColumn.spacing
              color: root.contentForeground
              opacity: 0.1
            }
          }

          // ---- Month stepping, spanning the grid it drives. The chevrons
          //      sit on the grid's outer bounds, the same edges the year
          //      rail above uses, so the row reads as the panel's other
          //      full-width rail instead of a cluster floating in space.
          //      The label is centered and fixed-width, so it holds still
          //      from "MAY" to "SEPTEMBER".
          Item {
            visible: !root.editorOpen
            width: parent.width
            height: monthNav.height

            Item {
              id: monthNav
              anchors.horizontalCenter: parent.horizontalCenter
              width: gridColumn.width
              height: monthLabel.implicitHeight + Style.space(10)

              Text {
                id: monthLabel
                textFormat: Text.PlainText
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.verticalCenter: parent.verticalCenter
                // Fixed width so the chevrons hold still between a
                // "MAY 2026" and a "SEPTEMBER 2026".
                width: Style.space(root.viewMode === "month" ? 130 : 320)
                horizontalAlignment: Text.AlignHCenter
                text: (root.viewMode === "month"
                  ? Qt.formatDate(root.viewDate, "MMMM yyyy")
                  : Model.rangeTitle(root.viewMode, root.selectedKey, root.weekStart)).toUpperCase()
                color: Qt.darker(root.contentForeground, 1.4)
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.body
                font.letterSpacing: 1
              }

              PanelActionButton {
                // Pulled out by the button's own padding so the glyph, not
                // its hit box, lines up with the "2026" on the year rail.
                anchors.left: parent.left
                anchors.leftMargin: -Style.space(8)
                anchors.verticalCenter: parent.verticalCenter
                iconText: "󰅁"
                tooltipText: "Previous " + ({day: "day", week: "week", workweek: "week", month: "month", year: "year"}[root.viewMode])
                foreground: root.contentForeground
                fontFamily: root.contentFontFamily
                onClicked: root.step(-1)
              }

              PanelActionButton {
                anchors.right: parent.right
                anchors.rightMargin: -Style.space(8)
                anchors.verticalCenter: parent.verticalCenter
                iconText: "󰅂"
                tooltipText: "Next " + ({day: "day", week: "week", workweek: "week", month: "month", year: "year"}[root.viewMode])
                foreground: root.contentForeground
                fontFamily: root.contentFontFamily
                onClicked: root.step(1)
              }
            }
          }

          // ---- The selected day's events. Every row opens the event in its
          //      own calendar app; a meeting gets a Join button. The time
          //      views show the events themselves, so they don't need it.
          Item {
            visible: !root.editorOpen
            width: parent.width
            height: agenda.height

            Column {
              id: agenda
              anchors.horizontalCenter: parent.horizontalCenter
              width: gridColumn.width
              spacing: Style.space(6)

              Rectangle {
                width: parent.width
                height: Style.spacing.hairline
                color: root.contentForeground
                opacity: 0.1
              }

              Text {
                visible: !root.isTimeView
                textFormat: Text.PlainText
                text: Model.dayTitle(root.selectedKey, root.todayKey).toUpperCase()
                color: Qt.darker(root.contentForeground, 1.4)
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.bodySmall
                font.letterSpacing: 1
              }

              Text {
                visible: !root.isTimeView && root.selectedEvents.length === 0
                textFormat: Text.PlainText
                text: "Nothing on."
                color: Qt.darker(root.contentForeground, 1.9)
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.body
              }

              Repeater {
                model: root.isTimeView ? [] : root.selectedEvents

                Rectangle {
                  id: eventRow
                  required property var modelData
                  width: agenda.width
                  height: Math.max(eventText.implicitHeight, rowButtons.visible ? rowButtons.height : 0) + Style.space(8)
                  radius: Style.cornerRadius
                  color: rowMouse.containsMouse ? Style.hoverFillFor(root.contentForeground, Color.accent) : "transparent"
                  opacity: modelData.declined ? 0.5 : 1

                  Rectangle {
                    id: colorBar
                    anchors.left: parent.left
                    anchors.leftMargin: Style.space(4)
                    anchors.verticalCenter: parent.verticalCenter
                    width: Style.space(3)
                    height: parent.height - Style.space(10)
                    radius: width / 2
                    color: eventRow.modelData.color
                  }

                  MouseArea {
                    id: rowMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.openEditor(eventRow.modelData)
                  }

                  Column {
                    id: eventText
                    anchors.left: colorBar.right
                    anchors.leftMargin: Style.space(10)
                    anchors.right: rowButtons.visible ? rowButtons.left : parent.right
                    anchors.rightMargin: Style.space(8)
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: Style.space(1)

                    Text {
                      width: parent.width
                      textFormat: Text.PlainText
                      elide: Text.ElideRight
                      text: eventRow.modelData.title
                      color: root.contentForeground
                      font.family: root.contentFontFamily
                      font.pixelSize: Style.font.body
                      font.strikeout: eventRow.modelData.declined
                    }

                    Text {
                      width: parent.width
                      textFormat: Text.PlainText
                      elide: Text.ElideRight
                      text: eventRow.modelData.label + "  ·  " + eventRow.modelData.calendarName
                        + (eventRow.modelData.location && !eventRow.modelData.join ? "  ·  " + eventRow.modelData.location : "")
                      color: Qt.darker(root.contentForeground, 1.5)
                      font.family: root.contentFontFamily
                      font.pixelSize: Style.font.bodySmall
                    }

                    // An invitation not yet answered for sure: answer it here.
                    // A recurring one is answered for the whole series.
                    Row {
                      visible: !eventRow.modelData.organizer
                               && (eventRow.modelData.response === "needsAction" || eventRow.modelData.response === "tentative")
                      topPadding: Style.space(3)
                      bottomPadding: Style.space(2)
                      spacing: Style.space(4)

                      Repeater {
                        model: [
                          { answer: "accept", label: "Accept", icon: "󰄬" },
                          { answer: "tentative", label: "Maybe", icon: "󰋗" },
                          { answer: "decline", label: "Decline", icon: "󰅖" }
                        ]
                        Button {
                          required property var modelData
                          visible: !(modelData.answer === "tentative" && eventRow.modelData.response === "tentative")
                          enabled: root.writingUid === ""
                          bordered: true
                          iconText: modelData.icon
                          text: root.writingUid === eventRow.modelData.uid ? "…" : modelData.label
                          tooltipText: (eventRow.modelData.recurring ? "Every occurrence: " : "")
                                       + modelData.label + " and let the organiser know"
                          foreground: root.contentForeground
                          fontFamily: root.contentFontFamily
                          onClicked: root.respond(eventRow.modelData, modelData.answer, eventRow.modelData.recurring)
                        }
                      }
                    }
                  }

                  Row {
                    id: rowButtons
                    visible: joinButton.visible || snoozeButton.visible
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: Style.space(6)

                  // Omarchy's notification cards have no buttons, only a
                  // click (which joins), so Snooze lives here while a
                  // reminder is fresh.
                  Button {
                    id: snoozeButton
                    bordered: true
                    visible: root.canSnooze(eventRow.modelData, root.fired, root.clockNow)
                    iconText: "󰒲"
                    text: "Snooze"
                    tooltipText: "Remind me again in " + root.snoozeMinutes + " minutes"
                    foreground: root.contentForeground
                    fontFamily: root.contentFontFamily
                    onClicked: root.snooze(eventRow.modelData)
                  }

                  Button {
                    id: joinButton
                    bordered: true
                    visible: !!eventRow.modelData.join
                    iconText: "󰕧"
                    text: "Join"
                    tooltipText: eventRow.modelData.join
                      ? "Join the " + ({teams: "Teams", zoom: "Zoom", meet: "Meet", webex: "Webex"}[eventRow.modelData.join.kind] || "online") + " meeting"
                      : ""
                    foreground: root.contentForeground
                    fontFamily: root.contentFontFamily
                    onClicked: root.openUrl(eventRow.modelData.join.url)
                  }
                  }
                }
              }

              // An account that needs attention says so here, not silently.
              Repeater {
                model: root.problemAccounts

                Text {
                  required property var modelData
                  width: agenda.width
                  wrapMode: Text.WordWrap
                  textFormat: Text.PlainText
                  text: modelData.name + ": " + (modelData.status === "signin"
                    ? "sign-in needed (calendar-ctl add-" + (modelData.provider === "google" ? "google" : "microsoft") + " " + modelData.name + " …)"
                    : modelData.status === "offline" ? "offline, showing the last copy" : "couldn't sync")
                  color: Color.urgent
                  font.family: root.contentFontFamily
                  font.pixelSize: Style.font.bodySmall
                }
              }

              Row {
                anchors.right: parent.right
                spacing: Style.space(4)

                Button {
                  iconText: "󰐕"
                  text: "New"
                  tooltipText: "New event on this day (n)"
                  visible: root.editableCalendars.length > 0
                  foreground: root.contentForeground
                  fontFamily: root.contentFontFamily
                  onClicked: root.newEvent()
                }

                Button {
                  iconText: "󰃭"
                  text: "Choose calendars"
                  tooltipText: "Pick which calendars to show"
                  foreground: root.contentForeground
                  fontFamily: root.contentFontFamily
                  onClicked: root.chooseCalendars()
                }

                Button {
                  iconText: syncProc.running ? "󰑓" : "󰑐"
                  text: syncProc.running ? "Syncing…" : "Sync"
                  tooltipText: "Sync now"
                  foreground: root.contentForeground
                  fontFamily: root.contentFontFamily
                  onClicked: root.syncNow()
                }
              }
            }
          }
        }
      }
    }
  }
}
