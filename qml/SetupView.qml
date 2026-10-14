import QtQuick
import qs.Commons

// Add a device: local network discovery, or by IP address.
Column {
    id: view
    required property var ctl
    readonly property var disc: ctl.status && ctl.status.discovery ? ctl.status.discovery : ({ running: false, found: [] })
    readonly property var found: disc.found || []
    spacing: Style.space(12)

    function shortLabel(kind) {
        return ({ androidtv: "Google TV", appletv: "Apple TV", samsung: "Samsung", webos: "LG webOS",
                  roku: "Roku", cast: "Chromecast" })[kind] || kind;
    }
    function icon(kind) {
        return ({ androidtv: "󰔂", appletv: "󰀵", cast: "󰄘" })[kind] || "󰟴";
    }

    // Search when the view opens, unless a recent result is already there.
    function refreshIfStale() {
        if (visible && !disc.running && (!disc.at || Date.now() / 1000 - disc.at > 120))
            ctl.op({ op: "discover" });
    }
    onVisibleChanged: refreshIfStale()

    Item {
        width: parent.width
        height: Style.space(32)
        Key {
            ctl: view.ctl; label: "󰅁"; size: Style.space(30); fontSize: Style.font.body
            visible: view.ctl.order.length > 0
            anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
            onActivated: view.ctl.view = "remote"
        }
        Text {
            anchors.centerIn: parent
            text: "Add a device"
            color: view.ctl.fg
            font.family: view.ctl.fontFamily
            font.pixelSize: Style.font.subtitle
            font.bold: true
        }
        Key {
            ctl: view.ctl; label: view.disc.running ? "…" : "󰑐"; size: Style.space(30); fontSize: Style.font.body
            enabled: !view.disc.running
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            onActivated: view.ctl.op({ op: "discover" })
        }
    }

    Text {
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        text: view.disc.running ? "Searching the local network…"
            : view.found.length ? view.found.length + (view.found.length > 1 ? " devices found" : " device found")
            : "No device found on this network"
        color: view.ctl.muted
        font.family: view.ctl.fontFamily
        font.pixelSize: Style.font.caption
    }

    Repeater {
        model: view.found
        delegate: Rectangle {
            required property var modelData
            width: view.width
            height: Style.space(52)
            radius: Style.space(14)
            color: view.ctl.faint
            border.width: 1
            border.color: view.ctl.line

            Text {
                id: kindIcon
                anchors.left: parent.left
                anchors.leftMargin: Style.space(12)
                anchors.verticalCenter: parent.verticalCenter
                text: view.icon(modelData.kind)
                color: view.ctl.fg
                font.family: view.ctl.fontFamily
                font.pixelSize: Style.space(20)
            }
            Column {
                anchors.left: kindIcon.right
                anchors.leftMargin: Style.space(10)
                anchors.right: addKey.left
                anchors.rightMargin: Style.space(8)
                anchors.verticalCenter: parent.verticalCenter
                spacing: Style.space(2)
                Text {
                    width: parent.width
                    elide: Text.ElideRight
                    text: modelData.name
                    color: view.ctl.fg
                    font.family: view.ctl.fontFamily
                    font.pixelSize: Style.font.body
                    font.bold: true
                }
                Text {
                    width: parent.width
                    elide: Text.ElideRight
                    text: [modelData.model || view.shortLabel(modelData.kind), modelData.host].join(" · ")
                    color: view.ctl.muted
                    font.family: view.ctl.fontFamily
                    font.pixelSize: Style.font.caption
                }
            }
            Key {
                id: addKey
                ctl: view.ctl
                anchors.right: parent.right
                anchors.rightMargin: Style.space(10)
                anchors.verticalCenter: parent.verticalCenter
                size: Style.space(28); fontSize: Style.font.caption
                label: modelData.added ? "󰄬 Added" : "󰐕 Add"
                enabled: !modelData.added
                tint: modelData.added ? "transparent" : Color.accent
                textColor: modelData.added ? view.ctl.muted : view.ctl.ink
                onActivated: view.ctl.op({ op: "add", uid: modelData.uid, host: modelData.host })
            }
        }
    }

    // Manual add by IP address (for networks where discovery sees nothing).
    Row {
        width: parent.width
        spacing: Style.space(8)
        Rectangle {
            width: parent.width - manualKey.width - parent.spacing
            height: Style.space(30)
            radius: height / 2
            color: view.ctl.faint
            border.width: 1
            border.color: ipInput.activeFocus ? Color.accent : view.ctl.line
            TextInput {
                id: ipInput
                anchors.fill: parent
                anchors.leftMargin: Style.space(14)
                anchors.rightMargin: Style.space(14)
                verticalAlignment: TextInput.AlignVCenter
                color: view.ctl.fg
                font.family: view.ctl.fontFamily
                font.pixelSize: Style.font.caption
                clip: true
                Keys.onReturnPressed: manualKey.activated()
                Keys.onEscapePressed: view.ctl.focusKeys()
            }
            Text {
                anchors.fill: ipInput
                verticalAlignment: Text.AlignVCenter
                visible: !ipInput.text && !ipInput.activeFocus
                text: "󰩟  IP address (e.g. 192.168.1.20)"
                color: view.ctl.muted
                font.family: view.ctl.fontFamily
                font.pixelSize: Style.font.caption
            }
        }
        Key {
            id: manualKey
            ctl: view.ctl; label: "󰐕"; size: Style.space(30); fontSize: Style.font.body
            onActivated: {
                if (!ipInput.text) return;
                view.ctl.op({ op: "add", host: ipInput.text.trim() });
                ipInput.text = "";
            }
        }
    }

    Text {
        width: parent.width
        wrapMode: Text.Wrap
        text: "Google TV / Android TV and Apple TV: a code appears on the TV. Samsung and LG: accept the request on screen. Roku and Chromecast: nothing to do."
        color: view.ctl.muted
        font.family: view.ctl.fontFamily
        font.pixelSize: Style.font.caption
    }
}
