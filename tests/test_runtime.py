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


def test_local_run_survives_a_sleeping_computer(tmp_path, monkeypatch):
    """A stale heartbeat alone is not death: while the runner process lives the run is running, and a run that was
    marked lost is picked up again."""
    import os
    import time as _t
    from runboard.backends.local import LocalBackend
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    (tmp_path / "runs.yaml").write_text("runs:\n  a: {x: 1}\n")
    (tmp_path / "runboard.yaml").write_text(yaml.safe_dump({"name": "T", "runs": {"file": "runs.yaml"}, "backends": {"local": {"command": "x"}}}))
    p = Project(tmp_path)
    b = LocalBackend()
    log, code, alive = b._files(p, "a")
    alive.touch()
    old = _t.time() - 600
    os.utime(alive, (old, old))  # the heartbeat stopped 10 minutes ago
    assert b.status(p, "a", {"pid": os.getpid()}) == ("RUNNING", None)  # but the runner (here: us) still lives
    assert b.status(p, "a", {"pid": 999999})[0] == "ERROR"
    assert b.may_still_run(p, "a", {"pid": os.getpid(), "status": "ERROR"})
    code.write_text("0")
    assert not b.may_still_run(p, "a", {"pid": os.getpid()}) and b.status(p, "a", {})[0] == "COMPLETE"


def test_watchdog_restarts_only_after_a_real_outage():
    from runboard.watch import check
    st = {}
    assert not check(st, busy=True)
    assert not check(st, busy=False)  # one missed look: a restart in progress, not an outage
    assert not check(st, busy=True)
    assert not check(st, busy=False)
    assert check(st, busy=False)  # 20 s without an answer: start it again
    assert not check(st, busy=False) and not check(st, busy=False)  # and give it time to come up


def test_resume_needs_a_stopped_run_and_a_resume_command(tmp_path, monkeypatch):
    import json as _json
    from runboard.backends.kaggle import KaggleBackend
    from runboard.backends.local import LocalBackend
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    (tmp_path / "runs.yaml").write_text("runs:\n  a: {x: 1}\n")
    (tmp_path / "train.py").write_text("print(1)\n")
    (tmp_path / "runboard.yaml").write_text(yaml.safe_dump({"name": "T", "runs": {"file": "runs.yaml", "name": "{id}-x"}, "backends": {
        "local": {"command": "train {id}", "resume": "train {id} --resume {resume}", "output_dir": "out"},
        "kaggle": {"command": "python train.py {id}", "resume": "python train.py {id} --resume {resume}", "files": {"train.py": "train.py"}}}}))
    p = Project(tmp_path)
    info = p.info("a")
    loc = LocalBackend()
    with pytest.raises(ValueError, match="stopped"):
        loc.resume_info(p, "a", {"status": "RUNNING", "backend": "local"}, info)
    with pytest.raises(ValueError, match="not found"):
        loc.resume_info(p, "a", {"status": "ERROR", "backend": "local"}, info)
    (tmp_path / "out" / "a-x").mkdir(parents=True)
    assert loc.resume_info(p, "a", {"status": "ERROR", "backend": "local"}, info)["resume"].endswith("a-x")

    kg = KaggleBackend()
    r = kg.resume_info(p, "a", {"status": "ERROR", "backend": "kaggle", "kernel": "t-a"}, info)
    assert r == {"resume": "/kaggle/input/t-a/a-x", "_kernel": "t-a-r2", "_from_kernel": "t-a"}
    kg.build(p, "a", {**info, **r}, tmp_path / "push", "me")
    meta = _json.loads((tmp_path / "push" / "kernel-metadata.json").read_text())
    assert meta["id"] == "me/t-a-r2" and meta["kernel_sources"] == ["me/t-a"]
    assert "--resume /kaggle/input/t-a/a-x" in (tmp_path / "push" / "run.py").read_text()


def test_resumed_attempt_keeps_the_settings_it_started_with(setup, monkeypatch):
    rt, p, fake = setup
    fake._resume_info = lambda project, run_id, st, info: {"resume": "/prev/out"}
    (p.root / "runboard.yaml").write_text(yaml.safe_dump({"name": "T", "runs": {"file": "runs.yaml"}, "backends": {"fake": {"resume": "go --resume {resume}"}}}))
    p = rt.project(p.key)
    p.state.set("a", {"status": "ERROR", "backend": "fake", "spec": {"x": 1, "id": "a"}})
    (p.root / "runs.yaml").write_text("runs:\n  a: {x: 5}\n  b: {x: 2}\n")  # edited after it ran
    rt.start(p, "a", "fake", resume=True)
    st = p.state.get("a")
    assert st["resumed_from"] == "/prev/out" and st["attempt"] == 2 and st["spec"] == {"x": 1, "id": "a"}


