# Changelog

## 0.3.0
- Renamed to **Universal TV Remote**.
- Fire TV and other Android devices over ADB (pure Python, no `adb` binary).
- Now playing (title, artist, progress) for Cast sessions and Apple TV.
- Floating window that stays on top on every workspace.
- Dependencies pinned and hash-checked; installed only after you press Install.
- Discovery also uses the Cast setup API, so names and models show up even
  when mDNS is slow to answer.

## 0.2.0
- Generic plugin: device discovery, pairing from the popup, per-device settings.
- Apple TV, Samsung (Tizen), LG (webOS), Roku and plain Chromecast drivers.
- Remote tailored to the device kind (Google TV, Apple TV, classic TV, Cast).
- Single service shared by the bar, the popup and the terminal.
- English interface.

## 0.1.0
- Google TV / Android TV remote in the bar.
