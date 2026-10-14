import QtQuick
import qs.Commons

// Round key (a pill when the label is long). Press and hold = long press on the
// remote; `repeat` keeps sending while the button is held.
Rectangle {
    id: key
    required property var ctl
    property string cmd: ""
    property string label: ""
    property real size: Style.space(40)
    property color tint: ctl.faint
    property color textColor: ctl.fg
    property real fontSize: Style.font.subtitle
    property bool repeat: false
    property bool bold: false
    signal activated()

    width: Math.max(size, labelText.implicitWidth + Style.space(18))
    height: size
    radius: height / 2
    color: tint
    opacity: enabled ? 1 : 0.35

    Rectangle {
        anchors.fill: parent
        radius: parent.radius
        color: key.ctl.fg
        opacity: area.pressed ? 0.22 : (area.containsMouse ? 0.09 : 0)
        Behavior on opacity { NumberAnimation { duration: 90 } }
    }
    Text {
        id: labelText
        anchors.centerIn: parent
        text: key.label
        color: key.textColor
        font.family: key.ctl.fontFamily
        font.pixelSize: key.fontSize
        font.bold: key.bold
    }
    Timer {
        id: repeater
        repeat: true
        onTriggered: { interval = 150; area.held = true; key.ctl.send(key.cmd); }
    }
    MouseArea {
        id: area
        property bool held: false
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onPressed: {
            held = false;
            if (key.repeat && key.cmd) { repeater.interval = 400; repeater.start(); }
        }
        onReleased: repeater.stop()
        onCanceled: repeater.stop()
        onPressAndHold: {
            if (key.repeat || !key.cmd) return;
            held = true;
            key.ctl.send("long:" + key.cmd);
            key.ctl.say("Long press: " + key.cmd);
        }
        onClicked: {
            if (held) return;
            if (key.cmd) key.ctl.send(key.cmd);
            key.activated();
        }
    }
}
