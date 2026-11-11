import QtQuick
import QtQuick.Controls as Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

// One event: new, editable, or someone else's invitation.
//
// The panel owns the writes. This only collects the fields into a draft
// (see Model.draftArgs) and says what the person asked for: save, delete,
// answer, open, join. An event this account can't change is shown read-only,
// with the invitation answers when it is one. Either way it lists who is
// invited and what each of them answered; on an event you can change, guests
// are added and taken off here too, and sent with Save like any other field.
Item {
  id: editor

  property var draft: null          // Model.newDraft / Model.eventDraft
  property var event: null          // the row it came from, or null for a new one
  property var calendars: []        // [{ value: "<account>/<id>", label }], editable ones
  property bool saving: false
  // The compact layout has no room for a guest list: it's shown only in the
  // expanded one.
  property bool showGuests: true
  property string error: ""
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  // Handed to the date popup. DateField cannot read these off Color itself.
  readonly property color themeAccent: Color.accent
  readonly property color themeInk: Color.background
  readonly property color themePopupBg: Color.popups.background
  readonly property color themePopupEdge: Color.popups.border

  signal save(var draft)
  signal cancel()
  signal remove(bool series)
  signal respond(string answer, bool series)
  signal openLink(string url)

  readonly property bool creating: !!draft && draft.mode === "create"
  readonly property bool editable: creating || (!!event && event.editable)
  // The calendar entry's notes. Empty when the event has none (or only
  // divider lines), so the field stays hidden.
  readonly property string notesText: {
    var row = editor.event
    return Model.meetingNotes(row ? row.notes : "")
  }
  readonly property bool invitation: !!event && !event.organizer
  readonly property bool removable: !!event && (event.editable || event.calendarEditable)
  readonly property bool recurring: !!event && event.recurring

  property bool allDay: false
  property bool busy: true
  property bool busyTouched: false
  property bool series: false
  property string calendarRef: ""
  // The date popup follows the calendar's week and marks busy days on it.
  property string todayKey: ""
  // 24-hour clock unless the clock format asks for am/pm.
  property bool use24h: true
  property int weekStart: 1
  property var byDay: ({})
  property bool confirmingDelete: false
  // One width for every field label (SHOW AS, STARTS, ENDS / LAST DAY), wide
  // enough for the longest, so the columns line up on every kind of event.
  readonly property real labelWidth: Style.space(76)

  // Guest changes in this edit, sent with Save (see Model.guestEdit).
  property var invited: []
  property var uninvited: []
  property bool showAllGuests: false
  property string guestError: ""
  readonly property int guestPreview: 8
  readonly property var guestList: !!event && event.guests ? event.guests : []
  readonly property var guestRows: Model.guestRows(guestList, invited, uninvited)
  readonly property bool hasGuests: guestRows.length > 0 || (!!event && event.guestsHidden)
  // Names offered while an address is typed. People already on cached events;
  // the list stays up for the click that picks one, which would otherwise
  // take focus off the field and hide it first.
  property bool suggestHeld: false
  property string suggestTarget: ""
  property bool inviteSuggestOpen: false
  property bool guestSuggestOpen: false
  readonly property var knownPeople: Model.knownGuests(byDay)
  readonly property var invitePicks: Model.guestSuggestions(knownPeople, inviteField.text, [], 6)
  readonly property var guestPicks: Model.guestSuggestions(knownPeople, guestField.text, guestTaken(), 6)
  // Rooms from meeting-links.txt. Empty when that file is missing or has
  // no https link, so the form grows a menu only for someone who made one.
  property string meetingLinksText: ""
  readonly property string meetingLinksPath: {
    var base = Quickshell.env("XDG_CONFIG_HOME")
    if (!base) base = (Quickshell.env("HOME") || "") + "/.config"
    return base + "/blacksheep.calendar/meeting-links.txt"
  }
  readonly property var roomPicks: {
    var links = Model.parseMeetingLinks(meetingLinksText)
    var out = []
    for (var i = 0; i < links.length; i++) {
      var link = links[i]
      var named = link.name !== link.url
      out.push({ name: link.name, detail: named ? link.url : "", email: link.url })
    }
    return out
  }

  property FileView meetingLinksFile: FileView {
    path: editor.meetingLinksPath
    watchChanges: true
    printErrors: false
    onLoaded: editor.meetingLinksText = String(text() || "")
    onLoadFailed: editor.meetingLinksText = ""
    onFileChanged: reload()
  }

  implicitHeight: form.implicitHeight
  // Where the Delete/Open/Join/Close row goes instead of the form's end.
  property Item footerHost: null
  // The height the editor may fill (the sheet sets it); 0 for no limit.
  property real fitHeight: 0
  // How tall the notes text may be: what fitHeight leaves after the rest of
  // the form, and never less than twelve lines.
  readonly property real notesRoom: {
    var least = Style.font.body * 12
    if (fitHeight <= 0) return least
    var used = 0, shown = 0
    for (var i = 0; i < form.children.length; i++) {
      var c = form.children[i]
      if (c === notesBox || !c.visible || c.height <= 0) continue
      used += c.height
      shown++
    }
    return Math.max(least, fitHeight - used - form.spacing * shown - Style.space(16))
  }

  function load() {
    dateField.close()
    endDateField.close()
    fromField.close()
    toField.close()
    if (!draft) return
    titleField.text = draft.title
    locationField.text = draft.location
    inviteField.text = draft.invite || ""
    dateField.date = draft.date
    endDateField.date = draft.endDate
    fromField.text = draft.from
    toField.text = draft.to
    editor.startWas = { date: draft.date, from: draft.from }
    editor.allDay = draft.allDay
    editor.busy = draft.busy !== false
    editor.busyTouched = !editor.creating
    editor.series = false
    editor.calendarRef = draft.calendar
    editor.confirmingDelete = false
    editor.invited = draft.invited || []
    editor.uninvited = draft.uninvited || []
    editor.showAllGuests = false
    editor.guestError = ""
    editor.suggestHeld = false
    editor.suggestTarget = ""
    editor.inviteSuggestOpen = false
    editor.guestSuggestOpen = false
    guestField.text = draft.guestText || ""
    notesField.text = draft.notes || ""
    Qt.callLater(function() {
      if (editor.editable) { titleField.forceActiveFocus(); titleField.selectAll() }
      else form.forceActiveFocus()
    })
  }
  onDraftChanged: load()

  // Where the start was before the last change, so a new start day or time
  // can carry the end with it and keep the event's length.
  property var startWas: ({ date: "", from: "" })
  function moveStart(newDate, newFrom) {
    var before = { allDay: editor.allDay, date: startWas.date, endDate: endDateField.date,
                   from: startWas.from, to: toField.text }
    var moved = Model.moveStart(before, newDate, newFrom)
    endDateField.date = moved.endDate
    if (!editor.allDay) toField.text = moved.to
    startWas = { date: newDate, from: newFrom }
  }

  function collect() {
    var d = {}
    for (var k in draft) d[k] = draft[k]
    d.title = titleField.text
    d.location = locationField.text
    d.invite = inviteField.text
    d.date = dateField.date
    d.endDate = endDateField.date
    d.from = fromField.text
    d.to = toField.text
    d.allDay = editor.allDay
    d.busy = editor.busy
    d.series = editor.series
    d.calendar = editor.calendarRef
    d.invited = editor.invited
    d.uninvited = editor.uninvited
    d.guestText = guestField.text
    d.notes = notesField.text
    return d
  }

  // Write the fields back onto the create draft. The panel reads that when
  // the popup is dismissed, so an address typed here is still there when it
  // opens again. Cancel and Escape never ask for this: they drop the draft.
  function remember() {
    if (!draft || draft.mode !== "create") return
    draft.title = titleField.text
    draft.location = locationField.text
    draft.invite = inviteField.text
    draft.date = dateField.date
    draft.endDate = endDateField.date
    draft.from = fromField.text
    draft.to = toField.text
    draft.allDay = editor.allDay
    draft.busy = editor.busy
    draft.calendar = editor.calendarRef
    draft.notes = notesField.text
  }

  // The field they were filling in, without selecting its text: selecting
  // the title would wipe it on the next key.
  function resume() {
    if (!editor.creating) return
    var field = inviteField.text !== "" ? inviteField
              : locationField.text !== "" ? locationField
              : notesField.text !== "" ? notesField
              : titleField
    field.forceActiveFocus()
    field.deselect()
  }

  // The addresses typed in the guest box, onto the list (Enter or Add).
  function addTypedGuests() {
    var r = Model.guestEdit(editor.guestList, editor.invited, editor.uninvited, guestField.text)
    if (r.error) { editor.guestError = r.error; return }
    editor.invited = r.invited
    editor.uninvited = r.uninvited
    editor.guestError = ""
    guestField.text = ""
  }

  // Addresses already on this event, so they are not offered again.
  function guestTaken() {
    var out = [], drop = editor.uninvited || [], guests = editor.guestList || []
    for (var i = 0; i < guests.length; i++) {
      var email = String(guests[i].email || "").toLowerCase()
      if (!email || drop.indexOf(email) >= 0) continue
      out.push(email)
    }
    var added = editor.invited || []
    for (var j = 0; j < added.length; j++) out.push(added[j])
    return out
  }

  // Focus leaving the field is deferred: the click that picks a row takes
  // focus before its press handler runs, and the row has to still be there.
  function suggestFocus(which, focused) {
    if (focused) {
      if (which === "invite") editor.inviteSuggestOpen = true
      else editor.guestSuggestOpen = true
      return
    }
    Qt.callLater(function() {
      if (which === "invite") {
        if (!(editor.suggestHeld && editor.suggestTarget === "invite") && !inviteField.activeFocus)
          editor.inviteSuggestOpen = false
      } else if (!(editor.suggestHeld && editor.suggestTarget === "guest") && !guestField.activeFocus) {
        editor.guestSuggestOpen = false
      }
    })
  }

  function pickInvite(email) {
    inviteField.text = Model.applyGuestPick(inviteField.text, email)
    inviteField.forceActiveFocus()
    inviteField.cursorPosition = inviteField.text.length
    editor.suggestHeld = false
  }

  function pickGuest(email) {
    guestField.text = Model.applyGuestPick(guestField.text, email)
    guestField.forceActiveFocus()
    editor.suggestHeld = false
    editor.addTypedGuests()
  }

  function removeGuest(email) {
    var r = Model.guestRemove(editor.invited, editor.uninvited, email)
    editor.invited = r.invited
    editor.uninvited = r.uninvited
  }

  function undoRemoveGuest(email) {
    var a = String(email).toLowerCase()
    editor.uninvited = editor.uninvited.filter(function(x) { return x !== a })
  }

  function answerColor(response) {
    return response === "accepted" ? Color.accent
         : response === "declined" ? Color.urgent
         : response === "tentative" ? editor.foreground
         : Qt.darker(editor.foreground, 1.5)
  }

  function answerIcon(row) {
    if (row.response === "" && row.pending !== "add") return ""   // the organiser
    if (row.pending === "add") return "󰐕"
    return row.response === "accepted" ? "󰄬"
         : row.response === "tentative" ? "󰋗"
         : row.response === "declined" ? "󰅖" : "󰥔"
  }

  function submit() {
    if (editor.saving) return
    if (editor.editable) editor.save(collect())
    else editor.cancel()
  }

  function fieldKey(event) {
    if (event.key === Qt.Key_Escape) {
      editor.cancel()
      event.accepted = true
    } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
      editor.submit()
      event.accepted = true
    }
  }

  function providerName() {
    var link = editor.event ? String(editor.event.webLink || "") : ""
    if (link === "") return "your calendar's own app"   // CalDAV events have no web link
    return link.indexOf("google.com") >= 0 ? "Google Calendar" : "Outlook"
  }

  component Caption: Text {
    textFormat: Text.PlainText
    color: Qt.darker(editor.foreground, 1.5)
    font.family: editor.fontFamily
    font.pixelSize: Style.font.bodySmall
    font.letterSpacing: 1
  }

  component Field: TextField {
    readOnly: !editor.editable || editor.saving
    foreground: editor.foreground
    font.family: editor.fontFamily
    Keys.onPressed: function(event) { editor.fieldKey(event) }
  }

  // People from other events matching the address being typed.
  component SuggestList: Column {
    id: suggestList
    property string target: ""
    property var picks: []
    // A guest row has to stay up for the click that picks it. A room list
    // stays up on its own, so its click must not hold the guest list open.
    property bool holdFocus: true
    signal picked(string email)
    width: parent.width
    spacing: Style.space(2)

    Repeater {
      model: suggestList.picks

      Rectangle {
        id: suggestRow
        required property var modelData
        width: suggestList.width
        height: suggestWho.implicitHeight + Style.space(8)
        radius: Style.cornerRadius
        color: suggestMouse.containsMouse
               ? Style.hoverFillFor(editor.foreground, editor.themeAccent)
               : Qt.rgba(editor.foreground.r, editor.foreground.g, editor.foreground.b, 0.06)

        Column {
          id: suggestWho
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          anchors.leftMargin: Style.space(8)
          anchors.rightMargin: Style.space(8)

          Text {
            width: parent.width
            elide: Text.ElideRight
            textFormat: Text.PlainText
            text: suggestRow.modelData.name
            color: editor.foreground
            font.family: editor.fontFamily
            font.pixelSize: Style.font.body
          }
          Text {
            visible: text !== ""
            width: parent.width
            elide: Text.ElideRight
            textFormat: Text.PlainText
            text: suggestRow.modelData.detail
            color: Qt.darker(editor.foreground, 1.5)
            font.family: editor.fontFamily
            font.pixelSize: Style.font.bodySmall
          }
        }

        MouseArea {
          id: suggestMouse
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: Qt.PointingHandCursor
          onPressed: function(mouse) {
            if (suggestList.holdFocus) {
              editor.suggestTarget = suggestList.target
              editor.suggestHeld = true
            }
            suggestList.picked(suggestRow.modelData.email)
            mouse.accepted = true
          }
        }
      }
    }
  }

  // Several lines, so Enter starts a new one instead of saving. Escape still
  // drops the form. Styled like Field; the kit has no multi-line input.
  component NotesInput: Controls.TextArea {
    id: notesInput
    readOnly: editor.saving
    wrapMode: TextEdit.Wrap
    selectByMouse: true
    placeholderText: "Agenda, a link, anything the invitation should say"
    font.family: editor.fontFamily
    font.pixelSize: Style.font.body
    color: editor.foreground
    selectionColor: Style.selectionFillFor(editor.foreground, editor.themeAccent)
    selectedTextColor: editor.foreground
    placeholderTextColor: Qt.darker(editor.foreground, 1.6)
    readonly property bool _focused: activeFocus
    readonly property bool _hot: hovered
    readonly property var _borderSpec: Border.controlSpec(_focused ? "focus" : (_hot ? "hover-cursor" : "normal"),
                                                          editor.foreground, editor.themeAccent)
    leftPadding: Style.spacing.controlPaddingX + Border.left(_borderSpec)
    rightPadding: Style.spacing.controlPaddingX + Border.right(_borderSpec)
    topPadding: Style.spacing.inputPaddingY + Border.top(_borderSpec)
    bottomPadding: Style.spacing.inputPaddingY + Border.bottom(_borderSpec)
    height: Style.font.body * 6 + topPadding + bottomPadding
    background: BorderSurface {
      color: Style.controlFill(notesInput._focused, notesInput._hot, editor.foreground, editor.themeAccent)
      borderSpec: notesInput._borderSpec
      radius: Style.cornerRadius
    }
    Keys.onPressed: function(event) {
      if (event.key === Qt.Key_Escape) {
        editor.cancel()
        event.accepted = true
      }
    }
  }

  Column {
    id: form
    width: parent.width
    spacing: Style.space(8)
    focus: true
    Keys.onPressed: function(event) { editor.fieldKey(event) }

    Caption {
      text: editor.creating ? "NEW EVENT" : editor.editable ? "EDIT EVENT" : "INVITATION"
    }

    Field {
      id: titleField
      width: parent.width
      placeholderText: "Title"
      font.pixelSize: Style.font.subtitle
    }

    // Which calendar: chosen for a new event, shown for an existing one.
    Dropdown {
      visible: editor.creating
      width: parent.width
      showLabel: false
      options: editor.calendars
      value: editor.calendarRef
      foreground: editor.foreground
      fontFamily: editor.fontFamily
      onChanged: function(v) { editor.calendarRef = v }
    }
    Caption {
      visible: !editor.creating && !!editor.event
      text: editor.event ? (editor.event.calendarName + (editor.recurring ? "  ·  repeats" : "")) : ""
      font.letterSpacing: 0
    }

    Toggle {
      visible: editor.editable
      width: parent.width
      label: "All day"
      checked: editor.allDay
      foreground: editor.foreground
      fontFamily: editor.fontFamily
      titleSize: Style.font.body
      onClicked: {
        if (editor.saving) return
        editor.allDay = !editor.allDay
        // A new all-day event shows as free, a timed one as busy, until chosen.
        if (!editor.busyTouched) editor.busy = !editor.allDay
      }
    }

    // How it shows to people checking your availability.
    Row {
      visible: editor.editable
      spacing: Style.space(10)
      Caption { anchors.verticalCenter: parent.verticalCenter; text: "SHOW AS"; width: editor.labelWidth }
      ButtonGroup {
        options: [
          { label: "Busy", value: "busy", tooltip: "Others see you as busy" },
          { label: "Free", value: "free", tooltip: "Others see you as available" }
        ]
        value: editor.busy ? "busy" : "free"
        focusable: false
        foreground: editor.foreground
        fontFamily: editor.fontFamily
        fontSize: Style.font.bodySmall
        onChanged: function(v) {
          if (editor.saving) return
          editor.busy = v === "busy"
          editor.busyTouched = true
        }
      }
    }

    // Starts and ends. The dates open a month; the times stay typed.
    // All-day events end on their last day, as people say it.
    // A Grid skips hidden items, so with the times hidden a third column
    // would pull LAST DAY up beside STARTS: all-day events get two columns.
    Grid {
      columns: editor.allDay ? 2 : 3
      columnSpacing: Style.space(8)
      rowSpacing: Style.space(6)
      verticalItemAlignment: Grid.AlignVCenter

      Caption { text: "STARTS"; width: editor.labelWidth }
      DateField {
        id: dateField
        readOnly: !editor.editable || editor.saving
        todayKey: editor.todayKey
        weekStart: editor.weekStart
        byDay: editor.byDay
        foreground: editor.foreground
        accent: editor.themeAccent
        ink: editor.themeInk
        popupBackground: editor.themePopupBg
        popupBorder: editor.themePopupEdge
        fontFamily: editor.fontFamily
        onPopupOpened: { endDateField.close(); fromField.close(); toField.close() }
        onPicked: function(key) { editor.moveStart(key, fromField.text) }
      }
      TimeField {
        id: fromField
        visible: !editor.allDay
        readOnly: !editor.editable || editor.saving
        use24h: editor.use24h
        foreground: editor.foreground
        accent: editor.themeAccent
        popupBackground: editor.themePopupBg
        popupBorder: editor.themePopupEdge
        fontFamily: editor.fontFamily
        onPopupOpened: { dateField.close(); endDateField.close(); toField.close() }
        onPicked: function(value) { editor.moveStart(dateField.date, value) }
      }

      Caption { text: editor.allDay ? "LAST DAY" : "ENDS"; width: editor.labelWidth }
      DateField {
        id: endDateField
        readOnly: !editor.editable || editor.saving
        todayKey: editor.todayKey
        weekStart: editor.weekStart
        byDay: editor.byDay
        foreground: editor.foreground
        accent: editor.themeAccent
        ink: editor.themeInk
        popupBackground: editor.themePopupBg
        popupBorder: editor.themePopupEdge
        fontFamily: editor.fontFamily
        onPopupOpened: { dateField.close(); fromField.close(); toField.close() }
      }
      TimeField {
        id: toField
        visible: !editor.allDay
        readOnly: !editor.editable || editor.saving
        use24h: editor.use24h
        // Lengths beside each choice while the event ends on its first day.
        since: endDateField.date === dateField.date ? fromField.minutes : -1
        foreground: editor.foreground
        accent: editor.themeAccent
        popupBackground: editor.themePopupBg
        popupBorder: editor.themePopupEdge
        fontFamily: editor.fontFamily
        onPopupOpened: { dateField.close(); endDateField.close(); fromField.close() }
      }
    }

    Field {
      id: locationField
      visible: editor.editable || text !== ""
      width: parent.width
      placeholderText: "Location"
    }

    // Choosing a room writes its link into Location. Join still comes from
    // that link once the event is saved. No rooms, and this row is absent.
    SuggestList {
      visible: editor.editable && editor.roomPicks.length > 0
      holdFocus: false
      picks: editor.roomPicks
      onPicked: function(url) {
        locationField.text = url
        locationField.forceActiveFocus()
        locationField.cursorPosition = locationField.text.length
      }
    }

    // Typed on a new event, and sent as the invitation text. An existing
    // event shows its notes below, read-only: they can be selected, and https
    // links open in the browser.
    Caption {
      visible: editor.creating || editor.notesText !== ""
      text: "NOTES"
    }
    NotesInput {
      id: notesField
      visible: editor.creating
      width: parent.width
    }

    // Shown when the entry has notes. Width is the form's own width: a nested
    // column, or a text height tied to contentHeight, laid out as nothing.
    // Long notes (a Teams footer) scroll inside the box, which takes the room
    // the sheet has left, so the buttons below stay on screen.
    Rectangle {
      id: notesBox
      visible: editor.notesText !== ""
      width: form.width
      height: Math.min(notesBody.implicitHeight, editor.notesRoom) + Style.space(16)
      radius: Style.cornerRadius
      color: Qt.rgba(editor.foreground.r, editor.foreground.g, editor.foreground.b, 0.06)
      border.width: Style.spacing.hairline
      border.color: Qt.rgba(editor.foreground.r, editor.foreground.g, editor.foreground.b, 0.25)

      Flickable {
        id: notesScroll
        x: Style.space(8)
        y: Style.space(8)
        width: notesBox.width - Style.space(16)
        height: notesBox.height - Style.space(16)
        contentHeight: notesBody.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        // The wheel scrolls; a drag selects text instead of scrolling.
        acceptedButtons: Qt.NoButton

        TextEdit {
          id: notesBody
          width: notesScroll.width
          readOnly: true
          selectByMouse: true
          wrapMode: TextEdit.Wrap
          textFormat: TextEdit.RichText
          text: Model.notesHtml(editor.notesText, String(editor.themeAccent))
          color: editor.foreground
          selectionColor: Qt.rgba(editor.themeAccent.r, editor.themeAccent.g, editor.themeAccent.b, 0.4)
          selectedTextColor: editor.foreground
          font.family: editor.fontFamily
          font.pixelSize: Style.font.body
          onLinkActivated: function(link) { editor.openLink(link) }

          HoverHandler {
            cursorShape: notesBody.hoveredLink !== "" ? Qt.PointingHandCursor : Qt.IBeamCursor
          }
        }
      }
    }

    // ---- Who's invited, and what they said.
    Column {
      visible: editor.showGuests && !editor.creating && (editor.hasGuests || editor.editable)
      width: parent.width
      spacing: Style.space(4)

      Row {
        spacing: Style.space(10)
        Caption { text: "GUESTS" }
        Caption {
          visible: editor.guestList.length > 0
          text: Model.guestSummary(editor.guestList, editor.event ? editor.event.guestTotal : 0)
          font.letterSpacing: 0
        }
      }

      Caption {
        visible: !!editor.event && editor.event.guestsHidden
        width: parent.width
        wrapMode: Text.WordWrap
        text: "The organiser has hidden the guest list."
        font.letterSpacing: 0
      }

      Repeater {
        model: editor.showAllGuests ? editor.guestRows : editor.guestRows.slice(0, editor.guestPreview)

        Item {
          id: guestRow
          required property var modelData
          readonly property bool removing: modelData.pending === "remove"
          width: parent.width
          height: Math.max(who.implicitHeight, rowButton.implicitHeight)
          opacity: removing ? 0.55 : 1

          Text {
            id: answerGlyph
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            width: Style.space(22)
            textFormat: Text.PlainText
            text: editor.answerIcon(guestRow.modelData)
            color: guestRow.modelData.pending === "add" ? Color.accent : editor.answerColor(guestRow.modelData.response)
            font.family: editor.fontFamily
            font.pixelSize: Style.font.iconSmall
          }

          Column {
            id: who
            anchors.left: answerGlyph.right
            anchors.right: answerLabel.left
            anchors.rightMargin: Style.space(8)
            anchors.verticalCenter: parent.verticalCenter

            Text {
              width: parent.width
              elide: Text.ElideRight
              textFormat: Text.PlainText
              text: guestRow.modelData.title
              color: editor.foreground
              font.family: editor.fontFamily
              font.pixelSize: Style.font.body
              font.strikeout: guestRow.removing
            }
            Text {
              visible: text !== ""
              width: parent.width
              elide: Text.ElideRight
              textFormat: Text.PlainText
              text: [guestRow.modelData.detail, guestRow.modelData.tags].filter(function(x) { return x }).join("  ·  ")
              color: Qt.darker(editor.foreground, 1.5)
              font.family: editor.fontFamily
              font.pixelSize: Style.font.bodySmall
            }
          }

          Text {
            id: answerLabel
            // The answers line up whether or not a row can be taken off.
            anchors.right: parent.right
            anchors.rightMargin: editor.editable ? rowButton.implicitWidth + Style.space(4) : 0
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: guestRow.removing ? "Take off" : guestRow.modelData.answer
            color: guestRow.modelData.pending ? Color.accent : editor.answerColor(guestRow.modelData.response)
            font.family: editor.fontFamily
            font.pixelSize: Style.font.bodySmall
          }

          Button {
            id: rowButton
            visible: editor.editable && !guestRow.modelData.fixed
            enabled: !editor.saving
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            iconText: guestRow.removing ? "󰕌" : "󰍴"
            tooltipText: guestRow.removing ? "Keep " + guestRow.modelData.title
                       : guestRow.modelData.pending === "add" ? "Don't invite " + guestRow.modelData.title
                       : "Take " + guestRow.modelData.title + " off (they get a cancellation when you save)"
            foreground: editor.foreground
            fontFamily: editor.fontFamily
            onClicked: guestRow.removing ? editor.undoRemoveGuest(guestRow.modelData.email)
                                         : editor.removeGuest(guestRow.modelData.email)
          }
        }
      }

      Button {
        visible: !editor.showAllGuests && editor.guestRows.length > editor.guestPreview
        text: "Show all " + editor.guestRows.length
        foreground: editor.foreground
        fontFamily: editor.fontFamily
        fontSize: Style.font.bodySmall
        onClicked: editor.showAllGuests = true
      }

      Caption {
        readonly property int more: editor.event ? editor.event.guestTotal - editor.guestList.length : 0
        visible: more > 0
        width: parent.width
        wrapMode: Text.WordWrap
        text: "…and " + more + " more. Open it in " + editor.providerName() + " to see everyone."
        font.letterSpacing: 0
      }

      // Add guests: one or several addresses, then Enter or Add. They're
      // invited when the event is saved.
      Item {
        visible: editor.editable
        width: parent.width
        height: guestField.implicitHeight

        // A plain TextField, not Field: Enter here adds, where Field's saves.
        TextField {
          id: guestField
          anchors.left: parent.left
          anchors.right: addButton.left
          anchors.rightMargin: Style.space(6)
          readOnly: editor.saving
          foreground: editor.foreground
          font.family: editor.fontFamily
          placeholderText: "Add guests: a name or an email"
          onTextChanged: editor.guestError = ""
          onActiveFocusChanged: editor.suggestFocus("guest", activeFocus)
          Keys.onPressed: function(event) {
            if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && text.trim() !== "") {
              var frag = Model.guestQuery(text)
              if (editor.guestSuggestOpen && editor.guestPicks.length && !Model.isEmail(frag)) {
                editor.suggestTarget = "guest"
                editor.suggestHeld = true
                editor.pickGuest(editor.guestPicks[0].email)
              } else {
                editor.addTypedGuests()
              }
              event.accepted = true
            } else {
              editor.fieldKey(event)
            }
          }
        }

        Button {
          id: addButton
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          enabled: !editor.saving && guestField.text.trim() !== ""
          bordered: true
          iconText: "󰐕"
          text: "Add"
          tooltipText: "Invited when you save"
          foreground: editor.foreground
          fontFamily: editor.fontFamily
          onClicked: editor.addTypedGuests()
        }
      }

      SuggestList {
        target: "guest"
        visible: editor.guestSuggestOpen && editor.guestPicks.length > 0
        picks: editor.guestPicks
        onPicked: function(email) { editor.pickGuest(email) }
      }

      Text {
        visible: editor.guestError !== ""
        width: parent.width
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        text: editor.guestError
        color: Color.urgent
        font.family: editor.fontFamily
        font.pixelSize: Style.font.bodySmall
      }
    }

    // A plain TextField, not Field: Enter picks a suggested person when one
    // is listed, and otherwise saves. Field's own Enter always saves.
    TextField {
      id: inviteField
      visible: editor.creating
      width: parent.width
      readOnly: !editor.editable || editor.saving
      foreground: editor.foreground
      font.family: editor.fontFamily
      placeholderText: "Invite: a name or an email, separated by commas"
      onActiveFocusChanged: editor.suggestFocus("invite", activeFocus)
      Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Escape) {
          editor.cancel()
          event.accepted = true
        } else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
                   && editor.inviteSuggestOpen && editor.invitePicks.length) {
          editor.suggestTarget = "invite"
          editor.suggestHeld = true
          editor.pickInvite(editor.invitePicks[0].email)
          event.accepted = true
        } else {
          editor.fieldKey(event)
        }
      }
    }

    SuggestList {
      target: "invite"
      visible: editor.creating && editor.inviteSuggestOpen && editor.invitePicks.length > 0
      picks: editor.invitePicks
      onPicked: function(email) { editor.pickInvite(email) }
    }

    Toggle {
      visible: editor.recurring && (editor.editable || editor.invitation)
      width: parent.width
      label: "Every occurrence"
      description: editor.editable ? "Title, place, guests and delete apply to the whole series; times move one at a time"
                                   : "Answer for the whole series"
      checked: editor.series
      foreground: editor.foreground
      fontFamily: editor.fontFamily
      titleSize: Style.font.body
      onClicked: if (!editor.saving) editor.series = !editor.series
    }

    // Someone else's event: answer it.
    Row {
      visible: editor.invitation && !!editor.event
      spacing: Style.space(6)

      Repeater {
        model: [
          { answer: "accept", response: "accepted", label: "Accept", icon: "󰄬" },
          { answer: "tentative", response: "tentative", label: "Maybe", icon: "󰋗" },
          { answer: "decline", response: "declined", label: "Decline", icon: "󰅖" }
        ]
        Button {
          required property var modelData
          readonly property bool current: !!editor.event && editor.event.response === modelData.response
          enabled: !editor.saving
          bordered: true
          iconText: current ? "󰄵" : modelData.icon
          text: modelData.label
          tooltipText: current ? "Your answer now" : modelData.label + " and let the organiser know"
          foreground: current ? Color.accent : editor.foreground
          fontFamily: editor.fontFamily
          onClicked: editor.respond(modelData.answer, editor.series)
        }
      }
    }

    Text {
      visible: editor.error !== ""
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: editor.error
      color: Color.urgent
      font.family: editor.fontFamily
      font.pixelSize: Style.font.bodySmall
    }

    // As tall as the taller side: an invitation has only a plain Close on the
    // right, shorter than the boxed Join on the left. The sheet can hold it
    // in footerHost, pinned below the scrolling form, so Join stays in view.
    Item {
      id: footer
      parent: editor.footerHost ? editor.footerHost : form
      width: parent.width
      height: Math.max(links.height, actions.height)

      Row {
        id: links
        anchors.left: parent.left
        spacing: Style.space(6)

        Button {
          visible: !editor.creating && editor.removable
          enabled: !editor.saving
          bordered: editor.confirmingDelete
          iconText: "󰆴"
          text: editor.confirmingDelete ? (editor.series ? "Delete the series?" : "Really delete?") : "Delete"
          tooltipText: editor.invitation ? "Take it off your calendar (decline to tell the organiser)"
                                         : "Delete it; guests get a cancellation"
          foreground: editor.confirmingDelete ? Color.urgent : editor.foreground
          fontFamily: editor.fontFamily
          onClicked: {
            if (editor.confirmingDelete) editor.remove(editor.series)
            else editor.confirmingDelete = true
          }
        }

        Button {
          visible: !!editor.event && /^https:\/\//.test(String(editor.event.webLink || ""))
          iconText: "󰏌"
          text: "Open"
          tooltipText: "Open in " + editor.providerName()
          foreground: editor.foreground
          fontFamily: editor.fontFamily
          onClicked: editor.openLink(editor.event.webLink)
        }

        Button {
          visible: !!editor.event && !!editor.event.join
          bordered: true
          iconText: "󰕧"
          text: "Join"
          foreground: editor.foreground
          fontFamily: editor.fontFamily
          onClicked: editor.openLink(editor.event.join.url)
        }
      }

      Row {
        id: actions
        anchors.right: parent.right
        spacing: Style.space(6)

        Button {
          text: editor.editable ? "Cancel" : "Close"
          foreground: editor.foreground
          fontFamily: editor.fontFamily
          onClicked: editor.cancel()
        }

        Button {
          visible: editor.editable
          enabled: !editor.saving
          bordered: true
          iconText: editor.saving ? "󰑓" : "󰄬"
          text: editor.saving ? "Saving…" : editor.creating ? "Create" : "Save"
          foreground: editor.foreground
          fontFamily: editor.fontFamily
          onClicked: editor.submit()
        }
      }
    }
  }
}
