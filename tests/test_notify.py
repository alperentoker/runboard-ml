"""Windows notifications when a run ends: once per start of a run, worded in the dashboard's language, from the
runtime's own loop (so no page has to be open); the switch and the language on the System page."""
import os

import pytest
import yaml
from fastapi.testclient import TestClient

from runboard import home, notify
from runboard.backends import BACKENDS
from runboard.backends.base import Backend
from runboard.runtime import Runtime


class Ending(Backend):
    """A backend whose runs report the states it is told."""
    name = "ending"
    label = "Ending"

    def __init__(self):
        self.state = ("RUNNING", None)

    def submit(self, project, run_id, info):
        return {"pid": 1, "url": None}

    def status(self, project, run_id, st):
        return self.state

    def final_log(self, project, run_id, st):
        return []

    def fetch(self, project, run_id, st):
        (project.root / "out" / run_id).mkdir(parents=True, exist_ok=True)
        (project.root / "out" / run_id / "summary.json").write_text('{"map": 55.06}')


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    monkeypatch.setattr(home, "CONFIG", tmp_path / ".rb" / "config.yaml")
    home.save_config({"projects": [], "port": 8000, "lang": "tr"})
    b = Ending()
    monkeypatch.setitem(BACKENDS, "ending", b)
    (tmp_path / "runs.yaml").write_text("runs:\n  R7: {x: 1}\n")
    (tmp_path / "runboard.yaml").write_text(yaml.safe_dump({
        "name": "G2A", "runs": {"file": "runs.yaml"}, "backends": {"ending": {"output_dir": "out"}},
        "results": {"report": "{out}/summary.json", "metrics": {"primary": "map"}, "labels": {"primary": "val mAP"}}}))
    shown = []
    monkeypatch.setattr(notify, "available", lambda: True)
    monkeypatch.setattr(notify, "show", lambda title, body, url=None: shown.append((title, body, url)))
    rt = Runtime()
    p = rt.add_project(tmp_path)
    p.state.update("R7", status="RUNNING", backend="ending", pushed_at="2026-11-04T10:00:00")
    return rt, p, b, shown


def settle(rt):
    """One poll, and the collection it may have started in the background."""
    import time
    rt.poll_once()
    end = time.time() + 10
    while rt._collecting and time.time() < end:
        time.sleep(0.05)


def test_a_finished_run_is_told_once_with_its_score(rig):
    rt, p, b, shown = rig
    rt.poll_once()
    assert shown == []  # still running
    b.state = ("COMPLETE", None)
    settle(rt)
    assert len(shown) == 1
    title, body, url = shown[0]
    assert title == "R7 bitti" and body == "G2A · val mAP 55.06" and url.endswith("#/p/" + p.key + "/run/R7")
    settle(rt)
    assert len(shown) == 1


def test_a_failed_run_is_told_at_once_and_only_once(rig):
    rt, p, b, shown = rig
    b.state = ("ERROR", "exit code 3")
    rt.poll_once()
    rt.poll_once()
    assert shown == [("R7 hata verdi", "G2A · exit code 3", shown[0][2])]


def test_a_new_start_is_told_again_and_the_switch_turns_it_off(rig):
    rt, p, b, shown = rig
    notify.run_ended(p, "R7", "ERROR", "x")
    notify.run_ended(p, "R7", "ERROR", "x")
    p.state.update("R7", pushed_at="2026-11-04T12:00:00")  # started again
    notify.run_ended(p, "R7", "ERROR", "x")
    assert len(shown) == 2
    cfg = home.config()
    cfg["notify"] = False
    home.save_config(cfg)
    p.state.update("R7", pushed_at="2026-11-04T13:00:00")
    notify.run_ended(p, "R7", "ERROR", "x")
    assert len(shown) == 2


def test_the_switch_and_the_language_on_the_system_page(rig):
    from runboard import server
    c = TestClient(server.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    assert c.post("/api/system/lang", json={"lang": "en"}).json() == {"lang": "en"}
    assert c.post("/api/system/lang", json={"lang": "xx"}).json() == {"lang": "en"}  # only languages the page has
    assert c.post("/api/system/notify", json={"on": False}).json() == {"notify": False}
    assert c.get("/api/system").json()["notify"] is False
    _, _, _, shown = rig
    c.post("/api/system/notify", json={"on": True, "test": True})
    assert shown[-1][0] == "runboard notifications are on"


@pytest.mark.skipif(os.name != "nt" or not os.environ.get("CI"), reason="shows a real toast: Windows CI only")
def test_a_real_toast_is_accepted_by_windows():
    p = notify.show("runboard test", "a toast from the test suite, with ' quotes & signs", "http://localhost:8000/")
    _, err = p.communicate(timeout=60)
    assert p.returncode == 0, err
