import QtQuick
import qs.Commons

// Classic TV remote (Samsung, LG, Roku…): digits, channels, source.
Column {
    id: remote
    required property var ctl
    spacing: Style.space(14)

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
            Key { ctl: remote.ctl; cmd: "settings"; label: "󰒓"; visible: remote.ctl.has("settings") }
        }
    }

    NumPad {
        ctl: remote.ctl
        visible: remote.ctl.has("digits")
        anchors.horizontalCenter: parent.horizontalCenter
        leftKey: "info"; leftLabel: "󰋼"
        rightKey: "guide"; rightLabel: "󰕰"
    }

    Item {
        width: parent.width
        height: Style.space(128)
        Rocker { ctl: remote.ctl; up: "vol+"; down: "vol-"; caption: "VOL"; anchors.left: parent.left; anchors.leftMargin: Style.space(10) }
        Column {
            anchors.centerIn: parent
            spacing: Style.space(14)
            Key { ctl: remote.ctl; cmd: "mute"; label: "󰖁" }
            Key { ctl: remote.ctl; cmd: "home"; label: "󰋜" }
        }
        Rocker {
            ctl: remote.ctl; up: "ch+"; down: "ch-"; caption: "CH"; visible: remote.ctl.has("channels")
            anchors.right: parent.right; anchors.rightMargin: Style.space(10)
        }
    }

    DPad {
        ctl: remote.ctl
        anchors.horizontalCenter: parent.horizontalCenter
        diameter: Style.space(160)
        centerSize: Style.space(64)
    }

    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: Style.space(14)
        Key { ctl: remote.ctl; cmd: "back"; label: "󰕌" }
        Key { ctl: remote.ctl; cmd: "menu"; label: "󰍜" }
        Key { ctl: remote.ctl; cmd: "exit"; label: "Exit"; fontSize: Style.font.caption; bold: true }
    }

    ColorKeys { ctl: remote.ctl; visible: remote.ctl.has("colors"); anchors.horizontalCenter: parent.horizontalCenter }

    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: Style.space(10)
        Key { ctl: remote.ctl; cmd: "rew"; label: "󰑟"; size: Style.space(34); fontSize: Style.font.body }
        Key { ctl: remote.ctl; cmd: "play"; label: "󰐎"; size: Style.space(34); fontSize: Style.font.body }
        Key { ctl: remote.ctl; cmd: "stop"; label: "󰓛"; size: Style.space(34); fontSize: Style.font.body }
        Key { ctl: remote.ctl; cmd: "ff"; label: "󰈑"; size: Style.space(34); fontSize: Style.font.body }
    }

    AppsBar { ctl: remote.ctl; width: parent.width }
    TextBar { ctl: remote.ctl; width: parent.width; visible: remote.ctl.has("text"); onDone: remote.ctl.focusKeys() }
}
