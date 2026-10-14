"""Full-screen remote in the terminal (keyboard + mouse).

A client of the omarchy-tv service: keys go through its command pipe and the
state is read back from its status file, so it works with every kind of
device the service supports.
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import signal
import sys
import termios
import tty

from omarchy_tv import STATUS_FILE, TvError, daemon_send, read_status

# Button panels: (id, label, shortcut hint). [] = blank line, dropped when the
# window is too short. App shortcuts are appended at draw time.
NAV = [
    [("power", "Power", "p"), ("input", "Source", "i"), ("settings", "Settings", "s")],
    [],
    [("up", "  ▲  ", "")],
    [("left", " ◀ ", ""), ("ok", "   OK   ", ""), ("right", " ▶ ", "")],
    [("down", "  ▼  ", "")],
    [],
    [("back", "Back", "⌫"), ("home", "Home", "h"), ("voice", "Voice", "v")],
    [("search", "Search", "/"), ("text", "Keyboard", "t"), ("menu", "Menu", "e")],
]
MEDIA = [
    [("mute", "Mute", "m"), ("vol-", "Vol −", "-"), ("vol+", "Vol +", "+")],
    [("prev", "|◀", ","), ("rew", "◀◀", "["), ("play", "▶‖", "␣"), ("ff", "▶▶", "]"), ("next", "▶|", ".")],
    [("ch+", "Ch+", "PgUp"), ("ch-", "Ch−", "PgDn"), ("info", "Info", "I"), ("captions", "CC", "u"), ("guide", "Guide", "g")],
    [("red", "    ", "F1"), ("green", "    ", "F2"), ("yellow", "    ", "F3"), ("blue", "    ", "F4")],
    [(d, d, "") for d in "1234567890"],
]
MINI = [
    [("up", "  ▲  ", "")],
    [("left", " ◀ ", ""), ("ok", " OK ", ""), ("right", " ▶ ", "")],
    [("down", "  ▼  ", "")],
    [("back", "↩", "⌫"), ("home", "⌂", "h"), ("play", "▶‖", "␣")],
    [("vol-", "−", "-"), ("mute", "Mute", "m"), ("vol+", "+", "+")],
]
APP_HOTKEYS = "ynckw"
MODES = ["auto", "big", "wide", "normal", "mini"]
GAP = 2

# Colors: only the 16 terminal colors, so the remote follows the Omarchy theme.
RESET = "\x1b[0m"
BUTTON = "\x1b[100;39m"
STYLES = {
    "power": "\x1b[31;7m", "ok": "\x1b[34;7;1m",
    "red": "\x1b[31;7m", "green": "\x1b[32;7m", "yellow": "\x1b[33;7m", "blue": "\x1b[34;7m",
}
FLASH = "\x1b[35;7;1m"
FRAME = "\x1b[90m"
DIM = "\x1b[2m"

HOTKEYS = {
    "p": "power", "i": "input", "s": "settings", "UP": "up", "DOWN": "down",
    "LEFT": "left", "RIGHT": "right", "ENTER": "ok", "BS": "back", "ESC": "back",
    "h": "home", "v": "voice", "/": "search", "t": "text", "e": "menu", "m": "mute",
    "-": "vol-", "+": "vol+", "=": "vol+", ",": "prev", "[": "rew", " ": "play",
    "]": "ff", ".": "next", "PGUP": "ch+", "PGDN": "ch-", "I": "info", "u": "captions",
    "g": "guide", "F1": "red", "F2": "green", "F3": "yellow", "F4": "blue",
    "o": "apps", "TAB": "nextdev", "L": "long", "M": "mode", "q": "quit", "\x03": "quit",
    **{d: d for d in "0123456789"},
    **{k: f"appslot:{i}" for i, k in enumerate(APP_HOTKEYS)},
}
SEQUENCES = {
    "\x1b[A": "UP", "\x1b[B": "DOWN", "\x1b[C": "RIGHT", "\x1b[D": "LEFT",
    "\x1b[5~": "PGUP", "\x1b[6~": "PGDN", "\x1bOP": "F1", "\x1bOQ": "F2",
    "\x1bOR": "F3", "\x1bOS": "F4", "\x1b[11~": "F1", "\x1b[12~": "F2",
    "\x1b[13~": "F3", "\x1b[14~": "F4", "\r": "ENTER", "\n": "ENTER",
    "\x7f": "BS", "\x08": "BS", "\t": "TAB", "\x1b": "ESC",
}
TOKEN = re.compile(r"\x1b\[<(\d+);(\d+);(\d+)([Mm])|\x1b\[[\d;]*[A-Za-z~]|\x1bO[A-Za-z]|\x1b|[\s\S]")
ANSI = re.compile(r"\x1b\[[\d;]*m")
LOCAL = {"apps", "nextdev", "long", "mode", "quit", "text", "voice"}

Segment = tuple[str, int, str | None]


def visible_len(s: str) -> int:
    return len(ANSI.sub("", s))


def blank(width: int) -> Segment:
    return (" " * width, width, None)


class RemoteScreen:
    def __init__(self, device: str | None) -> None:
        self.status = read_status()
        self.name = device or self.status.get("default")
        self.msg = ""
        self.mode = "auto"
        self.flash: str | None = None
        self.hits: list[tuple[int, int, int, str]] = []
        self.long_next = False
        self.queue: asyncio.Queue = asyncio.Queue()
        self.loop = asyncio.get_running_loop()
        self.fd = sys.stdin.fileno()
        self.saved_tty = termios.tcgetattr(self.fd)
        self.status_mtime = 0.0

    # Service data

    @property
    def names(self) -> list[str]:
        return self.status.get("order", [])

    @property
    def dev(self) -> dict:
        return self.status.get("devices", {}).get(self.name, {})

    def apps(self) -> list[list[str]]:
        return self.dev.get("apps") or []

    def send(self, *cmds: str) -> None:
        try:
            daemon_send({"op": "send", "device": self.name, "cmds": list(cmds)})
        except TvError as e:
            self.msg = str(e)

    def poll_status(self) -> None:
        try:
            mtime = os.stat(STATUS_FILE).st_mtime
        except OSError:
            return
        if mtime != self.status_mtime:
            self.status_mtime = mtime
            self.status = read_status() or self.status
            if self.status.get("message") and not self.msg:
                self.msg = self.status["message"]
            self.draw()

    async def watch_status(self) -> None:
        while True:
            self.poll_status()
            await asyncio.sleep(0.25)

    # Terminal

    def write(self, s: str) -> None:
        sys.stdout.write(s)
        sys.stdout.flush()

    def raw_mode(self) -> None:
        tty.setcbreak(self.fd)
        mode = termios.tcgetattr(self.fd)
        mode[3] &= ~termios.ISIG  # Ctrl-C arrives as a key
        termios.tcsetattr(self.fd, termios.TCSADRAIN, mode)
        self.write("\x1b[?25l\x1b[?1000h\x1b[?1006h")
        self.loop.add_reader(self.fd, self.on_input)

    def cooked_mode(self) -> None:
        self.loop.remove_reader(self.fd)
        self.write("\x1b[?1000l\x1b[?1006l\x1b[?25h")
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved_tty)

    def on_input(self) -> None:
        try:
            data = os.read(self.fd, 1024).decode(errors="ignore")
        except OSError:
            return
        for m in TOKEN.finditer(data):
            if m[1]:
                self.queue.put_nowait(("mouse", int(m[1]), int(m[2]), int(m[3]), m[4] == "M"))
            else:
                self.queue.put_nowait(("key", SEQUENCES.get(m[0], m[0])))

    def prompt(self, label: str) -> str:
        self.cooked_mode()
        rows = shutil.get_terminal_size().lines
        self.write(f"\x1b[{rows};1H\x1b[K")
        try:
            return input(label).strip()
        except EOFError:
            return ""
        finally:
            self.raw_mode()

    # Drawing

    def media_rows(self) -> list:
        apps = self.apps()[:5]
        if not apps:
            return MEDIA
        slots = [(f"appslot:{i}", a[1][:11], APP_HOTKEYS[i]) for i, a in enumerate(apps)]
        return MEDIA + [[], slots[:3], slots[3:] + [("apps", "More apps", "o")]]

    def layouts(self):
        media = self.media_rows()
        return [
            ("big", [NAV, media], True, True),
            ("wide", [NAV, media], False, True),
            ("wide", [NAV, media], False, False),
            ("normal", [NAV + [[]] + media], False, True),
            ("normal", [NAV + [[]] + media], False, False),
            ("mini", [MINI], False, False),
        ]

    def button(self, bid: str, label: str, hint: str, big: bool) -> tuple[str, list[str], int]:
        style = FLASH if bid == self.flash else STYLES.get(bid, BUTTON)
        hint = f"{DIM}{hint}\x1b[22m " if hint else ""
        pad = "  " if big else " "
        middle = f"{style}{pad}{label} {hint}{pad[1:]}{RESET}"
        width = visible_len(middle)
        if not big:
            return bid, [middle], width
        filler = f"{style}{' ' * width}{RESET}"
        return bid, [filler, middle, filler], width

    def panel(self, rows: list, big: bool, blanks: bool) -> tuple[int, list]:
        built = []
        for row in rows:
            if row:
                built.append([self.button(*b, big) for b in row if b])
            elif blanks:
                built.append(None)
        widths = [sum(w for _, _, w in r) + GAP * (len(r) - 1) for r in built if r]
        return max(widths) + 2, built

    @staticmethod
    def panel_lines(built: list, width: int) -> list[list[Segment]]:
        lines = []
        for row in built:
            if row is None:
                lines.append([blank(width)])
                continue
            total = sum(w for _, _, w in row) + GAP * (len(row) - 1)
            left = (width - total) // 2
            for k in range(len(row[0][1])):
                segs = [blank(left)]
                for i, (bid, texts, w) in enumerate(row):
                    if i:
                        segs.append(blank(GAP))
                    segs.append((texts[k], w, bid))
                segs.append(blank(width - left - total))
                lines.append(segs)
        return lines

    def status_text(self, width: int) -> str:
        d = self.dev
        if not self.status:
            return DIM + "omarchy-tv service stopped"[:width] + RESET
        if not d:
            return DIM + "no device — tv discover"[:width] + RESET
        if d.get("needs_pairing"):
            return "\x1b[33m" + f"needs pairing: tv {self.name} pair"[:width] + RESET
        if not d.get("online"):
            return DIM + (d.get("error") and "unreachable" or "connecting…")[:width] + RESET
        power = {True: "on", False: "standby"}.get(d.get("on"), "?")
        app = d.get("app") or "—"
        volume = d.get("volume") or "—"
        dot = "\x1b[32m●" if d.get("on") else DIM + "○"
        for text in (f"{power} · {app} · volume: {volume}", f"{app} · vol. {volume}", f"{app} {volume}", app):
            if len(text) + 2 <= width:
                break
        return f"{dot}{RESET} {text[:max(0, width - 2)]}"

    def header_tabs(self, mini: bool) -> list[Segment]:
        names = [self.name] if mini else self.names
        segs: list[Segment] = []
        for n in names:
            style = "\x1b[7;1m" if n == self.name else DIM
            label = self.status.get("devices", {}).get(n, {}).get("name") or n or "TV"
            text = f" {label[:14]} "
            if segs:
                segs.append(blank(2))
            segs.append((f"{style}{text}{RESET}", len(text), f"dev:{n}"))
        if mini:
            segs += [blank(1), (f"{DIM} ▸ {RESET}", 3, "nextdev")]
        return segs

    def choose_layout(self, cols: int, rows: int):
        options = [l for l in self.layouts() if self.mode in ("auto", l[0])]
        for name, panels, big, blanks in options:
            built = [self.panel(p, big, blanks) for p in panels]
            widths = [w for w, _ in built]
            tabs_width = sum(w for _, w, _ in self.header_tabs(name == "mini")) + 2
            widths[-1] += max(0, tabs_width - (sum(widths) + len(widths) - 1))
            inner = sum(widths) + len(widths) - 1
            body = max(len(self.panel_lines(b, w)) for (_, b), w in zip(built, widths))
            if inner + 2 <= cols and 4 + body + 2 <= rows:
                return name, built, widths
        return name, built, widths  # nothing fits: smallest layout, clipped

    def draw(self, *_) -> None:
        cols, rows = shutil.get_terminal_size()
        mode, built, widths = self.choose_layout(cols, rows)
        inner = sum(widths) + len(widths) - 1
        panels = [self.panel_lines(b, w) for (_, b), w in zip(built, widths)]
        body_height = max(len(p) for p in panels)

        body: list[list[Segment]] = []
        for i in range(body_height):
            segs: list[Segment] = []
            for p, (lines, w) in enumerate(zip(panels, widths)):
                if p:
                    segs.append((f"{FRAME}│{RESET}", 1, None))
                j = i - (body_height - len(lines)) // 2
                segs += lines[j] if 0 <= j < len(lines) else [blank(w)]
            body.append(segs)

        tabs = self.header_tabs(mode == "mini")
        tabs_width = sum(w for _, w, _ in tabs)
        left = (inner - tabs_width) // 2
        status = self.status_text(inner - 2)
        header: list[list[Segment]] = [
            [blank(left), *tabs, blank(inner - left - tabs_width)],
            [(" " + status, 1 + visible_len(status), None), blank(inner - 1 - visible_len(status))],
        ]
        help_text = (
            "Tab device · L+key long press · M layout · q quit"
            if mode != "mini" else "Tab · M · q"
        )
        footer = [("\x1b[33m", self.msg), (DIM, help_text)]
        if 4 + body_height + 1 + len(footer) + 1 > rows:
            footer = footer[:1]
        x0 = max(0, (cols - inner - 2) // 2) + 1
        y0 = max(0, (rows - (4 + body_height + 1 + len(footer) + 1)) // 2)
        margin = " " * (x0 - 1)
        out: list[str] = [""] * y0
        self.hits = []

        def rule(l: str, mid: str, r: str) -> str:
            return margin + FRAME + l + mid.join("─" * w for w in widths) + r + RESET

        def framed(segs: list[Segment]) -> str:
            x, y, text = x0 + 1, len(out) + 1, []
            for s, w, bid in segs:
                if bid:
                    self.hits.append((y, x, x + w - 1, bid))
                text.append(s)
                x += w
            return f"{margin}{FRAME}│{RESET}{''.join(text)}{FRAME}│{RESET}"

        out.append(margin + FRAME + "╭" + "─" * inner + "╮" + RESET)
        out += [framed(r) for r in header]
        out.append(rule("├", "┬", "┤"))
        out += [framed(segs) for segs in body]
        out.append(rule("╰", "┴", "╯"))
        if len(footer) > 1:
            out.append("")
        for style, text in footer:
            out.append(margin + style + text[: max(0, cols - x0)] + RESET)
        self.write("\x1b[H" + "\x1b[K\n".join(out[:rows]) + "\x1b[K\x1b[J")

    def blink(self, bid: str) -> None:
        self.flash = bid
        self.draw()

        def off() -> None:
            if self.flash == bid:
                self.flash = None
                self.draw()

        self.loop.call_later(0.15, off)

    # Actions

    def switch(self, name: str) -> None:
        self.name = name
        self.msg = ""
        try:
            daemon_send({"op": "connect", "device": name})
        except TvError as e:
            self.msg = str(e)

    def act(self, bid: str) -> bool:
        if bid == "quit":
            return False
        if bid == "mode":
            self.mode = MODES[(MODES.index(self.mode) + 1) % len(MODES)]
            self.msg = f"Layout: {self.mode}"
        elif bid == "nextdev" and self.names:
            i = self.names.index(self.name) if self.name in self.names else -1
            self.switch(self.names[(i + 1) % len(self.names)])
        elif bid.startswith("dev:"):
            self.switch(bid[4:])
        elif bid == "long":
            self.long_next = True
            self.msg = "Long press: pick a key…"
        elif bid == "text":
            text = self.prompt("Text to send: ")
            if text:
                self.send("text:" + text)
        elif bid == "voice":
            try:
                daemon_send({"op": "voice", "device": self.name, "seconds": 6})
                self.msg = "Listening… (6 s)"
            except TvError as e:
                self.msg = str(e)
        elif bid == "apps":
            apps = self.apps()
            listing = " ".join(f"{i + 1}:{a[1]}" for i, a in enumerate(apps[:15]))
            choice = self.prompt(f"App ({listing}): ")
            if choice.isdigit() and 0 < int(choice) <= len(apps):
                self.send("app:" + apps[int(choice) - 1][0])
            elif choice:
                match = next((a for a in apps if a[1].lower() == choice.lower()), None)
                self.send("app:" + (match[0] if match else choice))
        elif bid.startswith("appslot:"):
            apps = self.apps()
            i = int(bid.split(":")[1])
            if i < len(apps):
                self.blink(bid)
                self.send("app:" + apps[i][0])
        else:
            self.blink(bid)
            self.msg = ""
            if self.long_next:
                self.long_next = False
                self.send("long:" + bid)
            else:
                self.send(bid)
        return True

    def hit(self, x: int, y: int) -> str | None:
        for hy, xa, xb, bid in self.hits:
            if hy == y and xa <= x <= xb:
                return bid
        return None

    async def run(self) -> None:
        self.write("\x1b[?1049h\x1b[2J")
        self.raw_mode()
        self.loop.add_signal_handler(signal.SIGWINCH, self.draw)
        watcher = self.loop.create_task(self.watch_status())
        try:
            if self.name:
                self.switch(self.name)
            self.draw()
            while True:
                event = await self.queue.get()
                if event[0] == "mouse":
                    _, button, x, y, pressed = event
                    if not pressed:
                        continue
                    bid = {64: "up", 65: "down"}.get(button) or (self.hit(x, y) if button == 0 else None)
                else:
                    bid = HOTKEYS.get(event[1])
                if bid is None:
                    continue
                if not self.act(bid):
                    break
                self.draw()
        finally:
            watcher.cancel()
            self.cooked_mode()
            self.write("\x1b[?1049l")


def run_tui(device: str | None) -> None:
    async def main() -> None:
        await RemoteScreen(device).run()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
