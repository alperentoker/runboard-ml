"""Edge cases found in review: each test fails on the code before its fix."""
import hashlib
import json
import os
import subprocess
import sys
import threading

import pytest
import yaml

from runboard import home


@pytest.fixture
def rb(tmp_path, monkeypatch):
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    monkeypatch.setattr(home, "CONFIG", tmp_path / ".rb" / "config.yaml")
    return tmp_path


def make(root, runs="runs:\n  a: {x: 1}\n", fields=None, **manifest):
    (root / "runs.yaml").write_text(runs, encoding="utf-8")
    plan = {"file": "runs.yaml", **({"fields": fields} if fields else {})}
    (root / "runboard.yaml").write_text(yaml.safe_dump({"name": "T", "runs": plan, **manifest}), encoding="utf-8")
    from runboard.project import Project
    return Project(root)


# ---------------------------------------------------------------- QR code (pairing)

def test_qr_matrix_is_a_readable_qr_code():
    from runboard import qr
    text = "http://192.168.1.20:8000/pair?c=123456"
    m = qr.matrix(text)
    # the exact modules, so a change to the encoder shows up even where no decoder is installed
    bits = "".join("1" if v else "0" for row in m for v in row)
    assert len(m) == 29 and hashlib.sha256(bits.encode()).hexdigest()[:16] == GOLDEN
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    for t in (text, "ABC", "https://example.com/" + "x" * 60):
        img = np.kron(1 - np.pad(np.array(qr.matrix(t), dtype=np.uint8), 4), np.ones((8, 8), np.uint8)) * 255
        assert cv2.QRCodeDetector().detectAndDecode(img)[0] == t


GOLDEN = "49ad31ee49b8bc69"  # sha256 of the modules; the encoder was checked with OpenCV when this was set


# ---------------------------------------------------------------- plan edits

def test_decision_value_is_written_as_yaml(rb):
    runs = 'runs:\n  a: {model: "x: y"}\n  b: {model: null}\n'
    p = make(rb, runs, ["model"],
             decisions=[{"id": "D", "candidates": ["a"], "field": "model"}],
             results={"report": "out/{id}.json", "metrics": {"primary": "s"}})
    (rb / "out").mkdir()
    (rb / "out" / "a.json").write_text(json.dumps({"s": 1}))
    p.decide("D", "x: y", "the only candidate there is")
    assert yaml.safe_load(p.runs_file.read_text(encoding="utf-8"))["runs"]["b"]["model"] == "x: y"


def test_render_reads_yaml_values_and_python_is_the_configured_one(rb, monkeypatch):
    (rb / "cfg.yaml").write_text("train: {lr: 0.01}\n")
    p = make(rb, backends={"local": {"command": '"{python}" -u t.py --lr {yaml:cfg.yaml:train.lr}',
                                     "python": "C:/envs/train/python.exe"}})
    from runboard.backends import local
    seen = {}
    monkeypatch.setattr(local, "popen_detached", lambda args, **kw: seen.setdefault("args", args) and
                        type("P", (), {"pid": 1})())
    out = local.LocalBackend().submit(p, "a", p.info("a"))
    assert out["command"] == '"C:/envs/train/python.exe" -u t.py --lr 0.01'


# ---------------------------------------------------------------- server

