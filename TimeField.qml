import QtQuick
import QtQuick.Controls
import QtQuick.Window
import qs.Commons
import qs.Ui
import "Model.js" as Model

// A time, shown as a field. Clicking it opens a list every 15 minutes,
// scrolled to the time it holds. Up and Down step 15 minutes without opening
// the list. For an end time, `since` is the start, and each choice says how
// long the event would run, as in Outlook.
Item {
  id: root

  // "HH:MM", as the editor's draft keeps it.
  property string text: ""
  property bool use24h: true
  property bool readOnly: false
  // Minutes after midnight of the start, for end-time lengths. -1: none.
  property int since: -1
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  property color accent: foreground
  property color popupBackground: foreground
  property color popupBorder: foreground

  signal picked(string value)
  signal popupOpened()

  readonly property int minutes: Model.parseClock(text)
  readonly property var slots: Model.timeSlots(15, minutes)
  property bool quietClose: false

  function lengthFor(m) {
    if (since < 0) return ""
    var length = m - since
    if (length <= 0) length += 24 * 60
    return Model.lengthLabel(length)
  }
  function open() {
    if (readOnly || listPopup.opened) return
    listPopup.open()
  }
  function close() {
    if (!listPopup.opened) return
    quietClose = true
    listPopup.close()
  }
  function choose(m) {
    var value = Model.clockText(m, true)
    if (value !== text) {
      text = value
      picked(value)
    }
    listPopup.close()
  }
  function step(delta) {
    var base = minutes >= 0 ? minutes : 9 * 60
    var next = (Math.round(base / 15) * 15 + delta + 24 * 60) % (24 * 60)
    if (base % 15 !== 0 && delta < 0) next = Math.floor(base / 15) * 15
    var value = Model.clockText(next, true)
    text = value
    picked(value)
  }
  function place() {
    var gap = Style.space(4)
    var margin = Style.space(8)
    var global = trigger.mapToGlobal(0, 0)
    var screenTop = Screen.virtualY
    var screenBottom = screenTop + Screen.height
    var screenLeft = Screen.virtualX
    var screenRight = screenLeft + Screen.width
    var px = 0
    if (global.x + listPopup.width > screenRight - margin)
      px = (screenRight - margin) - (global.x + listPopup.width)
    var py = trigger.height + gap
    if (global.y + py + listPopup.height > screenBottom - margin
        && global.y - listPopup.height - gap > screenTop)
      py = -listPopup.height - gap
    placeX = px
    placeY = py
  }

  property real placeX: 0
  property real placeY: 0

  implicitWidth: Style.space(since >= 0 || !use24h ? 104 : 90)
  implicitHeight: valueText.implicitHeight + Style.spacing.inputPaddingY * 2 + Style.normalBorderWidth * 2
  width: implicitWidth
  height: implicitHeight

  BorderSurface {
    id: trigger
    anchors.fill: parent
    radius: Style.cornerRadius
    activeFocusOnTab: true

    readonly property bool _focused: activeFocus || listPopup.opened
    readonly property bool _hot: triggerHover.hovered

    color: Style.controlFill(_focused, _hot, root.foreground, root.accent)
    borderSpec: Border.controlSpec(_focused ? "focus" : (_hot ? "hover-cursor" : "normal"), root.foreground, root.accent)

    HoverHandler { id: triggerHover }

    Keys.onPressed: function(event) {
      if (root.readOnly) return
      if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
        root.open()
        event.accepted = true
      } else if (event.key === Qt.Key_Up || event.key === Qt.Key_Down) {
        root.step(event.key === Qt.Key_Up ? -15 : 15)
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
      text: root.minutes >= 0 ? Model.clockText(root.minutes, root.use24h) : "Pick a time"
      color: root.minutes >= 0 ? root.foreground : Qt.darker(root.foreground, 1.6)
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
      text: "󰥔"
      color: Qt.darker(root.foreground, 1.2)
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
    }

    MouseArea {
      anchors.fill: parent
      enabled: !root.readOnly
      cursorShape: Qt.PointingHandCursor
      // Open after the click, as DateField does, or the popup takes this
      // click as an outside press and closes at once.
      onClicked: {
        trigger.forceActiveFocus()
        Qt.callLater(root.open)
      }
      onWheel: function(wheel) {
        if (listPopup.opened) return
        root.step(wheel.angleDelta.y > 0 ? -15 : 15)
      }
    }

    Popup {
      id: listPopup
      x: root.placeX
      y: root.placeY
      width: Math.max(root.width, Style.space(root.since >= 0 ? 168 : 120))
      height: Math.min(Style.space(280), slotList.contentHeight + topPadding + bottomPadding)
      padding: Style.space(4)
      modal: true
      dim: false
      focus: true
      closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent

      background: BorderSurface {
        color: root.popupBackground
        borderSpec: Border.localOrSurfaceSpec("popups", "border", root.popupBorder, root.popupBorder, Style.normalBorderWidth)
        radius: Style.cornerRadius
      }

      onAboutToShow: root.place()
      onOpened: {
        var at = root.slots.indexOf(root.minutes)
        if (at < 0) at = root.slots.indexOf(9 * 60)
        slotList.currentIndex = at
        slotList.positionViewAtIndex(at, ListView.Center)
        slotList.forceActiveFocus()
        root.popupOpened()
        Qt.callLater(root.place)
      }
      onClosed: {
        if (!root.quietClose) trigger.forceActiveFocus()
        root.quietClose = false
      }

      contentItem: ListView {
        id: slotList
        clip: true
        model: root.slots
        boundsBehavior: Flickable.StopAtBounds
        keyNavigationWraps: true
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Keys.onPressed: function(event) {
          if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            if (currentIndex >= 0) root.choose(root.slots[currentIndex])
            event.accepted = true
          } else if (event.key === Qt.Key_Escape) {
            listPopup.close()
            event.accepted = true
          }
        }

        delegate: Rectangle {
          id: slotRow
          required property int modelData
          required property int index
          readonly property bool chosen: modelData === root.minutes
          readonly property bool current: ListView.isCurrentItem
          width: slotList.width - (slotList.ScrollBar.vertical.visible ? slotList.ScrollBar.vertical.width : 0)
          height: slotLabel.implicitHeight + Style.space(10)
          radius: Style.cornerRadius
          color: chosen ? Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.22)
                 : (rowMouse.containsMouse || current) ? Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.08)
                 : "transparent"

          Text {
            id: slotLabel
            anchors.left: parent.left
            anchors.leftMargin: Style.space(8)
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: Model.clockText(slotRow.modelData, root.use24h)
            color: slotRow.chosen ? root.accent : root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
            font.bold: slotRow.chosen
          }
          Text {
            visible: root.since >= 0
            anchors.right: parent.right
            anchors.rightMargin: Style.space(8)
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: root.lengthFor(slotRow.modelData)
            color: Qt.darker(root.foreground, 1.55)
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }
          MouseArea {
            id: rowMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.choose(slotRow.modelData)
          }
        }
      }
    }
  }
}
