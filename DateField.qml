import QtQuick
import QtQuick.Controls
import QtQuick.Window
import qs.Commons
import qs.Ui
import "Model.js" as Model

// A date, shown as a field. Clicking it opens a month on the day it already
// holds. The popup names that day in words and fills it on the grid, so the
// current choice stays obvious while the month arrows look at other months.
Item {
  id: root

  property string date: ""
  property string todayKey: ""
  property int weekStart: 1
  property var byDay: ({})
  property bool readOnly: false
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  // The parent passes these. Reading Color.accent from this file comes back
  // empty (the name clashes once a popup is in the tree), and the calendar
  // then paints as a white card.
  property color accent: foreground
  property color ink: foreground
  property color popupBackground: foreground
  property color popupBorder: foreground

  signal picked(string key)
  signal popupOpened()

  readonly property string shown: Model.formatDayField(date)
  readonly property string shownLong: Model.formatDayLong(date)
  readonly property bool gridShowsSelection: {
    var d = Model.keyToDate(date)
    return !isNaN(d.getTime()) && picker.year === d.getFullYear() && picker.month === d.getMonth()
  }
  // load() closes a popup while the editor is going away. That close must
  // not pull keyboard focus back onto a field that is no longer on screen.
  property bool quietClose: false

  function open() {
    if (readOnly || calendarPopup.opened) return
    calendarPopup.open()
  }
  function close() {
    if (!calendarPopup.opened) return
    quietClose = true
    calendarPopup.close()
  }
  function choose(key) {
    if (key !== date) {
      date = key
      picked(key)
    }
    calendarPopup.close()
  }
  function place() {
    var gap = Style.space(4)
    var margin = Style.space(8)
    var global = trigger.mapToGlobal(0, 0)
    var screenLeft = Screen.virtualX
    var screenTop = Screen.virtualY
    var screenRight = screenLeft + Screen.width
    var screenBottom = screenTop + Screen.height
    // Stay on the calendar panel. The layer behind it is full screen, so the
    // last ancestor before that is the panel, and the popup should not cover
    // the window sitting beside the calendar.
    var limit = root
    var item = root.parent
    while (item) {
      if (item.width > (screenRight - screenLeft) - Style.space(80)) break
      limit = item
      item = item.parent
    }
    var limitRight = limit.mapToGlobal(limit.width, 0).x
    var px = 0
    if (global.x + calendarPopup.width > limitRight - margin)
      px = (limitRight - margin) - (global.x + calendarPopup.width)
    if (global.x + px + calendarPopup.width > screenRight - margin)
      px = (screenRight - margin) - (global.x + calendarPopup.width)
    if (global.x + px < screenLeft + margin)
      px = (screenLeft + margin) - global.x
    var py = trigger.height + gap
    if (global.y + py + calendarPopup.height > screenBottom - margin
        && global.y - calendarPopup.height - gap > screenTop)
      py = -calendarPopup.height - gap
    placeX = px
    placeY = py
  }

  property real placeX: 0
  property real placeY: 0

  implicitWidth: Style.space(164)
  implicitHeight: valueText.implicitHeight + Style.spacing.inputPaddingY * 2 + Style.normalBorderWidth * 2
  width: implicitWidth
  height: implicitHeight

  BorderSurface {
    id: trigger
    anchors.fill: parent
    radius: Style.cornerRadius
    activeFocusOnTab: true

    readonly property bool _focused: activeFocus || calendarPopup.opened
    readonly property bool _hot: triggerHover.hovered
    readonly property var _borderSpec: Border.controlSpec(_focused ? "focus" : (_hot ? "hover-cursor" : "normal"), root.foreground, root.accent)

    color: Style.controlFill(_focused, _hot, root.foreground, root.accent)
    borderSpec: _borderSpec

    HoverHandler { id: triggerHover }

    Keys.onPressed: function(event) {
      if (root.readOnly) return
      if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter
          || event.key === Qt.Key_Space || event.key === Qt.Key_Down) {
        root.open()
        event.accepted = true
      }
    }

    Text {
      id: valueText
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      anchors.leftMargin: trigger.borderLeft + Style.spacing.controlPaddingX
      anchors.rightMargin: trigger.borderRight + (root.readOnly ? Style.spacing.controlPaddingX
                           : icon.implicitWidth + Style.spacing.controlGap + Style.spacing.md)
      textFormat: Text.PlainText
      text: root.shown !== "" ? root.shown : "Pick a date"
      color: root.shown !== "" ? root.foreground : Qt.darker(root.foreground, 1.6)
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
      elide: Text.ElideRight
    }

    Text {
      id: icon
      visible: !root.readOnly
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      anchors.rightMargin: trigger.borderRight + Style.spacing.controlGap
      text: "󰃭"
      color: Qt.darker(root.foreground, 1.2)
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
    }

    MouseArea {
      anchors.fill: parent
      enabled: !root.readOnly
      cursorShape: Qt.PointingHandCursor
      // Open after this click is finished. Opening inside the click makes the
      // popup treat that same click as an outside press and close at once,
      // which is all an all-day event was showing: the month never stayed up.
      onClicked: {
        trigger.forceActiveFocus()
        Qt.callLater(root.open)
      }
    }

    PanelToolTip {
      visible: triggerHover.hovered && !root.readOnly && !calendarPopup.opened
      text: "Choose a date"
      fontFamily: root.fontFamily
    }

    Popup {
      id: calendarPopup
      x: root.placeX
      y: root.placeY
      width: Style.space(292)
      height: contentCol.implicitHeight + topPadding + bottomPadding
      padding: Style.space(12)
      modal: true
      dim: false
      focus: true
      // Outside the field, not merely outside the month. The click that opens
      // the month lands on this field, and a press-outside rule closes it again.
      closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent

      readonly property var popupBorderSpec: Border.localOrSurfaceSpec("popups", "border", root.popupBorder, root.popupBorder, Style.normalBorderWidth)

      background: BorderSurface {
        color: root.popupBackground
        borderSpec: calendarPopup.popupBorderSpec
        radius: Style.cornerRadius
      }

      onAboutToShow: root.place()
      onOpened: {
        picker.follow()
        contentCol.forceActiveFocus()
        root.popupOpened()
        Qt.callLater(root.place)
      }
      onClosed: {
        if (!root.quietClose) trigger.forceActiveFocus()
        root.quietClose = false
      }

      contentItem: Column {
        id: contentCol
        width: calendarPopup.availableWidth
        spacing: Style.space(8)
        focus: true

        Keys.onPressed: function(event) {
          if (event.key === Qt.Key_Escape) {
            calendarPopup.close()
          } else if (event.key === Qt.Key_Left || event.key === Qt.Key_Up) {
            picker.browse(-1)
          } else if (event.key === Qt.Key_Right || event.key === Qt.Key_Down) {
            picker.browse(1)
          }
          event.accepted = true
        }

        // The choice, written out. Stays put while the grid browses, so a
        // month with no filled day still says which date is selected.
        Rectangle {
          id: selectedBanner
          width: parent.width
          height: selectedRow.implicitHeight + Style.space(12)
          radius: Style.cornerRadius
          color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.18)
          border.width: Math.max(Style.spacing.hairline, 1)
          border.color: root.accent

          Row {
            id: selectedRow
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: Style.space(8)
            anchors.rightMargin: Style.space(8)
            spacing: Style.space(8)

            Rectangle {
              id: dayMark
              width: Style.space(28)
              height: width
              radius: width / 2
              color: root.accent

              Text {
                anchors.centerIn: parent
                textFormat: Text.PlainText
                text: {
                  var d = Model.keyToDate(root.date)
                  return isNaN(d.getTime()) ? "" : String(d.getDate())
                }
                color: root.ink
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                font.bold: true
              }
            }

            Column {
              width: Math.max(0, selectedRow.width - dayMark.width - selectedRow.spacing)
              spacing: Style.space(1)

              Text {
                textFormat: Text.PlainText
                text: "SELECTED"
                color: root.accent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.letterSpacing: 1
                font.bold: true
              }
              Text {
                width: parent.width
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
                text: root.shownLong !== "" ? root.shownLong : "Pick a date"
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: true
              }
              Text {
                visible: root.date !== "" && root.date === root.todayKey
                textFormat: Text.PlainText
                text: "This is today"
                color: root.accent
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }
          }
        }

        Text {
          visible: !root.gridShowsSelection
          width: parent.width
          wrapMode: Text.WordWrap
          textFormat: Text.PlainText
          text: "Show " + root.shownLong
          color: showMouse.containsMouse ? Style.hoverStateColor(root.foreground, root.accent) : root.accent
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
          font.bold: true

          MouseArea {
            id: showMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: picker.follow()
          }
        }

        MiniMonth {
          id: picker
          width: parent.width
          selectedKey: root.date
          todayKey: root.todayKey
          weekStart: root.weekStart
          byDay: root.byDay
          foreground: root.foreground
          fontFamily: root.fontFamily
          onPickDay: function(key) { root.choose(key) }
        }

        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          textFormat: Text.PlainText
          text: !root.gridShowsSelection
                ? "The date above stays selected while this month is on screen."
                : root.date === root.todayKey
                  ? "The filled day is the date above, and it is today."
                  : "The filled day is the date above. A ring marks today."
          color: Qt.darker(root.foreground, 1.55)
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
    }
  }
}
