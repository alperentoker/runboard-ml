import json
import time

import pytest
import yaml

from runboard import home
from runboard.progress import Parser, log_lines
from runboard.project import Project

RUNS = """\
defaults:
  epochs: 50
  seed: 0

runs:
  base: {data: ground, model: small.pt}
  big: {data: ground, model: null}
"""
MANIFEST = {
    "name": "Demo", "id": "demo",
    "runs": {"file": "runs.yaml", "section": "runs", "defaults": "defaults", "fields": ["data", "model", "seed"],
             "required": ["model"], "name": "{id}-{data|upper}-{model|stem}-s{seed}", "locked": True,
             "extras": {"prefix": "X", "fields": {"data": {"choices": "$existing"}, "seed": {"int": [0, 9], "default": 0}}}},
    "results": {"report": "out/{name}.json", "metrics": {"primary": "score"}},
    "decisions": [{"id": "D1", "candidates": ["base"], "field": "model", "log": "decisions.md"}],
}


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    monkeypatch.setattr("runboard.home.HOME", tmp_path / ".rb")
    (tmp_path / "runs.yaml").write_text(RUNS, encoding="utf-8")
    (tmp_path / "runboard.yaml").write_text(yaml.safe_dump(MANIFEST), encoding="utf-8")
    return Project(tmp_path)


def test_info_and_names(proj):
    base, big = proj.info("base"), proj.info("big")
    assert base["name"] == "base-GROUND-small-s0" and base["ready"] and base["locked"]
    assert big["name"] is None and big["missing"] == ["model"]


def test_extras_roundtrip_keeps_file(proj):
    before = proj.runs_file.read_bytes()
    rid = proj.add_extra({"data": "ground", "seed": 3}, "a note # with hash")
    assert rid == "X1" and proj.info("X1")["extra"] and not proj.info("X1")["locked"]
    with pytest.raises(ValueError):
        proj.add_extra({"data": "nope"})
    with pytest.raises(ValueError):
        proj.add_extra({"data": "ground", "seed": 42})
    proj.remove_extra("X1")
    assert proj.runs_file.read_bytes() == before
    with pytest.raises(ValueError):
        proj.remove_extra("base")


def test_decision_needs_results_then_writes(proj):
    with pytest.raises(ValueError, match="finish"):
        proj.decide("D1", "small.pt", "because it is the only one")
    (proj.root / "out").mkdir()
    (proj.root / "out" / "base-GROUND-small-s0.json").write_text(json.dumps({"score": 51.2}))
    assert proj.metrics("base")["primary"] == 51.2
    with pytest.raises(ValueError, match="reason"):
        proj.decide("D1", "small.pt", "short")
    proj.decide("D1", "small.pt", "highest score, only candidate")
    assert proj.info("big")["model"] == "small.pt"
    assert "D1: small.pt" in (proj.root / "decisions.md").read_text(encoding="utf-8")


def test_protocol_events_and_dedup():
    now = time.time()
    lines = ["noise", "@@rb " + json.dumps({"t": "start", "epochs": 10, "batches": 100, "optimizer": "SGD", "lr0": 0.01}),
             "@@rb " + json.dumps({"t": "stage", "text": "Training · epoch 2/10", "epoch": 2, "ts": now - 20}),
             "@@rb " + json.dumps({"t": "epoch", "epoch": 1, "epochs": 10, "secs": 90, "metrics": {"map": 40.5}, "best": 40.5, "eta": now + 900}),
             "@@rb " + json.dumps({"t": "epoch", "epoch": 1, "epochs": 10, "secs": 90, "metrics": {"map": 40.5}}),
             "@@rb " + json.dumps({"t": "beat", "epoch": 2, "batch": 50, "batches": 100, "its": 5.0, "ts": now - 5})]
    p = Parser(None).parse(lines)
    assert p["epochs"] == 10 and p["optimizer"] == "SGD" and len(p["history"]) == 1
    assert p["epoch"] == 1 and p["best"] == 40.5 and p["batch"] == 50 and p["eta_at"] == pytest.approx(now + 900)
    assert Parser(None).human(lines) == ["noise"]