def test_running_log_survives_a_restart(setup):
    rt, p, fake = setup
    p.state.set("a", {"status": "RUNNING", "backend": "fake"})
    rt.logs[(p.key, "a")] = [f"line {i}" for i in range(50)]
    rt._checkpoint_log(p, "a")
    fresh = Runtime()  # the dashboard restarted: nothing in memory yet
    assert fresh.log(p, "a") == [f"line {i}" for i in range(50)]
    fresh.logs[(p.key, "a")] = ["line 0", "line 1"]  # the stream is replaying from the start
    fresh._checkpoint_log(p, "a")
    assert len(fresh.log(p, "a")) == 50  # the longer saved copy wins and is not overwritten


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows jobs")
def test_detached_process_outlives_the_job_of_the_app_that_started_it():
    # An app (an editor, an AI assistant) holds its children in a job that ends them all when it closes; the
    # dashboard and local runs started from such a terminal must keep running.
    import ctypes
    import subprocess
    import sys
    from ctypes import wintypes

    from runboard.proc import pid_alive, stop_pid

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.OpenProcess.restype = wintypes.HANDLE

    class Limits(ctypes.Structure):  # JOBOBJECT_EXTENDED_LIMIT_INFORMATION
        _fields_ = [("times", ctypes.c_int64 * 2), ("flags", wintypes.DWORD), ("ws", ctypes.c_size_t * 2),
                    ("procs", wintypes.DWORD), ("affinity", ctypes.c_size_t), ("cls", wintypes.DWORD * 2),
                    ("io", ctypes.c_uint64 * 6), ("memory", ctypes.c_size_t * 4)]

    job = k32.CreateJobObjectW(None, None)
    lim = Limits(flags=0x2000 | 0x800)  # KILL_ON_JOB_CLOSE | BREAKAWAY_OK, as such apps set it
    assert k32.SetInformationJobObject(wintypes.HANDLE(job), 9, ctypes.byref(lim), ctypes.sizeof(lim))
    app = subprocess.Popen([sys.executable, "-c", "import sys, time; from runboard.proc import popen_detached; "
                            "sys.stdin.readline(); p = popen_detached([sys.executable, '-c', 'import time; "
                            "time.sleep(60)']); print(p.pid, flush=True); time.sleep(60)"],
                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    handle = k32.OpenProcess(0x1F0FFF, False, app.pid)
    child = None
    try:
        assert k32.AssignProcessToJobObject(wintypes.HANDLE(job), wintypes.HANDLE(handle))
        app.stdin.write("go\n")
        app.stdin.flush()
        child = int(app.stdout.readline())
        k32.CloseHandle(wintypes.HANDLE(job))  # the app closes: everything still in its job ends
        job = None
        app.wait(10)
        assert pid_alive(child)
    finally:
        if job:
            k32.CloseHandle(wintypes.HANDLE(job))
        k32.CloseHandle(wintypes.HANDLE(handle))
        app.kill()
        if child:
            stop_pid(child)


def test_queue_needs_an_hour_of_quota_without_an_estimate(setup, monkeypatch):
    rt, p, fake = setup
    monkeypatch.setitem(BACKENDS, "kaggle", fake)
    (p.root / "runboard.yaml").write_text(yaml.safe_dump({"name": "T", "runs": {"file": "runs.yaml"}, "backends": {"kaggle": {}}}))
    monkeypatch.setattr(Runtime, "estimate_hours", staticmethod(lambda project, run_id: None))  # nothing finished yet
    rt.backend_info["kaggle"] = {"ok": True, "quota": {"used_h": 29.5, "total_h": 30.0}}
    rt.enqueue(rt.project(p.key), "a", "kaggle")
    assert rt.run_queue() == [] and rt.queue()[0]["waiting"] == "quota" and fake.calls == 0
    rt.backend_info["kaggle"]["quota"]["used_h"] = 20.0
    assert rt.run_queue() == [f"{p.key}:a"]


def test_queueing_several_runs_is_all_or_nothing(setup):
    rt, p, fake = setup
    rt.enqueue(p, "a", "fake")
    assert [e["run"] for e in rt.enqueue_many(p, ["a", "b"], "fake")] == ["b"]  # a was already waiting
    rt.dequeue(rt.queue()[1]["id"])
    with pytest.raises(ValueError, match="nope"):
        rt.enqueue_many(p, ["b", "nope"], "fake")
    assert [e["run"] for e in rt.queue()] == ["a"]  # b was not added either


def test_a_runner_that_died_before_writing_is_an_error(tmp_path, monkeypatch):
    from runboard.backends.local import LocalBackend
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    (tmp_path / "runs.yaml").write_text("runs:\n  a: {x: 1}\n")
    (tmp_path / "runboard.yaml").write_text(yaml.safe_dump({"name": "T", "runs": {"file": "runs.yaml"}, "backends": {"local": {"command": "x"}}}))
    p, b = Project(tmp_path), LocalBackend()
    assert b.status(p, "a", {})[0] == "STARTING"
    assert b.status(p, "a", {"pid": 999999}) == ("ERROR", "the runner exited before the run started")


def test_finished_logs_do_not_pile_up_in_memory(setup, monkeypatch):
    rt, p, _ = setup
    monkeypatch.setattr(Runtime, "KEEP_LOGS", 3)
    for i in range(6):
        rt.save_log(p, f"r{i}", [f"line {i}"])
        assert rt.log(p, f"r{i}") == [f"line {i}"]
    assert len(rt._files) == 3
    assert rt.log(p, "r0") == ["line 0"]  # read again from disk


def test_serve_and_stop_on_a_fresh_machine(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys
    env = {**os.environ, "RUNBOARD_HOME": str(tmp_path / "fresh")}
    r = subprocess.run([sys.executable, "-m", "runboard", "stop"], env=env, capture_output=True, text=True)
    assert r.returncode == 0 and "not running" in r.stdout
    from runboard import server
    monkeypatch.setattr(home, "HOME", tmp_path / "fresh2")
    monkeypatch.setattr(home, "CONFIG", tmp_path / "fresh2" / "config.yaml")
    monkeypatch.setattr(server, "port_busy", lambda p: True)  # stops right after the start checks
    server.serve()
    assert (tmp_path / "fresh2").is_dir()


def test_a_missing_kaggle_token_is_reported_not_fatal(monkeypatch):
    # newer Kaggle clients print a guide and call exit(1) when there is no token
    from kaggle.api.kaggle_api_extended import KaggleApi

    from runboard.backends.kaggle import KaggleBackend

    def no_token(self):
        print("Authentication required to call the Kaggle API.")
        exit(1)
    monkeypatch.setattr(KaggleApi, "authenticate", no_token)
    assert KaggleBackend().available() == (False, "no Kaggle token (~/.kaggle/access_token)")


def test_one_dashboard_per_home(tmp_path):
    """A second process cannot take the dashboard lock while the first holds it; once the first ends it can."""
    import subprocess
    import sys
    from runboard.proc import hold_lock
    lock = tmp_path / "server.lock"
    held = hold_lock(lock)
    assert held is not None
    probe = "import sys; from pathlib import Path; from runboard.proc import hold_lock; " \
            "sys.exit(0 if hold_lock(Path(sys.argv[1])) else 3)"
    assert subprocess.run([sys.executable, "-c", probe, str(lock)]).returncode == 3
    held.close()
    assert subprocess.run([sys.executable, "-c", probe, str(lock)]).returncode == 0


def _wait(fn, timeout=30):
    import time
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.2)
    return False


def test_a_job_outlives_the_dashboard(setup):
    """A job runs on its own: a dashboard started afterwards (a new Runtime) finds it running, follows its log and
    sees it end; its log and exit code are files, not memory of the process that started it."""
    import sys
    rt, p, _ = setup
    p.m["jobs"] = {"count": {"title": "Count", "cmd": f'"{sys.executable}" -u -c "import time; '
                                                       f'[print(i, flush=True) or time.sleep(0.4) for i in range(8)]"'}}
    job = rt.start_job(p, "count")
    assert job.status == "running" and (p.state.dir / "jobs" / "count.json").exists()
    assert _wait(lambda: len(job.view()["lines"]) >= 2)

    later = Runtime()  # the dashboard after a restart: it knows nothing in memory
    later.restore_jobs()
    again = later.jobs[(p.key, "count")]
    assert again is not job and again.status == "running"
    assert _wait(lambda: again.status == "ok")
    v = again.view()
    assert v["lines"] == [str(i) for i in range(8)] and v["code"] == 0 and v["title"] == "Count"
    later.restore_jobs()
    assert later.jobs[(p.key, "count")] is again  # a job it already knows is kept


def test_a_lost_job_says_so_and_a_new_one_can_start(setup):
    """No exit code, no heartbeat and no process (the computer was switched off): an error, not "running" forever."""
    import json
    import os
    import sys
    import time
    rt, p, _ = setup
    d = p.state.dir / "jobs"
    d.mkdir(parents=True)
    (d / "old.log").write_text("half way\n")
    (d / "old.alive").write_text("")
    long_ago = time.time() - 3600
    os.utime(d / "old.alive", (long_ago, long_ago))
    (d / "old.json").write_text(json.dumps({"key": "old", "title": "Old", "cwd": str(p.root), "started": long_ago - 60,
                                            "pid": 2 ** 22 + 7}))
    rt.restore_jobs()
    v = rt.jobs[(p.key, "old")].view()
    assert v["status"] == "error" and v["lines"][0] == "half way" and "without an exit code" in v["lines"][-1]
    assert v["seconds"] == 60
    p.m["jobs"] = {"quick": {"title": "Quick", "cmd": f'"{sys.executable}" -c "print(1)"'}}
    assert rt.start_job(p, "quick").status in ("running", "ok")  # a lost job does not block the next


def test_one_job_at_a_time_per_project(setup):
    import sys
    from runboard.errors import Busy
    rt, p, _ = setup
    p.m["jobs"] = {k: {"title": k, "cmd": f'"{sys.executable}" -c "import time; time.sleep(3)"'} for k in ("a", "b")}
    rt.start_job(p, "a")
    with pytest.raises(Busy):
        rt.start_job(p, "b")


def test_runboard_stop_ends_the_dashboard_alone(monkeypatch):
    """On Windows the dashboard's runs and jobs are its children; stopping it must not end them."""
    import subprocess
    from runboard import proc
    calls = []
    monkeypatch.setattr(proc.os, "name", "nt")
    monkeypatch.setattr(subprocess, "run", lambda args, **k: calls.append(args))
    proc.stop_pid(123, tree=False)
    proc.stop_pid(456)
    assert calls == [["taskkill", "/PID", "123", "/F"], ["taskkill", "/PID", "456", "/T", "/F"]]


def test_local_cancel_ends_the_run_and_everything_it_started(tmp_path, monkeypatch):
    """Cancelling a local run really stops it: the training process and a process it started itself."""
    import json
    import sys
    from runboard.backends.local import LocalBackend
    from runboard.proc import pid_alive
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    monkeypatch.setattr(home, "CONFIG", tmp_path / ".rb" / "config.yaml")
    (tmp_path / "runs.yaml").write_text("runs:\n  a: {x: 1}\n")
    (tmp_path / "train.py").write_text(
        "import json, os, subprocess, sys, time\n"
        "kid = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        "json.dump([os.getpid(), kid.pid], open('pids.json', 'w'))\n"
        "time.sleep(120)\n")
    (tmp_path / "runboard.yaml").write_text(yaml.safe_dump({"name": "T", "runs": {"file": "runs.yaml"},
                                                            "backends": {"local": {"command": '"{python}" -u train.py'}}}))
    p = Project(tmp_path)
    b = LocalBackend()
    st = b.submit(p, "a", p.info("a"))
    assert _wait(lambda: (tmp_path / "pids.json").exists())
    pids = json.loads((tmp_path / "pids.json").read_text())
    assert all(pid_alive(x) for x in pids)
    b.cancel(p, "a", st)
    assert _wait(lambda: not any(pid_alive(x) for x in pids), 20)
    assert _wait(lambda: b.status(p, "a", st)[0] == "CANCELLED", 20)


def test_a_job_starts_whatever_the_project_folder_holds(setup):
    """The runner of jobs and local runs is started by its file, isolated: a folder of the project named like
    runboard (or anything on the user's path) cannot replace it."""
    import sys
    rt, p, _ = setup
    fake = p.root / "runboard"
    fake.mkdir()
    (fake / "__init__.py").write_text("raise SystemExit('the project folder was imported instead of runboard')\n")
    p.m["jobs"] = {"hi": {"title": "Hi", "cmd": f'"{sys.executable}" -c "print(42)"'}}
    job = rt.start_job(p, "hi")
    assert _wait(lambda: job.status != "running")
    v = job.view()
    assert v["status"] == "ok" and v["lines"] == ["42"]
