import pytest
import yaml

from runboard import home
from runboard.backends import BACKENDS
from runboard.backends.base import Backend
from runboard.project import Project
from runboard.runtime import Runtime


class Fake(Backend):
    name = "fake"
    label = "Fake"

    def __init__(self):
        self.calls = 0
        self.fail = False

    def submit(self, project, run_id, info):
        self.calls += 1
        if self.fail:
            raise RuntimeError("boom")
        return {"pid": 4321, "url": None}  # same keys the real backends return


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    monkeypatch.setattr(home, "CONFIG", tmp_path / ".rb" / "config.yaml")
    fake = Fake()
    monkeypatch.setitem(BACKENDS, "fake", fake)
    (tmp_path / "runs.yaml").write_text("runs:\n  a: {x: 1}\n  b: {x: 2}\n")
    (tmp_path / "runboard.yaml").write_text(yaml.safe_dump({"name": "T", "runs": {"file": "runs.yaml"}, "backends": {"fake": {}}}))
    rt = Runtime()
    p = rt.add_project(tmp_path)
    return rt, p, fake


def test_start_records_once_and_blocks_second(setup):
    rt, p, fake = setup
    rt.start(p, "a", "fake")
    st = p.state.get("a")
    assert st["status"] == "QUEUED" and st["pid"] == 4321 and st["backend"] == "fake"
    with pytest.raises(ValueError, match="busy"):
        rt.start(p, "b", "fake")
    assert fake.calls == 1 and p.state.get("b") == {}


def test_failed_launch_restores_previous_record(setup):
    rt, p, fake = setup
    p.state.update("a", status="COMPLETE", backend="fake", note="old")
    fake.fail = True
    with pytest.raises(RuntimeError):
        rt.start(p, "a", "fake")
    assert p.state.get("a") == {"status": "COMPLETE", "backend": "fake", "note": "old"}
    with pytest.raises(RuntimeError):
        rt.start(p, "b", "fake")
    assert p.state.get("b") == {}


def test_queue_starts_one_per_free_backend_in_order(setup):
    rt, p, fake = setup
    rt.backend_info["fake"] = {"ok": True}
    rt.enqueue(p, "a", "fake")
    rt.enqueue(p, "b", "fake")
    with pytest.raises(ValueError, match="already queued"):
        rt.enqueue(p, "b", "fake")
    assert rt.run_queue() == [f"{p.key}:a"] and [e["run"] for e in rt.queue()] == ["b"]
    assert rt.run_queue() == [] and rt.queue()[0]["waiting"] == "busy"  # a is still running
    p.state.update("a", status="COMPLETE")
    assert rt.run_queue() == [f"{p.key}:b"] and rt.queue() == [] and fake.calls == 2


def test_queue_order_and_failures(setup):
    rt, p, fake = setup
    rt.backend_info["fake"] = {"ok": True}
    ea, eb = rt.enqueue(p, "a", "fake"), rt.enqueue(p, "b", "fake")
    rt.move(eb["id"], -1)
    assert [e["run"] for e in rt.queue()] == ["b", "a"]
    fake.fail = True
    assert rt.run_queue() == []
    q = rt.queue()
    assert q[0]["waiting"].startswith("error") and q[1]["waiting"] == "busy" and p.state.get("b") == {}
    rt.dequeue(eb["id"])
    assert [e["run"] for e in rt.queue()] == ["a"]


def test_queue_waits_for_kaggle_quota(setup, monkeypatch):
    rt, p, fake = setup
    monkeypatch.setitem(BACKENDS, "kaggle", fake)
    (p.root / "runboard.yaml").write_text(yaml.safe_dump({"name": "T", "runs": {"file": "runs.yaml"}, "backends": {"kaggle": {}}}))
    monkeypatch.setattr(Runtime, "estimate_hours", staticmethod(lambda project, run_id: 5.0))
    rt.backend_info["kaggle"] = {"ok": True, "quota": {"used_h": 27.0, "total_h": 30.0}}
    rt.enqueue(rt.project(p.key), "a", "kaggle")
    assert rt.run_queue() == [] and rt.queue()[0]["waiting"] == "quota" and fake.calls == 0
    rt.backend_info["kaggle"]["quota"]["used_h"] = 2.0  # the weekly quota came back
    assert rt.run_queue() == [f"{p.key}:a"]


def test_a_run_gone_from_the_plan_does_not_hold_up_the_queue(setup):
    rt, p, fake = setup
    rt.backend_info["fake"] = {"ok": True}
    rt.enqueue(p, "a", "fake")
    rt.enqueue(p, "b", "fake")
    (p.root / "runs.yaml").write_text("runs:\n  b: {x: 2}\n")  # a was removed from the plan by hand
    assert rt.run_queue() == [f"{p.key}:b"] and rt.queue()[0]["waiting"] == "missing"
    rt.forget(p.key, "a")
    assert rt.queue() == []
