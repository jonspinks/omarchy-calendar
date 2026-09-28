import QtQuick
import qs.Commons
import qs.Ui
import "Model.js" as Model

// The year at a glance: twelve small months, each day shaded by how much is on
// it. Click a day to open it in the day view.
Item {
  id: year

  property int yearNumber: new Date().getFullYear()
  property var byDay: ({})
  property string todayKey: ""
  property int weekStart: 1
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family

  signal pickDay(string key)

  readonly property int cell: Style.space(18)
  readonly property int monthWidth: cell * 7
  readonly property var weekdays: Model.weekdayOrder(weekStart)

  implicitWidth: months.implicitWidth
  implicitHeight: months.implicitHeight

  Grid {
    id: months
    anchors.horizontalCenter: parent.horizontalCenter
    columns: 4
    columnSpacing: Style.space(18)
    rowSpacing: Style.space(12)

    Repeater {
      model: 12

      Column {
        id: month
        required property int index
        spacing: Style.space(2)

        Text {
          textFormat: Text.PlainText
          text: ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST",
                 "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"][month.index]
          color: Qt.darker(year.foreground, 1.4)
          font.family: year.fontFamily
          font.pixelSize: Style.font.caption
          font.letterSpacing: 1
          font.bold: true
        }

        Row {
          Repeater {
            model: year.weekdays
            Text {
              required property var modelData
              width: year.cell
              horizontalAlignment: Text.AlignHCenter
              textFormat: Text.PlainText
              text: ["S", "M", "T", "W", "T", "F", "S"][modelData]
              color: Qt.darker(year.foreground, 1.9)
              font.family: year.fontFamily
              font.pixelSize: Style.font.caption
            }
          }
        }

        Repeater {
          model: Model.monthGrid(year.yearNumber, month.index, year.weekStart, year.todayKey)

          Row {
            required property var modelData

            Repeater {
              model: modelData.days

              Rectangle {
                id: dayCell
                required property var modelData
                readonly property int busy: modelData.inMonth ? Model.busyLevel(year.byDay[modelData.key] || []) : 0
                width: year.cell
                height: year.cell
                radius: Style.cornerRadius
                color: busy ? Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, [0, 0.18, 0.34, 0.55][busy])
                     : (dayMouse.containsMouse && modelData.inMonth ? Style.hoverFillFor(year.foreground, Color.accent) : "transparent")
                border.width: modelData.today ? Style.spacing.hairline : 0
                border.color: Style.normalBorderFor(year.foreground, Color.accent)

                Text {
                  anchors.centerIn: parent
                  visible: dayCell.modelData.inMonth
                  textFormat: Text.PlainText
                  text: dayCell.modelData.day
                  color: dayCell.modelData.weekend ? Qt.darker(year.foreground, 1.45) : year.foreground
                  font.family: year.fontFamily
                  font.pixelSize: Style.font.caption
                  font.bold: dayCell.modelData.today
                }

                MouseArea {
                  id: dayMouse
                  anchors.fill: parent
                  enabled: dayCell.modelData.inMonth
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: year.pickDay(dayCell.modelData.key)
                }
              }
            }
          }
        }
      }
    }
  }
}
