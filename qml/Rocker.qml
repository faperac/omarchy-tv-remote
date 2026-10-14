import QtQuick
import qs.Commons

// Vertical + / − rocker (volume, channels) with auto-repeat.
Rectangle {
    id: rocker
    required property var ctl
    property string up: ""
    property string down: ""
    property string caption: ""
    width: Style.space(46)
    height: Style.space(128)
    radius: width / 2
    color: ctl.faint
    border.width: 1
    border.color: ctl.line

    Key {
        ctl: rocker.ctl; cmd: rocker.up; label: "󰐕"; repeat: true; tint: "transparent"
        anchors.top: parent.top; anchors.topMargin: Style.space(3)
        anchors.horizontalCenter: parent.horizontalCenter
    }
    Text {
        anchors.centerIn: parent
        text: rocker.caption
        color: rocker.ctl.muted
        font.family: rocker.ctl.fontFamily
        font.pixelSize: Style.font.caption
        font.bold: true
    }
    Key {
        ctl: rocker.ctl; cmd: rocker.down; label: "󰍴"; repeat: true; tint: "transparent"
        anchors.bottom: parent.bottom; anchors.bottomMargin: Style.space(3)
        anchors.horizontalCenter: parent.horizontalCenter
    }
}
