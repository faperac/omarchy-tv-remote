# Changelog

## 0.3.1

- Hardened every file the remote writes. Config, credentials and runtime
  directories must be real directories owned by you (created 0700, tightened if
  looser). `config.json` / `credentials.json` are written to an exclusive
  `mkstemp` file and renamed over the target; `status.json`, the lock, the log
  and the command FIFO are opened with `O_NOFOLLOW` and checked by `fstat`
  (type and owner). The process runs with umask 077, so TV pairing keys are
  never briefly world-readable. Without `XDG_RUNTIME_DIR`, the runtime fallback
  `/tmp/omarchy-tv-<uid>` is refused if someone else created it.

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
