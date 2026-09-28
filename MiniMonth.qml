import QtQuick
import qs.Commons
import qs.Ui
import "Model.js" as Model

// The rail's small month: a date picker that also shows which days are busy.
// It follows the selected day, and its own arrows browse without moving it.
Item {
  id: mini

  property string selectedKey: ""
  property string todayKey: ""
  property int weekStart: 1
  property var byDay: ({})
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family

  signal pickDay(string key)

  property int year: 2026
  property int month: 0
  function follow() {
    var d = Model.keyToDate(mini.selectedKey || mini.todayKey)
    mini.year = d.getFullYear()
    mini.month = d.getMonth()
  }
  onSelectedKeyChanged: follow()
  Component.onCompleted: follow()

  function browse(delta) {
    var n = Model.stepMonth(mini.year, mini.month, delta)
    mini.year = n.year
    mini.month = n.month
  }

  readonly property real cell: Math.floor(width / 7)
  readonly property var weekdays: Model.weekdayOrder(weekStart)
  implicitHeight: head.height + names.height + grid.height + Style.space(4)

  Item {
    id: head
    width: parent.width
    height: Style.space(26)

    Text {
      anchors.left: parent.left
      anchors.leftMargin: Style.space(4)
      anchors.verticalCenter: parent.verticalCenter
      textFormat: Text.PlainText
      text: ["January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December"][mini.month] + " " + mini.year
      color: mini.foreground
      font.family: mini.fontFamily
      font.pixelSize: Style.font.bodySmall
      font.bold: true
    }

    Row {
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      PanelActionButton {
        iconText: "󰅁"
        tooltipText: "Previous month"
        foreground: mini.foreground
        fontFamily: mini.fontFamily
        onClicked: mini.browse(-1)
      }
      PanelActionButton {
        iconText: "󰅂"
        tooltipText: "Next month"
        foreground: mini.foreground
        fontFamily: mini.fontFamily
        onClicked: mini.browse(1)
      }
    }
  }

  Row {
    id: names
    anchors.top: head.bottom
    Repeater {
      model: mini.weekdays
      Text {
        required property var modelData
        width: mini.cell
        horizontalAlignment: Text.AlignHCenter
        textFormat: Text.PlainText
        text: ["S", "M", "T", "W", "T", "F", "S"][modelData]
        color: Qt.darker(mini.foreground, 1.9)
        font.family: mini.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
  }

  Column {
    id: grid
    anchors.top: names.bottom
    anchors.topMargin: Style.space(2)

    Repeater {
      model: Model.monthGrid(mini.year, mini.month, mini.weekStart, mini.todayKey)

      Row {
        required property var modelData
        Repeater {
          model: modelData.days

          Item {
            id: day
            required property var modelData
            readonly property bool selected: modelData.key === mini.selectedKey
            readonly property int busy: Model.busyLevel(mini.byDay[modelData.key] || [])
            width: mini.cell
            height: Math.round(mini.cell * 0.86)

            Rectangle {
              anchors.centerIn: parent
              width: Math.min(parent.width, parent.height) - Style.space(2)
              height: width
              radius: width / 2
              color: day.selected ? Color.accent
                   : dayMouse.containsMouse ? Style.hoverFillFor(mini.foreground, Color.accent) : "transparent"
              border.width: day.modelData.today && !day.selected ? Style.spacing.hairline : 0
              border.color: Color.accent
            }

            Text {
              anchors.centerIn: parent
              textFormat: Text.PlainText
              text: day.modelData.day
              color: day.selected ? Color.background
                   : !day.modelData.inMonth ? Qt.darker(mini.foreground, 2.2)
                   : day.modelData.weekend ? Qt.darker(mini.foreground, 1.4) : mini.foreground
              font.family: mini.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: day.modelData.today || day.selected
            }

            // A dot under busy days.
            Rectangle {
              visible: day.busy > 0 && !day.selected && day.modelData.inMonth
              anchors.horizontalCenter: parent.horizontalCenter
              anchors.bottom: parent.bottom
              width: Style.space(3)
              height: width
              radius: width / 2
              color: mini.foreground
              opacity: [0, 0.35, 0.6, 0.9][day.busy]
            }

            MouseArea {
              id: dayMouse
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: mini.pickDay(day.modelData.key)
            }
          }
        }
      }
    }
  }
}
