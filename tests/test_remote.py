"""SSH and SLURM backends (RB-6): what is sent, how states are read, one run per host, and a whole run end to end
through a stand-in ssh that runs commands with the local sh."""
import io
import os
import shutil
import sys
import tarfile
import time
from pathlib import Path

import pytest
import yaml

from runboard import home
from runboard.errors import Invalid

FAKE = str(Path(__file__).with_name("fake_ssh.py"))


def make(root, backends, runs="runs:\n  A: {seed: 0}\n  B: {seed: 1}\n"):
    root.mkdir(parents=True, exist_ok=True)
    (root / "runs.yaml").write_text(runs)
    (root / "train.py").write_text(
        "import sys, os, time, json\nrun = sys.argv[1]\nfor i in range(3):\n    print(f'epoch {i}', flush=True)\n"
        "    time.sleep(float(os.environ.get('NAP', '0')))\nos.makedirs(f'runs/{run}', exist_ok=True)\n"
        "json.dump({'map': 42.0}, open(f'runs/{run}/summary.json', 'w'))\nsys.exit(int(os.environ.get('FAIL', '0')))\n")
    (root / "data" / "images").mkdir(parents=True)
    (root / "data" / "images" / "big.txt").write_text("not code")
    (root / "runboard.yaml").write_text(yaml.safe_dump({"name": root.name, "runs": {"file": "runs.yaml", "name": "{id}"},
                                                        "backends": backends}))
    from runboard.project import Project
    return Project(root)


@pytest.fixture
def rb(tmp_path, monkeypatch):
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    monkeypatch.setattr(home, "CONFIG", tmp_path / ".rb" / "config.yaml")
    home.save_config({"projects": [], "port": 8000})
    return tmp_path


class Scripted:
    """Records commands and answers them from a list of (match, stdout, code)."""

    def __init__(self, answers=()):
        self.calls, self.answers = [], list(answers)

    def __call__(self, cmd, data=None, timeout=120):  # set on the class: not bound, no self of Remote
        self.calls.append((cmd, data))
        import subprocess
        for m, out, code in self.answers:
            if m in cmd:
                return subprocess.CompletedProcess([], code, out.encode(), b"boom" if code else b"")
        return subprocess.CompletedProcess([], 0, b"", b"")


# ---------------------------------------------------------------- what is sent and read

def test_ssh_submit_sends_the_code_and_starts_a_detached_run(rb, monkeypatch):
    from runboard.backends.remote import Remote, SSHBackend
    p = make(rb / "p", {"ssh": {"host": "gpu-box", "command": '"{python}" -u train.py {id}', "setup": ["pip install x"]}})
    fake = Scripted([("echo $!", "4242\n", 0)])
    monkeypatch.setattr(Remote, "run", fake)
    out = SSHBackend().submit(p, "A", p.info("A"))
    assert out == {"pid": 4242, "host": "gpu-box", "command": '"python3" -u train.py A', "url": None}
    (push, tar), (start, _) = fake.calls
    assert 'mkdir -p "$HOME"/runboard/p/.runboard && tar xzf - -C "$HOME"/runboard/p' == push
    names = tarfile.open(fileobj=io.BytesIO(tar)).getnames()
    assert "train.py" in names and "runs.yaml" in names and not any(n.startswith("data") for n in names)
    assert "; set -m; nohup sh -c" in start and "pip install x && ( \"python3\" -u train.py A ); echo $?" in start
    assert "< /dev/null &" in start


@pytest.mark.parametrize("out, state", [("0", ("COMPLETE", None)), ("3", ("ERROR", "exit code 3")), ("RUNNING", ("RUNNING", None)),
                                        ("cancelled", ("CANCELLED", None))])
def test_ssh_states(out, state):
    from runboard.backends.remote import SSHBackend
    assert SSHBackend.read_code(out) == state
    assert SSHBackend.read_code("LOST")[0] == "ERROR"


@pytest.mark.parametrize("out, state", [("PENDING|0:0", "QUEUED"), ("RUNNING|0:0", "RUNNING"), ("COMPLETED|0:0", "COMPLETE"),
                                        ("CANCELLED by 1000|0:15", "CANCELLED"), ("TIMEOUT|0:0", "ERROR"),
                                        ("OUT_OF_MEMORY|0:125", "ERROR"), ("", "QUEUED")])
def test_slurm_states(out, state):
    from runboard.backends.remote import SlurmBackend
    assert SlurmBackend.read_state(out)[0] == state
    assert "TIMEOUT" in (SlurmBackend.read_state("TIMEOUT|0:0")[1] or "")


def test_slurm_submits_a_batch_script(rb, monkeypatch):
    from runboard.backends.remote import Remote, SlurmBackend
    p = make(rb / "p", {"slurm": {"host": "login", "command": "python train.py {id}",
                                  "sbatch": {"partition": "gpu", "gres": "gpu:1", "time": "02:00:00"}}})
    fake = Scripted([("sbatch", "98765;cluster\n", 0)])
    monkeypatch.setattr(Remote, "run", fake)
    out = SlurmBackend().submit(p, "A", p.info("A"))
    assert out["job"] == 98765
    tar = tarfile.open(fileobj=io.BytesIO(fake.calls[0][1]))
    script = tar.extractfile(".runboard/A.sbatch").read().decode()
    assert "#SBATCH --partition=gpu" in script and "#SBATCH --gres=gpu:1" in script and "#SBATCH --job-name=rb-p-A" in script
    assert script.strip().endswith('echo $? > "$HOME"/runboard/p/.runboard/A.code')
    assert "sbatch --parsable --output=" in fake.calls[1][0]
    fake = Scripted([("sbatch", "nope", 0)])
    monkeypatch.setattr(Remote, "run", fake)
    with pytest.raises(Invalid):
        SlurmBackend().submit(p, "A", p.info("A"))


