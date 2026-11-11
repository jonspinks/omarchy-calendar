import QtQuick
import QtTest
import "../../.." as Datebook
import "../../../Model.js" as Model

// The real EventEditor.qml, reused for one draft after another as the
// panel reuses it (#14402): nothing typed or pasted for one event may land
// in the next. The shell's modules are stand-ins (make_stubs.py); the
// fields are Qt's own, read-only. Run by tests/run.sh.
Item {
  id: root
  width: 700
  height: 900

  Datebook.EventEditor {
    id: editor
    width: 600
    calendars: [{ value: "G/c", label: "Work" }]
  }

  function field(name) { return findChildByName(editor, name) }

  function existing(uid, title) {
    return { uid: uid, account: "G", calendar: "c", title: title, location: "", editable: true,
             organizer: true, start: "2026-11-12T14:00:00", end: "2026-11-12T15:00:00", notes: "",
             recurring: false, guestsHidden: false, calendarEditable: true, guests: [] }
  }

  // What the panel does to show an event: the row, then its draft.
  function open(row) {
    editor.event = row
    editor.draft = Model.eventDraft(row)
  }

  function close() {
    editor.draft = null
    editor.event = null
  }

  TestCase {
    name: "EditorDrafts"
    when: windowShown

    function findChild(parent, name) { return root.findChildByName(parent, name) }

    function init() {
      root.close()
      wait(0)
    }

    // Opening selects the whole title on the next turn (Qt.callLater), as
    // the panel shows it; let that happen before typing.
    function show(row) {
      root.open(row)
      wait(0)
    }

    function typeInto(f, text) {
      f.forceActiveFocus()
      f.cursorPosition = f.text.length
      for (var i = 0; i < text.length; i++) keyClick(text.charAt(i))
    }

    function test_undo_does_not_cross_into_another_event() {
      // A: type in the title, then cancel.
      show(root.existing("A", "Budget review"))
      var title = field("titleField")
      verify(title.readOnly, "the field is read-only to Qt")
      typeInto(title, " draft")
      compare(title.text, "Budget review draft")
      root.close()
      // B in the same editor: its own title, and Undo has nothing of A's.
      show(root.existing("B", "Dentist"))
      compare(field("titleField"), title, "the same field object is reused")
      compare(title.text, "Dentist")
      title.forceActiveFocus()
      keyClick(Qt.Key_Z, Qt.ControlModifier)
      compare(title.text, "Dentist")
      keyClick(Qt.Key_Z, Qt.ControlModifier | Qt.ShiftModifier)
      compare(title.text, "Dentist")
    }

    function test_undo_does_not_cross_without_closing() {
      // Switching straight from A to B (no cancel in between), and the same title on both.
      show(root.existing("A", "Standup"))
      var title = field("titleField")
      typeInto(title, "!")
      show(root.existing("B", "Standup!"))
      title.forceActiveFocus()
      keyClick(Qt.Key_Z, Qt.ControlModifier)
      compare(title.text, "Standup!")
    }

    function test_undo_still_works_within_one_event() {
      show(root.existing("A", "Lunch"))
      var title = field("titleField")
      typeInto(title, "es")
      keyClick(Qt.Key_Z, Qt.ControlModifier)
      compare(title.text, "Lunche")
      keyClick(Qt.Key_Z, Qt.ControlModifier)
      compare(title.text, "Lunch")
    }

    function test_a_paste_for_one_event_is_dropped_in_another() {
      var proc = findChild(editor, "pasteProc")
      show(root.existing("A", "Call"))
      var title = field("titleField")
      title.forceActiveFocus()
      title.cursorPosition = title.text.length
      keyClick(Qt.Key_V, Qt.ControlModifier)
      verify(proc.running, "Ctrl+V asked the bounded helper")
      verify(String(proc.command).indexOf("paste.py") >= 0)
      // The helper answers only after B is open in the same field.
      show(root.existing("B", "Dinner"))
      title.forceActiveFocus()
      proc.finish(0, " meant for A")
      compare(title.text, "Dinner")
    }

    function test_a_paste_lands_in_its_own_event() {
      var proc = findChild(editor, "pasteProc")
      show(root.existing("A", "Call"))
      var title = field("titleField")
      title.forceActiveFocus()
      title.cursorPosition = title.text.length
      keyClick(Qt.Key_V, Qt.ControlModifier)
      proc.finish(0, " with Sam")
      compare(title.text, "Call with Sam")
    }

    function test_new_event_fields_are_read_only_and_typed() {
      editor.event = null
      editor.draft = Model.newDraft("2026-11-12", new Date(2026, 10, 11, 9, 0), "G/c")
      wait(0)
      var notes = field("notesField")
      verify(notes.readOnly)
      verify(!notes.canPaste, "a read-only notes box never asks for the clipboard")
      typeInto(notes, "a")
      keyClick(Qt.Key_Return)
      keyClick("b")
      compare(notes.text, "a\nb")
      var invite = field("inviteField")
      verify(invite.readOnly && !invite.canPaste)
    }
  }

  function findChildByName(parent, name) {
    if (!parent) return null
    if (parent.objectName === name) return parent
    var kids = [].concat(parent.children ? Array.prototype.slice.call(parent.children) : [],
                         parent.data ? Array.prototype.slice.call(parent.data) : [],
                         parent.contentItem && parent.contentItem !== parent ? [parent.contentItem] : [])
    for (var i = 0; i < kids.length; i++) {
      if (kids[i] === parent) continue
      var hit = findChildByName(kids[i], name)
      if (hit) return hit
    }
    return null
  }
}
