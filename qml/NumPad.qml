import QtQuick
import qs.Commons

// 3 × 4 number pad.
Grid {
    id: grid
    required property var ctl
    property string leftKey: ""
    property string leftLabel: ""
    property string rightKey: ""
    property string rightLabel: ""
    columns: 3
    spacing: Style.space(8)
    Repeater {
        model: ["1", "2", "3", "4", "5", "6", "7", "8", "9", "L", "0", "R"]
        delegate: Key {
            required property string modelData
            readonly property bool side: modelData === "L" || modelData === "R"
            ctl: grid.ctl
            cmd: modelData === "L" ? grid.leftKey : modelData === "R" ? grid.rightKey : modelData
            label: modelData === "L" ? grid.leftLabel : modelData === "R" ? grid.rightLabel : modelData
            opacity: cmd ? 1 : 0
            enabled: cmd !== ""
            size: Style.space(34); fontSize: Style.font.body
        }
    }
}
