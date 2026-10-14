import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// Bar button of the TV plugin: current app and volume of the bar device, read
// from the state published by the omarchy-tv service.
// Click: remote · scroll: volume · right click: play/pause · middle click: mute
BarWidget {
    id: root
    moduleName: "faperac.tv"

    // The service ships with the plugin: nothing to install elsewhere.
    readonly property string cli: Qt.resolvedUrl("bin/omarchy-tv").toString().replace(/^file:\/\//, "")

    // First run: Python libraries are installed only after the user clicks Install.
    property bool depsReady: false
    property bool installing: false
    property string installError: ""

    // State published by the service; shared with the popup (hostWidget.status).
    property var status: null
    readonly property bool hasDevices: !!(status && status.order && status.order.length)
    readonly property bool online: !!(status && status.online)
    readonly property bool on: online && status.on !== false
    readonly property string app: on && status.app ? String(status.app).slice(0, 14) : ""
    readonly property string volume: {
        if (!online) return "";
        if (status.muted) return "muted";
        return status.max ? String(status.level) : "";
    }

    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight

    readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false
    readonly property bool popoutSwitchClosing: panelLoader.item
        ? panelLoader.item.popoutSwitchClosing === true : false

    function tv(cmd) { if (depsReady && hasDevices) Util.execArgv([cli, cmd]); }

    function startService() { Util.execArgv([cli, "daemon", "--ensure"]); }
    function installDeps() {
        if (installing) return;
        installing = true;
        installError = "";
        installProc.running = true;
    }

    Process {
        id: checkProc
        command: [root.cli, "check"]
        onExited: function (code) {
            root.depsReady = code === 0;
            if (root.depsReady) root.startService();
        }
    }
    Process {
        id: installProc
        command: [root.cli, "setup"]
        stderr: StdioCollector { id: installErr; waitForEnd: true }
        onExited: function (code) {
            root.installing = false;
            if (code === 0) { root.depsReady = true; root.startService(); }
            else root.installError = "Install failed: " + (installErr.text || ("exit code " + code)).trim().split("\n").pop();
        }
    }

    function injectPanel() {
        var p = panelLoader.item;
        if (!p) return;
        if ("bar" in p) p.bar = root.bar;
        if ("settings" in p) p.settings = root.settings;
        if ("anchorItem" in p) p.anchorItem = button;
        if ("hostWidget" in p) p.hostWidget = root;
    }
    function open() { if (panelLoader.item) panelLoader.item.open() }
    function close() { if (panelLoader.item) panelLoader.item.close() }
    function togglePanel() { if (panelLoader.item && panelLoader.item.toggle) panelLoader.item.toggle() }
    function closeForPopoutSwitch() { if (panelLoader.item) panelLoader.item.closeForPopoutSwitch() }

    onBarChanged: injectPanel()
    onSettingsChanged: injectPanel()

    // Start the service if its dependencies are installed (no-op when it already runs).
    Component.onCompleted: checkProc.running = true

    FileView {
        id: statusFile
        path: Quickshell.env("XDG_RUNTIME_DIR") + "/omarchy-tv/status.json"
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: { try { root.status = JSON.parse(text()); } catch (e) {} }
        onLoadFailed: root.status = null
    }

    // Safety net in case the file watch gets lost (service restart).
    Timer { interval: 10000; running: true; repeat: true; onTriggered: statusFile.reload() }

    Loader {
        id: panelLoader
        active: true
        source: Qt.resolvedUrl("Panel.qml")
        visible: false
        onLoaded: { root.injectPanel(); Qt.callLater(root.injectPanel); }
    }

    WidgetButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: root.on && root.app ? "󰔂 " + root.app + (root.volume ? " · " + root.volume : "") : "󰔂"
        dimmed: !root.on
        active: root.opened
        tooltipText: {
            if (!root.depsReady) return "Universal TV Remote\nClick to finish the one-time setup";
            if (!root.status) return "TV: starting the service…";
            if (!root.hasDevices) return "TV: no device\nClick: find TVs on the network";
            var name = root.status.name || root.status.device;
            var head = !root.online ? name + ": unreachable"
                : name + ": " + (root.on ? (root.status.app || "on") : "standby")
                  + (root.status.volume ? " · volume " + root.status.volume : "");
            return head + "\nClick: remote · Scroll: volume\nRight click: play/pause · Middle click: mute";
        }
        onPressed: function (b) {
            if (b === Qt.RightButton) root.tv("play");
            else if (b === Qt.MiddleButton) root.tv("mute");
            else root.togglePanel();
        }
        onWheelMoved: function (delta) { root.tv(delta > 0 ? "vol+" : "vol-"); }
    }
}