def test_cancel_unstarted_run_and_logo_outside_the_project(rb):
    from fastapi.testclient import TestClient

    from runboard import server
    secret = rb / "secret.txt"
    secret.write_text("x")
    proj = rb / "proj"
    proj.mkdir()
    make(proj, logo="../secret.txt")
    home.register(proj)
    c = TestClient(server.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    key = next(iter(server.rt.projects()))
    r = c.post(f"/api/p/{key}/cancel/a")
    assert r.status_code == 400 and r.json()["code"] == "not_launched"
    assert c.get(f"/api/p/{key}/logo").status_code == 404


def test_unknown_error_code_does_not_crash():
    from runboard.errors import Invalid
    assert str(Invalid("no_such_code")) == "no_such_code"


# ---------------------------------------------------------------- processes

def test_a_process_that_exited_with_259_is_not_alive():
    from runboard.proc import pid_alive
    p = subprocess.Popen([sys.executable, "-c", "raise SystemExit(259)"])
    p.wait()
    assert p.returncode == 259 and not pid_alive(p.pid)  # our handle keeps the process object around
    assert pid_alive(os.getpid())


def test_only_one_watchdog_claims_the_pid_file(tmp_path):
    from runboard.watch import _claim
    f = tmp_path / "watch.pid"
    assert _claim(f) and _claim(f)  # we hold it
    f.write_text("999999")  # left by a watchdog that died
    assert _claim(f) and f.read_text() == str(os.getpid())
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        f.write_text(str(p.pid))  # a live one holds it
        assert not _claim(f) and f.read_text() == str(p.pid)
    finally:
        p.kill()


def test_localrun_writes_log_heartbeat_and_exit_code(tmp_path):
    log, code, alive = tmp_path / "a.log", tmp_path / "a.code", tmp_path / "a.alive"
    cmd = f'"{sys.executable}" -c "print(\'hello\'); raise SystemExit(3)"'
    r = subprocess.run([sys.executable, "-m", "runboard.localrun", str(log), str(code), str(alive), sys.executable, cmd],
                       timeout=60)
    assert r.returncode == 3 and code.read_text() == "3" and alive.exists()
    assert "hello" in log.read_text(encoding="utf-8")


def test_kaggle_log_stream_stops_when_told(monkeypatch):
    from runboard.backends import kaggle

    def endless(ref):
        while True:
            yield {"data": "line\n"}

    monkeypatch.setattr(kaggle, "api", lambda: type("A", (), {"kernels_logs_stream": staticmethod(endless)})())
    monkeypatch.setattr(kaggle.KaggleBackend, "ref", lambda self, *a, **k: "u/k")
    sink, left = [], iter([True, True, False])
    kaggle.KaggleBackend().stream(None, "a", {}, sink, lambda: next(left))
    assert sink == ["line", "line"]


# ---------------------------------------------------------------- runtime

def test_starting_a_queued_run_does_not_lock_the_queue(rb, monkeypatch):
    from runboard.backends import BACKENDS
    from runboard.backends.base import Backend
    from runboard.runtime import Runtime
    rt = Runtime()

    class Slow(Backend):
        name, label = "slow", "Slow"

        def submit(self, project, run_id, info):
            free = rt.queue_lock.acquire(timeout=2)  # a request adding to the queue meanwhile
            if free:
                rt.queue_lock.release()
            seen.append(free)
            return {"pid": 1, "url": None}

    seen = []
    monkeypatch.setitem(BACKENDS, "slow", Slow())
    p = make(rb, "runs:\n  a: {x: 1}\n  b: {x: 2}\n", backends={"slow": {}})
    p = rt.add_project(rb)
    rt.backend_info["slow"] = {"ok": True}
    rt.enqueue(p, "a", "slow")
    rt.enqueue(p, "b", "slow")
    assert rt.run_queue() == [f"{p.key}:a"] and seen == [True]
    assert [(e["run"], e["waiting"]) for e in rt.queue()] == [("b", "busy")]


def test_an_unchanged_record_is_not_written_again(rb):
    st = home.State("x")
    st.update("a", status="RUNNING")
    before = st.file.stat().st_mtime_ns
    st.update("a", status="RUNNING")
    assert st.file.stat().st_mtime_ns == before
    st.update("a", status="COMPLETE")
    assert st.get("a")["status"] == "COMPLETE"


# ---------------------------------------------------------------- command line

def test_cli_add_list_remove(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "runs.yaml").write_text("runs:\n  a: {x: 1}\n")
    (proj / "runboard.yaml").write_text("name: T\nruns: {file: runs.yaml}\n")
    env = {**os.environ, "RUNBOARD_HOME": str(tmp_path / ".rb")}
    run = lambda *a: subprocess.run([sys.executable, "-m", "runboard", *a], env=env, capture_output=True, text=True,
                                    timeout=60)
    assert run("add", str(proj)).returncode == 0
    assert str(proj.resolve()) in run("list").stdout
    assert run("remove", str(proj)).returncode == 0
    assert run("list").stdout.strip() == ""
