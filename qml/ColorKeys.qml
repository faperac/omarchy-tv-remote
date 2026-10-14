import QtQuick
import qs.Commons

// The 4 color keys (teletext, broadcaster menus).
Row {
    id: row
    required property var ctl
    spacing: Style.space(8)
    Repeater {
        model: [["red", "#c0504d"], ["green", "#5a9e5a"], ["yellow", "#d6b44a"], ["blue", "#4f7fc0"]]
        delegate: Key {
            required property var modelData
            ctl: row.ctl; cmd: modelData[0]; tint: modelData[1]
            size: Style.space(16); width: Style.space(42)
        }
    }
}
