"""Starting with the computer: what each system gets written, checked by that system's own tools where they exist
(systemd-analyze on Linux, plutil on macOS), and the switch on the System page."""
import os
import shutil
import subprocess
import sys

import pytest

from runboard import autostart


@pytest.fixture
def systemd(tmp_path, monkeypatch):
    monkeypatch.setattr(autostart, "kind", lambda: "systemd")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path / "config" / "systemd" / "user"


@pytest.mark.skipif(os.name == "nt", reason="the systemd link is a symlink, which Windows allows only to administrators")
def test_systemd_user_service_is_written_and_enabled(systemd):
    assert autostart.enabled() is False
    autostart.enable()
    unit, link = systemd / "runboard.service", systemd / "default.target.wants" / "runboard.service"
    assert autostart.enabled() is True and link.is_symlink() and link.resolve() == unit.resolve()
    text = unit.read_text()
    assert f"-m runboard serve" in text and "RUNBOARD_NO_WATCHDOG=1" in text and "Restart=on-failure" in text
    assert "WantedBy=default.target" in text
    if shutil.which("systemd-analyze"):  # the unit as systemd itself reads it
        r = subprocess.run(["systemd-analyze", "verify", "--user", str(unit)], capture_output=True, text=True)
        assert "runboard.service" not in r.stderr, r.stderr
    autostart.disable()
    assert autostart.enabled() is False and not unit.exists() and not link.is_symlink()


def test_launchd_agent(tmp_path, monkeypatch):
    monkeypatch.setattr(autostart, "kind", lambda: "launchd")
    monkeypatch.setattr(autostart.Path, "home", classmethod(lambda cls: tmp_path))
    autostart.enable()
    plist = tmp_path / "Library" / "LaunchAgents" / "io.github.runboard.plist"
    text = plist.read_text()
    assert autostart.enabled() is True and "<key>RunAtLoad</key><true/>" in text and "RUNBOARD_NO_WATCHDOG" in text
    assert f"<string>{sys.executable}</string><string>-m</string><string>runboard</string><string>serve</string>" in text
    if shutil.which("plutil"):  # macOS: the property list as Apple's own tool reads it
        assert subprocess.run(["plutil", "-lint", str(plist)], capture_output=True).returncode == 0
    import plistlib
    assert plistlib.loads(plist.read_bytes())["KeepAlive"] == {"SuccessfulExit": False}
    autostart.disable()
    assert autostart.enabled() is False


def test_windows_startup_script(tmp_path, monkeypatch):
    monkeypatch.setattr(autostart, "kind", lambda: "windows")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    autostart.enable()
    f = tmp_path / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "runboard.vbs"
    assert autostart.enabled() is True and f.read_bytes().count(b"\r\n") == 2 and b"\r\r" not in f.read_bytes()
    assert b"-m runboard serve" in f.read_bytes()
    autostart.disable()
    assert not f.exists()


def test_elsewhere_the_switch_is_not_offered(monkeypatch):
    monkeypatch.setattr(autostart, "kind", lambda: None)
    assert autostart.enabled() is None and autostart.files() == []


def test_a_service_manager_turns_the_watchdog_off(monkeypatch, tmp_path):
    from runboard import home, server
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    monkeypatch.setattr(home, "CONFIG", tmp_path / ".rb" / "config.yaml")
    monkeypatch.delenv("RUNBOARD_NO_WATCHDOG", raising=False)
    assert server.watchdog_wanted() is True
    monkeypatch.setenv("RUNBOARD_NO_WATCHDOG", "1")  # what the systemd service and the launchd agent set
    assert server.watchdog_wanted() is False
