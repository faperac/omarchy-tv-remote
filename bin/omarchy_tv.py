"""omarchy-tv — universal TV remote for the Omarchy bar and the terminal.

Supported devices: Google TV / Android TV (Chromecast with Google TV, Sony,
TCL, Philips… TVs), Fire TV and other Android devices over ADB, Apple TV,
Samsung TVs (Tizen), LG TVs (webOS), Roku, and plain Chromecasts (playback and
volume only).

  tv setup                      install the pinned Python dependencies (once)

  tv                            full-screen remote (keyboard + mouse)
  tv [device] CMD...            keys: tv vol+ vol+ ; tv bedroom netflix ; tv text:"dune"
  tv discover                   find devices on the local network
  tv add NUMBER|IP [NAME]       add a discovered device (or an IP), then pair it
  tv [device] pair              (re)pair a device
  tv [device] status            device state
  tv [device] voice             voice command (Google TV) through the PC microphone
  tv list                       configured devices and commands
  tv remove|rename|default|volume-via ...   settings (see tv list)
  tv daemon [--ensure]          background service (started automatically)
  tv op -                       one JSON request on stdin (used by the bar plugin)

Keys: power on off input settings menu search up down left right ok back
home exit mute vol+ vol- play pause stop rew ff prev next ch+ ch- info captions
guide red green yellow blue 0-9, long:KEY, text:TEXT, app:ID
"""
from __future__ import annotations

import asyncio
import contextlib
import fcntl
import ipaddress
import json
import os
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HOME = Path.home()
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config")
CONF_DIR = CONFIG_HOME / "omarchy-tv"
CONFIG_FILE, CREDS_FILE = CONF_DIR / "config.json", CONF_DIR / "credentials.json"
CERT, KEY = CONF_DIR / "androidtv-cert.pem", CONF_DIR / "androidtv-key.pem"
RUN_DIR = (Path(os.environ["XDG_RUNTIME_DIR"]) / "omarchy-tv" if os.environ.get("XDG_RUNTIME_DIR")
           else Path(f"/tmp/omarchy-tv-{os.getuid()}"))
STATUS_FILE, CMD_FIFO = RUN_DIR / "status.json", RUN_DIR / "cmd"
LOCK_FILE, LOG_FILE = RUN_DIR / "daemon.lock", RUN_DIR / "daemon.log"
CLIENT_NAME = f"Omarchy ({socket.gethostname()})"

VOLUME_KEYS = {"vol+", "vol-", "mute"}
ALL_KEYS = [
    "power", "on", "off", "input", "settings", "menu", "search", "up", "down", "left",
    "right", "ok", "back", "home", "exit", "mute", "vol+", "vol-", "play", "pause", "stop",
    "rew", "ff", "prev", "next", "ch+", "ch-", "info", "captions", "guide",
    "red", "green", "yellow", "blue", *"0123456789",
]


class TvError(Exception):
    pass


class NeedsPairing(TvError):
    pass


class Unreachable(TvError):
    pass


class BadCode(TvError):
    pass


class Unsupported(TvError):
    pass


# --- Files ------------------------------------------------------------------

def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


# Every file lives in a directory that only we can write to (checked here), and
# is opened without following symlinks, so no other user can redirect a write.

def private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    st = os.lstat(path)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid():
        raise TvError(f"refusing to use {path}: not a directory owned by you")
    if stat.S_IMODE(st.st_mode) & 0o077:
        os.chmod(path, 0o700)
    return path


def open_private(path: Path, flags: int, kind=stat.S_ISREG) -> int:
    private_dir(path.parent)
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    st = os.fstat(fd)
    if not kind(st.st_mode) or st.st_uid != os.getuid():
        os.close(fd)
        raise TvError(f"refusing to use {path}: unexpected file type or owner")
    return fd


