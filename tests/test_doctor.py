"""runboard doctor: a report to paste into an issue, with nothing personal in it."""
import getpass
import os
from pathlib import Path

import yaml

from runboard import doctor, home


def test_the_report_hides_what_is_personal(tmp_path, monkeypatch):
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    monkeypatch.setattr(home, "CONFIG", tmp_path / ".rb" / "config.yaml")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "users" / "ayse"))
    monkeypatch.setattr(getpass, "getuser", lambda: "ayse")
    good, bad = tmp_path / "users" / "ayse" / "proj", tmp_path / "users" / "ayse" / "broken"
    for p in (good, bad):
        p.mkdir(parents=True)
        (p / "runs.yaml").write_text("runs:\n  a: {x: 1}\n")
        (p / "runboard.yaml").write_text(yaml.safe_dump({"name": p.name, "id": p.name, "runs": {"file": "runs.yaml"},
                                                        "backends": {"local": {"command": "echo"}}}))
    (bad / "runboard.yaml").write_text("name: [x\n")
    home.save_config({"projects": [str(good), str(bad)], "port": 8000, "lan": True, "lang": "tr", "secret_thing": "x"})
    folder = str(tmp_path / "users" / "ayse")
    (home.HOME / "server.log").write_text(
        f"started from {Path(folder) / 'proj'}\n"
        "tablet: http://192.168.1.104:8000 and http://127.0.0.1:8000\n"
        "token=KGAT_abcdefghijklmnop api_key: 123456789abc\n"
        "mail ayse.yilmaz@example.com, user ayse here\n", encoding="utf-8")
    r = doctor.report()
    assert "### runboard doctor" in r and "settings: port 8000, lan True, lang tr" in r
    assert "secret_thing" not in r  # only the settings worth knowing
    assert "proj: manifest v1, no plan.yaml, 1 runs, backends local" in r
    assert "broken: cannot be read: ParserError" in r
    for personal in (folder, "192.168.1.104", "KGAT_abcdefghijklmnop", "123456789abc", "ayse.yilmaz@example.com", " ayse "):
        assert personal not in r, personal
    assert f"~{os.sep}proj" in r and "127.0.0.1:8000" in r and "<ip>" in r and "<e-mail>" in r and "<user>" in r


def test_the_command_runs(capsys, tmp_path, monkeypatch):
    from runboard.cli import main
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    monkeypatch.setattr(home, "CONFIG", tmp_path / ".rb" / "config.yaml")
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "Paste this into the issue" in out and "**Backends**" in out and "- none" in out
