import QtQuick
import QtTest
import "../../Typing.js" as Typing

// Real key events on read-only native fields wired as Datebook wires them
// (EventEditor.qml): Qt draws and navigates, Typing.js edits, paste is
// handed to the bounded helper. Run: tests/run.sh, or
//   QT_QPA_PLATFORM=offscreen qmltestrunner -input tests/qml
Item {
  id: root
  width: 400
  height: 300

  property string pasteMode: ""

  TextInput {
    id: line
    width: 300
    height: 30
    readOnly: true
    cursorVisible: activeFocus
    Keys.onPressed: function(event) {
      Typing.handle(line, event, true, false, function(mode) { root.pasteMode = mode })
    }
  }

  TextEdit {
    id: notes
    y: 40
    width: 300
    height: 100
    readOnly: true
    selectByKeyboard: true
    textFormat: TextEdit.PlainText
    Keys.onPressed: function(event) {
      Typing.handle(notes, event, true, true, function(mode) { root.pasteMode = mode })
    }
  }

  TestCase {
    name: "Typing"
    when: windowShown

    function init() {
      line.text = ""
      notes.text = ""
      root.pasteMode = ""
      Typing.forget([line, notes])
    }

    function test_typing_and_deleting() {
      line.forceActiveFocus()
      keyClick(Qt.Key_L); keyClick(Qt.Key_U); keyClick(Qt.Key_N); keyClick(Qt.Key_C); keyClick(Qt.Key_H)
      compare(line.text, "lunch")
      keyClick(Qt.Key_Backspace)
      compare(line.text, "lunc")
      keyClick(Qt.Key_Home)
      keyClick(Qt.Key_Delete)
      compare(line.text, "unc")
      compare(line.cursorPosition, 0)
    }

    function test_native_navigation_and_selection_still_work() {
      line.forceActiveFocus()
      line.text = "Team lunch"
      line.cursorPosition = 10
      keyClick(Qt.Key_Left, Qt.ShiftModifier)
      keyClick(Qt.Key_Left, Qt.ShiftModifier)
      compare(line.selectedText, "ch")
      keyClick(Qt.Key_X, Qt.NoModifier, -1)
      compare(line.text, "Team lunx")
      keyClick(Qt.Key_A, Qt.ControlModifier)
      compare(line.selectedText, "Team lunx")
    }

    function test_undo_and_redo() {
      line.forceActiveFocus()
      keyClick(Qt.Key_A); keyClick(Qt.Key_B)
      keyClick(Qt.Key_Z, Qt.ControlModifier)
      compare(line.text, "a")
      keyClick(Qt.Key_Z, Qt.ControlModifier | Qt.ShiftModifier)
      compare(line.text, "ab")
    }

    function test_paste_goes_to_the_helper_and_never_to_qt() {
      line.forceActiveFocus()
      verify(!line.canPaste, "a read-only field never asks for the clipboard")
      verify(!notes.canPaste, "nor does a read-only TextEdit")
      keyClick(Qt.Key_V, Qt.ControlModifier)
      compare(root.pasteMode, "clipboard")
      root.pasteMode = ""
      keyClick(Qt.Key_Insert, Qt.ShiftModifier)
      compare(root.pasteMode, "clipboard")
      compare(line.text, "")
      Typing.insert(line, "from\nthe helper", false)
      compare(line.text, "from the helper")
    }

    function test_notes_take_line_breaks() {
      notes.forceActiveFocus()
      keyClick(Qt.Key_A)
      keyClick(Qt.Key_Return)
      keyClick(Qt.Key_B)
      compare(notes.text, "a\nb")
      keyClick(Qt.Key_Up)
      keyClick(Qt.Key_End)
      keyClick(Qt.Key_C)
      compare(notes.text, "ac\nb")
    }
  }
}
