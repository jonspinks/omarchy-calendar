// Typing.js under node: the edits the fields make now that Qt doesn't.
//   node tests/typing.test.js
const fs = require("fs")
const path = require("path")
const src = fs.readFileSync(path.join(__dirname, "..", "Typing.js"), "utf8").replace(/^\.pragma library\s*$/m, "")
const T = new Function(src + "; return { apply, splice, clean, MAX_CHARS, KEY_BACKSPACE, KEY_DELETE, KEY_RETURN," +
  " KEY_INSERT, KEY_V, KEY_X, KEY_Z, KEY_Y, KEY_A, SHIFT, CTRL }")()

let failed = 0
function eq(got, want, name) {
  const ok = JSON.stringify(got) === JSON.stringify(want)
  if (!ok) failed++
  console.log((ok ? "ok   " : "FAIL ") + name + (ok ? "" : "\n     got  " + JSON.stringify(got) + "\n     want " + JSON.stringify(want)))
}

const at = (text, cursor, selStart, selEnd) =>
  ({ text, cursor, selStart: selStart === undefined ? cursor : selStart, selEnd: selEnd === undefined ? cursor : selEnd })
const key = (k, mods, text) => ({ key: k, modifiers: mods || 0, text: text || "" })
const type = (ch) => ({ key: ch.toUpperCase().charCodeAt(0), modifiers: 0, text: ch })

// Typing inserts at the cursor, or over the selection.
eq(T.apply(at("Lunch", 5), type("!"), false), { text: "Lunch!", cursor: 6 }, "type at the end")
eq(T.apply(at("Lnch", 1), type("u"), false), { text: "Lunch", cursor: 2 }, "type in the middle")
eq(T.apply(at("Team lunch", 10, 5, 10), type("s"), false), { text: "Team s", cursor: 6 }, "type over a selection")
eq(T.apply(at("Café", 4), { key: 0, modifiers: 0, text: "é" }, false), { text: "Caféé", cursor: 5 }, "non-ASCII text")

// Deleting.
eq(T.apply(at("Lunch", 5), key(T.KEY_BACKSPACE), false), { text: "Lunc", cursor: 4 }, "Backspace")
eq(T.apply(at("Lunch", 0), key(T.KEY_BACKSPACE), false), { handled: true }, "Backspace at the start does nothing")
eq(T.apply(at("Team lunch", 10), key(T.KEY_BACKSPACE, T.CTRL), false), { text: "Team ", cursor: 5 }, "Ctrl+Backspace: a word")
eq(T.apply(at("Lunch", 0), key(T.KEY_DELETE), false), { text: "unch", cursor: 0 }, "Delete")
eq(T.apply(at("Team lunch", 0), key(T.KEY_DELETE, T.CTRL), false), { text: " lunch", cursor: 0 }, "Ctrl+Delete: a word")
eq(T.apply(at("Team lunch", 4, 0, 4), key(T.KEY_DELETE), false), { text: " lunch", cursor: 0 }, "Delete a selection")

// Cut copies first (the QML calls the field's copy()), then deletes.
eq(T.apply(at("Team lunch", 4, 0, 4), key(T.KEY_X, T.CTRL), false), { cut: true, text: " lunch", cursor: 0 }, "Ctrl+X")
eq(T.apply(at("Team", 4), key(T.KEY_X, T.CTRL), false), { handled: true }, "Ctrl+X with nothing selected")

// Every way to paste goes to the bounded helper; Qt's own paste is never used.
eq(T.apply(at("", 0), key(T.KEY_V, T.CTRL), false), { paste: "clipboard" }, "Ctrl+V asks the helper")
eq(T.apply(at("", 0), key(T.KEY_V, T.CTRL | T.SHIFT), false), { paste: "clipboard" }, "Ctrl+Shift+V asks the helper")
eq(T.apply(at("", 0), key(T.KEY_INSERT, T.SHIFT), false), { paste: "clipboard" }, "Shift+Insert asks the helper")

// Undo and redo.
eq(T.apply(at("a", 1), key(T.KEY_Z, T.CTRL), false), { undo: true }, "Ctrl+Z")
eq(T.apply(at("a", 1), key(T.KEY_Z, T.CTRL | T.SHIFT), false), { redo: true }, "Ctrl+Shift+Z")
eq(T.apply(at("a", 1), key(T.KEY_Y, T.CTRL), false), { redo: true }, "Ctrl+Y")

// Keys the field keeps: navigation, select all, copy, Enter on one line, Escape, Tab.
eq(T.apply(at("a", 1), key(T.KEY_A, T.CTRL, "\u0001"), false), null, "Ctrl+A stays with the field")
eq(T.apply(at("a", 1), key(T.KEY_RETURN, 0, "\r"), false), null, "Enter on one line stays with the form")
eq(T.apply(at("a", 1), key(0x01000000, 0, "\u001b"), false), null, "Escape stays with the form")
eq(T.apply(at("a", 1), key(0x01000001, 0, "\t"), false), null, "Tab stays with the form")
eq(T.apply(at("a", 1), key(0x01000012), false), null, "Left arrow stays with the field")

// Several lines: Enter breaks the line.
eq(T.apply(at("Agenda", 6), key(T.KEY_RETURN, 0, "\r"), true), { text: "Agenda\n", cursor: 7 }, "Enter in notes")

// What a paste may insert.
eq(T.clean("a\r\nb\u0007c", true), "a\nbc", "notes keep line breaks, drop control characters")
eq(T.clean("one\ntwo\r\nthree", false), "one two three", "one-line fields join lines")
eq(T.splice(at("", 0), "x".repeat(T.MAX_CHARS + 50), false).text.length, T.MAX_CHARS, "a field never grows past its limit")
eq(T.splice(at("abc", 3), "", false), null, "inserting nothing changes nothing")

if (failed) { console.log(failed + " failed"); process.exit(1) }
console.log("all passed")
