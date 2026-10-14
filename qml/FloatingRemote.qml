import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.Commons

// Detached remote: a layer-shell window, so it stays visible on every
// workspace without any Hyprland rule. Drag the top grip to move it.
PanelWindow {
    id: win
    required property var ctl
    property real offsetRight: Style.space(24)
    property real offsetTop: Style.space(44)
    readonly property alias view: remoteView

    visible: ctl.floating
    anchors.top: true
    anchors.right: true
    margins.top: offsetTop
    margins.right: offsetRight
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.layer: WlrLayer.Top
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.OnDemand
    WlrLayershell.namespace: "faperac-tv-remote"
    color: "transparent"
    implicitWidth: card.width
    implicitHeight: card.height

    onVisibleChanged: if (visible) Qt.callLater(remoteView.focusKeys)

    Rectangle {
        id: card
        width: Style.space(290)
        height: grip.height + remoteView.implicitHeight + Style.space(26)
        radius: Style.cornerRadius
        color: Color.popups.background
        border.width: Math.max(1, Style.space(2))
        border.color: Color.popups.border

        // Drag handle: moving the mouse moves the window by the same amount,
        // so the press point stays under the cursor.
        Item {
            id: grip
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: Style.space(18)
            Rectangle {
                anchors.centerIn: parent
                width: Style.space(36)
                height: Style.space(4)
                radius: height / 2
                color: win.ctl.line
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                property real pressX: 0
                property real pressY: 0
                onPressed: function (mouse) { pressX = mouse.x; pressY = mouse.y; }
                onPositionChanged: function (mouse) {
                    win.offsetRight = Math.max(0, win.offsetRight - (mouse.x - pressX));
                    win.offsetTop = Math.max(0, win.offsetTop + (mouse.y - pressY));
                }
            }
        }

        RemoteView {
            id: remoteView
            ctl: win.ctl
            floating: true
            anchors.top: grip.bottom
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width - Style.space(26)
        }
    }
}
