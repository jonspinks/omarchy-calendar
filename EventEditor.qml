import QtQuick
import qs.Commons
import qs.Ui
import "Model.js" as Model

// One event: new, editable, or someone else's invitation.
//
// The panel owns the writes. This only collects the fields into a draft
// (see Model.draftArgs) and says what the person asked for: save, delete,
// answer, open, join. An event this account can't change is shown read-only,
// with the invitation answers when it is one.
Item {
  id: editor

  property var draft: null          // Model.newDraft / Model.eventDraft
  property var event: null          // the row it came from, or null for a new one
  property var calendars: []        // [{ value: "<account>/<id>", label }], editable ones
  property bool saving: false
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
  readonly property bool recurring: !!event && event.recurring

  property bool allDay: false
  property bool busy: true
  property bool busyTouched: false
  property bool series: false
  property string calendarRef: ""
  property bool confirmingDelete: false

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
    return d
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
      Caption { anchors.verticalCenter: parent.verticalCenter; text: "SHOW AS"; width: Style.space(60) }
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
    Grid {
      columns: 3
      columnSpacing: Style.space(8)
      rowSpacing: Style.space(6)
      verticalItemAlignment: Grid.AlignVCenter

      Caption { text: "STARTS"; width: Style.space(60) }
      Field { id: dateField; width: Style.space(120); placeholderText: "2026-10-02" }
      Field { id: fromField; visible: !editor.allDay; width: Style.space(90); placeholderText: "14:30" }

      Caption { text: editor.allDay ? "LAST DAY" : "ENDS"; width: Style.space(60) }
      Field { id: endDateField; width: Style.space(120); placeholderText: "2026-10-02" }
      Field { id: toField; visible: !editor.allDay; width: Style.space(90); placeholderText: "15:30" }
    }

    Field {
      id: locationField
      visible: editor.editable || text !== ""
      width: parent.width
      placeholderText: "Location"
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
      description: editor.editable ? "Title, place and delete apply to the whole series; times move one at a time"
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

    Item {
      width: parent.width
      height: actions.height

      Row {
        anchors.left: parent.left
        spacing: Style.space(6)

        Button {
          visible: !editor.creating && editor.editable
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