def save_json(path: Path, data) -> None:
    """Atomic replace: write a fresh 0600 file next to it, then rename over it."""
    fd, tmp = tempfile.mkstemp(dir=private_dir(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower().translate(str.maketrans("àâäéèêëîïôöùûüç", "aaaeeeeiioouuuc")))
    return s.strip("-") or "tv"


def load_config() -> dict:
    config = load_json(CONFIG_FILE, {})
    config.setdefault("devices", {})
    config.setdefault("default", next(iter(config["devices"]), None))
    return config


# --- Drivers ----------------------------------------------------------------

class Driver:
    """One kind of device. Commands are the generic names in ALL_KEYS."""

    kind = ""
    layout = "tv"       # remote layout: google, apple, tv, cast
    label = ""
    pairing = None      # None, "code" (code shown on the TV) or "accept" (approve on the TV)
    caps: set[str] = set()

    def __init__(self, daemon: Daemon, dev_id: str) -> None:
        self.daemon, self.id = daemon, dev_id
        self.connected = False
        self.online = True

    @property
    def conf(self) -> dict:
        return self.daemon.config["devices"][self.id]

    @property
    def host(self) -> str:
        return self.conf["host"]

    @property
    def creds(self) -> dict:
        return self.daemon.creds.setdefault(self.id, {})

    def save_creds(self, **values) -> None:
        self.creds.update(values)
        save_json(CREDS_FILE, self.daemon.creds)

    def changed(self, *_) -> None:
        self.daemon.status_changed()

    async def connect(self) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        self.connected = False

    async def send(self, cmd: str) -> None:
        raise NotImplementedError

    async def refresh(self) -> None:
        """Refresh the state of devices that don't push updates."""

    def state(self) -> dict:
        return {}

    def apps(self) -> list[list[str]]:
        return []

    async def pair_begin(self) -> str:
        raise Unsupported("no pairing")

    async def pair_finish(self, code: str) -> str | None:
        """Return None when done, otherwise the prompt for the next step."""
        raise Unsupported("no pairing")

    async def pair_accept(self) -> None:
        await self.connect()

    async def voice(self, seconds: float) -> None:
        raise Unsupported("voice")


class CastWatcher:
    """Read-only Cast connection used for "now playing" (title, progress).

    Google TVs also speak Cast; their remote protocol only reports the app.
    Best effort: when Cast is unavailable the remote keeps working without it.
    """

    def __init__(self, driver: Driver) -> None:
        self.driver = driver
        self.cc = None

    async def start(self) -> None:
        import uuid

        import pychromecast
        uid = self.driver.conf.get("uid") or ""
        try:
            cast_uuid = uuid.UUID(uid) if re.fullmatch(r"[0-9a-f]{32}", uid) else None
        except ValueError:
            cast_uuid = None
        info = (self.driver.host, 8009, cast_uuid, self.driver.conf.get("model"), self.driver.conf.get("name"))
        cc = await asyncio.to_thread(pychromecast.get_chromecast_from_host, info, 1, 1, 5)
        await asyncio.to_thread(cc.wait, 8)
        loop = asyncio.get_running_loop()
        watcher = self

        class Listener:
            def new_cast_status(self, status):
                loop.call_soon_threadsafe(watcher.driver.changed)

            def new_media_status(self, status):
                loop.call_soon_threadsafe(watcher.driver.changed)

            def load_media_failed(self, item, error_code):
                pass

        self._listener = Listener()
        cc.register_status_listener(self._listener)
        cc.media_controller.register_status_listener(self._listener)
        self.cc = cc

    def media(self) -> dict | None:
        if not self.cc or self.cc.is_idle:
            return None
        m = self.cc.media_controller.status
        if not m or not m.title:
            return None
        return {
            "title": m.title, "artist": m.artist or m.series_title or m.album_name,
            "position": m.adjusted_current_time, "duration": m.duration,
            "playing": m.player_is_playing,
        }

    async def close(self) -> None:
        if self.cc:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(self.cc.disconnect, 2)
        self.cc = None


# Google TV / Android TV ------------------------------------------------------

ANDROID_KEYS = {
    "power": "POWER", "on": "WAKEUP", "off": "SLEEP", "input": "TV_INPUT",
    "settings": "SETTINGS", "menu": "MENU", "search": "SEARCH", "assist": "ASSIST",
    "up": "DPAD_UP", "down": "DPAD_DOWN", "left": "DPAD_LEFT", "right": "DPAD_RIGHT",
    "ok": "DPAD_CENTER", "back": "BACK", "home": "HOME", "exit": "BACK",
    "mute": "VOLUME_MUTE", "vol-": "VOLUME_DOWN", "vol+": "VOLUME_UP",
    "play": "MEDIA_PLAY_PAUSE", "pause": "MEDIA_PAUSE", "stop": "MEDIA_STOP",
    "rew": "MEDIA_REWIND", "ff": "MEDIA_FAST_FORWARD", "prev": "MEDIA_PREVIOUS", "next": "MEDIA_NEXT",
    "ch+": "CHANNEL_UP", "ch-": "CHANNEL_DOWN", "info": "INFO", "captions": "CAPTIONS",
    "guide": "GUIDE", "red": "PROG_RED", "green": "PROG_GREEN", "yellow": "PROG_YELLOW",
    "blue": "PROG_BLUE", **{d: f"KEYCODE_{d}" for d in "0123456789"},
}
ANDROID_APPS = [
    ["https://www.youtube.com", "YouTube"],
    ["https://www.netflix.com/title", "Netflix"],
    ["com.amazon.amazonvideo.livingroom", "Prime Video"],
    ["com.disney.disneyplus", "Disney+"],
    ["com.spotify.tv.android", "Spotify"],
]
ANDROID_PACKAGES = {
    "com.google.android.youtube.tv": "YouTube", "com.netflix.ninja": "Netflix",
    "com.amazon.amazonvideo.livingroom": "Prime Video", "com.disney.disneyplus": "Disney+",
    "com.spotify.tv.android": "Spotify", "com.canal.android.canal": "CANAL+",
    "com.google.android.youtube.tvmusic": "YouTube Music", "tv.twitch.android.app": "Twitch",
    "com.plexapp.android": "Plex", "org.xbmc.kodi": "Kodi", "com.hbo.hbonow": "Max",
    "com.apple.atve.androidtv.appletv": "Apple TV+", "fr.francetv.pluzz": "france.tv",
    "tv.arte.plus7": "ARTE", "fr.m6.m6replay": "M6+", "fr.tf1.mytf1": "TF1+",
    "com.google.android.apps.tv.launcherx": "Home", "com.google.android.tvlauncher": "Home",
    "com.sony.dtv.tvx": "TV", "com.google.android.katniss": "Assistant",
}
# System apps that are never learned as shortcuts.
ANDROID_SKIP = re.compile(r"launcher|tvx|katniss|settings|setupwraith|backdrop|^com\.android\.|^android$")


def package_label(package: str) -> str:
    if package in ANDROID_PACKAGES:
        return ANDROID_PACKAGES[package]
    parts = [p for p in package.split(".") if p not in ("com", "android", "tv", "app", "fr", "org", "net")]
    return (parts[-1] if parts else package).capitalize()


class AndroidTV(Driver):
    kind, layout, label, pairing = "androidtv", "google", "Google TV / Android TV", "code"
    caps = {"dpad", "volume", "media", "power", "input", "text", "voice", "apps", "digits",
            "channels", "colors", "long", "settings"}

    def __init__(self, daemon: Daemon, dev_id: str) -> None:
        super().__init__(daemon, dev_id)
        self.remote = None
        self._pairing = None
        self.cast = CastWatcher(self)

    def make_remote(self):
        from androidtvremote2 import AndroidTVRemote
        private_dir(CONF_DIR)
        return AndroidTVRemote(CLIENT_NAME, str(CERT), str(KEY), self.host, enable_voice=True)

    async def connect(self) -> None:
        from androidtvremote2 import CannotConnect, ConnectionClosed, InvalidAuth
        if not CERT.exists():
            raise NeedsPairing(self.id)
        remote = self.make_remote()
        try:
            await asyncio.wait_for(remote.async_connect(), 10)
        except InvalidAuth:
            raise NeedsPairing(self.id)
        except (CannotConnect, ConnectionClosed, TimeoutError, OSError) as e:
            raise Unreachable(str(e) or type(e).__name__)
        self.remote = remote
        remote.add_is_on_updated_callback(self.changed)
        remote.add_current_app_updated_callback(self.on_app)
        remote.add_volume_info_updated_callback(self.changed)
        remote.add_is_available_updated_callback(self.on_available)
        remote.keep_reconnecting()
        self.connected = True
        self.on_app(remote.current_app)
        asyncio.get_running_loop().create_task(self._start_cast())
        await asyncio.sleep(0.5)  # some TVs (Sony) drop a key sent right after connecting

    async def _start_cast(self) -> None:
        with contextlib.suppress(Exception):
            await self.cast.start()
            self.changed()

    def on_available(self, available: bool) -> None:
        self.online = available
        self.changed()

    def on_app(self, package) -> None:
        """Remember opened apps and turn them into shortcuts."""
        if package and not ANDROID_SKIP.search(package):
            learned = self.conf.setdefault("apps", {})
            label = learned.pop(package, None) or package_label(package)
            self.conf["apps"] = {package: label, **learned}
            while len(self.conf["apps"]) > 12:
                self.conf["apps"].pop(next(reversed(self.conf["apps"])))
            self.daemon.save_config()
        self.changed()

    async def close(self) -> None:
        if self.remote:
            self.remote.disconnect()
        await self.cast.close()
        self.remote, self.connected = None, False

    async def send(self, cmd: str) -> None:
        r = self.remote
        if cmd.startswith("long:") and cmd[5:] in ANDROID_KEYS:
            r.send_key_command(ANDROID_KEYS[cmd[5:]], "START_LONG")
            await asyncio.sleep(1)
            r.send_key_command(ANDROID_KEYS[cmd[5:]], "END_LONG")
        elif cmd in ANDROID_KEYS:
            r.send_key_command(ANDROID_KEYS[cmd])
        elif cmd.startswith("text:"):
            r.send_text(cmd[5:])
        elif cmd.startswith("app:"):
            r.send_launch_app_command(cmd[4:])
        elif cmd.startswith("key:"):
            r.send_key_command(cmd[4:].upper())
        else:
            raise Unsupported(cmd)

    def state(self) -> dict:
        r = self.remote
        vol = r.volume_info or {}
        return {
            "on": r.is_on, "package": r.current_app,
            "app": package_label(r.current_app) if r.current_app else None,
            "level": vol.get("level"), "max": vol.get("max") or None, "muted": vol.get("muted"),
            "media": self.cast.media(),
        }

    def apps(self) -> list[list[str]]:
        learned = [[pkg, label] for pkg, label in self.conf.get("apps", {}).items()]
        known = {a[0] for a in learned} | {"com.google.android.youtube.tv", "com.netflix.ninja"}
        return learned + [a for a in ANDROID_APPS if a[0] not in known]

    async def pair_begin(self) -> str:
        remote = self.make_remote()
        if await remote.async_generate_cert_if_missing():
            KEY.chmod(0o600)
        await remote.async_start_pairing()
        self._pairing = remote
        return "Enter the 6-character code shown on the TV"

    async def pair_finish(self, code: str) -> str | None:
        from androidtvremote2 import InvalidAuth
        try:
            await self._pairing.async_finish_pairing(code.strip())
        except InvalidAuth:
            raise BadCode(code)
        self._pairing.disconnect()
        self._pairing = None
        return None

    async def voice(self, seconds: float) -> None:
        session = await self.remote.start_voice()
        proc = await asyncio.create_subprocess_exec(
            "arecord", "-q", "-t", "raw", "-f", "S16_LE", "-r", "8000", "-c", "1",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        end = time.monotonic() + seconds
        try:
            while time.monotonic() < end:
                try:
                    session.send_chunk(await proc.stdout.readexactly(8192))
                except asyncio.IncompleteReadError as e:
                    if e.partial:
                        session.send_chunk(e.partial)
                    break
        finally:
            proc.terminate()
            session.end()


# Fire TV and other Android devices over ADB -----------------------------------

ADB_KEY = CONF_DIR / "adbkey"
FIRETV_APPS = [
    ["com.netflix.ninja", "Netflix"], ["com.amazon.firetv.youtube", "YouTube"],
    ["com.amazon.avod", "Prime Video"], ["com.disney.disneyplus", "Disney+"],
    ["com.spotify.tv.android", "Spotify"],
]


class FireTV(Driver):
    """Fire TV Stick/Cube (and any Android device with network ADB enabled)."""

    kind, layout, label, pairing = "adb", "google", "Fire TV / Android (ADB)", "accept"
    caps = {"dpad", "volume", "media", "power", "text", "apps", "digits", "long", "settings"}

    def __init__(self, daemon: Daemon, dev_id: str) -> None:
        super().__init__(daemon, dev_id)
        self.adb = None
        self._state: dict = {}
        self._apps: list[list[str]] = []

    @staticmethod
    def signer():
        from adb_shell.auth.keygen import keygen
        from adb_shell.auth.sign_pythonrsa import PythonRSASigner
        if not ADB_KEY.exists():
            private_dir(CONF_DIR)
            keygen(str(ADB_KEY))
            ADB_KEY.chmod(0o600)
        return PythonRSASigner(Path(str(ADB_KEY) + ".pub").read_text(), ADB_KEY.read_text())

    async def connect(self, auth_timeout: float = 2) -> None:
        from adb_shell.adb_device_async import AdbDeviceTcpAsync
        if not self.creds.get("authorized") and auth_timeout < 10:
            raise NeedsPairing(self.id)
        dev = AdbDeviceTcpAsync(self.host, 5555, default_transport_timeout_s=9)
        try:
            ok = await dev.connect(rsa_keys=[self.signer()], auth_timeout_s=auth_timeout)
        except Exception as e:
            if "auth" in type(e).__name__.lower():
                raise NeedsPairing(self.id)
            raise Unreachable(str(e) or type(e).__name__)
        if not ok:
            raise Unreachable("ADB connection refused")
        if not self.creds.get("authorized"):
            self.save_creds(authorized=True)
        self.adb, self.connected, self.online = dev, True, True
        with contextlib.suppress(Exception):
            out = await dev.shell("pm list packages -3")
            pkgs = [line.split(":", 1)[1].strip() for line in out.splitlines() if ":" in line]
            self._apps = [[p, package_label(p)] for p in sorted(pkgs) if not ANDROID_SKIP.search(p)]
        await self.refresh()

    async def pair_accept(self) -> None:
        await self.connect(auth_timeout=40)  # the TV asks to allow USB debugging

    async def close(self) -> None:
        if self.adb:
            with contextlib.suppress(Exception):
                await self.adb.close()
        self.adb, self.connected = None, False

    async def shell(self, cmd: str) -> str:
        try:
            return await self.adb.shell(cmd)
        except Exception as e:
            self.connected = False
            raise Unreachable(str(e) or type(e).__name__)

    async def refresh(self) -> None:
        with contextlib.suppress(Exception):
            power = await self.shell("dumpsys power | grep -m1 mWakefulness=")
            focus = await self.shell("dumpsys window | grep -m1 -E 'mCurrentFocus|mFocusedApp'")
            pkg = re.search(r"([a-zA-Z0-9_.]+)/", focus)
            package = pkg.group(1) if pkg else None
            self._state = {"on": "Awake" in power, "package": package,
                           "app": package_label(package) if package else None}
            self.changed()

    async def send(self, cmd: str) -> None:
        import shlex
        if cmd.startswith("long:") and cmd[5:] in ANDROID_KEYS:
            await self.shell(f"input keyevent --longpress {self.keycode(cmd[5:])}")
        elif cmd in ANDROID_KEYS:
            await self.shell(f"input keyevent {self.keycode(cmd)}")
        elif cmd.startswith("text:"):
            await self.shell("input text " + shlex.quote(cmd[5:].replace(" ", "%s")))
        elif cmd.startswith("app:"):
            target = cmd[4:]
            if "://" in target:
                await self.shell("am start -a android.intent.action.VIEW -d " + shlex.quote(target))
            else:
                await self.shell(f"monkey -p {shlex.quote(target)} -c android.intent.category.LAUNCHER 1")
        elif cmd.startswith("key:"):
            await self.shell("input keyevent " + shlex.quote(cmd[4:].upper()))
        else:
            raise Unsupported(cmd)
        if cmd in ("power", "on", "off", "home", "back") or cmd.startswith("app:"):
            await asyncio.sleep(0.6)
            await self.refresh()

    @staticmethod
    def keycode(cmd: str) -> str:
        code = ANDROID_KEYS[cmd]
        return code if code.startswith("KEYCODE_") else "KEYCODE_" + code

    def state(self) -> dict:
        return self._state

    def apps(self) -> list[list[str]]:
        return self._apps or FIRETV_APPS


# Apple TV --------------------------------------------------------------------

class AppleTV(Driver):
    kind, layout, label, pairing = "appletv", "apple", "Apple TV", "code"
    caps = {"dpad", "volume", "media", "power", "text", "apps", "channels", "long", "settings"}

    def __init__(self, daemon: Daemon, dev_id: str) -> None:
        super().__init__(daemon, dev_id)
        self.atv = None
        self.playing = None
        self._apps: list[list[str]] = []
        self._pair_queue: list = []
        self._handler = None
        self._config = None

    async def scan_config(self):
        import pyatv
        loop = asyncio.get_running_loop()
        confs = await pyatv.scan(loop, hosts=[self.host], timeout=5)
        if not confs:
            raise Unreachable(f"no Apple TV at {self.host}")
        return confs[0]

    async def connect(self) -> None:
        import pyatv
        from pyatv.const import Protocol
        conf = await self.scan_config()
        saved = self.creds.get("protocols", {})
        if not saved:
            raise NeedsPairing(self.id)
        for proto, cred in saved.items():
            conf.set_credentials(Protocol[proto], cred)
        try:
            self.atv = await pyatv.connect(conf, asyncio.get_running_loop())
        except Exception as e:  # pyatv raises various exceptions (auth, network)
            if "auth" in type(e).__name__.lower() or "pair" in str(e).lower():
                raise NeedsPairing(self.id)
            raise Unreachable(str(e) or type(e).__name__)
        driver = self

        class Listener:
            def connection_lost(self, exception):
                driver.connected = driver.online = False
                driver.changed()

            def connection_closed(self):
                self.connection_lost(None)

            def playstatus_update(self, updater, playstatus):
                driver.playing = playstatus
                driver.changed()

            def playstatus_error(self, updater, exception):
                pass

            def powerstate_update(self, old_state, new_state):
                driver.changed()

            def volume_update(self, old_level, new_level):
                driver.changed()

            def outputdevices_update(self, old_devices, new_devices):
                pass

        self._listener = Listener()
        self.atv.listener = self._listener
        with contextlib.suppress(Exception):
            self.atv.push_updater.listener = self._listener
            self.atv.push_updater.start()
        with contextlib.suppress(Exception):
            self.atv.power.listener = self._listener
        with contextlib.suppress(Exception):
            self.atv.audio.listener = self._listener
        with contextlib.suppress(Exception):
            self._apps = [[a.identifier, a.name] for a in await self.atv.apps.app_list()]
        self.connected = self.online = True

    async def close(self) -> None:
        if self.atv:
            self.atv.close()
        self.atv, self.connected = None, False

    async def send(self, cmd: str) -> None:
        from pyatv.const import InputAction, PowerState
        rc = self.atv.remote_control
        simple = {
            "up": rc.up, "down": rc.down, "left": rc.left, "right": rc.right, "ok": rc.select,
            "back": rc.menu, "exit": rc.menu, "home": rc.home, "play": rc.play_pause, "pause": rc.pause,
            "stop": rc.stop, "next": rc.next, "prev": rc.previous, "rew": rc.skip_backward,
            "ff": rc.skip_forward, "ch+": rc.channel_up, "ch-": rc.channel_down, "guide": rc.guide,
            "settings": rc.control_center, "menu": rc.top_menu,
        }
        if cmd in ("vol+", "vol-"):
            try:
                await (self.atv.audio.volume_up() if cmd == "vol+" else self.atv.audio.volume_down())
            except Exception:
                await (rc.volume_up() if cmd == "vol+" else rc.volume_down())
        elif cmd in simple:
            await simple[cmd]()
        elif cmd == "long:home":
            await rc.home_hold()
        elif cmd.startswith("long:") and cmd[5:] in ("ok", "up", "down", "left", "right", "back"):
            await simple[cmd[5:]](action=InputAction.Hold)
        elif cmd in ("power", "on", "off"):
            is_on = self.atv.power.power_state == PowerState.On
            if cmd == "on" or (cmd == "power" and not is_on):
                await self.atv.power.turn_on()
            else:
                await self.atv.power.turn_off()
        elif cmd.startswith("text:"):
            await self.atv.keyboard.text_set(cmd[5:])
        elif cmd.startswith("app:"):
            await self.atv.apps.launch_app(cmd[4:])
        else:
            raise Unsupported(cmd)

    def state(self) -> dict:
        from pyatv.const import PowerState
        st: dict = {}
        with contextlib.suppress(Exception):
            st["on"] = self.atv.power.power_state == PowerState.On
        with contextlib.suppress(Exception):
            app = self.atv.metadata.app
            st["app"], st["package"] = (app.name, app.identifier) if app else (None, None)
        with contextlib.suppress(Exception):
            st["level"], st["max"] = round(self.atv.audio.volume), 100
        p = self.playing
        if p is not None and getattr(p, "title", None):
            from pyatv.const import DeviceState
            st["media"] = {
                "title": p.title, "artist": p.artist or p.series_name or p.album,
                "position": p.position, "duration": p.total_time,
                "playing": p.device_state == DeviceState.Playing,
            }
        return st

    def apps(self) -> list[list[str]]:
        return self._apps

    async def pair_begin(self) -> str:
        from pyatv.const import PairingRequirement, Protocol
        conf = await self.scan_config()
        self._config = conf
        wanted = [Protocol.Companion, Protocol.AirPlay, Protocol.MRP]
        self._pair_queue = [
            s.protocol for p in wanted for s in conf.services
            if s.protocol == p and s.pairing in (PairingRequirement.Mandatory, PairingRequirement.Optional)
        ]
        self._pair_total = len(self._pair_queue)
        self.save_creds(protocols={})
        if not self._pair_queue:
            return ""
        return await self._next_pairing()

    async def _next_pairing(self) -> str:
        import pyatv
        proto = self._pair_queue[0]
        self._handler = await pyatv.pair(self._config, proto, asyncio.get_running_loop(), name=CLIENT_NAME)
        await self._handler.begin()
        step = f" — {proto.name}" if self._pair_total > 1 else ""
        return f"Enter the code shown on the Apple TV{step}"

    async def pair_finish(self, code: str) -> str | None:
        self._handler.pin(code.strip())
        await self._handler.finish()
        if not self._handler.has_paired:
            await self._handler.close()
            self._handler = None
            raise BadCode("Wrong code. " + await self._next_pairing())
        proto = self._pair_queue.pop(0)
        protocols = dict(self.creds.get("protocols", {}), **{proto.name: self._handler.service.credentials})
        self.save_creds(protocols=protocols)
        await self._handler.close()
        self._handler = None
        return await self._next_pairing() if self._pair_queue else None


# Samsung (Tizen) ---------------------------------------------------------------

SAMSUNG_KEYS = {
    "power": "KEY_POWER", "off": "KEY_POWEROFF", "input": "KEY_SOURCE", "settings": "KEY_MENU",
    "menu": "KEY_TOOLS", "up": "KEY_UP", "down": "KEY_DOWN", "left": "KEY_LEFT", "right": "KEY_RIGHT",
    "ok": "KEY_ENTER", "back": "KEY_RETURN", "home": "KEY_HOME", "exit": "KEY_EXIT",
    "mute": "KEY_MUTE", "vol+": "KEY_VOLUP", "vol-": "KEY_VOLDOWN", "play": "KEY_PLAY",
    "pause": "KEY_PAUSE", "stop": "KEY_STOP", "rew": "KEY_REWIND", "ff": "KEY_FF",
    "ch+": "KEY_CHUP", "ch-": "KEY_CHDOWN", "info": "KEY_INFO", "guide": "KEY_GUIDE",
    "captions": "KEY_CAPTION", "red": "KEY_RED", "green": "KEY_GREEN", "yellow": "KEY_YELLOW",
    "blue": "KEY_CYAN", **{d: f"KEY_{d}" for d in "0123456789"},
}
SAMSUNG_APPS = [
    ["111299001912", "YouTube"], ["3201907018807", "Netflix"],
    ["3201910019365", "Prime Video"], ["3201901017640", "Disney+"], ["3201606009684", "Spotify"],
]


class Samsung(Driver):
    kind, layout, label, pairing = "samsung", "tv", "Samsung (Tizen)", "accept"
    caps = {"dpad", "volume", "media", "power", "input", "digits", "channels", "colors", "text",
            "apps", "settings"}

    def __init__(self, daemon: Daemon, dev_id: str) -> None:
        super().__init__(daemon, dev_id)
        self.tv = None
        self._on = None
        self._apps: list[list[str]] = []

    def _client(self, timeout: float):
        from samsungtvws import SamsungTVWS
        return SamsungTVWS(self.host, port=8002, token=self.creds.get("token"), timeout=timeout,
                           key_press_delay=0, name=CLIENT_NAME)

    async def connect(self, timeout: float = 8) -> None:
        if not self.creds.get("token") and timeout < 20:
            raise NeedsPairing(self.id)
        tv = self._client(timeout)
        try:
            await asyncio.to_thread(tv.open)
        except Exception as e:
            raise Unreachable(str(e) or type(e).__name__)
        if tv.token and tv.token != self.creds.get("token"):
            self.save_creds(token=tv.token)
        self.tv, self.connected, self.online = tv, True, True
        with contextlib.suppress(Exception):
            apps = await asyncio.to_thread(tv.app_list)
            self._apps = [[a["appId"], a["name"]] for a in apps or []]
        await self.refresh()

    async def pair_accept(self) -> None:
        await self.connect(timeout=40)  # the TV asks to allow the connection

    async def close(self) -> None:
        if self.tv:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(self.tv.close)
        self.tv, self.connected = None, False

    async def refresh(self) -> None:
        with contextlib.suppress(Exception):
            info = await asyncio.to_thread(self.tv.rest_device_info)
            self._on = info.get("device", {}).get("PowerState", "on") == "on"
            self.changed()

    async def send(self, cmd: str) -> None:
        if cmd in SAMSUNG_KEYS:
            await asyncio.to_thread(self.tv.send_key, SAMSUNG_KEYS[cmd])
        elif cmd.startswith("long:") and cmd[5:] in SAMSUNG_KEYS:
            await asyncio.to_thread(self.tv.hold_key, SAMSUNG_KEYS[cmd[5:]], 1)
        elif cmd.startswith("text:"):
            await asyncio.to_thread(self.tv.send_text, cmd[5:])
        elif cmd.startswith("app:"):
            await asyncio.to_thread(self.tv.run_app, cmd[4:])
        elif cmd.startswith("key:"):
            await asyncio.to_thread(self.tv.send_key, cmd[4:].upper())
        else:
            raise Unsupported(cmd)

    def state(self) -> dict:
        return {"on": self._on}

    def apps(self) -> list[list[str]]:
        return self._apps or SAMSUNG_APPS


# LG (webOS) ------------------------------------------------------------------

WEBOS_BUTTONS = {
    "up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT", "ok": "ENTER", "back": "BACK",
    "home": "HOME", "exit": "EXIT", "settings": "MENU", "menu": "QMENU", "input": "INPUT_HUB",
    "play": "PLAY", "pause": "PAUSE", "stop": "STOP", "rew": "REWIND", "ff": "FASTFORWARD",
    "ch+": "CHANNELUP", "ch-": "CHANNELDOWN", "info": "INFO", "guide": "GUIDE", "captions": "CC",
    "red": "RED", "green": "GREEN", "yellow": "YELLOW", "blue": "BLUE", "mute": "MUTE",
    **{d: d for d in "0123456789"},
}


class WebOS(Driver):
    kind, layout, label, pairing = "webos", "tv", "LG (webOS)", "accept"
    caps = {"dpad", "volume", "media", "power", "input", "digits", "channels", "colors", "text",
            "apps", "settings"}

    def __init__(self, daemon: Daemon, dev_id: str) -> None:
        super().__init__(daemon, dev_id)
        self.client = None
        self._playing = False

    async def connect(self, allow_prompt: bool = False) -> None:
        from aiowebostv import WebOsClient
        if not self.creds.get("client_key") and not allow_prompt:
            raise NeedsPairing(self.id)
        client = WebOsClient(self.host, self.creds.get("client_key"), connect_timeout=40 if allow_prompt else 8)
        try:
            await client.connect()
        except Exception as e:
            raise Unreachable(str(e) or type(e).__name__)
        if client.client_key and client.client_key != self.creds.get("client_key"):
            self.save_creds(client_key=client.client_key)

        async def on_state(_client) -> None:
            self.changed()

        await client.register_state_update_callback(on_state)
        self.client, self.connected, self.online = client, True, True

    async def pair_accept(self) -> None:
        await self.connect(allow_prompt=True)

    async def close(self) -> None:
        if self.client:
            with contextlib.suppress(Exception):
                await self.client.disconnect()
        self.client, self.connected = None, False

    async def send(self, cmd: str) -> None:
        c = self.client
        if cmd == "vol+":
            await c.volume_up()
        elif cmd == "vol-":
            await c.volume_down()
        elif cmd in ("power", "off"):
            await c.power_off()
        elif cmd == "on":
            await c.power_on()
        elif cmd == "play":
            await c.button("PAUSE" if self._playing else "PLAY")
            self._playing = not self._playing
        elif cmd in WEBOS_BUTTONS:
            await c.button(WEBOS_BUTTONS[cmd])
        elif cmd.startswith("text:"):
            from aiowebostv.endpoints import INSERT_TEXT
            await c.request(INSERT_TEXT, {"text": cmd[5:], "replace": 0})
        elif cmd.startswith("app:"):
            await c.launch_app(cmd[4:])
        else:
            raise Unsupported(cmd)

    def state(self) -> dict:
        s = self.client.tv_state
        app = s.apps.get(s.current_app_id, {}) if s.current_app_id else {}
        return {
            "on": s.is_on, "package": s.current_app_id, "app": app.get("title") or s.current_app_id,
            "level": s.volume, "max": 100 if s.volume is not None else None, "muted": s.muted,
        }

    def apps(self) -> list[list[str]]:
        return [[app_id, a.get("title", app_id)] for app_id, a in self.client.tv_state.apps.items()]


# Roku --------------------------------------------------------------------------

ROKU_KEYS = {
    "power": "Power", "on": "PowerOn", "off": "PowerOff", "up": "Up", "down": "Down",
    "left": "Left", "right": "Right", "ok": "Select", "back": "Back", "home": "Home",
    "exit": "Home", "mute": "VolumeMute", "vol+": "VolumeUp", "vol-": "VolumeDown",
    "play": "Play", "pause": "Play", "rew": "Rev", "ff": "Fwd", "prev": "InstantReplay",
    "info": "Info", "search": "Search", "ch+": "ChannelUp", "ch-": "ChannelDown",
    "input": "InputHDMI1",
}


class Roku(Driver):
    kind, layout, label, pairing = "roku", "tv", "Roku", None
    caps = {"dpad", "volume", "media", "power", "text", "apps", "channels", "input"}

    def __init__(self, daemon: Daemon, dev_id: str) -> None:
        super().__init__(daemon, dev_id)
        self.session = None
        self._state: dict = {}
        self._apps: list[list[str]] = []

    @property
    def base(self) -> str:
        return f"http://{self.host}:8060"

    async def _get(self, path: str) -> str:
        async with self.session.get(self.base + path) as resp:
            return await resp.text()

    async def _post(self, path: str) -> None:
        async with self.session.post(self.base + path) as resp:
            resp.raise_for_status()

    async def connect(self) -> None:
        import aiohttp
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5))
        try:
            await self._get("/query/device-info")
        except Exception as e:
            await self.session.close()
            raise Unreachable(str(e) or type(e).__name__)
        with contextlib.suppress(Exception):
            xml = await self._get("/query/apps")
            self._apps = [[i, n] for i, n in re.findall(r'<app id="([^"]+)"[^>]*>([^<]+)</app>', xml)]
        self.connected = self.online = True
        await self.refresh()

    async def close(self) -> None:
        if self.session:
            await self.session.close()
        self.session, self.connected = None, False

    async def refresh(self) -> None:
        with contextlib.suppress(Exception):
            info = await self._get("/query/device-info")
            power = re.search(r"<power-mode>([^<]+)</power-mode>", info)
            app = re.search(r'<app id="([^"]*)"[^>]*>([^<]*)</app>', await self._get("/query/active-app"))
            self._state = {
                "on": power is None or power.group(1) == "PowerOn",
                "package": app.group(1) if app else None, "app": app.group(2) if app else None,
            }
            self.changed()

    async def send(self, cmd: str) -> None:
        from urllib.parse import quote
        if cmd in ROKU_KEYS:
            await self._post(f"/keypress/{ROKU_KEYS[cmd]}")
        elif cmd.startswith("text:"):
            for ch in cmd[5:]:
                await self._post(f"/keypress/Lit_{quote(ch, safe='')}")
        elif cmd.startswith("app:"):
            await self._post(f"/launch/{cmd[4:]}")
        elif cmd.startswith("key:"):
            await self._post(f"/keypress/{cmd[4:]}")
        else:
            raise Unsupported(cmd)
        await asyncio.sleep(0.3)
        await self.refresh()

    def state(self) -> dict:
        return self._state

    def apps(self) -> list[list[str]]:
        return self._apps


