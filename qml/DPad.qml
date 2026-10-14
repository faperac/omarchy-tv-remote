import QtQuick
import qs.Commons

// Circular directional pad with OK in the center.
Item {
    id: pad
    required property var ctl
    property real diameter: Style.space(176)
    property real centerSize: Style.space(74)
    property color centerTint: Color.accent
    property string centerLabel: "OK"
    width: diameter
    height: diameter

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: pad.ctl.faint
        border.width: 1
        border.color: pad.ctl.line
    }
    Key {
        ctl: pad.ctl; cmd: "up"; label: "󰅃"; size: pad.diameter * 0.27; tint: "transparent"
        anchors.top: parent.top; anchors.topMargin: Style.space(4)
        anchors.horizontalCenter: parent.horizontalCenter
    }
    Key {
        ctl: pad.ctl; cmd: "down"; label: "󰅀"; size: pad.diameter * 0.27; tint: "transparent"
        anchors.bottom: parent.bottom; anchors.bottomMargin: Style.space(4)
        anchors.horizontalCenter: parent.horizontalCenter
    }
    Key {
        ctl: pad.ctl; cmd: "left"; label: "󰅁"; size: pad.diameter * 0.27; tint: "transparent"
        anchors.left: parent.left; anchors.leftMargin: Style.space(4)
        anchors.verticalCenter: parent.verticalCenter
    }
    Key {
        ctl: pad.ctl; cmd: "right"; label: "󰅂"; size: pad.diameter * 0.27; tint: "transparent"
        anchors.right: parent.right; anchors.rightMargin: Style.space(4)
        anchors.verticalCenter: parent.verticalCenter
    }
    Key {
        ctl: pad.ctl; cmd: "ok"; label: pad.centerLabel; size: pad.centerSize; bold: true
        tint: pad.centerTint; textColor: pad.ctl.ink
        anchors.centerIn: parent
    }
}
