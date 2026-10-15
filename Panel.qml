import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "qml"

// Popup of the TV plugin, plus the detachable floating window. Both show a
// RemoteView; this file owns the state and the actions. Everything goes through
// the omarchy-tv service: "omarchy-tv <device> <key>" for keys,
// "omarchy-tv op <json>" for the rest.
Panel {
    id: root
    moduleName: "faperac.tv"
    ipcTarget: "faperac.tv"

    property var anchorItem: null
    property var hostWidget: null
    readonly property var barIdentity: hostWidget || root

    readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
    readonly property color fg: Color.popups.text
    readonly property color ink: Color.background
    readonly property color muted: Util.alpha(fg, 0.55)
    readonly property color faint: Util.alpha(fg, 0.07)
    readonly property color line: Util.alpha(fg, 0.16)
    readonly property string cli: hostWidget ? hostWidget.cli : ""

    // First-run setup (Python libraries), handled by the bar widget.
    readonly property bool ready: !!(hostWidget && hostWidget.depsReady)
    readonly property bool installing: !!(hostWidget && hostWidget.installing)
    readonly property string installError: hostWidget ? hostWidget.installError : ""

    readonly property var status: hostWidget ? hostWidget.status : null
    readonly property var order: status && status.order ? status.order : []
    property string device: ""
    readonly property string currentDevice: device && order.indexOf(device) >= 0 ? device
        : (status && status.default ? status.default : (order.length ? order[0] : ""))
    readonly property var dev: status && status.devices && currentDevice ? status.devices[currentDevice] : null
    property string view: "remote"
    readonly property string shownView: order.length === 0 ? "setup" : view
    readonly property var pairing: status && status.pairing ? status.pairing : ({ state: "idle" })
    readonly property bool pairingActive: !!pairing.state && pairing.state !== "idle"
    property bool floating: false

    property string note: ""
    // Service messages are tied to a device: only show those for the device on screen.
    readonly property string daemonMessage: status && status.message
        && (!status.message_device || status.message_device === currentDevice) ? status.message : ""
    onDaemonMessageChanged: if (daemonMessage) say(daemonMessage, 4000)

    readonly property string statusLine: {
        if (note) return note;
        if (!status) return "starting the service…";
        if (!dev) return "";
        if (dev.needs_pairing) return "needs pairing";
        if (!dev.online) return dev.error ? "unreachable" : "connecting…";
        if (dev.on === false) return "standby";
        var parts = [dev.app || dev.label];
        if (dev.volume) parts.push("volume " + dev.volume);
        return parts.join(" · ");
    }

    function has(cap) { return !!(dev && dev.caps && dev.caps.indexOf(cap) >= 0); }
    function deviceName(id) {
        return status && status.devices && status.devices[id] ? status.devices[id].name : id;
    }
    // Every request goes to "omarchy-tv op -" over stdin, never argv: pairing
    // codes and typed searches must not show up in other users' process lists.
    function send(cmd) { if (currentDevice) op({ op: "send", device: currentDevice, cmds: [cmd] }); }
    function op(obj) {
        if (!ready || !cli) return;
        var proc = requestComponent.createObject(root, { command: [cli, "op", "-"], payload: JSON.stringify(obj) });
        proc.running = true;
    }
    function installDeps() { if (hostWidget) hostWidget.installDeps(); }
    function selectDevice(id) {
        device = id;
        view = "remote";
        op({ op: "connect", device: id });
    }
    function say(text, ms) {
        note = text;
        noteTimer.interval = ms || 2500;
        noteTimer.restart();
    }
    function voice() {
        op({ op: "voice", device: currentDevice, seconds: 6 });
        say("󰍬  Listening… (6 s)", 6500);
    }
    function focusKeys() {
        if (floating) floatingRemote.view.focusKeys();
        else dockedView.focusKeys();
    }
    function setFloating(on) {
        floating = on;
        if (on) close();
        else open();
    }
    function closeView(fromFloating) {
        if (fromFloating) floating = false;
        else close();
    }

    function open() {
        controller.show();
        if (ready && currentDevice) op({ op: "connect", device: currentDevice });
        dockedView.focusKeys();
    }
    function close() { controller.hide(); }
    function toggle() {
        if (floating) { floating = false; return; }
        opened ? close() : open();
    }
    function switchPanel(direction) {
        if (bar && typeof bar.switchPanelFrom === "function")
            return bar.switchPanelFrom(barIdentity, direction);
        return false;
    }

    Timer { id: noteTimer; onTriggered: root.note = "" }

    // One short-lived process per request, so fast key presses don't queue up.
    Component {
        id: requestComponent
        Process {
            property string payload: ""
            stdinEnabled: true
            onStarted: {
                write(payload + "\n");
                payload = "";
            }
            onExited: destroy()
        }
    }

    // "omarchy-shell faperac.tv.remote press vol+": same path as clicking a key
    // (handy for Hyprland keybindings).
    IpcHandler {
        target: "faperac.tv.remote"
        function press(cmd: string): void { root.send(cmd) }
        function show(view: string): void { root.view = view; root.open() }
        function select(device: string): void { root.selectDevice(device); root.open() }
        function float(): void { root.setFloating(true) }
    }

    FloatingRemote { id: floatingRemote; ctl: root }

    KeyboardPanel {
        id: panel
        anchorItem: root.anchorItem
        bar: root.bar
        owner: root.barIdentity
        open: root.opened
        focusTarget: dockedView
        contentWidth: panel.fittedContentWidth(root.shownView === "setup" && !root.pairingActive && root.ready
            ? Style.space(320) : Style.space(262))
        contentHeight: panel.fittedContentHeight(dockedView.implicitHeight)

        RemoteView {
            id: dockedView
            ctl: root
            width: parent.width
        }
    }
}