# Plain Chromecast (playback and volume) ----------------------------------------

class Cast(Driver):
    kind, layout, label, pairing = "cast", "cast", "Chromecast", None
    caps = {"volume", "media", "power"}

    def __init__(self, daemon: Daemon, dev_id: str) -> None:
        super().__init__(daemon, dev_id)
        self.cc = None

    async def connect(self) -> None:
        import uuid

        import pychromecast
        uid = self.conf.get("uid")
        host = (self.host, 8009, uuid.UUID(uid) if uid else None, self.conf.get("model"), self.conf.get("name"))
        try:
            cc = await asyncio.to_thread(pychromecast.get_chromecast_from_host, host, 1, 1, 5)
            await asyncio.to_thread(cc.wait, 8)
        except Exception as e:
            raise Unreachable(str(e) or type(e).__name__)
        loop = asyncio.get_running_loop()
        driver = self

        class Listener:
            def new_cast_status(self, status):
                loop.call_soon_threadsafe(driver.changed)

            def new_media_status(self, status):
                loop.call_soon_threadsafe(driver.changed)

            def load_media_failed(self, item, error_code):
                pass

        self._listener = Listener()
        cc.register_status_listener(self._listener)
        cc.media_controller.register_status_listener(self._listener)
        self.cc, self.connected, self.online = cc, True, True

    async def close(self) -> None:
        if self.cc:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(self.cc.disconnect, 2)
        self.cc, self.connected = None, False

    async def send(self, cmd: str) -> None:
        cc, mc = self.cc, self.cc.media_controller
        status = mc.status
        actions = {
            "vol+": lambda: cc.volume_up(0.05), "vol-": lambda: cc.volume_down(0.05),
            "mute": lambda: cc.set_volume_muted(not cc.status.volume_muted),
            "play": lambda: mc.pause() if status.player_is_playing else mc.play(),
            "pause": mc.pause, "stop": mc.stop, "next": mc.queue_next, "prev": mc.queue_prev,
            "ff": lambda: mc.seek((status.adjusted_current_time or 0) + 30),
            "rew": lambda: mc.seek(max(0, (status.adjusted_current_time or 0) - 10)),
            "power": cc.quit_app, "off": cc.quit_app,
        }
        if cmd not in actions:
            raise Unsupported(cmd)
        await asyncio.to_thread(actions[cmd])

    def state(self) -> dict:
        s = self.cc.status
        if not s:
            return {}
        m = self.cc.media_controller.status
        media = None
        if not self.cc.is_idle and m and m.title:
            media = {"title": m.title, "artist": m.artist or m.series_title or m.album_name,
                     "position": m.adjusted_current_time, "duration": m.duration,
                     "playing": m.player_is_playing}
        return {
            "on": not self.cc.is_idle, "app": s.display_name if not self.cc.is_idle else None,
            "level": round((s.volume_level or 0) * 100), "max": 100, "muted": s.volume_muted,
            "media": media,
        }


