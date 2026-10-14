import QtQuick
import qs.Commons

// Google TV / Android TV remote.
Column {
    id: remote
    required property var ctl
    property bool more: false
    spacing: Style.space(16)

    Item {
        width: parent.width
        height: Style.space(40)
        Key {
            ctl: remote.ctl; cmd: "power"; label: "󰐥"; tint: Color.urgent; textColor: remote.ctl.ink
            anchors.left: parent.left
        }
        Row {
            anchors.right: parent.right
            spacing: Style.space(8)
            Key { ctl: remote.ctl; cmd: "input"; label: "󰋺"; visible: remote.ctl.has("input") }
            Key { ctl: remote.ctl; cmd: "settings"; label: "󰒓" }
        }
    }

    DPad { ctl: remote.ctl; anchors.horizontalCenter: parent.horizontalCenter }

    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: Style.space(22)
        Key { ctl: remote.ctl; cmd: "back"; label: "󰕌" }
        Key { ctl: remote.ctl; cmd: "home"; label: "󰋜" }
        Key { ctl: remote.ctl; label: "󰍬"; visible: remote.ctl.has("voice"); onActivated: remote.ctl.voice() }
        Key { ctl: remote.ctl; cmd: "menu"; label: "󰍜"; visible: !remote.ctl.has("voice") }
    }

    Item {
        width: parent.width
        height: Style.space(128)
        Rocker {
            ctl: remote.ctl; up: "ch+"; down: "ch-"; caption: "CH"; visible: remote.ctl.has("channels")
            anchors.left: parent.left; anchors.leftMargin: Style.space(10)
        }
        Column {
            anchors.centerIn: parent
            spacing: Style.space(14)
            Key { ctl: remote.ctl; cmd: "mute"; label: "󰖁" }
            Key { ctl: remote.ctl; cmd: "play"; label: "󰐎" }
        }
        Rocker { ctl: remote.ctl; up: "vol+"; down: "vol-"; caption: "VOL"; anchors.right: parent.right; anchors.rightMargin: Style.space(10) }
    }

    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: Style.space(10)
        Key { ctl: remote.ctl; cmd: "prev"; label: "󰒮"; size: Style.space(34); fontSize: Style.font.body }
        Key { ctl: remote.ctl; cmd: "rew"; label: "󰑟"; size: Style.space(34); fontSize: Style.font.body }
        Key { ctl: remote.ctl; cmd: "ff"; label: "󰈑"; size: Style.space(34); fontSize: Style.font.body }
        Key { ctl: remote.ctl; cmd: "next"; label: "󰒭"; size: Style.space(34); fontSize: Style.font.body }
        Key {
            ctl: remote.ctl; label: remote.more ? "󰅃" : "󰇘"; size: Style.space(34); fontSize: Style.font.body
            onActivated: remote.more = !remote.more
        }
    }

    // Advanced keys (collapsed by default).
    Column {
        visible: remote.more
        width: parent.width
        spacing: Style.space(10)
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: Style.space(10)
            Key { ctl: remote.ctl; cmd: "search"; label: "󰍉"; size: Style.space(34); fontSize: Style.font.body }
            Key { ctl: remote.ctl; cmd: "info"; label: "󰋼"; size: Style.space(34); fontSize: Style.font.body }
            Key { ctl: remote.ctl; cmd: "captions"; label: "󰨖"; size: Style.space(34); fontSize: Style.font.body }
            Key { ctl: remote.ctl; cmd: "guide"; label: "󰕰"; size: Style.space(34); fontSize: Style.font.body }
            Key { ctl: remote.ctl; cmd: "menu"; label: "󰍜"; size: Style.space(34); fontSize: Style.font.body }
        }
        ColorKeys { ctl: remote.ctl; visible: remote.ctl.has("colors"); anchors.horizontalCenter: parent.horizontalCenter }
        NumPad { ctl: remote.ctl; anchors.horizontalCenter: parent.horizontalCenter }
    }

    AppsBar { ctl: remote.ctl; width: parent.width }
    TextBar { ctl: remote.ctl; width: parent.width; onDone: remote.ctl.focusKeys() }
}
