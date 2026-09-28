import QtQuick
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

  signal openEvent(string url)
  signal joinEvent(string url)
  signal pickDay(string key)

  readonly property int gutter: Style.space(46)
  readonly property int hourHeight: Style.space(40)
  readonly property int visibleHours: 11
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
              onClicked: grid.openEvent(parent.modelData.webLink)
            }
          }
        }

        Text {
          visible: allDayCol.items.length > 3
          leftPadding: Style.space(5)
          textFormat: Text.PlainText
          text: "+" + (allDayCol.items.length - 2) + " more"
          color: Qt.darker(grid.foreground, 1.5)
          font.family: grid.fontFamily
          font.pixelSize: Style.font.caption
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
      width: scroller.width
      height: scroller.contentHeight

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
              x: Style.space(2) + modelData.column * slot
              y: (modelData.top - grid.hours.first * 60) / 60 * grid.hourHeight + 1
              width: slot - Style.space(2)
              height: Math.max(Style.space(16), (modelData.bottom - modelData.top) / 60 * grid.hourHeight - 2)
              radius: Style.cornerRadius
              color: Qt.rgba(Qt.color(ev.color).r, Qt.color(ev.color).g, Qt.color(ev.color).b, blockMouse.containsMouse ? 0.42 : 0.28)
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
                  visible: block.height > Style.space(32)
                  width: parent.width
                  textFormat: Text.PlainText
                  elide: Text.ElideRight
                  text: block.ev.label
                  color: Qt.darker(grid.foreground, 1.4)
                  font.family: grid.fontFamily
                  font.pixelSize: Style.font.caption
                }
              }

              MouseArea {
                id: blockMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: grid.openEvent(block.ev.webLink)
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
