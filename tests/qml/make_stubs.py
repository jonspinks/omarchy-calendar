"""Stand-ins for the shell's modules, so the real EventEditor.qml loads
under qmltestrunner. Usage: python3 -B make_stubs.py <out-dir>

Quickshell's own modules live inside the shell binary, and qs.Commons
needs them, so neither loads outside the shell. The qs.Ui stand-ins are
generated from the installed shell's files (/usr/share/omarchy/shell/Ui):
each keeps the real widget's property and signal names, without its
drawing, so the editor binds to exactly what the shell offers. Except
TextField, which stays Qt Quick Controls' native TextField: the field
behaviour is what the tests are about. Nothing from the shell is copied
into this repository; the files are written to <out-dir> per run.

Exit 3 when the shell isn't installed (the test is then skipped).
"""

import os
import re
import sys

SHELL_UI = "/usr/share/omarchy/shell/Ui"

# Widget -> the root its stand-in is built on.
UI = {
    "BorderSurface": ("QtQuick", "Rectangle"),
    "Button": (None, "BorderSurface"),
    "Toggle": (None, "BorderSurface"),
    "PanelActionButton": (None, "BorderSurface"),
    "Dropdown": ("QtQuick", "Item"),
    "ButtonGroup": ("QtQuick", "Row"),
    "PanelToolTip": ("QtQuick.Controls", "ToolTip"),
}

DEFAULTS = {"bool": "false", "int": "0", "real": "0", "string": '""', "color": '"transparent"',
            "var": "undefined", "list<var>": "[]"}

COMMONS = {
    "Style.qml": """pragma Singleton
import QtQuick
QtObject {
  function space(n) { return n }
  readonly property var font: ({ body: 14, bodySmall: 12, caption: 11, subtitle: 16, title: 18,
                                 iconSmall: 14, icon: 16, family: "sans-serif" })
  readonly property var spacing: ({ controlPaddingX: 8, inputPaddingY: 6, controlGap: 6, xs: 2, sm: 4,
                                    md: 8, lg: 12, hairline: 1 })
  readonly property real cornerRadius: 4
  readonly property real normalBorderWidth: 1
  function controlFill() { return "transparent" }
  function selectionFillFor() { return "#335577" }
  function hoverStateColor() { return "#222222" }
  function hoverFillFor() { return "#222222" }
}
""",
    "Color.qml": """pragma Singleton
import QtQuick
QtObject {
  readonly property color accent: "#5588cc"
  readonly property color urgent: "#cc3333"
  readonly property color foreground: "#dddddd"
  readonly property color background: "#111111"
  readonly property var popups: ({ border: "#444444", background: "#222222" })
}
""",
    "Border.qml": """pragma Singleton
import QtQuick
QtObject {
  function none() { return ({}) }
  function controlSpec() { return ({}) }
  function localOrSurfaceSpec() { return ({}) }
  function needsOverlay() { return false }
  function top() { return 1 }
  function right() { return 1 }
  function bottom() { return 1 }
  function left() { return 1 }
}
""",
}

QUICKSHELL = """pragma Singleton
import QtQuick
QtObject {
  function env(name) { return "" }
}
"""

# A Process the test finishes by hand: running = true records the command;
# finish(code, text) sets stdout's text and emits exited.
PROCESS = """import QtQuick
QtObject {
  id: proc
  property var command: []
  property bool running: false
  property QtObject stdout: null
  property QtObject stderr: null
  property var started: []
  signal exited(int exitCode, int exitStatus)
  onRunningChanged: if (running) started.push(command)
  function finish(code, text) {
    if (stdout) stdout.text = text
    running = false
    exited(code, 0)
  }
}
"""

FILEVIEW = """import QtQuick
QtObject {
  property string path: ""
  property bool watchChanges: false
  property bool printErrors: true
  signal loaded()
  signal loadFailed(int error)
  signal fileChanged()
  function text() { return "" }
  function reload() {}
}
"""

COLLECTOR = """import QtQuick
QtObject {
  property string text: ""
  property bool waitForEnd: false
}
"""


def declarations(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^  (?:readonly |required |default )*property (\S+) (\w+)", line)
            if m:
                kind, name = m.groups()
                out.append(f"  property {kind} {name}: {DEFAULTS.get(kind, 'undefined' if kind not in ('real', 'int') else '0')}")
                continue
            m = re.match(r"^  (signal \w+(?:\([^)]*\))?)", line)
            if m:
                out.append("  " + m.group(1))
    return out


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main(out):
    if not os.path.isdir(SHELL_UI):
        print("no Omarchy shell at " + SHELL_UI, file=sys.stderr)
        return 3
    write(f"{out}/Quickshell/qmldir", "module Quickshell\nsingleton Quickshell 1.0 Quickshell.qml\n")
    write(f"{out}/Quickshell/Quickshell.qml", QUICKSHELL)
    write(f"{out}/Quickshell/Io/qmldir", "module Quickshell.Io\nProcess 1.0 Process.qml\nStdioCollector 1.0 StdioCollector.qml\nFileView 1.0 FileView.qml\n")
    write(f"{out}/Quickshell/Io/FileView.qml", FILEVIEW)
    write(f"{out}/Quickshell/Io/Process.qml", PROCESS)
    write(f"{out}/Quickshell/Io/StdioCollector.qml", COLLECTOR)
    qmldir = ["module qs.Commons"]
    for name, text in COMMONS.items():
        write(f"{out}/qs/Commons/{name}", text)
        qmldir.append(f"singleton {name[:-4]} 1.0 {name}")
    write(f"{out}/qs/Commons/qmldir", "\n".join(qmldir) + "\n")
    qmldir = ["module qs.Ui"]
    for name, (module, root) in UI.items():
        imports = "import QtQuick\nimport QtQuick.Controls\n"
        body = declarations(f"{SHELL_UI}/{name}.qml")
        if name == "BorderSurface":
            body = [l for l in body if not re.search(r"property \S+ (padding|topPadding|rightPadding|bottomPadding|leftPadding)\b", l)] + [
                "  property real padding: 0", "  property real topPadding: 0", "  property real rightPadding: 0",
                "  property real bottomPadding: 0", "  property real leftPadding: 0"]
        if root == "ToolTip":
            body = [l for l in body if not re.search(r"property \S+ (text|delay|timeout|visible)\b", l)]
        write(f"{out}/qs/Ui/{name}.qml", imports + f"{root} {{\n" + "\n".join(body) + "\n}\n")
        qmldir.append(f"{name} 1.0 {name}.qml")
    # The real field: Qt's TextField, with the shell's extra properties.
    write(f"{out}/qs/Ui/TextField.qml", "import QtQuick\nimport QtQuick.Controls as C\nC.TextField {\n"
          "  property color foreground: \"#dddddd\"\n  property color accent: \"#5588cc\"\n"
          "  property color selectionTint: \"#335577\"\n  property bool password: false\n"
          "  property bool hasCursor: false\n}\n")
    qmldir.append("TextField 1.0 TextField.qml")
    write(f"{out}/qs/Ui/qmldir", "\n".join(qmldir) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
