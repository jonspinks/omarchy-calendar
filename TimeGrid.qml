import QtQuick
import QtQuick.Controls
import qs.Commons
import qs.Ui
import "Model.js" as Model

// Day, week and working-week views: one column per day, hours down the side.
//
// All-day events sit in a strip above the grid. Timed events are blocks
// placed by Model.dayLayout, which puts overlapping meetings side by side.
// The grid scrolls; it opens on the current hour (or 8am on another day),
// and today carries a line at the current time.
Item {
  id: grid

  property var days: []            // day keys, left to right
  property var byDay: ({})
  property string todayKey: ""
  property bool use24h: false
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family

  signal openEvent(var ev)
  signal joinEvent(string url)
  signal pickDay(string key)
  signal createAt(string dayKey, int minutes)
  // A block dropped at new times (ms). The panel writes it.
  signal moveEvent(var ev, real startMs, real endMs)

  // The event being written, so a dropped block stays put until it lands.
  property string writingUid: ""

  // ---- Dragging. One block at a time: it says where the pointer is in the
  //      scroller's viewport, and the timer scrolls when that is near an edge.
  property var dragBlock: null
  property real dragViewY: 0
  Timer {
    interval: 40
    repeat: true
    running: grid.dragBlock !== null
    onTriggered: {
      var edge = grid.hourHeight / 2
      var step = 0
      if (grid.dragViewY < edge) step = -grid.hourHeight / 4
      else if (grid.dragViewY > scroller.height - edge) step = grid.hourHeight / 4
      if (!step) return
      var next = Math.max(0, Math.min(scroller.contentHeight - scroller.height, scroller.contentY + step))
      if (next === scroller.contentY) return
      scroller.contentY = next
      grid.dragBlock.follow()
    }
  }

  // The all-day events a "+n more" click is naming. The strip keeps the
  // first two; this is the rest, in the day's own order.
  property var moreItems: []
  property var moreAnchor: null

  function openMore(items, anchor) {
    moreItems = items
    moreAnchor = anchor
    // The list has to be built before it can be placed under the link.
    Qt.callLater(grid.placeMore)
  }

  function placeMore() {
    if (!moreAnchor || !moreItems.length) return
    // x and y are in this grid, the popup's own item, the same way the
    // date popup sits on its field.
    var pos = moreAnchor.mapToItem(grid, 0, moreAnchor.height + Style.space(2))
    var w = morePopup.width
    morePopup.x = Math.max(0, Math.min(pos.x, Math.max(0, width - w)))
    morePopup.y = Math.max(0, pos.y)
    morePopup.open()
  }

  onDaysChanged: morePopup.close()

  readonly property int gutter: Style.space(46)
  readonly property int hourHeight: Style.space(40)
  property int visibleHours: 11
  readonly property real colWidth: days.length ? (width - gutter) / days.length : 0
  readonly property var hours: Model.hourRange(days, byDay)
  readonly property int allDayRows: {
    var most = 0
    for (var i = 0; i < days.length; i++) {
      var n = (byDay[days[i]] || []).filter(function(e) { return e.allDay }).length
      most = Math.max(most, Math.min(n, 3))
    }
    return most
  }

  property date now: new Date()
  Timer { interval: 60000; running: true; repeat: true; onTriggered: grid.now = new Date() }

  function hourLabel(h) {
    if (use24h) return (h < 10 ? "0" : "") + h + ":00"
    return (h % 12 || 12) + (h < 12 ? "am" : "pm")
  }

  implicitHeight: header.height + allDay.height + scroller.height + Style.space(4)

  // ---- Day headers: click one to open that day on its own.
  Row {
    id: header
    x: grid.gutter
    height: Style.space(34)

    Repeater {
      model: grid.days

      Rectangle {
        id: head
        required property var modelData
        readonly property date date: Model.keyToDate(modelData)
        width: grid.colWidth
        height: header.height
        radius: Style.cornerRadius
        color: headMouse.containsMouse ? Style.hoverFillFor(grid.foreground, Color.accent) : "transparent"
        border.width: modelData === grid.todayKey ? Style.spacing.hairline : 0
        border.color: Style.normalBorderFor(grid.foreground, Color.accent)

        Column {
          anchors.centerIn: parent
          Text {
            anchors.horizontalCenter: parent.horizontalCenter
            textFormat: Text.PlainText
            text: ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"][head.date.getDay()]
            color: Qt.darker(grid.foreground, 1.5)
            font.family: grid.fontFamily
            font.pixelSize: Style.font.caption
            font.letterSpacing: 1
            font.bold: true
          }
          Text {
            anchors.horizontalCenter: parent.horizontalCenter
            textFormat: Text.PlainText
            text: head.date.getDate()
            color: grid.foreground
            font.family: grid.fontFamily
            font.pixelSize: Style.font.body
            font.bold: head.modelData === grid.todayKey
          }
        }

        MouseArea {
          id: headMouse
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: grid.days.length > 1 ? Qt.PointingHandCursor : Qt.ArrowCursor
          onClicked: if (grid.days.length > 1) grid.pickDay(head.modelData)
        }
      }
    }
  }

  // ---- All-day strip, up to three per day, then "+n more".
  Row {
    id: allDay
    anchors.top: header.bottom
    x: grid.gutter
    height: grid.allDayRows ? grid.allDayRows * Style.space(20) + Style.space(6) : 0
    visible: grid.allDayRows > 0

    Repeater {
      model: grid.days

      Column {
        id: allDayCol
        required property var modelData
        readonly property var items: (grid.byDay[modelData] || []).filter(function(e) { return e.allDay })
        width: grid.colWidth
        spacing: Style.space(2)
        topPadding: Style.space(3)

        Repeater {
          model: allDayCol.items.slice(0, allDayCol.items.length > 3 ? 2 : 3)

          Rectangle {
            required property var modelData
            width: allDayCol.width - Style.space(3)
            height: Style.space(18)
            radius: Style.cornerRadius
            color: Qt.rgba(Qt.color(modelData.color).r, Qt.color(modelData.color).g, Qt.color(modelData.color).b, 0.28)
            opacity: modelData.declined ? 0.5 : 1

            Text {
              anchors.fill: parent
              anchors.leftMargin: Style.space(5)
              anchors.rightMargin: Style.space(3)
              verticalAlignment: Text.AlignVCenter
              textFormat: Text.PlainText
              elide: Text.ElideRight
              text: parent.modelData.title
              color: grid.foreground
              font.family: grid.fontFamily
              font.pixelSize: Style.font.caption
            }

            MouseArea {
              anchors.fill: parent
              cursorShape: Qt.PointingHandCursor
              onClicked: grid.openEvent(parent.modelData)
            }
          }
        }

        Rectangle {
          id: moreLink
          visible: allDayCol.items.length > 3
          width: parent.width - Style.space(3)
          height: Style.space(16)
          radius: Style.cornerRadius
          color: moreMouse.containsMouse ? Style.hoverFillFor(grid.foreground, Color.accent) : "transparent"

          Text {
            anchors.fill: parent
            leftPadding: Style.space(5)
            verticalAlignment: Text.AlignVCenter
            textFormat: Text.PlainText
            elide: Text.ElideRight
            text: "+" + (allDayCol.items.length - 2) + " more"
            color: moreMouse.containsMouse ? grid.foreground : Qt.darker(grid.foreground, 1.5)
            font.family: grid.fontFamily
            font.pixelSize: Style.font.caption
          }

          MouseArea {
            id: moreMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: grid.openMore(allDayCol.items.slice(2), moreLink)
          }
        }
      }
    }
  }

  // Names the all-day events the strip left off. A row opens the event.
  Popup {
    id: morePopup
    padding: Style.space(6)
    width: Style.space(280)
    // Counted from the rows, not the column's height: the column is given
    // its height by the popup, so reading it back stays at nothing.
    height: Math.min(Style.space(280), grid.moreItems.length * (Style.space(26) + Style.space(2)) + padding * 2)
    modal: true
    dim: false
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    readonly property var popupBorderSpec: Border.localOrSurfaceSpec("popups", "border", Color.popups.border, Color.popups.border, Style.normalBorderWidth)

    background: BorderSurface {
      color: Color.popups.background
      borderSpec: morePopup.popupBorderSpec
      radius: Style.cornerRadius
    }

    contentItem: Column {
      id: moreColumn
      width: morePopup.availableWidth
      spacing: Style.space(2)

      Repeater {
        model: grid.moreItems

        Rectangle {
          id: moreRow
          required property var modelData
          width: moreColumn.width
          height: Style.space(26)
          radius: Style.cornerRadius
          color: Qt.rgba(Qt.color(moreRow.modelData.color).r, Qt.color(moreRow.modelData.color).g, Qt.color(moreRow.modelData.color).b, moreRowMouse.containsMouse ? 0.45 : 0.28)
          opacity: moreRow.modelData.declined ? 0.5 : 1

          Text {
            anchors.fill: parent
            anchors.leftMargin: Style.space(8)
            anchors.rightMargin: Style.space(6)
            verticalAlignment: Text.AlignVCenter
            textFormat: Text.PlainText
            elide: Text.ElideRight
            text: moreRow.modelData.title
            color: grid.foreground
            font.family: grid.fontFamily
            font.pixelSize: Style.font.bodySmall
            font.strikeout: moreRow.modelData.declined
          }

          MouseArea {
            id: moreRowMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
              var ev = moreRow.modelData
              morePopup.close()
              grid.openEvent(ev)
            }
          }
        }
      }
    }
  }

  // ---- The hour grid.
  Flickable {
    id: scroller
    anchors.top: allDay.bottom
    anchors.topMargin: Style.space(4)
    width: grid.width
    height: Math.min(grid.visibleHours, grid.hours.last - grid.hours.first) * grid.hourHeight
    contentHeight: (grid.hours.last - grid.hours.first) * grid.hourHeight
    clip: true
    boundsBehavior: Flickable.StopAtBounds

    function scrollToNow() {
      var focusHour = grid.days.indexOf(grid.todayKey) >= 0 ? grid.now.getHours() - 1 : 8
      contentY = Math.max(0, Math.min(contentHeight - height, (focusHour - grid.hours.first) * grid.hourHeight))
    }
    Component.onCompleted: scrollToNow()
    onContentHeightChanged: scrollToNow()

    Item {
      id: content
      width: scroller.width
      height: scroller.contentHeight

      // Behind the events, so a click on one still opens it. A double-click
      // on an empty hour starts an event then; a drag still scrolls.
      MouseArea {
        anchors.fill: parent
        onDoubleClicked: function(mouse) {
          if (mouse.x < grid.gutter || grid.colWidth <= 0) return
          var col = Math.floor((mouse.x - grid.gutter) / grid.colWidth)
          if (col < 0 || col >= grid.days.length) return
          var minutes = Model.slotStart(mouse.y, grid.hourHeight, grid.hours.first, grid.hours.last)
          if (minutes < 0) return
          grid.createAt(grid.days[col], minutes)
        }
      }

      // Hour lines and labels.
      Repeater {
        model: grid.hours.last - grid.hours.first

        Item {
          required property int index
          y: index * grid.hourHeight
          width: parent.width
          height: grid.hourHeight

          Text {
            width: grid.gutter - Style.space(8)
            horizontalAlignment: Text.AlignRight
            y: -Style.space(6)
            visible: index > 0
            textFormat: Text.PlainText
            text: grid.hourLabel(grid.hours.first + index)
            color: Qt.darker(grid.foreground, 1.9)
            font.family: grid.fontFamily
            font.pixelSize: Style.font.caption
          }

          Rectangle {
            x: grid.gutter
            width: parent.width - grid.gutter
            height: Style.spacing.hairline
            color: grid.foreground
            opacity: 0.08
          }
        }
      }

      // Column separators.
      Repeater {
        model: grid.days.length
        Rectangle {
          required property int index
          x: grid.gutter + index * grid.colWidth
          width: Style.spacing.hairline
          height: parent.height
          color: grid.foreground
          opacity: 0.06
        }
      }

      // Event blocks, day by day.
      Repeater {
        model: grid.days

        Item {
          id: dayCol
          required property var modelData
          required property int index
          x: grid.gutter + index * grid.colWidth
          width: grid.colWidth
          height: parent.height

          Repeater {
            model: Model.dayLayout(grid.byDay[dayCol.modelData] || [], dayCol.modelData)

            Rectangle {
              id: block
              required property var modelData
              readonly property var ev: modelData.event
              readonly property real slot: (dayCol.width - Style.space(4)) / modelData.columns
              readonly property real startMs: new Date(ev.start).getTime()
              readonly property real endMs: new Date(ev.end).getTime()
              // A block moves from the day its event starts on, and stretches
              // on the day it ends on; a middle day of a long event does neither.
              readonly property bool canMove: Model.draggable(ev) && Model.keyForDate(new Date(startMs)) === dayCol.modelData
              readonly property bool canResize: Model.draggable(ev) && modelData.bottom === (endMs - Model.keyToDate(dayCol.modelData).getTime()) / 60000

              // "", "move" or "resize" while the pointer is down and has moved.
              property string dragMode: ""
              property real pressX: 0
              property real pressY: 0
              property real viewX: 0
              property real viewY: 0
              property int dragDays: 0
              property var preview: null
              property bool held: false
              property bool justDragged: false
              readonly property bool lifted: (dragMode !== "" || held) && preview !== null
              readonly property string previewDay: grid.days[Math.max(0, Math.min(grid.days.length - 1, dayCol.index + dragDays))] || dayCol.modelData
              readonly property real previewTop: lifted ? (preview.start - Model.keyToDate(previewDay).getTime()) / 60000 : modelData.top
              readonly property real previewBottom: lifted ? previewTop + (preview.end - preview.start) / 60000 : modelData.bottom

              function press(mode, mouse, from) {
                var p = from.mapToItem(scroller, mouse.x, mouse.y)
                pressX = p.x
                pressY = p.y + scroller.contentY
                viewX = p.x
                viewY = p.y
                dragMode = ""
                justDragged = false
                pendingMode = mode
              }
              property string pendingMode: ""
              function moveTo(mouse, from) {
                var p = from.mapToItem(scroller, mouse.x, mouse.y)
                viewX = p.x
                viewY = p.y
                if (dragMode === "") {
                  if (Math.abs(p.x - pressX) + Math.abs(p.y + scroller.contentY - pressY) < Style.space(6)) return
                  dragMode = pendingMode
                  grid.dragBlock = block
                }
                follow()
              }
              // Where the pointer now is, as times. Also run by the scroll timer.
              function follow() {
                if (dragMode === "") return
                grid.dragViewY = viewY
                var dy = viewY + scroller.contentY - pressY
                var days = 0
                if (dragMode === "move" && grid.colWidth > 0) {
                  days = Math.round((viewX - pressX) / grid.colWidth)
                  days = Math.max(-dayCol.index, Math.min(grid.days.length - 1 - dayCol.index, days))
                }
                dragDays = days
                preview = Model.dragTimes(startMs, endMs, dy / grid.hourHeight * 60, days, dragMode)
              }
              function drop() {
                if (dragMode === "") return
                grid.dragBlock = null
                justDragged = true
                var p = preview
                dragMode = ""
                if (!p || (p.start === startMs && p.end === endMs)) { preview = null; return }
                held = true
                grid.moveEvent(ev, p.start, p.end)
                // A write already running refuses this one: let the block go back.
                Qt.callLater(function() { if (grid.writingUid !== block.ev.uid) block.release() })
              }
              function release() { held = false; preview = null; dragDays = 0 }
              readonly property bool writing: grid.writingUid === ev.uid
              onWritingChanged: if (!writing && held) settle.restart()
              // The write patches events.json; give the reload a moment before
              // letting go, so the block doesn't jump back and forward again.
              Timer { id: settle; interval: 1500; onTriggered: block.release() }

              x: lifted ? Style.space(2) + dragDays * grid.colWidth : Style.space(2) + modelData.column * slot
              y: (previewTop - grid.hours.first * 60) / 60 * grid.hourHeight + 1
              z: lifted ? 10 : 0
              width: lifted ? dayCol.width - Style.space(4) : slot - Style.space(2)
              height: Math.max(Style.space(16), (previewBottom - previewTop) / 60 * grid.hourHeight - 2)
              radius: Style.cornerRadius
              color: Qt.rgba(Qt.color(ev.color).r, Qt.color(ev.color).g, Qt.color(ev.color).b, (blockMouse.containsMouse || lifted) ? 0.42 : 0.28)
              border.width: lifted ? Style.normalBorderWidth : 0
              border.color: ev.color
              opacity: ev.declined ? 0.45 : 1
              clip: true

              Rectangle {
                width: Style.space(3)
                height: parent.height
                radius: width / 2
                color: block.ev.color
              }

              Column {
                anchors.fill: parent
                anchors.leftMargin: Style.space(6)
                anchors.rightMargin: joinIcon.visible ? joinIcon.width + Style.space(4) : Style.space(3)
                anchors.topMargin: Style.space(2)
                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  elide: Text.ElideRight
                  text: block.ev.title
                  color: grid.foreground
                  font.family: grid.fontFamily
                  font.pixelSize: Style.font.caption
                  font.strikeout: block.ev.declined
                }
                Text {
                  visible: block.height > Style.space(32) || block.lifted
                  width: parent.width
                  textFormat: Text.PlainText
                  elide: Text.ElideRight
                  text: block.lifted
                        ? Model.clockText(Model.minutesOf(new Date(block.preview.start)), grid.use24h) + " – "
                          + Model.clockText(Model.minutesOf(new Date(block.preview.end)), grid.use24h)
                        : block.ev.label
                  color: Qt.darker(grid.foreground, 1.4)
                  font.family: grid.fontFamily
                  font.pixelSize: Style.font.caption
                }
              }

              // Click opens it; your own events also drag to a new time or day.
              // Holding the press keeps the grid from scrolling under it.
              MouseArea {
                id: blockMouse
                anchors.fill: parent
                hoverEnabled: true
                preventStealing: block.canMove
                cursorShape: block.dragMode === "move" ? Qt.ClosedHandCursor : Qt.PointingHandCursor
                onPressed: function(mouse) { if (block.canMove) block.press("move", mouse, blockMouse) }
                onPositionChanged: function(mouse) { if (pressed && block.canMove) block.moveTo(mouse, blockMouse) }
                onReleased: block.drop()
                onCanceled: { grid.dragBlock = null; block.dragMode = ""; block.preview = null }
                onClicked: {
                  if (block.justDragged) { block.justDragged = false; return }
                  grid.openEvent(block.ev)
                }
              }

              // The bottom edge stretches the end.
              MouseArea {
                id: resizeMouse
                visible: block.canResize && block.height > Style.space(20)
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: Style.space(6)
                hoverEnabled: true
                preventStealing: true
                cursorShape: Qt.SizeVerCursor
                onPressed: function(mouse) { block.press("resize", mouse, resizeMouse) }
                onPositionChanged: function(mouse) { if (pressed) block.moveTo(mouse, resizeMouse) }
                onReleased: block.drop()
                onCanceled: { grid.dragBlock = null; block.dragMode = ""; block.preview = null }
              }

              Text {
                id: joinIcon
                visible: !!block.ev.join && block.width > Style.space(40)
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: Style.space(3)
                textFormat: Text.PlainText
                text: "󰕧"
                color: joinMouse.containsMouse ? Style.hoverStateColor(grid.foreground, Color.accent) : grid.foreground
                font.family: grid.fontFamily
                font.pixelSize: Style.font.body

                MouseArea {
                  id: joinMouse
                  anchors.fill: parent
                  anchors.margins: -Style.space(3)
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: grid.joinEvent(block.ev.join.url)
                }
              }
            }
          }
        }
      }

      // Now.
      Rectangle {
        readonly property int col: grid.days.indexOf(grid.todayKey)
        readonly property real minutes: grid.now.getHours() * 60 + grid.now.getMinutes()
        visible: col >= 0 && minutes >= grid.hours.first * 60 && minutes <= grid.hours.last * 60
        x: grid.gutter + col * grid.colWidth
        y: (minutes - grid.hours.first * 60) / 60 * grid.hourHeight
        width: grid.colWidth
        height: Style.space(2)
        color: Color.urgent
      }
    }
  }
}
