import QtQuick
import qs.Commons

// App shortcuts for the device (list provided by the service); "⋯" expands
// the full list.
Column {
    id: bar
    required property var ctl
    property bool expanded: false
    readonly property var apps: ctl.dev && ctl.dev.apps ? ctl.dev.apps : []
    visible: apps.length > 0
    spacing: Style.space(6)

    Flow {
        width: parent.width
        spacing: Style.space(6)
        Repeater {
            model: bar.expanded ? bar.apps : bar.apps.slice(0, 5)
            delegate: Key {
                required property var modelData
                ctl: bar.ctl
                cmd: "app:" + modelData[0]
                label: modelData[1].length > 14 ? modelData[1].slice(0, 13) + "…" : modelData[1]
                size: Style.space(28); fontSize: Style.font.caption
            }
        }
        Key {
            ctl: bar.ctl
            visible: bar.apps.length > 5
            label: bar.expanded ? "󰅃" : "󰇘"
            size: Style.space(28); fontSize: Style.font.caption
            onActivated: bar.expanded = !bar.expanded
        }
    }
}
