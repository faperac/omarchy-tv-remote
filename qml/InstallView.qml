import QtQuick
import qs.Commons

// First run: the remote needs a few Python libraries. Nothing is downloaded
// until the user clicks Install (pinned versions, hash-checked).
Column {
    id: view
    required property var ctl
    spacing: Style.space(14)

    Text {
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        text: "󰔂"
        color: Color.accent
        font.family: view.ctl.fontFamily
        font.pixelSize: Style.space(40)
    }
    Text {
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        text: "Universal TV Remote"
        color: view.ctl.fg
        font.family: view.ctl.fontFamily
        font.pixelSize: Style.font.subtitle
        font.bold: true
    }
    Text {
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        text: view.ctl.installing ? "Installing the Python libraries…"
            : "One-time setup: the remote needs a few Python libraries (Google TV, Apple TV, Samsung, LG, Cast, ADB protocols). Pinned versions, hash-checked, installed in ~/.local/share/omarchy-tv."
        color: view.ctl.muted
        font.family: view.ctl.fontFamily
        font.pixelSize: Style.font.caption
    }
    Key {
        ctl: view.ctl
        anchors.horizontalCenter: parent.horizontalCenter
        size: Style.space(32); fontSize: Style.font.caption
        label: view.ctl.installing ? "󰔟  Installing…" : "󰇚  Install"
        enabled: !view.ctl.installing
        tint: Color.accent; textColor: view.ctl.ink
        onActivated: view.ctl.installDeps()
    }
    Text {
        width: parent.width
        visible: !!view.ctl.installError
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        text: view.ctl.installError
        color: Color.urgent
        font.family: view.ctl.fontFamily
        font.pixelSize: Style.font.caption
    }
}