def test_a_failing_connection_says_why(rb, monkeypatch):
    from runboard.backends.remote import Remote, SSHBackend
    p = make(rb / "p", {"ssh": {"host": "gpu-box", "command": "x"}})
    monkeypatch.setattr(Remote, "run", Scripted([("", "", 255)]))
    with pytest.raises(Invalid) as e:
        SSHBackend().status(p, "A", {})
    assert e.value.code == "ssh_error" and e.value.params["host"] == "gpu-box"
    p2 = make(rb / "q", {"ssh": {"command": "x"}})
    with pytest.raises(Invalid) as e:
        SSHBackend().status(p2, "A", {})
    assert e.value.code == "remote_config"


def test_outputs_cannot_escape_the_target(tmp_path):
    from runboard.backends.remote import extract
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("../evil.txt")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(Invalid):
        extract(buf.getvalue(), tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists()


def test_one_run_per_host_and_none_for_a_cluster(rb, monkeypatch):
    from runboard.backends import BACKENDS
    from runboard.errors import Busy
    from runboard.runtime import Runtime
    for name in ("ssh", "slurm"):
        monkeypatch.setattr(BACKENDS[name], "submit", lambda *a: {"pid": 1, "url": None})
    rt = Runtime()
    a = rt.add_project(make(rb / "a", {"ssh": {"host": "box1", "command": "x"}, "slurm": {"host": "hpc", "command": "x"}}).root)
    b = rt.add_project(make(rb / "b", {"ssh": {"host": "box2", "command": "x"}}).root)
    rt.start(a, "A", "ssh")
    rt.start(b, "A", "ssh")  # another host: free
    with pytest.raises(Busy):
        rt.start(a, "B", "ssh")
    rt.start(a, "B", "slurm")
    assert a.state.get("B")["status"] == "QUEUED"


# ---------------------------------------------------------------- end to end through a stand-in ssh

needs_sh = pytest.mark.skipif(not shutil.which("sh") or not shutil.which("tar") or (os.name == "nt" and not os.environ.get("RUNBOARD_TEST_SH")),
                              reason="needs a POSIX sh and tar (Linux, macOS)")


def wait(fn, want, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        got = fn()
        if got[0] in want:
            return got
        time.sleep(0.3)
    raise AssertionError(f"still {got}")


@needs_sh
def test_ssh_run_end_to_end(rb, monkeypatch):
    from runboard.backends.remote import SSHBackend
    monkeypatch.setenv("FAKE_SSH_HOME", str(rb / "remote-home"))
    p = make(rb / "p", {"ssh": {"host": "box", "ssh": [sys.executable, FAKE], "python": sys.executable,
                                "command": '"{python}" -u train.py {id}', "output": "runs/{name}", "output_dir": "runs/ssh"}})
    b = SSHBackend()
    st = b.submit(p, "A", p.info("A"))
    assert st["pid"]
    assert wait(lambda: b.status(p, "A", st), {"COMPLETE", "ERROR"}) == ("COMPLETE", None)
    sink = []
    b.stream(p, "A", st, sink, lambda: True)
    assert sink == ["epoch 0", "epoch 1", "epoch 2"] and b.final_log(p, "A", st) == sink
    b.fetch(p, "A", st)
    assert (p.root / "runs" / "ssh" / "A" / "summary.json").read_text() == '{"map": 42.0}'

    monkeypatch.setenv("NAP", "5")
    st = b.submit(p, "B", p.info("B"))
    assert wait(lambda: b.status(p, "B", st), {"RUNNING"})[0] == "RUNNING"
    b.cancel(p, "B", st)
    assert wait(lambda: b.status(p, "B", st), {"CANCELLED"})[0] == "CANCELLED"


@needs_sh
def test_ssh_failure_reports_the_exit_code(rb, monkeypatch):
    from runboard.backends.remote import SSHBackend
    monkeypatch.setenv("FAKE_SSH_HOME", str(rb / "remote-home"))
    monkeypatch.setenv("FAIL", "3")
    p = make(rb / "p", {"ssh": {"host": "box", "ssh": [sys.executable, FAKE], "python": sys.executable,
                                "command": '"{python}" -u train.py {id}'}})
    b = SSHBackend()
    st = b.submit(p, "A", p.info("A"))
    assert wait(lambda: b.status(p, "A", st), {"COMPLETE", "ERROR"}) == ("ERROR", "exit code 3")



def test_the_wizard_sets_up_ssh_and_slurm(tmp_path):
    from runboard import wizard
    (tmp_path / "w" / "data").mkdir(parents=True)
    (tmp_path / "w" / "data" / "data.yaml").write_text("train: t.txt\nval: v.txt\nnames: [a]\n")
    spec = {"path": str(tmp_path / "w"), "kind": "yolo", "yolo": {"data": "data/data.yaml", "models": ["yolo11n.pt"]},
            "backends": ["ssh", "slurm"], "remote": {"host": "me@gpu", "partition": "gpu"}}
    m = yaml.safe_load(wizard.build(spec)["runboard.yaml"])
    ssh, slurm = m["backends"]["ssh"], m["backends"]["slurm"]
    assert ssh["host"] == "me@gpu" and ssh["command"].endswith("--run {id} --out runs/remote") and ssh["output"] == "runs/remote/{name}"
    assert slurm["sbatch"] == {"partition": "gpu", "gres": "gpu:1", "time": "12:00:00"} and slurm["output_dir"] == "runs/slurm"
    with pytest.raises(Invalid) as e:
        wizard.build({**spec, "remote": {}})
    assert e.value.code == "remote_config"
