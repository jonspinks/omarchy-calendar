import QtQuick
import qs.Commons
import qs.Ui
import "Model.js" as Model

// The calendar as an app: one header line, a rail on the left (what's next,
// a small month, your calendars) and the chosen view filling the rest. An
// event opens in a sheet over the view's right side, so the day stays in
// sight while it is edited.
//
// It owns no state: everything is the panel's (p), so the stock layout and
// this one stay interchangeable.
Item {
  id: layout

  property var p: null

  readonly property color fg: p ? p.contentForeground : Color.foreground
  readonly property string fontName: p ? p.contentFontFamily : Style.font.family
  readonly property int railWidth: Style.space(236)
  readonly property int gap: Style.space(14)

  readonly property var next: p ? Model.nextUp(p.eventIndex.byDay, p.clockNow, p.use24h) : null

  readonly property string title: {
    if (!p) return ""
    if (p.viewMode === "month")
      return ["January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December"][p.viewMonth] + " " + p.viewYear
    return Model.rangeTitle(p.viewMode, p.selectedKey, p.weekStart)
  }

  // ---------------------------------------------------------------- header
  Item {
    id: header
    width: parent.width
    height: Style.space(34)

    // The title follows the arrows, not the other way round: its length
    // changes as you step, and the arrows stay put under the pointer.
    Text {
      id: titleText
      anchors.left: navRow.right
      anchors.leftMargin: layout.gap
      anchors.verticalCenter: parent.verticalCenter
      width: Math.min(implicitWidth, parent.width - navRow.width - rightRow.width - layout.gap * 3)
      elide: Text.ElideRight
      textFormat: Text.PlainText
      text: layout.title
      color: layout.fg
      font.family: layout.fontName
      font.pixelSize: Style.font.subtitle * 1.25
      font.bold: true
    }

    Row {
      id: navRow
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
      spacing: Style.space(2)

      PanelActionButton {
        anchors.verticalCenter: parent.verticalCenter
        iconText: "󰅁"
        tooltipText: "Previous ([)"
        foreground: layout.fg
        fontFamily: layout.fontName
        onClicked: layout.p.step(-1)
      }
      Button {
        anchors.verticalCenter: parent.verticalCenter
        text: "Today"
        tooltipText: "Back to today (t)"
        foreground: layout.fg
        fontFamily: layout.fontName
        onClicked: layout.p.goToToday()
      }
      PanelActionButton {
        anchors.verticalCenter: parent.verticalCenter
        iconText: "󰅂"
        tooltipText: "Next (])"
        foreground: layout.fg
        fontFamily: layout.fontName
        onClicked: layout.p.step(1)
      }
    }

    Row {
      id: rightRow
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      spacing: Style.space(8)

      ButtonGroup {
        anchors.verticalCenter: parent.verticalCenter
        options: layout.p ? layout.p.viewOptions : []
        value: layout.p ? layout.p.viewMode : "month"
        focusable: false
        foreground: layout.fg
        fontFamily: layout.fontName
        fontSize: Style.font.bodySmall
        onChanged: function(v) { layout.p.setView(v) }
      }

      PanelActionButton {
        anchors.verticalCenter: parent.verticalCenter
        iconText: layout.p && layout.p.syncing ? "󰑓" : "󰑐"
        tooltipText: layout.p && layout.p.syncing ? "Syncing…" : "Sync now"
        foreground: layout.fg
        fontFamily: layout.fontName
        onClicked: layout.p.syncNow()
      }

      PanelActionButton {
        anchors.verticalCenter: parent.verticalCenter
        iconText: "󰊔"
        tooltipText: "Compact: Omarchy's month and the day's appointments"
        foreground: layout.fg
        fontFamily: layout.fontName
        onClicked: layout.p.setLayout(false)
      }

      Button {
        anchors.verticalCenter: parent.verticalCenter
        visible: layout.p && layout.p.editableCalendars.length > 0
        bordered: true
        iconText: "󰐕"
        text: "New"
        tooltipText: "New event on the selected day (n)"
        foreground: Color.accent
        fontFamily: layout.fontName
        onClicked: layout.p.newEvent()
      }
    }
  }

  // ------------------------------------------------------------------ rail
  Flickable {
    id: rail
    anchors.top: header.bottom
    anchors.topMargin: layout.gap
    anchors.bottom: parent.bottom
    width: layout.railWidth
    contentHeight: railColumn.implicitHeight
    clip: true
    boundsBehavior: Flickable.StopAtBounds

    Column {
      id: railColumn
      width: rail.width
      spacing: layout.gap

      // Next up: the one thing the panel is opened for most.
      Rectangle {
        id: nextCard
        readonly property var n: layout.next
        width: parent.width
        height: nextColumn.implicitHeight + Style.space(20)
        radius: Math.max(Style.cornerRadius, Style.space(6))
        color: n && (n.live || n.soon)
               ? Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.14)
               : Qt.rgba(layout.fg.r, layout.fg.g, layout.fg.b, nextMouse.containsMouse && n ? 0.08 : 0.05)
        border.width: Style.spacing.hairline
        border.color: n && (n.live || n.soon) ? Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.5)
                                              : Qt.rgba(layout.fg.r, layout.fg.g, layout.fg.b, 0.1)

        MouseArea {
          id: nextMouse
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: nextCard.n ? Qt.PointingHandCursor : Qt.ArrowCursor
          onClicked: if (nextCard.n) layout.p.openEditor(nextCard.n.event)
        }

        Column {
          id: nextColumn
          x: Style.space(12)
          y: Style.space(10)
          width: parent.width - Style.space(24)
          spacing: Style.space(3)

          Text {
            textFormat: Text.PlainText
            text: nextCard.n && nextCard.n.live ? "NOW" : "NEXT UP"
            color: nextCard.n && (nextCard.n.live || nextCard.n.soon) ? Color.accent : Qt.darker(layout.fg, 1.5)
            font.family: layout.fontName
            font.pixelSize: Style.font.caption
            font.letterSpacing: 1
            font.bold: true
          }

          Text {
            width: parent.width
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
            text: nextCard.n ? nextCard.n.event.title : "Nothing in the next week"
            color: nextCard.n ? layout.fg : Qt.darker(layout.fg, 1.6)
            font.family: layout.fontName
            font.pixelSize: Style.font.body
            font.bold: !!nextCard.n
          }

          Text {
            visible: !!nextCard.n
            width: parent.width
            textFormat: Text.PlainText
            elide: Text.ElideRight
            text: nextCard.n ? nextCard.n.when + "  ·  " + nextCard.n.event.calendarName : ""
            color: Qt.darker(layout.fg, 1.35)
            font.family: layout.fontName
            font.pixelSize: Style.font.bodySmall
          }

          Row {
            visible: !!nextCard.n && (!!nextCard.n.event.join || snoozeNext.visible)
            topPadding: Style.space(5)
            spacing: Style.space(6)

            Button {
              visible: !!nextCard.n && !!nextCard.n.event.join
              bordered: true
              iconText: "󰕧"
              text: "Join"
              foreground: nextCard.n && (nextCard.n.live || nextCard.n.soon) ? Color.accent : layout.fg
              fontFamily: layout.fontName
              onClicked: layout.p.openUrl(nextCard.n.event.join.url)
            }
            Button {
              id: snoozeNext
              visible: !!nextCard.n && layout.p.canSnooze(nextCard.n.event, layout.p.fired, layout.p.clockNow)
              iconText: "󰒲"
              text: "Snooze"
              tooltipText: "Remind me again in " + layout.p.snoozeMinutes + " minutes"
              foreground: layout.fg
              fontFamily: layout.fontName
              onClicked: layout.p.snooze(nextCard.n.event)
            }
          }
        }
      }

      MiniMonth {
        width: parent.width
        selectedKey: layout.p ? layout.p.selectedKey : ""
        todayKey: layout.p ? layout.p.todayKey : ""
        weekStart: layout.p ? layout.p.weekStart : 1
        byDay: layout.p ? layout.p.eventIndex.byDay : ({})
        foreground: layout.fg
        fontFamily: layout.fontName
        onPickDay: function(key) { layout.p.pickDay(key) }
      }

      // Calendars, by account: click one to show or hide it.
      Column {
        width: parent.width
        spacing: Style.space(2)

        Text {
          leftPadding: Style.space(4)
          bottomPadding: Style.space(2)
          textFormat: Text.PlainText
          text: "CALENDARS"
          color: Qt.darker(layout.fg, 1.5)
          font.family: layout.fontName
          font.pixelSize: Style.font.caption
          font.letterSpacing: 1
          font.bold: true
        }

        Repeater {
          model: layout.p ? layout.p.eventIndex.calendarList : []

          Column {
            id: calRow
            required property var modelData
            required property int index
            readonly property var list: layout.p.eventIndex.calendarList
            readonly property bool firstOfAccount: index === 0 || list[index - 1].account !== modelData.account
            readonly property var account: layout.p.eventIndex.accounts.filter(function(a) { return a.name === calRow.modelData.account })[0] || {}
            readonly property bool pending: layout.p.writingUid === "cal:" + modelData.ref
            width: parent.width

            // The account's name, and what's wrong with it if anything is.
            Item {
              visible: calRow.firstOfAccount
              width: parent.width
              height: visible ? Style.space(22) : 0
              Text {
                anchors.left: parent.left
                anchors.leftMargin: Style.space(4)
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.bottomMargin: Style.space(2)
                elide: Text.ElideRight
                textFormat: Text.PlainText
                text: calRow.modelData.account + (calRow.account.status && calRow.account.status !== "ok"
                      ? "  ·  " + (calRow.account.status === "signin" ? "sign-in needed"
                                   : calRow.account.status === "offline" ? "offline" : "couldn't sync") : "")
                color: calRow.account.status && calRow.account.status !== "ok" ? Color.urgent : Qt.darker(layout.fg, 1.25)
                font.family: layout.fontName
                font.pixelSize: Style.font.caption
                font.bold: true
              }
            }

            Rectangle {
              width: parent.width
              height: Style.space(24)
              radius: Style.cornerRadius
              color: calMouse.containsMouse ? Style.hoverFillFor(layout.fg, Color.accent) : "transparent"

              // A filled swatch is shown, an outline is hidden.
              Rectangle {
                id: swatch
                x: Style.space(6)
                anchors.verticalCenter: parent.verticalCenter
                width: Style.space(12)
                height: width
                radius: Math.min(Style.cornerRadius, Style.space(3))
                color: calRow.modelData.shown ? calRow.modelData.color : "transparent"
                border.width: Math.max(1, Style.space(1.5))
                border.color: calRow.modelData.color
                opacity: calRow.pending ? 0.4 : 1

                Text {
                  visible: calRow.modelData.shown
                  anchors.centerIn: parent
                  textFormat: Text.PlainText
                  text: "󰄬"
                  color: Color.background
                  font.family: layout.fontName
                  font.pixelSize: Style.font.caption * 0.9
                }
              }

              Text {
                anchors.left: swatch.right
                anchors.leftMargin: Style.space(8)
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                elide: Text.ElideRight
                textFormat: Text.PlainText
                text: calRow.pending ? calRow.modelData.name + "  …" : calRow.modelData.name
                color: calRow.modelData.shown ? layout.fg : Qt.darker(layout.fg, 1.8)
                font.family: layout.fontName
                font.pixelSize: Style.font.bodySmall
              }

              MouseArea {
                id: calMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: layout.p.toggleCalendar(calRow.modelData)
              }
            }
          }
        }

        Text {
          visible: layout.p && layout.p.eventIndex.calendarList.length === 0
          leftPadding: Style.space(4)
          width: parent.width
          wrapMode: Text.WordWrap
          textFormat: Text.PlainText
          text: "No accounts yet: add one with calendar-ctl."
          color: Qt.darker(layout.fg, 1.6)
          font.family: layout.fontName
          font.pixelSize: Style.font.bodySmall
        }
      }
    }
  }

  // ------------------------------------------------------------------ main
  Item {
    id: main
    anchors.top: header.bottom
    anchors.topMargin: layout.gap
    anchors.left: rail.right
    anchors.leftMargin: layout.gap + Style.space(4)
    anchors.right: parent.right
    anchors.bottom: parent.bottom
    clip: true

    MonthGrid {
      visible: layout.p && layout.p.viewMode === "month"
      anchors.fill: parent
      year: layout.p ? layout.p.viewYear : 2026
      monthIndex: layout.p ? layout.p.viewMonth : 0
      selectedKey: layout.p ? layout.p.selectedKey : ""
      todayKey: layout.p ? layout.p.todayKey : ""
      weekStart: layout.p ? layout.p.weekStart : 1
      byDay: layout.p ? layout.p.eventIndex.byDay : ({})
      use24h: layout.p ? layout.p.use24h : false
      foreground: layout.fg
      fontFamily: layout.fontName
      onPickDay: function(key) { layout.p.pickDay(key) }
      onOpenDay: function(key) { layout.p.openDay(key) }
      onOpenEvent: function(ev) { layout.p.openEditor(ev) }
    }

    TimeGrid {
      id: timeGrid
      visible: layout.p && layout.p.isTimeView
      width: parent.width
      days: layout.p ? Model.viewDays(layout.p.viewMode, layout.p.selectedKey, layout.p.weekStart) : []
      byDay: layout.p ? layout.p.eventIndex.byDay : ({})
      todayKey: layout.p ? layout.p.todayKey : ""
      use24h: layout.p ? layout.p.use24h : false
      foreground: layout.fg
      fontFamily: layout.fontName
      // As many hours as the space allows; the rest scroll.
      visibleHours: Math.max(4, Math.floor((main.height - Style.space(34) - allDayRows * Style.space(20) - Style.space(14)) / hourHeight))
      onOpenEvent: function(ev) { layout.p.openEditor(ev) }
      onJoinEvent: function(url) { layout.p.openUrl(url) }
      onPickDay: function(key) { layout.p.openDay(key) }
    }

    YearView {
      visible: layout.p && layout.p.viewMode === "year"
      anchors.verticalCenter: parent.verticalCenter
      width: parent.width
      fitHeight: main.height
      selectedKey: layout.p ? layout.p.selectedKey : ""
      yearNumber: layout.p ? Model.keyToDate(layout.p.selectedKey).getFullYear() : 2026
      byDay: layout.p ? layout.p.eventIndex.byDay : ({})
      todayKey: layout.p ? layout.p.todayKey : ""
      weekStart: layout.p ? layout.p.weekStart : 1
      foreground: layout.fg
      fontFamily: layout.fontName
      onPickDay: function(key) { layout.p.openDay(key) }
      onOpenMonth: function(m) { layout.p.openMonth(m) }
    }
  }

  // ----------------------------------------------------------------- sheet
  // A click on the dimmed view closes the sheet, like any modern side sheet.
  Rectangle {
    visible: layout.p && layout.p.editorOpen
    anchors.fill: main
    color: Color.popups.background
    opacity: 0.45
    MouseArea { anchors.fill: parent; onClicked: layout.p.closeEditor() }
  }

  Rectangle {
    id: sheet
    visible: layout.p && layout.p.editorOpen
    anchors.top: main.top
    anchors.bottom: main.bottom
    anchors.right: main.right
    width: Math.min(main.width, Style.space(440))
    color: Color.popups.background
    border.width: Style.spacing.hairline
    border.color: Qt.rgba(layout.fg.r, layout.fg.g, layout.fg.b, 0.15)
    radius: Style.cornerRadius

    MouseArea { anchors.fill: parent }   // clicks on the sheet stay on it

    Flickable {
      anchors.fill: parent
      anchors.margins: Style.space(14)
      contentHeight: sheetEditor.implicitHeight
      clip: true
      boundsBehavior: Flickable.StopAtBounds

      EventEditor {
        id: sheetEditor
        width: parent.width
        draft: layout.p && layout.p.modern ? layout.p.draft : null
        event: layout.p ? layout.p.draftEvent : null
        calendars: layout.p ? layout.p.editableCalendars : []
        saving: layout.p ? layout.p.writingUid !== "" : false
        error: layout.p ? layout.p.editorError : ""
        foreground: layout.fg
        fontFamily: layout.fontName
        onSave: function(d) { layout.p.saveDraft(d) }
        onCancel: layout.p.closeEditor()
        onRemove: function(series) { layout.p.removeDraftEvent(series) }
        onRespond: function(answer, series) { layout.p.respondFromEditor(answer, series) }
        onOpenLink: function(url) { layout.p.openUrl(url) }
      }
    }
  }
}
