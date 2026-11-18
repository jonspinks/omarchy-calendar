import QtQuick
import qs.Commons
import qs.Ui
import "Model.js" as Model

// What a new event starts with: its calendar and how long it runs. Each is
// still a choice on the event itself; this is only where the form begins.
//
// It owns no state: the panel passes the current values in and writes the
// choices to the widget's shell.json entry (defaultCalendar, defaultDuration).
Item {
  id: sheet

  property var calendars: []          // [{ value: "<account>/<id>", label }], editable ones
  property string calendarRef: ""     // the one new events start on now
  property int duration: 60           // minutes; one of Model.MEETING_LENGTHS
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family

  signal calendarChosen(string ref)
  signal durationChosen(int minutes)
  signal done()

  implicitHeight: column.implicitHeight

  component Caption: Text {
    textFormat: Text.PlainText
    color: Qt.darker(sheet.foreground, 1.5)
    font.family: sheet.fontFamily
    font.pixelSize: Style.font.bodySmall
    font.letterSpacing: 1
  }

  Column {
    id: column
    width: parent.width
    spacing: Style.space(8)

    Caption { text: "SETTINGS" }

    Caption { topPadding: Style.space(6); text: "CALENDAR FOR NEW EVENTS" }
    Dropdown {
      id: calendarPicker
      objectName: "calendarPicker"
      visible: sheet.calendars.length > 0
      width: parent.width
      showLabel: false
      options: sheet.calendars
      value: sheet.calendarRef
      foreground: sheet.foreground
      fontFamily: sheet.fontFamily
      onChanged: function(v) { if (v !== sheet.calendarRef) sheet.calendarChosen(v) }
    }
    Caption {
      visible: sheet.calendars.length === 0
      width: parent.width
      wrapMode: Text.WordWrap
      font.letterSpacing: 0
      text: "No calendar you can add events to yet."
    }

    Caption { topPadding: Style.space(6); text: "MEETING LENGTH" }
    Dropdown {
      id: durationPicker
      objectName: "durationPicker"
      width: parent.width
      showLabel: false
      options: Model.meetingLengthOptions()
      value: String(Model.meetingLength(sheet.duration))
      foreground: sheet.foreground
      fontFamily: sheet.fontFamily
      onChanged: function(v) {
        var minutes = Model.meetingLength(v)
        if (minutes !== sheet.duration) sheet.durationChosen(minutes)
      }
    }

    Caption {
      topPadding: Style.space(6)
      width: parent.width
      wrapMode: Text.WordWrap
      font.letterSpacing: 0
      text: "New events start here; each one can still be changed in its own form."
    }

    Item {
      width: parent.width
      height: doneButton.height + Style.space(6)
      Button {
        id: doneButton
        objectName: "doneButton"
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        bordered: true
        text: "Done"
        tooltipText: "Close settings (Esc)"
        foreground: sheet.foreground
        fontFamily: sheet.fontFamily
        onClicked: sheet.done()
      }
    }
  }
}
