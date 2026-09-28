import QtQuick
import qs.Commons
import qs.Ui
import "Model.js" as Model

// The month with its events in it: each day lists as many as fit (all-day
// ones as coloured bars, timed ones as a dot, time and title), then
// "+n more". Click a day to select it, double-click to open it in the day
// view; click an event to open it.
Item {
  id: month

  property int year: 2026
  property int monthIndex: 0
  property string selectedKey: ""
  property string todayKey: ""
  property int weekStart: 1
  property var byDay: ({})
  property bool use24h: false
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family

  signal pickDay(string key)
  signal openDay(string key)
  signal openEvent(var ev)

  readonly property var weeks: Model.monthGrid(year, monthIndex, weekStart, todayKey)
  readonly property var weekdays: Model.weekdayOrder(weekStart)
  readonly property real colWidth: width / 7
  readonly property real headHeight: Style.space(22)
  readonly property real rowHeight: (height - headHeight) / Math.max(1, weeks.length)
  readonly property int chipHeight: Style.space(17)
  // Rows for events once the day number has its line.
  readonly property int fits: Math.max(0, Math.floor((rowHeight - Style.space(22)) / (chipHeight + Style.space(1))))

  function timeOf(ev) {
    return Model.clockLabel(new Date(ev.start), month.use24h)
  }

  Row {
    id: head
    height: month.headHeight
    Repeater {
      model: month.weekdays
      Text {
        required property var modelData
        width: month.colWidth
        height: month.headHeight
        leftPadding: Style.space(8)
        verticalAlignment: Text.AlignVCenter
        textFormat: Text.PlainText
        text: ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"][modelData]
        color: Qt.darker(month.foreground, 1.6)
        font.family: month.fontFamily
        font.pixelSize: Style.font.caption
        font.letterSpacing: 1
      }
    }
  }

  Repeater {
    model: month.weeks

    Row {
      id: week
      required property var modelData
      required property int index
      y: month.headHeight + index * month.rowHeight

      Repeater {
        model: week.modelData.days

        Rectangle {
          id: cell
          required property var modelData
          required property int index
          readonly property var events: month.byDay[modelData.key] || []
          readonly property bool selected: modelData.key === month.selectedKey
          readonly property bool overflow: events.length > month.fits
          readonly property int shown: overflow ? Math.max(0, month.fits - 1) : events.length
          width: month.colWidth
          height: month.rowHeight
          color: selected ? Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.10)
               : cellMouse.containsMouse ? Style.hoverFillFor(month.foreground, Color.accent) : "transparent"

          // Hairline grid: the top and left of every cell.
          Rectangle { width: parent.width; height: Style.spacing.hairline; color: month.foreground; opacity: 0.08 }
          Rectangle { visible: cell.index > 0; width: Style.spacing.hairline; height: parent.height; color: month.foreground; opacity: 0.08 }

          MouseArea {
            id: cellMouse
            anchors.fill: parent
            hoverEnabled: true
            onClicked: month.pickDay(cell.modelData.key)
            onDoubleClicked: month.openDay(cell.modelData.key)
          }

          // Day number, today in an accent disc.
          Rectangle {
            id: dayNumber
            x: Style.space(4)
            y: Style.space(3)
            width: Math.max(Style.space(20), dayText.implicitWidth + Style.space(8))
            height: Style.space(18)
            radius: height / 2
            color: cell.modelData.today ? Color.accent : "transparent"

            Text {
              id: dayText
              anchors.centerIn: parent
              textFormat: Text.PlainText
              text: cell.modelData.day === 1
                    ? ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][Model.keyToDate(cell.modelData.key).getMonth()] + " 1"
                    : cell.modelData.day
              color: cell.modelData.today ? Color.background
                   : !cell.modelData.inMonth ? Qt.darker(month.foreground, 2.2)
                   : cell.modelData.weekend ? Qt.darker(month.foreground, 1.35) : month.foreground
              font.family: month.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: cell.modelData.today
            }
          }

          Column {
            x: Style.space(3)
            y: Style.space(22)
            width: parent.width - Style.space(6)
            spacing: Style.space(1)
            opacity: cell.modelData.inMonth ? 1 : 0.55

            Repeater {
              model: cell.events.slice(0, cell.shown)

              Rectangle {
                id: chip
                required property var modelData
                width: parent.width
                height: month.chipHeight
                radius: Style.cornerRadius
                color: chip.modelData.allDay
                       ? Qt.rgba(Qt.color(chip.modelData.color).r, Qt.color(chip.modelData.color).g, Qt.color(chip.modelData.color).b, chipMouse.containsMouse ? 0.45 : 0.30)
                       : chipMouse.containsMouse ? Style.hoverFillFor(month.foreground, Color.accent) : "transparent"
                opacity: chip.modelData.declined ? 0.5 : 1

                Rectangle {
                  id: dot
                  visible: !chip.modelData.allDay
                  x: Style.space(4)
                  anchors.verticalCenter: parent.verticalCenter
                  width: Style.space(6)
                  height: width
                  radius: width / 2
                  color: chip.modelData.color
                }

                Text {
                  anchors.left: chip.modelData.allDay ? parent.left : dot.right
                  anchors.leftMargin: Style.space(4)
                  anchors.right: parent.right
                  anchors.rightMargin: Style.space(2)
                  anchors.verticalCenter: parent.verticalCenter
                  textFormat: Text.PlainText
                  elide: Text.ElideRight
                  text: (chip.modelData.allDay ? "" : month.timeOf(chip.modelData) + " ") + chip.modelData.title
                  color: month.foreground
                  font.family: month.fontFamily
                  font.pixelSize: Style.font.caption
                  font.strikeout: chip.modelData.declined
                }

                MouseArea {
                  id: chipMouse
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: month.openEvent(chip.modelData)
                }
              }
            }

            Text {
              visible: cell.overflow
              leftPadding: Style.space(4)
              textFormat: Text.PlainText
              text: "+" + (cell.events.length - cell.shown) + " more"
              color: Qt.darker(month.foreground, 1.5)
              font.family: month.fontFamily
              font.pixelSize: Style.font.caption

              MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: month.openDay(cell.modelData.key)
              }
            }
          }
        }
      }
    }
  }
}
