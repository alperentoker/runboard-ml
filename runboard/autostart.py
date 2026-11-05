"""Start runboard when the computer starts (when its user signs in), the way each system does it.

- Windows: a script in the Startup folder that runs `runboard serve` without a window.
- Linux: a systemd user service (~/.config/systemd/user/runboard.service), enabled for the user's default target.
- macOS: a launchd agent (~/Library/LaunchAgents/io.github.runboard.plist) that runs at load.

Each is one file (and on Linux one link) in the user's own folders: switching it on or off needs no administrator and
starts or stops nothing now; it takes effect at the next sign-in. Under systemd and launchd the service manager
restarts a crashed dashboard, so runboard's own watchdog stays off there (RUNBOARD_NO_WATCHDOG).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from xml.sax.saxutils import escape

LABEL = "io.github.runboard"


def kind() -> str | None:
    return {"nt": "windows"}.get(os.name) or {"linux": "systemd", "darwin": "launchd"}.get(sys.platform)


def _python() -> str:
    if kind() == "windows":  # no console window at sign-in
        pyw = Path(sys.executable).with_name("pythonw.exe")
        return str(pyw if pyw.exists() else sys.executable)
    return sys.executable


def files() -> list[Path]:
    """What switching it on writes: the file itself first."""
    k = kind()
    if k == "windows":
        return [Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup/runboard.vbs"]
    if k == "systemd":
        d = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "systemd" / "user"
        return [d / "runboard.service", d / "default.target.wants" / "runboard.service"]
    if k == "launchd":
        return [Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"]
    return []


def text() -> str:
    k, py = kind(), _python()
    if k == "windows":
        return ('Set sh = CreateObject("WScript.Shell")\r\n'
                f'sh.Run """{py}"" -m runboard serve", 0, False\r\n')
    if k == "systemd":
        return ("[Unit]\nDescription=runboard dashboard\nAfter=network-online.target\n\n"
                "[Service]\nType=simple\n"
                f"ExecStart={_systemd_quote(py)} -m runboard serve\n"
                "Environment=RUNBOARD_NO_WATCHDOG=1\nRestart=on-failure\nRestartSec=10\n\n"
                "[Install]\nWantedBy=default.target\n")
    if k == "launchd":
        log = escape(str(Path.home() / ".runboard" / "launchd.log"))
        return ('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                '<plist version="1.0">\n<dict>\n'
                f"  <key>Label</key><string>{LABEL}</string>\n"
                "  <key>ProgramArguments</key><array>"
                f"<string>{escape(py)}</string><string>-m</string><string>runboard</string><string>serve</string></array>\n"
                "  <key>EnvironmentVariables</key><dict><key>RUNBOARD_NO_WATCHDOG</key><string>1</string></dict>\n"
                "  <key>RunAtLoad</key><true/>\n"
                "  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>\n"
                f"  <key>StandardOutPath</key><string>{log}</string>\n"
                f"  <key>StandardErrorPath</key><string>{log}</string>\n"
                "</dict>\n</plist>\n")
    return ""


def _systemd_quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"' if any(c in s for c in ' "\\') else s


def enabled() -> bool | None:
    """None where runboard does not know how to start with the computer."""
    fs = files()
    return all(f.exists() or f.is_symlink() for f in fs) if fs else None


def enable() -> None:
    fs = files()
    fs[0].parent.mkdir(parents=True, exist_ok=True)
    fs[0].write_text(text(), encoding="utf-8", newline="")
    if kind() == "systemd":  # what `systemctl --user enable` does, without needing the user's bus
        fs[1].parent.mkdir(parents=True, exist_ok=True)
        fs[1].unlink(missing_ok=True)
        fs[1].symlink_to(fs[0])


def disable() -> None:
    for f in reversed(files()):
        f.unlink(missing_ok=True)