DRIVERS = {d.kind: d for d in (AndroidTV, FireTV, AppleTV, Samsung, WebOS, Roku, Cast)}


# --- Network discovery ------------------------------------------------------

def local_network() -> ipaddress.IPv4Network | None:
    with contextlib.suppress(OSError):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # no packet is actually sent
            ip = s.getsockname()[0]
        return ipaddress.ip_network(f"{ip}/24", strict=False)
    return None


MDNS_TYPES = ["_androidtvremote2._tcp.local.", "_googlecast._tcp.local.", "_airplay._tcp.local.",
              "_amzn-wplay._tcp.local."]


class MdnsWatcher:
    """Long-running mDNS listener: Wi-Fi devices answer irregularly, so we keep
    everything they announce over time."""

    def __init__(self) -> None:
        self.aiozc = None
        self.browser = None
        self.entries: dict[tuple[str, str], tuple[str | None, dict, float]] = {}

    async def start(self) -> None:
        from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconf
        loop = asyncio.get_running_loop()
        self.aiozc = AsyncZeroconf()

        def handler(zeroconf, service_type, name, state_change):
            loop.call_soon_threadsafe(lambda: loop.create_task(self.resolve(service_type, name)))

        self.browser = AsyncServiceBrowser(self.aiozc.zeroconf, MDNS_TYPES, handlers=[handler])

    async def resolve(self, service_type: str, name: str) -> None:
        from zeroconf.asyncio import AsyncServiceInfo
        info = AsyncServiceInfo(service_type, name)
        with contextlib.suppress(Exception):
            if await info.async_request(self.aiozc.zeroconf, 3000):
                props = {k.decode(errors="ignore"): (v or b"").decode(errors="ignore")
                         for k, v in info.properties.items()}
                ipv4 = next((a for a in info.parsed_addresses() if ":" not in a), None)
                self.entries[(service_type, name)] = (ipv4, props, time.time())

    def snapshot(self, max_age: float = 3600) -> list[tuple[str, str, str | None, dict]]:
        now = time.time()
        return [
            (stype.split(".")[0], name.split(".")[0].replace("\\032", " "), ip, props)
            for (stype, name), (ip, props, seen) in self.entries.items() if now - seen < max_age
        ]

    async def close(self) -> None:
        if self.browser:
            await self.browser.async_cancel()
        if self.aiozc:
            await self.aiozc.async_close()