def test_text_patterns_with_clock():
    cfg = {"marker": "■", "clock": r"\[(?P<clock>\d\d:\d\d:\d\d)\]", "utc_offset": 0,
           "patterns": {"epoch": r"epoch (?P<epoch>\d+)/(?P<epochs>\d+) done \((?P<time>[\d:]+)\) · (?P<loss>.*?) · map (?P<map>[\d.]+)",
                        "eta": r"left ~(?P<left>[\d:]+)"}}
    p = Parser(cfg).parse(["■ [00:00:01] epoch 3/9 done (00:02:50) · box_loss 1.25 cls_loss 0.71 · map 48.95",
                           "■ [00:00:01] left ~01:00:00", "unmarked epoch 4/9 done (00:01:00) · x · map 1"])
    assert p["history"] == [{"e": 3, "map": 48.95, "box_loss": 1.25, "cls_loss": 0.71, "secs": 170}]
    assert p["eta_at"] is not None


def test_kaggle_log_blob_and_mojibake():
    blob = json.dumps([{"stream_name": "stdout", "time": 1, "data": "Eğitim başlıyor\r\n"},
                       {"stream_name": "stdout", "time": 2, "data": "0.00s - Debugger warning: frozen modules\n"}])
    assert log_lines(blob) == ["Eğitim başlıyor"]
    assert log_lines("Eğitim".encode("utf-8").decode("latin-1")) == ["Eğitim"]


def test_nan_never_reaches_json():
    import json
    from runboard.server import SafeJSON
    body = SafeJSON({"a": float("nan"), "b": [1.5, float("inf")], "c": {"d": -float("inf")}}).body
    assert json.loads(body) == {"a": None, "b": [1.5, None], "c": {"d": None}}


def test_delta_appends_or_restarts():
    from runboard.server import delta
    assert delta(None, ["a"]) is None
    assert delta([], ["a", "b"]) == ["a", "b"]  # a job that printed nothing yet continues, it does not start over
    assert delta(["a", "b"], ["a", "b", "c", "d"]) == ["c", "d"]
    assert delta(["a", "b"], ["b", "c"]) is None  # what was sent is no longer there: start over
    assert delta(["x", "a", "b"], ["a", "b", "c"]) is None  # tail of 3 no longer present → start over
    assert delta(["a", "b"], ["a", "b"]) == []
    assert delta(["a", "b"], ["new log"]) is None


def test_job_lines_stream_once(tmp_path):
    import sys
    from runboard import server
    from runboard.runtime import Job
    code = "import time\nfor i in range(6):\n    print('line', i, flush=True)\n    time.sleep(0.3)"
    job = Job("demo", "Demo", [sys.executable, "-c", code], tmp_path)
    server.rt.jobs[("demo-proj", "demo")] = job
    S, got = {}, []
    try:
        for _ in range(40):
            for name, body in server.events_once(S, "", "", False, False, "demo-proj"):
                if name == "job":
                    got.append(json.loads(body))
            if job.status != "running" and got and got[-1]["status"] != "running":
                break
            time.sleep(0.15)
    finally:
        server.rt.jobs.pop(("demo-proj", "demo"))
    lines = got[0]["lines"] + [ln for g in got[1:] for ln in g["lines"]]
    assert got[0]["reset"] and not any(g["reset"] for g in got[1:])
    assert lines == [f"line {i}" for i in range(6)] and got[-1]["status"] == "ok"


def test_every_error_has_a_turkish_text_with_the_same_values():
    import re
    from pathlib import Path
    from runboard.errors import MESSAGES
    page = (Path(__file__).parents[1] / "runboard" / "static" / "index.html").read_text(encoding="utf-8")
    block = page[page.index("const ERR_TR"):page.index("function errText")]
    tr = dict(re.findall(r'(?:^\s*|, )(\w+): "([^"]*)"', block, re.M))
    assert set(tr) == set(MESSAGES)
    for code, text in MESSAGES.items():
        assert set(re.findall(r"\{(\w+)\}", text)) == set(re.findall(r"\{(\w+)\}", tr[code])), code


def test_api_errors_carry_codes(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    monkeypatch.setattr(home, "CONFIG", tmp_path / ".rb" / "config.yaml")
    home.save_config({"projects": [], "port": 8000})
    from runboard import server
    c = TestClient(server.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 1))
    r = c.get("/api/p/nope/plan")
    assert r.status_code == 404 and r.json()["code"] == "unknown_project"
    r = c.post("/api/connections/kaggle", json={"token": "x"})
    assert r.status_code == 400 and r.json()["code"] == "bad_token"
    tablet = TestClient(server.app, base_url="http://192.168.1.9:8000", client=("192.168.1.9", 1))
    assert tablet.get("/api/projects").json()["code"] == "not_paired"
