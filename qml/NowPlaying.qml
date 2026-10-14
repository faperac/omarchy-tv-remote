import QtQuick
import qs.Commons

// What is playing (title, artist, progress) when the device reports it:
// Cast sessions on Google TV / Chromecast, and Apple TV.
Rectangle {
    id: card
    required property var ctl
    readonly property var media: ctl.dev && ctl.dev.media ? ctl.dev.media : ({})
    readonly property real progress: media.duration ? Math.min(1, (media.position || 0) / media.duration) : -1
    height: column.implicitHeight + Style.space(16)
    radius: Style.space(14)
    color: ctl.faint
    border.width: 1
    border.color: ctl.line

    Column {
        id: column
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.margins: Style.space(12)
        spacing: Style.space(4)
        Text {
            width: parent.width
            elide: Text.ElideRight
            text: (card.media.playing === false ? "󰏤  " : "󰐊  ") + (card.media.title || "")
            color: card.ctl.fg
            font.family: card.ctl.fontFamily
            font.pixelSize: Style.font.body
            font.bold: true
        }
        Text {
            width: parent.width
            visible: !!card.media.artist
            elide: Text.ElideRight
            text: card.media.artist || ""
            color: card.ctl.muted
            font.family: card.ctl.fontFamily
            font.pixelSize: Style.font.caption
        }
        Rectangle {
            visible: card.progress >= 0
            width: parent.width
            height: Style.space(3)
            radius: height / 2
            color: card.ctl.line
            Rectangle {
                width: parent.width * Math.max(0, card.progress)
                height: parent.height
                radius: parent.radius
                color: Color.accent
            }
        }
    }
}