async def _probe_ports(hosts: list[str], ports: list[int]) -> dict[str, set[int]]:
    sem = asyncio.Semaphore(200)
    open_ports: dict[str, set[int]] = {}

    async def probe(host: str, port: int) -> None:
        async with sem:
            with contextlib.suppress(OSError, TimeoutError):
                _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), 0.7)
                writer.close()
                open_ports.setdefault(host, set()).add(port)

    await asyncio.gather(*(probe(h, p) for h in hosts for p in ports))
    return open_ports


async def discover(seconds: float = 4, hosts: list[str] | None = None,
                   watcher: MdnsWatcher | None = None) -> list[dict]:
    """mDNS + Apple TV scan + port probing (ufw usually blocks SSDP replies)."""
    import aiohttp
    import pyatv
    from pyatv.const import OperatingSystem

    loop = asyncio.get_running_loop()
    targeted = hosts is not None
    if hosts is None:
        net = local_network()
        hosts = [str(h) for h in net.hosts()] if net else []
    own = watcher is None
    if own:
        watcher = MdnsWatcher()
        await watcher.start()
    try:
        _, atvs, ports = await asyncio.gather(
            asyncio.sleep(seconds),
            pyatv.scan(loop, timeout=int(seconds), aiozc=watcher.aiozc, hosts=hosts if targeted else None),
            _probe_ports(hosts, [8060, 8001, 3001, 6466, 5555, 8009]),
        )
        mdns = [m for m in watcher.snapshot() if not targeted or m[2] in hosts]
    finally:
        if own:
            await watcher.close()

    # Evidence per address, then classification: the most capable kind wins
    # (a Google TV also announces Chromecast, a Samsung TV also AirPlay…).
    ev: dict[str, dict] = {}
    for stype, name, ip, props in mdns:
        if not ip:
            continue
        e = ev.setdefault(ip, {})
        if stype == "_androidtvremote2":
            e["android"] = {"name": name, "bt": props.get("bt")}
        elif stype == "_googlecast" and props.get("md") != "Google Cast Group":
            e["cast"] = {"name": props.get("fn") or name, "model": props.get("md"), "id": props.get("id")}
        elif stype == "_airplay":
            e["airplay"] = {"name": name, "maker": props.get("manufacturer", ""), "model": props.get("model", "")}
        elif stype == "_amzn-wplay":
            e["firetv"] = {"name": props.get("n") or name}
    for conf in atvs:
        if conf.device_info.operating_system == OperatingSystem.TvOS:
            ev.setdefault(str(conf.address), {})["apple"] = {
                "name": conf.name, "uid": conf.identifier,
                "model": getattr(conf.device_info, "model_str", None) or "Apple TV",
            }
    for ip, opened in ports.items():
        ev.setdefault(ip, {})["ports"] = opened

    by_ip: dict[str, dict] = {}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as http:
        async def get(url: str) -> str:
            with contextlib.suppress(Exception):
                async with http.get(url, ssl=False) as resp:  # Cast devices use self-signed certificates
                    return await resp.text()
            return ""

        async def eureka(ip: str) -> dict:
            """Name, model and id from the Cast setup API (when mDNS stayed silent)."""
            with contextlib.suppress(ValueError):
                info = json.loads(await get(f"https://{ip}:8443/setup/eureka_info?params=name,device_info") or "{}")
                dev = info.get("device_info", {})
                udn = (dev.get("ssdp_udn") or "").replace("-", "")
                return {"name": info.get("name"), "model": dev.get("model_name"), "id": udn or None}
            return {}

        for ip, e in ev.items():
            opened, cast, air = e.get("ports", set()), e.get("cast") or {}, e.get("airplay") or {}
            if not cast.get("name") and (8009 in opened or 6466 in opened or "android" in e):
                cast = {k: v for k, v in (await eureka(ip)).items() if v} or cast
            found = None
            if "apple" in e:
                found = {"kind": "appletv", **e["apple"]}
            elif "android" in e or 6466 in opened:
                android = e.get("android") or {}
                found = {"kind": "androidtv", "name": cast.get("name") or android.get("name"),
                         "model": cast.get("model"), "uid": cast.get("id") or android.get("bt")}
            elif 8060 in opened and (xml := await get(f"http://{ip}:8060/query/device-info")):
                field = lambda tag: (m.group(1) if (m := re.search(f"<{tag}>([^<]*)</{tag}>", xml)) else None)
                found = {"kind": "roku", "name": field("user-device-name") or field("friendly-device-name") or "Roku",
                         "model": field("model-name"), "uid": field("serial-number")}
            elif 8001 in opened and (raw := await get(f"http://{ip}:8001/api/v2/")):
                with contextlib.suppress(ValueError):
                    data = json.loads(raw)
                    dev = data.get("device", {})
                    if "Samsung" in data.get("type", "") or dev.get("OS") == "Tizen":
                        found = {"kind": "samsung", "name": dev.get("name") or air.get("name") or "Samsung TV",
                                 "model": dev.get("modelName"), "uid": dev.get("id") or dev.get("wifiMac")}
            if found is None and 3001 in opened and (
                    "LG" in air.get("maker", "") or "hello" in (await get(f"http://{ip}:3000/")).lower()):
                found = {"kind": "webos", "name": air.get("name") or "LG TV",
                         "model": air.get("model") or "webOS", "uid": air.get("name")}
            if found is None and (5555 in opened or "firetv" in e):
                fire = e.get("firetv") or {}
                found = {"kind": "adb", "name": fire.get("name") or cast.get("name") or "Fire TV",
                         "model": "Fire TV" if fire else cast.get("model"), "uid": fire.get("name") or ip}
            if found is None and cast:
                found = {"kind": "cast", "name": cast.get("name"), "model": cast.get("model"), "uid": cast.get("id")}
            if found:
                by_ip[ip] = {k: v for k, v in found.items() if v} | {"host": ip}

    for c in by_ip.values():
        c.setdefault("name", c["host"])
        c.setdefault("uid", c["host"])
        c["label"] = DRIVERS[c["kind"]].label
    return sorted(by_ip.values(), key=lambda c: (list(DRIVERS).index(c["kind"]), c["name"].lower()))


