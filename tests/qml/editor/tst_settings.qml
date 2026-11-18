import QtQuick
import QtTest
import "../../.." as Datebook

// The real SettingsSheet.qml against the same stand-ins as the editor test:
// it shows the panel's values and passes on only a real change.
Item {
  id: root
  width: 500
  height: 400

  property var calendarsChosen: []
  property var durationsChosen: []
  property int doneCount: 0

  Datebook.SettingsSheet {
    id: sheet
    width: 440
    calendars: [{ value: "G/work", label: "G: Work" }, { value: "M/home", label: "M: Home" }]
    calendarRef: "G/work"
    duration: 60
    onCalendarChosen: function(ref) { root.calendarsChosen.push(ref) }
    onDurationChosen: function(minutes) { root.durationsChosen.push(minutes) }
    onDone: root.doneCount++
  }

  TestCase {
    name: "SettingsSheet"
    when: windowShown

    function child(name) { return findChild(sheet, name) }

    function init() {
      sheet.calendarRef = "G/work"
      sheet.duration = 60
      root.calendarsChosen = []
      root.durationsChosen = []
      root.doneCount = 0
    }

    function test_shows_the_current_values() {
      compare(child("calendarPicker").value, "G/work")
      compare(child("calendarPicker").options.length, 2)
      compare(child("durationPicker").value, "60")
      compare(child("durationPicker").options.map(function(o) { return o.value }),
              ["15", "30", "45", "60", "90", "120"])
      sheet.duration = 30
      compare(child("durationPicker").value, "30")
    }

    function test_a_length_not_offered_shows_as_an_hour() {
      sheet.duration = 7
      compare(child("durationPicker").value, "60")
    }

    function test_choices_are_passed_on() {
      child("calendarPicker").changed("M/home")
      compare(root.calendarsChosen, ["M/home"])
      child("durationPicker").changed("90")
      compare(root.durationsChosen, [90])
    }

    function test_the_same_value_again_is_no_change() {
      child("calendarPicker").changed("G/work")
      child("durationPicker").changed("60")
      compare(root.calendarsChosen, [])
      compare(root.durationsChosen, [])
    }

    function test_done_closes() {
      child("doneButton").clicked()
      compare(root.doneCount, 1)
    }
  }
}
