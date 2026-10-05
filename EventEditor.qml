import QtQuick
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

  signal save(var draft)
  signal cancel()
  signal remove(bool series)
  signal respond(string answer, bool series)
  signal openLink(string url)

  readonly property bool creating: !!draft && draft.mode === "create"
  readonly property bool editable: creating || (!!event && event.editable)
  readonly property bool invitation: !!event && !event.organizer
  readonly property bool removable: !!event && (event.editable || event.calendarEditable)
  readonly property bool recurring: !!event && event.recurring

  property bool allDay: false
  property bool busy: true
  property bool busyTouched: false
  property bool series: false
  property string calendarRef: ""
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

  implicitHeight: form.implicitHeight

  function load() {
    if (!draft) return
    titleField.text = draft.title
    locationField.text = draft.location
    inviteField.text = draft.invite || ""
    dateField.text = draft.date
    endDateField.text = draft.endDate
    fromField.text = draft.from
    toField.text = draft.to
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
    guestField.text = draft.guestText || ""
    Qt.callLater(function() {
      if (editor.editable) { titleField.forceActiveFocus(); titleField.selectAll() }
      else form.forceActiveFocus()
    })
  }
  onDraftChanged: load()

  function collect() {
    var d = {}
    for (var k in draft) d[k] = draft[k]
    d.title = titleField.text
    d.location = locationField.text
    d.invite = inviteField.text
    d.date = dateField.text
    d.endDate = endDateField.text
    d.from = fromField.text
    d.to = toField.text
    d.allDay = editor.allDay
    d.busy = editor.busy
    d.series = editor.series
    d.calendar = editor.calendarRef
    d.invited = editor.invited
    d.uninvited = editor.uninvited
    d.guestText = guestField.text
    return d
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

    // Starts and ends. All-day events end on their last day, as people say it.
    // A Grid skips hidden items, so with the times hidden a third column
    // would pull LAST DAY up beside STARTS: all-day events get two columns.
    Grid {
      columns: editor.allDay ? 2 : 3
      columnSpacing: Style.space(8)
      rowSpacing: Style.space(6)
      verticalItemAlignment: Grid.AlignVCenter

      Caption { text: "STARTS"; width: editor.labelWidth }
      Field { id: dateField; width: Style.space(120); placeholderText: "2026-10-02" }
      Field { id: fromField; visible: !editor.allDay; width: Style.space(90); placeholderText: "14:30" }

      Caption { text: editor.allDay ? "LAST DAY" : "ENDS"; width: editor.labelWidth }
      Field { id: endDateField; width: Style.space(120); placeholderText: "2026-10-02" }
      Field { id: toField; visible: !editor.allDay; width: Style.space(90); placeholderText: "15:30" }
    }

    Field {
      id: locationField
      visible: editor.editable || text !== ""
      width: parent.width
      placeholderText: "Location"
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
          placeholderText: "Add guests: email addresses"
          onTextChanged: editor.guestError = ""
          Keys.onPressed: function(event) {
            if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && text.trim() !== "") {
              editor.addTypedGuests()
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

    Field {
      id: inviteField
      visible: editor.creating
      width: parent.width
      placeholderText: "Invite: email addresses, separated by commas"
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
    // right, shorter than the boxed Join on the left.
    Item {
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