# --- Service ------------------------------------------------------------------

class Daemon:
    def __init__(self) -> None:
        self.config = load_config()
        self.creds = load_json(CREDS_FILE, {})
        self.drivers: dict[str, Driver] = {}
        self.locks: dict[str, asyncio.Lock] = {}
        self.errors: dict[str, str] = {}
        self.needs_pairing: set[str] = set()
        self.wanted: set[str] = set()
        self.discovery: dict = {"running": False, "found": [], "at": None}
        self.pairing: dict = {"state": "idle"}
        self.message = ""
        self.message_device: str | None = None
        self._pair_driver: Driver | None = None
        self._status_pending = False
        self._last_rediscovery: dict[str, float] = {}
        self.mdns = MdnsWatcher()
        self.loop = asyncio.get_running_loop()

    # Configuration

    def save_config(self) -> None:
        save_json(CONFIG_FILE, self.config)

    def devices(self) -> dict:
        return self.config["devices"]

    def driver(self, dev_id: str) -> Driver:
        if dev_id not in self.drivers:
            self.drivers[dev_id] = DRIVERS[self.devices()[dev_id]["kind"]](self, dev_id)
        return self.drivers[dev_id]

    # Published state (bar, popup, terminal)

    def status_changed(self) -> None:
        if not self._status_pending:
            self._status_pending = True
            self.loop.call_later(0.05, self.write_status)

    def device_status(self, dev_id: str) -> dict:
        conf = self.devices()[dev_id]
        cls = DRIVERS[conf["kind"]]
        drv = self.drivers.get(dev_id)
        st = {
            "name": conf.get("name", dev_id), "kind": conf["kind"], "layout": cls.layout,
            "label": cls.label, "model": conf.get("model"), "host": conf.get("host"),
            "caps": sorted(cls.caps), "volume_via": conf.get("volume_via"),
            "connected": bool(drv and drv.connected), "online": bool(drv and drv.connected and drv.online),
            "needs_pairing": dev_id in self.needs_pairing, "error": self.errors.get(dev_id),
            "pairing_type": cls.pairing,
        }
        if drv and drv.connected:
            with contextlib.suppress(Exception):
                st.update(drv.state())
            with contextlib.suppress(Exception):
                st["apps"] = drv.apps()[:40]
        via = conf.get("volume_via")
        if via and via in self.drivers and self.drivers[via].connected:
            with contextlib.suppress(Exception):
                vst = self.drivers[via].state()
                st.update(level=vst.get("level"), max=vst.get("max"), muted=vst.get("muted"))
        if st.get("muted"):
            st["volume"] = "muted"
        elif st.get("max"):
            st["volume"] = f"{st.get('level')}/{st['max']}"
        else:
            st["volume"] = None
        return st

    def write_status(self) -> None:
        self._status_pending = False
        default = self.config.get("default")
        status = {
            "default": default,
            "order": list(self.devices()),
            "devices": {d: self.device_status(d) for d in self.devices()},
            "discovery": self.discovery,
            "pairing": self.pairing,
            "message": self.message,
            "message_device": self.message_device,
            "updated": time.time(),
        }
        if default in status["devices"]:
            status.update(device=default, **status["devices"][default])
        # Written in place (no rename) so file watchers keep working.
        with os.fdopen(open_private(STATUS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC), "w") as f:
            f.write(json.dumps(status, ensure_ascii=False) + "\n")

    def say(self, text: str, device: str | None = None) -> None:
        self.message, self.message_device = text, device
        self.status_changed()

    # Connections

    async def ensure(self, dev_id: str) -> Driver:
        if dev_id not in self.devices():
            raise TvError(f"unknown device: {dev_id}")
        self.wanted.add(dev_id)
        drv = self.driver(dev_id)
        async with self.locks.setdefault(dev_id, asyncio.Lock()):
            if drv.connected:
                return drv
            try:
                await drv.connect()
            except NeedsPairing:
                self.needs_pairing.add(dev_id)
                self.status_changed()
                raise
            except Unreachable as e:
                self.errors[dev_id] = str(e)
                self.status_changed()
                if await self.rediscover(dev_id):
                    await drv.connect()
                else:
                    raise
            self.errors.pop(dev_id, None)
            self.needs_pairing.discard(dev_id)
            self.status_changed()
            return drv

    async def rediscover(self, dev_id: str) -> bool:
        """The IP may have changed (DHCP, moving house): find the device by its id."""
        if time.monotonic() - self._last_rediscovery.get(dev_id, -1e9) < 120:
            return False
        self._last_rediscovery[dev_id] = time.monotonic()
        conf = self.devices()[dev_id]
        for c in await discover(3, watcher=self.mdns):
            if c["kind"] == conf["kind"] and c.get("uid") == conf.get("uid") and c["host"] != conf["host"]:
                conf["host"] = c["host"]
                self.save_config()
                return True
        return False

    async def send(self, dev_id: str, cmds: list[str]) -> None:
        drv = await self.ensure(dev_id)
        via = self.devices()[dev_id].get("volume_via")
        for cmd in cmds:
            if cmd == "connect":
                continue
            target = drv
            if cmd in VOLUME_KEYS and via and via in self.devices():
                with contextlib.suppress(TvError):
                    target = await self.ensure(via)
            try:
                await target.send(cmd)
            except Unsupported:
                self.say(f"\"{cmd}\" is not available on {target.label}", dev_id)
            await asyncio.sleep(0.12)

    # Pairing

    async def start_pairing(self, dev_id: str) -> None:
        if self._pair_driver:
            await self.cancel_pairing()
        old = self.drivers.pop(dev_id, None)
        if old:
            await old.close()
        drv = self.driver(dev_id)
        name = self.devices()[dev_id].get("name", dev_id)
        self._pair_driver = drv
        self.pairing = {"device": dev_id, "name": name, "state": "working", "prompt": "Connecting…",
                        "started": time.time()}
        self.status_changed()
        try:
            if drv.pairing == "accept":
                self.pairing.update(state="waiting_accept", prompt="Accept the connection request on the TV")
                self.status_changed()
                await drv.pair_accept()
                await self.pairing_done(dev_id)
            elif drv.pairing == "code":
                prompt = await drv.pair_begin()
                if prompt:
                    self.pairing.update(state="waiting_code", prompt=prompt)
                    self.status_changed()
                else:
                    await self.pairing_done(dev_id)
            else:
                await self.pairing_done(dev_id)
        except TvError as e:
            self.pairing.update(state="error", prompt=f"Failed: {e}")
            self._pair_driver = None
            self.status_changed()

    async def pairing_code(self, code: str) -> None:
        drv = self._pair_driver
        if not drv or self.pairing.get("state") != "waiting_code":
            return
        self.pairing.update(state="working", prompt="Checking…")
        self.status_changed()
        try:
            prompt = await drv.pair_finish(code)
        except BadCode as e:
            msg = str(e) if str(e) != code else ""
            self.pairing.update(state="waiting_code", prompt=(msg or "Wrong code, try again"), retry=True)
            self.status_changed()
            return
        except Exception as e:
            self.pairing.update(state="error", prompt=f"Failed: {e}")
            self._pair_driver = None
            self.status_changed()
            return
        if prompt:
            self.pairing.update(state="waiting_code", prompt=prompt, retry=False)
            self.status_changed()
        else:
            await self.pairing_done(drv.id)

    async def pairing_done(self, dev_id: str) -> None:
        self._pair_driver = None
        self.needs_pairing.discard(dev_id)
        self.pairing.update(state="done", prompt="Paired")
        self.status_changed()
        with contextlib.suppress(TvError):
            await self.ensure(dev_id)
        await asyncio.sleep(4)
        if self.pairing.get("state") == "done":
            self.pairing = {"state": "idle"}
            self.status_changed()

    async def cancel_pairing(self) -> None:
        drv, self._pair_driver = self._pair_driver, None
        if drv:
            with contextlib.suppress(Exception):
                await drv.close()
            self.drivers.pop(drv.id, None)
        self.pairing = {"state": "idle"}
        self.status_changed()

    # Adding / settings

    async def run_discovery(self, hosts: list[str] | None = None) -> list[dict]:
        if self.discovery["running"]:
            return self.discovery["found"]
        self.discovery = {"running": True, "found": self.discovery["found"], "at": None}
        self.status_changed()
        try:
            found = await discover(4, hosts, self.mdns)
        except Exception as e:
            found = []
            self.say(f"Discovery failed: {e}")
        for conf in self.devices().values():
            for c in found:
                if c["host"] == conf.get("host") and c["kind"] == conf["kind"]:
                    if c["uid"] != c["host"]:
                        conf.setdefault("uid", c["uid"])
                    if not conf.get("model"):
                        conf["model"] = c.get("model")
        self.save_config()
        known = {(d["kind"], d.get("uid")) for d in self.devices().values()}
        known_hosts = {d.get("host") for d in self.devices().values()}
        for c in found:
            c["added"] = (c["kind"], c["uid"]) in known or c["host"] in known_hosts
        if hosts is None:
            self.discovery = {"running": False, "found": found, "at": time.time()}
        else:
            merged = {c["host"]: c for c in self.discovery["found"]} | {c["host"]: c for c in found}
            self.discovery = {"running": False, "found": list(merged.values()), "at": time.time()}
        self.status_changed()
        return found

    async def add(self, candidate: dict, name: str | None = None) -> str:
        name = name or candidate.get("name") or candidate["host"]
        dev_id, n = slug(name), 2
        while dev_id in self.devices():
            dev_id, n = f"{slug(name)}-{n}", n + 1
        self.devices()[dev_id] = {
            "name": name, "kind": candidate["kind"], "host": candidate["host"],
            "uid": candidate.get("uid"), "model": candidate.get("model"),
        }
        if not self.config.get("default"):
            self.config["default"] = dev_id
        self.save_config()
        for c in self.discovery["found"]:
            if c["host"] == candidate["host"]:
                c["added"] = True
        self.status_changed()
        await self.start_pairing(dev_id)
        return dev_id

    async def remove(self, dev_id: str) -> None:
        drv = self.drivers.pop(dev_id, None)
        if drv:
            await drv.close()
        host = self.devices().pop(dev_id, {}).get("host")
        self.creds.pop(dev_id, None)
        save_json(CREDS_FILE, self.creds)
        for conf in self.devices().values():
            if conf.get("volume_via") == dev_id:
                conf.pop("volume_via")
        if self.config.get("default") == dev_id:
            self.config["default"] = next(iter(self.devices()), None)
        self.wanted.discard(dev_id)
        self.needs_pairing.discard(dev_id)
        for c in self.discovery["found"]:
            if c.get("host") == host:
                c["added"] = False
        self.save_config()
        self.status_changed()

    async def handle(self, msg: dict) -> None:
        op = msg.get("op", "send")
        dev = msg.get("device") or self.config.get("default")
        try:
            if op == "send":
                await self.send(dev, msg.get("cmds", []))
            elif op == "connect":
                await self.ensure(dev)
                await self.driver(dev).refresh()
            elif op == "discover":
                await self.run_discovery()
            elif op == "add":
                candidate = next((c for c in self.discovery["found"]
                                  if c.get("uid") == msg.get("uid") or c["host"] == msg.get("host")), None)
                if candidate is None and msg.get("host"):
                    found = await self.run_discovery([msg["host"]])
                    candidate = found[0] if found else None
                if candidate is None:
                    self.say("No supported device at this address")
                    return
                await self.add(candidate, msg.get("name"))
            elif op == "pair":
                await self.start_pairing(dev)
            elif op == "pair_code":
                await self.pairing_code(str(msg.get("code", "")))
            elif op == "pair_cancel":
                await self.cancel_pairing()
            elif op == "remove":
                await self.remove(dev)
            elif op == "rename":
                self.devices()[dev]["name"] = msg["name"]
                self.save_config()
            elif op == "default":
                self.config["default"] = dev
                self.wanted.add(dev)
                self.save_config()
                await self.ensure(dev)
            elif op == "volume_via":
                target = msg.get("target")
                if target and target in self.devices() and target != dev:
                    self.devices()[dev]["volume_via"] = target
                    await self.ensure(target)
                else:
                    self.devices()[dev].pop("volume_via", None)
                self.save_config()
            elif op == "voice":
                drv = await self.ensure(dev)
                self.say("Listening…", dev)
                await drv.voice(float(msg.get("seconds", 6)))
                self.say("", dev)
            elif op == "clear_message":
                self.message = ""
        except NeedsPairing:
            self.say(f"\"{self.devices()[dev].get('name', dev)}\" needs to be paired", dev)
        except TvError as e:
            self.say(str(e), dev)
        except Exception as e:  # a driver error must not stop the service
            print(f"{op} {dev}: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            self.say(f"Error: {e or type(e).__name__}", dev)
        finally:
            self.status_changed()

    async def keep_connected(self, stop: asyncio.Event) -> None:
        """Keep the useful connections open (default, volume target) and refresh state."""
        while not stop.is_set():
            default = self.config.get("default")
            wanted = set(self.wanted)
            if default:
                wanted.add(default)
                via = self.devices().get(default, {}).get("volume_via")
                if via:
                    wanted.add(via)
            for dev_id in wanted & set(self.devices()):
                if dev_id in self.needs_pairing:
                    continue
                with contextlib.suppress(TvError):
                    drv = await self.ensure(dev_id)
                    await drv.refresh()
            self.status_changed()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), 15)

    async def run(self) -> None:
        private_dir(RUN_DIR)
        with contextlib.suppress(FileExistsError):
            os.mkfifo(CMD_FIFO, 0o600)
        rfd = open_private(CMD_FIFO, os.O_RDONLY | os.O_NONBLOCK, stat.S_ISFIFO)
        wfd = open_private(CMD_FIFO, os.O_WRONLY, stat.S_ISFIFO)  # avoids EOF when no client is writing
        buffer = b""

        def on_command() -> None:
            nonlocal buffer
            buffer += os.read(rfd, 65536)
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                with contextlib.suppress(ValueError):
                    msg = json.loads(line)
                    if isinstance(msg, list):  # legacy format: [device, cmd...]
                        msg = {"op": "send", "device": msg[0], "cmds": msg[1:]}
                    self.loop.create_task(self.handle(msg))

        self.loop.add_reader(rfd, on_command)
        stop = asyncio.Event()
        self.loop.add_signal_handler(signal.SIGTERM, stop.set)
        self.loop.add_signal_handler(signal.SIGINT, stop.set)
        await self.mdns.start()
        self.write_status()
        keeper = self.loop.create_task(self.keep_connected(stop))
        try:
            await stop.wait()
        finally:
            keeper.cancel()  # stop now, even in the middle of a slow connection attempt
            self.loop.remove_reader(rfd)
            os.close(rfd)
            os.close(wfd)
            for drv in list(self.drivers.values()):
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(drv.close(), 3)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self.mdns.close(), 3)
            STATUS_FILE.unlink(missing_ok=True)


