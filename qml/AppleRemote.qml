import QtQuick
import qs.Commons

// Apple TV remote (Siri Remote): clickpad, Back, TV, play/pause.
Column {
    id: remote
    required property var ctl
    spacing: Style.space(16)

    Item {
        width: parent.width
        height: Style.space(40)
        Key {
            ctl: remote.ctl; cmd: "settings"; label: "󰒓"
            anchors.left: parent.left
        }
        Key {
            ctl: remote.ctl; cmd: "power"; label: "󰐥"; tint: Color.urgent; textColor: remote.ctl.ink
            anchors.right: parent.right
        }
    }

    // Clickpad: directional ring, click in the center.
    DPad {
        ctl: remote.ctl
        anchors.horizontalCenter: parent.horizontalCenter
        diameter: Style.space(184)
        centerSize: Style.space(96)
        centerLabel: ""
        centerTint: remote.ctl.faint
    }

    Item {
        width: parent.width
        height: Style.space(128)
        Column {
            anchors.left: parent.left
            anchors.leftMargin: Style.space(14)
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(14)
            Key { ctl: remote.ctl; cmd: "back"; label: "󰅁" }
            Key { ctl: remote.ctl; cmd: "play"; label: "󰐎" }
        }
        Column {
            anchors.centerIn: parent
            spacing: Style.space(14)
            Key { ctl: remote.ctl; cmd: "home"; label: "󰔂" }
            Key { ctl: remote.ctl; cmd: "menu"; label: "󰍜" }
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
    }

    AppsBar { ctl: remote.ctl; width: parent.width }
    TextBar { ctl: remote.ctl; width: parent.width; onDone: remote.ctl.focusKeys() }
}
