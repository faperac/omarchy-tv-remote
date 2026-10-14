import QtQuick
import qs.Commons

// Pairing in progress: code to enter, request to accept on the TV, error.
Column {
    id: card
    required property var ctl
    readonly property var p: ctl.pairing
    readonly property bool needsCode: p.state === "waiting_code"
    spacing: Style.space(14)

    onNeedsCodeChanged: if (needsCode) codeInput.forceActiveFocus()
    Component.onCompleted: if (needsCode) codeInput.forceActiveFocus()

    Text {
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        text: "Pairing — " + (card.p.name || "")
        color: card.ctl.fg
        font.family: card.ctl.fontFamily
        font.pixelSize: Style.font.subtitle
        font.bold: true
    }
    Text {
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        text: ({ done: "󰄬", error: "󰅚", waiting_accept: "󰔂", waiting_code: "󰌆" })[card.p.state] || "󰔟"
        color: card.p.state === "error" ? Color.urgent : card.p.state === "done" ? Color.accent : card.ctl.muted
        font.family: card.ctl.fontFamily
        font.pixelSize: Style.space(40)
        RotationAnimation on rotation {
            running: card.p.state === "working"
            from: 0; to: 360; duration: 1200; loops: Animation.Infinite
        }
    }
    Text {
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        text: card.p.prompt || ""
        color: card.ctl.fg
        font.family: card.ctl.fontFamily
        font.pixelSize: Style.font.body
    }

    Rectangle {
        visible: card.needsCode
        anchors.horizontalCenter: parent.horizontalCenter
        width: Style.space(170)
        height: Style.space(44)
        radius: Style.space(14)
        color: card.ctl.faint
        border.width: 1
        border.color: codeInput.activeFocus ? Color.accent : card.ctl.line
        TextInput {
            id: codeInput
            anchors.fill: parent
            horizontalAlignment: TextInput.AlignHCenter
            verticalAlignment: TextInput.AlignVCenter
            color: card.ctl.fg
            font.family: card.ctl.fontFamily
            font.pixelSize: Style.space(22)
            font.letterSpacing: Style.space(4)
            font.capitalization: Font.AllUppercase
            maximumLength: 8
            Keys.onReturnPressed: submit.activated()
            Keys.onEscapePressed: card.ctl.op({ op: "pair_cancel" })
        }
    }

    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: Style.space(10)
        Key {
            id: submit
            ctl: card.ctl; visible: card.needsCode
            label: "Pair"; size: Style.space(30); fontSize: Style.font.caption
            tint: Color.accent; textColor: card.ctl.ink
            onActivated: {
                if (!codeInput.text) return;
                card.ctl.op({ op: "pair_code", code: codeInput.text });
                codeInput.text = "";
            }
        }
        Key {
            ctl: card.ctl; visible: card.p.state === "error"
            label: "Retry"; size: Style.space(30); fontSize: Style.font.caption
            tint: Color.accent; textColor: card.ctl.ink
            onActivated: card.ctl.op({ op: "pair", device: card.p.device })
        }
        Key {
            ctl: card.ctl; visible: card.p.state !== "done"
            label: card.p.state === "error" ? "Close" : "Cancel"
            size: Style.space(30); fontSize: Style.font.caption
            onActivated: card.ctl.op({ op: "pair_cancel" })
        }
    }
}