def systemd_managed() -> bool:
    """True when the user installed the systemd unit: let systemd own the service."""
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        return subprocess.run(["systemctl", "--user", "is-enabled", "--quiet", "omarchy-tv"],
                              timeout=5).returncode == 0
    return False


def run_daemon(ensure: bool) -> None:
    if ensure and "INVOCATION_ID" not in os.environ and systemd_managed():
        subprocess.run(["systemctl", "--user", "start", "omarchy-tv"], check=False)
        return
    lock = open_private(LOCK_FILE, os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        if ensure:
            return
        sys.exit("omarchy-tv: the service is already running")

    async def main() -> None:
        await Daemon().run()

    asyncio.run(main())


# --- Client (terminal, bar) -------------------------------------------------

def daemon_send(msg: dict, start: bool = True) -> None:
    for attempt in range(40):
        try:
            fd = open_private(CMD_FIFO, os.O_WRONLY | os.O_NONBLOCK, stat.S_ISFIFO)
        except OSError:
            if not start:
                raise TvError("the omarchy-tv service is not running")
            if attempt == 0:
                start_daemon()
            time.sleep(0.15)
            continue
        with os.fdopen(fd, "w") as fifo:
            fifo.write(json.dumps(msg, ensure_ascii=False) + "\n")
        return
    raise TvError("the omarchy-tv service does not start (see " + str(LOG_FILE) + ")")


def start_daemon() -> None:
    if systemd_managed():
        subprocess.run(["systemctl", "--user", "start", "omarchy-tv"], check=False)
        return
    with os.fdopen(open_private(LOG_FILE, os.O_WRONLY | os.O_APPEND | os.O_CREAT), "a") as log:
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "daemon", "--ensure"],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)


