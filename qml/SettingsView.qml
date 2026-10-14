import QtQuick
import qs.Commons

// Settings for the shown device: name, bar device, sound output, re-pairing,
// removal.
Column {
    id: view
    required property var ctl
    readonly property var dev: ctl.dev || ({})
    readonly property string id_: ctl.currentDevice
    property bool confirmRemove: false
    spacing: Style.space(14)

    Item {
        width: parent.width
        height: Style.space(32)
        Key {
            ctl: view.ctl; label: "󰅁"; size: Style.space(30); fontSize: Style.font.body
            anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
            onActivated: view.ctl.view = "remote"
        }
        Text {
            anchors.centerIn: parent
            text: "Settings"
            color: view.ctl.fg
            font.family: view.ctl.fontFamily
            font.pixelSize: Style.font.subtitle
            font.bold: true
        }
    }

    Text {
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        text: [view.dev.label, view.dev.model, view.dev.host].filter(function (x) { return x; }).join(" · ")
        color: view.ctl.muted
        font.family: view.ctl.fontFamily
        font.pixelSize: Style.font.caption
    }

    // Name
    Rectangle {
        width: parent.width
        height: Style.space(32)
        radius: height / 2
        color: view.ctl.faint
        border.width: 1
        border.color: nameInput.activeFocus ? Color.accent : view.ctl.line
        TextInput {
            id: nameInput
            anchors.fill: parent
            anchors.leftMargin: Style.space(14)
            anchors.rightMargin: Style.space(14)
            verticalAlignment: TextInput.AlignVCenter
            text: view.dev.name || ""
            color: view.ctl.fg
            font.family: view.ctl.fontFamily
            font.pixelSize: Style.font.body
            clip: true
            Keys.onReturnPressed: {
                if (text) { view.ctl.op({ op: "rename", device: view.id_, name: text }); view.ctl.say("Renamed"); }
                view.ctl.focusKeys();
            }
            Keys.onEscapePressed: view.ctl.focusKeys()
        }
        Text {
            anchors.right: parent.right
            anchors.rightMargin: Style.space(12)
            anchors.verticalCenter: parent.verticalCenter
            text: "󰏫"
            color: view.ctl.muted
            font.family: view.ctl.fontFamily
            font.pixelSize: Style.font.body
        }
    }

    Key {
        ctl: view.ctl
        width: parent.width
        size: Style.space(32); fontSize: Style.font.caption
        readonly property bool isDefault: view.ctl.status && view.ctl.status.default === view.id_
        label: isDefault ? "󰓎  Shown in the bar" : "󰓒  Show in the bar"
        enabled: !isDefault
        onActivated: view.ctl.op({ op: "default", device: view.id_ })
    }

    Column {
        width: parent.width
        spacing: Style.space(6)
        visible: view.ctl.order.length > 1
        Text {
            text: "Sound goes through"
            color: view.ctl.muted
            font.family: view.ctl.fontFamily
            font.pixelSize: Style.font.caption
        }
        Flow {
            width: parent.width
            spacing: Style.space(6)
            Repeater {
                model: [""].concat(view.ctl.order.filter(function (d) { return d !== view.id_; }))
                delegate: Key {
                    required property string modelData
                    readonly property bool selected: (view.dev.volume_via || "") === modelData
                    ctl: view.ctl
                    size: Style.space(28); fontSize: Style.font.caption
                    label: modelData ? view.ctl.deviceName(modelData) : "this device"
                    tint: selected ? Color.accent : view.ctl.faint
                    textColor: selected ? view.ctl.ink : view.ctl.fg
                    onActivated: view.ctl.op({ op: "volume_via", device: view.id_, target: modelData || null })
                }
            }
        }
        Text {
            width: parent.width
            wrapMode: Text.Wrap
            text: "Useful when a streaming box can't control the TV volume (infrared-only remote): volume keys go straight to the chosen device."
            color: view.ctl.muted
            font.family: view.ctl.fontFamily
            font.pixelSize: Style.font.caption
        }
    }

    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: Style.space(10)
        Key {
            ctl: view.ctl; size: Style.space(30); fontSize: Style.font.caption
            visible: !!view.dev.pairing_type
            label: "󰑐  Re-pair"
            onActivated: view.ctl.op({ op: "pair", device: view.id_ })
        }
        Key {
            ctl: view.ctl; size: Style.space(30); fontSize: Style.font.caption
            label: view.confirmRemove ? "󰆴  Confirm?" : "󰆴  Remove"
            tint: view.confirmRemove ? Color.urgent : view.ctl.faint
            textColor: view.confirmRemove ? view.ctl.ink : view.ctl.fg
            onActivated: {
                if (!view.confirmRemove) { view.confirmRemove = true; confirmTimer.restart(); return; }
                view.ctl.op({ op: "remove", device: view.id_ });
                view.ctl.device = "";
                view.ctl.view = "remote";
            }
        }
    }
    Timer { id: confirmTimer; interval: 4000; onTriggered: view.confirmRemove = false }
}
