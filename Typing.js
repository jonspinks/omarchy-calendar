.pragma library
// Typing for Datebook's text fields, done here instead of by Qt.
//
// Every field is a native TextInput/TextEdit kept readOnly. A writable one
// reads the whole clipboard by itself each time the clipboard changes (Qt
// 6.12 q_canPasteChanged), with no size or time limit, so a hostile
// clipboard owner could stall or bloat the shell. Read-only, Qt still draws
// the text, the cursor and the selection, and handles arrows, Home/End,
// Shift-selection and copy; it never asks for the clipboard. The keys that
// change text come here, and paste goes through scripts/omcal/paste.py,
// which reads at most a few KB within a fixed time.
//
// `apply` is pure (tested under node); `handle` is the QML glue.

var KEY_BACKSPACE = 0x01000003
var KEY_RETURN = 0x01000004
var KEY_ENTER = 0x01000005
var KEY_INSERT = 0x01000006
var KEY_DELETE = 0x01000007
var KEY_A = 0x41
var KEY_V = 0x56
var KEY_X = 0x58
var KEY_Y = 0x59
var KEY_Z = 0x5a
var SHIFT = 0x02000000
var CTRL = 0x04000000
var ALT = 0x08000000
var META = 0x10000000

// Longest text a field takes, typed or pasted.
var MAX_CHARS = 8000
var UNDO_STEPS = 100

function wordStartBefore(text, at) {
  var i = at
  while (i > 0 && /\s/.test(text.charAt(i - 1))) i--
  while (i > 0 && !/\s/.test(text.charAt(i - 1))) i--
  return i
}

function wordEndAfter(text, at) {
  var i = at
  while (i < text.length && /\s/.test(text.charAt(i))) i++
  while (i < text.length && !/\s/.test(text.charAt(i))) i++
  return i
}

// Text that may be inserted: no control characters, except a line break in
// a multi-line field.
function clean(text, multiLine) {
  var s = String(text || "").replace(/\r\n?/g, "\n")
  s = multiLine ? s.replace(/[\u0000-\u0009\u000b-\u001f\u007f]/g, "")
                : s.replace(/\n+/g, " ").replace(/[\u0000-\u001f\u007f]/g, "")
  return s
}

// Put `insert` in place of the selection (or at the cursor).
function splice(state, insert, multiLine) {
  var text = state.text
  var a = Math.min(state.selStart, state.selEnd)
  var b = Math.max(state.selStart, state.selEnd)
  if (a === b) a = b = state.cursor
  var add = clean(insert, multiLine)
  var room = MAX_CHARS - (text.length - (b - a))
  if (add.length > room) add = add.slice(0, Math.max(0, room))
  if (add === "" && a === b) return null
  return { text: text.slice(0, a) + add + text.slice(b), cursor: a + add.length }
}

// One key on a field's state {text, cursor, selStart, selEnd}. Returns
//   {text, cursor}  the edit to make,
//   {paste: "clipboard" | "primary"}  ask the bounded helper,
//   {cut: true, text, cursor}  copy the selection first, then make the edit,
//   {undo: true} / {redo: true},
//   null  not a typing key: leave it to the field (navigation, Enter, Tab).
function apply(state, ev, multiLine) {
  var mods = ev.modifiers & (SHIFT | CTRL | ALT | META)
  var ctrl = (mods & CTRL) !== 0
  var hasSel = state.selStart !== state.selEnd
  if ((ctrl && !(mods & ALT) && ev.key === KEY_V) || (mods === SHIFT && ev.key === KEY_INSERT))
    return { paste: "clipboard" }
  if (ctrl && ev.key === KEY_X) {
    if (!hasSel) return { handled: true }
    var cut = splice(state, "", multiLine)
    return { cut: true, text: cut.text, cursor: cut.cursor }
  }
  if (ctrl && ev.key === KEY_Z) return (mods & SHIFT) ? { redo: true } : { undo: true }
  if (ctrl && ev.key === KEY_Y) return { redo: true }
  if (ev.key === KEY_BACKSPACE) {
    if (hasSel) return splice(state, "", multiLine)
    if (state.cursor === 0) return { handled: true }
    var from = ctrl ? wordStartBefore(state.text, state.cursor) : state.cursor - 1
    return { text: state.text.slice(0, from) + state.text.slice(state.cursor), cursor: from }
  }
  if (ev.key === KEY_DELETE && !(mods & SHIFT)) {
    if (hasSel) return splice(state, "", multiLine)
    if (state.cursor >= state.text.length) return { handled: true }
    var to = ctrl ? wordEndAfter(state.text, state.cursor) : state.cursor + 1
    return { text: state.text.slice(0, state.cursor) + state.text.slice(to), cursor: state.cursor }
  }
  if (multiLine && (ev.key === KEY_RETURN || ev.key === KEY_ENTER) && !ctrl)
    return splice(state, "\n", true) || { handled: true }
  if (ctrl || (mods & (ALT | META))) return null
  var typed = String(ev.text || "")
  if (typed === "" || /^[\u0000-\u001f\u007f]+$/.test(typed)) return null
  return splice(state, typed, multiLine) || { handled: true }
}

// ---- QML glue

var history = new WeakMap()

function stacks(field) {
  var h = history.get(field)
  if (!h) {
    h = { undo: [], redo: [] }
    history.set(field, h)
  }
  return h
}

function stateOf(field) {
  return { text: String(field.text), cursor: field.cursorPosition,
           selStart: field.selectionStart, selEnd: field.selectionEnd }
}

function remember(field) {
  var h = stacks(field)
  h.undo.push({ text: String(field.text), cursor: field.cursorPosition })
  if (h.undo.length > UNDO_STEPS) h.undo.shift()
  h.redo = []
}

function set(field, text, cursor) {
  field.text = text
  field.cursorPosition = Math.max(0, Math.min(cursor, text.length))
}

// Insert text the helper read, where the cursor is now.
function insert(field, text, multiLine) {
  var edit = splice(stateOf(field), text, multiLine)
  if (!edit) return
  remember(field)
  set(field, edit.text, edit.cursor)
}

// From a field's Keys.onPressed. `canEdit`: the field is editable now.
// `paste(mode)`: start the bounded helper for this field. Returns true when
// the key was taken.
function handle(field, event, canEdit, multiLine, paste) {
  if (!canEdit) return false
  var out = apply(stateOf(field), event, multiLine)
  if (!out) return false
  event.accepted = true
  if (out.paste) {
    if (paste) paste(out.paste)
  } else if (out.undo || out.redo) {
    var h = stacks(field)
    var from = out.undo ? h.undo : h.redo
    var to = out.undo ? h.redo : h.undo
    if (from.length) {
      to.push({ text: String(field.text), cursor: field.cursorPosition })
      var step = from.pop()
      set(field, step.text, step.cursor)
    }
  } else if (out.text !== undefined) {
    if (out.cut) field.copy()
    remember(field)
    set(field, out.text, out.cursor)
  }
  return true
}

// The text was replaced from outside (a new draft): old undo steps no longer apply.
function forget(field) {
  history.delete(field)
}