def read_status() -> dict:
    return load_json(STATUS_FILE, {})


def wait_status(pred, timeout: float) -> dict:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        st = read_status()
        if st and pred(st):
            return st
        time.sleep(0.2)
    return read_status()


def pairing_cli(before: float | None) -> None:
    """Follow the pairing started after `before` and ask for codes in the terminal."""
    st = wait_status(lambda s: s.get("pairing", {}).get("started", 0) != before, 15)
    seen = None
    while True:
        p = st.get("pairing", {})
        if p.get("started", 0) == before:
            sys.exit(st.get("message") or "Pairing did not start.")
        key = (p.get("state"), p.get("prompt"))
        if key != seen:
            seen = key
            state = p.get("state")
            if state == "waiting_code":
                try:
                    code = input(f"{p.get('prompt')} : ")
                except (EOFError, KeyboardInterrupt):
                    daemon_send({"op": "pair_cancel"})
                    sys.exit(1)
                daemon_send({"op": "pair_code", "code": code})
            elif state == "waiting_accept":
                print(p.get("prompt"), "…")
            elif state == "done":
                print(f"OK, \"{p.get('name')}\" is paired.")
                return
            elif state in ("error", "idle"):
                sys.exit(p.get("prompt") or "Pairing cancelled.")
        st = wait_status(lambda s, k=key: (s.get("pairing", {}).get("state"), s.get("pairing", {}).get("prompt")) != k, 90)


def pairing_started() -> float | None:
    return read_status().get("pairing", {}).get("started")


def print_discovery(found: list[dict]) -> None:
    if not found:
        print("No device found. Same Wi-Fi network? Otherwise: tv add <IP>")
    for i, c in enumerate(found, 1):
        mark = "  (already added)" if c.get("added") else ""
        print(f"  {i:2}. {c['name']:<22} {c['label']:<24} {c.get('model') or '':<22} {c['host']}{mark}")


def main() -> None:
    os.umask(0o077)  # keys and certificates written by the TV libraries stay private
    args = sys.argv[1:]
    first = args[0] if args else ""
    if first in ("-h", "--help", "help"):
        print(__doc__)
        return
    if first == "daemon":
        run_daemon("--ensure" in args)
        return
    if first == "op" and len(args) == 2:  # used by the bar plugin
        # "op -" reads the JSON request from stdin, so pairing codes and typed
        # text never appear in the process arguments (visible to other users).
        raw = sys.stdin.readline() if args[1] == "-" else args[1]
        daemon_send(json.loads(raw))
        return
    if first in ("discover", "scan"):
        before = read_status().get("discovery", {}).get("at")
        daemon_send({"op": "discover"})
        print("Searching the network…")
        st = wait_status(lambda s: s.get("discovery", {}).get("at") != before
                         and not s.get("discovery", {}).get("running"), 30)
        print_discovery(st.get("discovery", {}).get("found", []))
        return
    if first == "add" and len(args) >= 2:
        target, name = args[1], " ".join(args[2:]) or None
        found = read_status().get("discovery", {}).get("found", [])
        if target.isdigit() and 0 < int(target) <= len(found):
            msg = {"op": "add", "uid": found[int(target) - 1]["uid"], "host": found[int(target) - 1]["host"]}
        else:
            msg = {"op": "add", "host": target}
        before = pairing_started()
        daemon_send({**msg, "name": name})
        pairing_cli(before)
        return

    config = load_config()
    devices = config["devices"]
    if first == "list":
        for dev_id, d in devices.items():
            extra = f"  sound → {d['volume_via']}" if d.get("volume_via") else ""
            star = "  (default)" if dev_id == config.get("default") else ""
            print(f"  {dev_id:<12} {DRIVERS[d['kind']].label:<24} {d.get('host', ''):<15}{star}{extra}")
        print("\nKeys:", " ".join(ALL_KEYS))
        print("Settings: tv DEVICE rename NAME | tv DEVICE default | tv DEVICE remove |"
              " tv DEVICE volume-via OTHER|none")
        return

    dev_id = next((a for a in args if a in devices), config.get("default"))
    if dev_id in args:
        args.remove(dev_id)
    sub = args[0] if args else ""
    if sub and not devices and sub not in ("tui",):
        sys.exit("No device configured: run \"tv discover\", then \"tv add NUMBER\"")
    if sub == "pair":
        before = pairing_started()
        daemon_send({"op": "pair", "device": dev_id})
        pairing_cli(before)
    elif sub == "status":
        daemon_send({"op": "connect", "device": dev_id})
        st = wait_status(lambda s: s.get("devices", {}).get(dev_id, {}).get("connected"), 8)
        d = st.get("devices", {}).get(dev_id, {})
        print(f"{d.get('name', dev_id)} — {d.get('label')} {d.get('model') or ''} ({d.get('host')})")
        if d.get("connected"):
            power = {True: "on", False: "standby"}.get(d.get("on"), "?")
            print(f"  state  : {power}\n  app    : {d.get('app') or '?'}\n  volume : {d.get('volume') or 'not available'}")
        else:
            print(f"  unreachable: {d.get('error') or st.get('message') or '?'}")
    elif sub == "voice":
        daemon_send({"op": "voice", "device": dev_id, "seconds": 6})
        print("Listening… (6 s)")
    elif sub == "remove":
        daemon_send({"op": "remove", "device": dev_id})
    elif sub == "rename" and len(args) >= 2:
        daemon_send({"op": "rename", "device": dev_id, "name": " ".join(args[1:])})
    elif sub == "default":
        daemon_send({"op": "default", "device": dev_id})
    elif sub == "volume-via" and len(args) == 2:
        daemon_send({"op": "volume_via", "device": dev_id, "target": None if args[1] == "none" else args[1]})
    elif args:
        daemon_send({"op": "send", "device": dev_id, "cmds": args})
    elif not sys.stdin.isatty():
        print(__doc__)
    else:
        from omarchy_tv_tui import run_tui
        run_tui(dev_id)


if __name__ == "__main__":
    try:
        main()
    except TvError as e:
        sys.exit(f"omarchy-tv: {e}")
    except KeyboardInterrupt:
        pass
