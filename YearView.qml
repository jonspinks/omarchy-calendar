import QtQuick
import qs.Commons
import qs.Ui
import "Model.js" as Model

// The year at a glance: twelve months, each day a disc tinted by how much is
// on it, today in the accent and the selected day ringed (the same marks as
// the small month and the month grid). It grows to the space it is given:
// set fitHeight to fill a height as well as the width. Click a day to open
// it in the day view, a month's name to open the month.
Item {
  id: year

  property int yearNumber: new Date().getFullYear()
  property var byDay: ({})
  property string todayKey: ""
  property string selectedKey: ""
  property int weekStart: 1
  property real fitHeight: 0
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family

  signal pickDay(string key)
  signal openMonth(int month)

  readonly property int columns: width > Style.space(900) || fitHeight === 0 || width / Math.max(1, fitHeight) > 1.1 ? 4 : 3
  readonly property int rows: Math.ceil(12 / columns)
  readonly property real colGap: Style.space(20)
  readonly property real rowGap: Style.space(14)
  // A month is 7 cells wide and a title plus weekday line plus 6 weeks tall.
  readonly property real cellByWidth: (width - colGap * (columns - 1)) / (columns * 7)
  readonly property real titleHeight: Style.space(26)
  readonly property real cellByHeight: fitHeight > 0
    ? (fitHeight - rowGap * (rows - 1) - rows * titleHeight) / (rows * 7)
    : cellByWidth
  readonly property real cell: Math.max(Style.space(14), Math.floor(Math.min(cellByWidth, cellByHeight, Style.space(34))))
  readonly property var weekdays: Model.weekdayOrder(weekStart)
  readonly property var monthNames: ["January", "February", "March", "April", "May", "June", "July", "August",
                                     "September", "October", "November", "December"]
  readonly property int thisMonth: Model.keyToDate(todayKey || Model.keyForDate(new Date())).getMonth()
  readonly property bool thisYear: Model.keyToDate(todayKey || Model.keyForDate(new Date())).getFullYear() === yearNumber

  implicitWidth: months.width
  implicitHeight: months.height

  Grid {
    id: months
    anchors.horizontalCenter: parent.horizontalCenter
    columns: year.columns
    columnSpacing: year.colGap
    rowSpacing: year.rowGap

    Repeater {
      model: 12

      Column {
        id: month
        required property int index
        readonly property bool current: year.thisYear && index === year.thisMonth
        width: year.cell * 7

        // The month's name: the current one in the accent. Opens the month.
        Item {
          width: parent.width
          height: year.titleHeight

          Text {
            anchors.left: parent.left
            anchors.leftMargin: Style.space(4)
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: year.monthNames[month.index]
            color: month.current ? Color.accent : titleMouse.containsMouse ? Style.hoverStateColor(year.foreground, Color.accent) : year.foreground
            font.family: year.fontFamily
            font.pixelSize: Math.max(Style.font.bodySmall, Math.min(Style.font.body, year.cell * 0.55))
            font.bold: true

            MouseArea {
              id: titleMouse
              anchors.fill: parent
              anchors.margins: -Style.space(4)
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: year.openMonth(month.index)
            }
          }
        }

        Row {
          Repeater {
            model: year.weekdays
            Text {
              required property var modelData
              width: year.cell
              height: year.cell * 0.8
              horizontalAlignment: Text.AlignHCenter
              verticalAlignment: Text.AlignVCenter
              textFormat: Text.PlainText
              text: ["S", "M", "T", "W", "T", "F", "S"][modelData]
              color: Qt.darker(year.foreground, 1.9)
              font.family: year.fontFamily
              font.pixelSize: Style.font.caption
            }
          }
        }

        // Always six weeks, so every month lines up with its neighbours.
        Repeater {
          model: {
            var w = Model.monthGrid(year.yearNumber, month.index, year.weekStart, year.todayKey)
            while (w.length < 6) w.push({ days: [] })
            return w
          }

          Row {
            required property var modelData
            height: year.cell

            Repeater {
              model: modelData.days

              Item {
                id: day
                required property var modelData
                readonly property int busy: modelData.inMonth ? Model.busyLevel(year.byDay[modelData.key] || []) : 0
                readonly property bool selected: modelData.inMonth && modelData.key === year.selectedKey
                width: year.cell
                height: year.cell

                Rectangle {
                  visible: day.modelData.inMonth
                  anchors.centerIn: parent
                  width: year.cell - Math.max(2, Style.space(3))
                  height: width
                  radius: width / 2
                  color: day.modelData.today ? Color.accent
                       : day.busy ? Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, [0, 0.16, 0.30, 0.48][day.busy])
                       : dayMouse.containsMouse ? Style.hoverFillFor(year.foreground, Color.accent) : "transparent"
                  border.width: day.selected && !day.modelData.today ? Math.max(1, Style.space(1.5))
                              : dayMouse.containsMouse && day.busy ? Style.spacing.hairline : 0
                  border.color: day.selected ? Color.accent : year.foreground
                }

                Text {
                  anchors.centerIn: parent
                  visible: day.modelData.inMonth
                  textFormat: Text.PlainText
                  text: day.modelData.day
                  color: day.modelData.today ? Color.background
                       : day.modelData.weekend ? Qt.darker(year.foreground, 1.45) : year.foreground
                  font.family: year.fontFamily
                  font.pixelSize: Math.max(Style.font.caption * 0.9, Math.min(Style.font.bodySmall, year.cell * 0.42))
                  font.bold: day.modelData.today || day.selected
                }

                MouseArea {
                  id: dayMouse
                  anchors.fill: parent
                  enabled: day.modelData.inMonth
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: year.pickDay(day.modelData.key)
                }
              }
            }
          }
        }
      }
    }
  }
}
