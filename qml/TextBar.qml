import QtQuick
import qs.Commons

// Text entry (search on the TV): Enter sends it.
Rectangle {
    id: box
    required property var ctl
    signal done()
    height: Style.space(30)
    radius: height / 2
    color: ctl.faint
    border.width: 1
    border.color: input.activeFocus ? Color.accent : ctl.line

    TextInput {
        id: input
        anchors.fill: parent
        anchors.leftMargin: Style.space(14)
        anchors.rightMargin: Style.space(14)
        verticalAlignment: TextInput.AlignVCenter
        color: box.ctl.fg
        font.family: box.ctl.fontFamily
        font.pixelSize: Style.font.caption
        clip: true
        Keys.onReturnPressed: {
            if (text) { box.ctl.send("text:" + text); box.ctl.say("Text sent"); }
            text = "";
        }
        Keys.onEscapePressed: box.done()
    }
    Text {
        anchors.fill: input
        verticalAlignment: Text.AlignVCenter
        visible: !input.text && !input.activeFocus
        text: "󰌌  Type text on the TV…"
        color: box.ctl.muted
        font.family: box.ctl.fontFamily
        font.pixelSize: Style.font.caption
    }
}
