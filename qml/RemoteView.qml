import QtQuick
import qs.Commons
import "."

// Everything inside the popup or the floating window: device chips, status,
// now playing, then the current view (remote, add a device, settings, pairing,
// first-run setup). `ctl` is the Panel, which owns the state and the actions.
FocusScope {
    id: view
    required property var ctl
    property bool floating: false
    implicitHeight: body.implicitHeight

    function focusKeys() { keys.forceActiveFocus(); }

    Component { id: googleRemote; GoogleRemote { ctl: view.ctl } }
    Component { id: appleRemote; AppleRemote { ctl: view.ctl } }
    Component { id: classicRemote; ClassicRemote { ctl: view.ctl } }
    Component { id: castRemote; CastRemote { ctl: view.ctl } }

    // The keyboard drives the TV: arrows, Enter, Backspace, Space, + / -, m, h, p.
    Item {
        id: keys
        anchors.fill: parent
        focus: true
        Keys.onPressed: function (event) {
            var cmd = "";
            switch (event.key) {
            case Qt.Key_Escape: view.ctl.closeView(view.floating); event.accepted = true; return;
            case Qt.Key_Tab: if (!view.floating) view.ctl.switchPanel(1); event.accepted = true; return;
            case Qt.Key_Backtab: if (!view.floating) view.ctl.switchPanel(-1); event.accepted = true; return;
            case Qt.Key_Up: cmd = "up"; break;
            case Qt.Key_Down: cmd = "down"; break;
            case Qt.Key_Left: cmd = "left"; break;
            case Qt.Key_Right: cmd = "right"; break;
            case Qt.Key_Return: case Qt.Key_Enter: cmd = "ok"; break;
            case Qt.Key_Backspace: cmd = "back"; break;
            case Qt.Key_Space: cmd = "play"; break;
            default:
                cmd = ({ "+": "vol+", "=": "vol+", "-": "vol-", "m": "mute", "h": "home", "p": "power" })[event.text] || "";
            }
            if (cmd && view.ctl.shownView === "remote" && !view.ctl.pairingActive) {
                view.ctl.send(cmd);
                event.accepted = true;
            }
        }

        Column {
            id: body
            width: parent.width
            spacing: Style.space(10)

            // ---- devices + add + settings + float ----
            Item {
                width: parent.width
                height: Style.space(26)
                visible: view.ctl.ready && view.ctl.order.length > 0
                Flickable {
                    anchors.left: parent.left
                    anchors.right: actions.left
                    anchors.rightMargin: Style.space(6)
                    height: parent.height
                    contentWidth: chips.implicitWidth
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    Row {
                        id: chips
                        spacing: Style.space(6)
                        Repeater {
                            model: view.ctl.order
                            delegate: Rectangle {
                                required property string modelData
                                readonly property bool selected: modelData === view.ctl.currentDevice && view.ctl.shownView !== "setup"
                                readonly property var info: view.ctl.status.devices[modelData] || ({})
                                width: chip.implicitWidth + Style.space(18)
                                height: Style.space(24)
                                radius: height / 2
                                color: selected ? Color.accent : (chipArea.containsMouse ? view.ctl.faint : "transparent")
                                border.width: selected ? 0 : 1
                                border.color: view.ctl.line
                                Text {
                                    id: chip
                                    anchors.centerIn: parent
                                    text: (info.needs_pairing ? "󰌆 " : "") + (info.name || modelData)
                                    color: parent.selected ? view.ctl.ink : (info.online ? view.ctl.fg : view.ctl.muted)
                                    font.family: view.ctl.fontFamily
                                    font.pixelSize: Style.font.caption
                                    font.bold: parent.selected
                                }
                                MouseArea {
                                    id: chipArea
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: view.ctl.selectDevice(modelData)
                                }
                            }
                        }
                    }
                }
                Row {
                    id: actions
                    anchors.right: parent.right
                    spacing: Style.space(2)
                    Key {
                        ctl: view.ctl; label: "󰐕"; size: Style.space(24); fontSize: Style.font.caption
                        tint: view.ctl.shownView === "setup" ? Color.accent : "transparent"
                        textColor: view.ctl.shownView === "setup" ? view.ctl.ink : view.ctl.fg
                        onActivated: view.ctl.view = view.ctl.view === "setup" ? "remote" : "setup"
                    }
                    Key {
                        ctl: view.ctl; label: "󰒓"; size: Style.space(24); fontSize: Style.font.caption
                        tint: view.ctl.shownView === "settings" ? Color.accent : "transparent"
                        textColor: view.ctl.shownView === "settings" ? view.ctl.ink : view.ctl.fg
                        onActivated: view.ctl.view = view.ctl.view === "settings" ? "remote" : "settings"
                    }
                    Key {
                        // Detach into a floating window / dock back into the bar popup.
                        ctl: view.ctl; label: view.floating ? "󱔓" : "󰹙"; size: Style.space(24); fontSize: Style.font.caption
                        tint: "transparent"
                        onActivated: view.ctl.setFloating(!view.floating)
                    }
                }
            }

            Text {
                width: parent.width
                visible: view.ctl.ready && view.ctl.shownView === "remote" && !view.ctl.pairingActive
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
                text: view.ctl.statusLine
                color: view.ctl.dev && view.ctl.dev.online && view.ctl.dev.on !== false && !view.ctl.note ? view.ctl.fg : view.ctl.muted
                font.family: view.ctl.fontFamily
                font.pixelSize: Style.font.caption
            }

            NowPlaying {
                ctl: view.ctl
                width: parent.width
                visible: view.ctl.ready && view.ctl.shownView === "remote" && !view.ctl.pairingActive
                    && !!view.ctl.dev && !!view.ctl.dev.media && view.ctl.dev.layout !== "cast"
            }

            // ---- content ----
            Rectangle {
                width: parent.width
                height: content.implicitHeight + Style.space(36)
                radius: Style.space(34)
                color: view.ctl.faint
                border.width: 1
                border.color: view.ctl.line

                Item {
                    id: content
                    anchors.top: parent.top
                    anchors.topMargin: Style.space(18)
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: parent.width - Style.space(36)
                    implicitHeight: shown ? shown.implicitHeight : 0
                    readonly property var shown: installView.visible ? installView
                        : pairingCard.visible ? pairingCard
                        : setupView.visible ? setupView
                        : settingsView.visible ? settingsView
                        : needsPairing.visible ? needsPairing
                        : remoteLoader.item

                    InstallView {
                        id: installView
                        ctl: view.ctl
                        width: parent.width
                        visible: !view.ctl.ready
                    }
                    PairingCard {
                        id: pairingCard
                        ctl: view.ctl
                        width: parent.width
                        visible: view.ctl.ready && view.ctl.pairingActive
                    }
                    SetupView {
                        id: setupView
                        ctl: view.ctl
                        width: parent.width
                        visible: view.ctl.ready && !view.ctl.pairingActive && view.ctl.shownView === "setup"
                    }
                    SettingsView {
                        id: settingsView
                        ctl: view.ctl
                        width: parent.width
                        visible: view.ctl.ready && !view.ctl.pairingActive && view.ctl.shownView === "settings" && !!view.ctl.dev
                    }
                    Column {
                        id: needsPairing
                        width: parent.width
                        spacing: Style.space(12)
                        visible: view.ctl.ready && !view.ctl.pairingActive && view.ctl.shownView === "remote"
                            && !!view.ctl.dev && view.ctl.dev.needs_pairing
                        Text {
                            width: parent.width
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.Wrap
                            text: "\"" + (view.ctl.dev ? view.ctl.dev.name : "") + "\" needs to be paired before it can be controlled."
                            color: view.ctl.fg
                            font.family: view.ctl.fontFamily
                            font.pixelSize: Style.font.body
                        }
                        Key {
                            ctl: view.ctl; label: "󰌆  Pair"; size: Style.space(32); fontSize: Style.font.caption
                            anchors.horizontalCenter: parent.horizontalCenter
                            tint: Color.accent; textColor: view.ctl.ink
                            onActivated: view.ctl.op({ op: "pair", device: view.ctl.currentDevice })
                        }
                    }
                    Loader {
                        id: remoteLoader
                        width: parent.width
                        active: view.ctl.ready && !view.ctl.pairingActive && view.ctl.shownView === "remote"
                            && !!view.ctl.dev && !view.ctl.dev.needs_pairing
                        visible: active
                        sourceComponent: !view.ctl.dev ? null
                            : view.ctl.dev.layout === "apple" ? appleRemote
                            : view.ctl.dev.layout === "cast" ? castRemote
                            : view.ctl.dev.layout === "google" ? googleRemote
                            : classicRemote
                        onLoaded: item.width = Qt.binding(function () { return remoteLoader.width; })
                    }
                }
            }
        }
    }
}
