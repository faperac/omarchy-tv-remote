import QtQuick
import qs.Commons

// Plain Chromecast: only the current playback and the volume can be controlled.
Column {
    id: remote
    required property var ctl
    readonly property var dev: ctl.dev || ({})
    spacing: Style.space(18)

    Column {
        width: parent.width
        spacing: Style.space(4)
        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: "󰄘"
            color: remote.ctl.muted
            font.family: remote.ctl.fontFamily
            font.pixelSize: Style.space(40)
        }
        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            text: remote.dev.app || "Nothing playing"
            color: remote.ctl.fg
            font.family: remote.ctl.fontFamily
            font.pixelSize: Style.font.body
            font.bold: !!remote.dev.app
        }
        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            text: "Cast a video from your phone or browser, then control it from here."
            visible: !remote.dev.app
            color: remote.ctl.muted
            font.family: remote.ctl.fontFamily
            font.pixelSize: Style.font.caption
        }
    }

    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: Style.space(6)
        Key { ctl: remote.ctl; cmd: "prev"; label: "󰒮"; size: Style.space(32); fontSize: Style.font.body; anchors.verticalCenter: parent.verticalCenter }
        Key { ctl: remote.ctl; cmd: "rew"; label: "󰑟"; size: Style.space(36); anchors.verticalCenter: parent.verticalCenter }
        Key {
            ctl: remote.ctl; cmd: "play"; label: "󰐎"; size: Style.space(54)
            tint: Color.accent; textColor: remote.ctl.ink
        }
        Key { ctl: remote.ctl; cmd: "ff"; label: "󰈑"; size: Style.space(36); anchors.verticalCenter: parent.verticalCenter }
        Key { ctl: remote.ctl; cmd: "next"; label: "󰒭"; size: Style.space(32); fontSize: Style.font.body; anchors.verticalCenter: parent.verticalCenter }
    }

    // Horizontal volume: − [bar] +
    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: Style.space(10)
        Key { ctl: remote.ctl; cmd: "mute"; label: "󰖁"; size: Style.space(34); fontSize: Style.font.body }
        Key { ctl: remote.ctl; cmd: "vol-"; label: "󰍴"; repeat: true; size: Style.space(34); fontSize: Style.font.body }
        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: Style.space(90)
            height: Style.space(6)
            radius: height / 2
            color: remote.ctl.faint
            Rectangle {
                width: parent.width * Math.max(0, Math.min(1, (remote.dev.level || 0) / (remote.dev.max || 100)))
                height: parent.height
                radius: parent.radius
                color: remote.dev.muted ? remote.ctl.muted : Color.accent
            }
        }
        Key { ctl: remote.ctl; cmd: "vol+"; label: "󰐕"; repeat: true; size: Style.space(34); fontSize: Style.font.body }
    }

    Key {
        ctl: remote.ctl; cmd: "stop"; label: "󰓛  Stop casting"
        anchors.horizontalCenter: parent.horizontalCenter
        size: Style.space(30); fontSize: Style.font.caption
    }
}
