"""The SSH and SLURM backends against a real machine: a container (tests/docker) with sshd, Python and a one-node
SLURM cluster that keeps accounting, reached through this computer's own ssh with a key made for the test.

Runs when RUNBOARD_TEST_DOCKER=1 and Docker and ssh are available (the CI's Linux job sets it); skipped otherwise.
The image is built once (a few hundred MB on the first build) and the container is removed at the end."""
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from test_remote import make, wait

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNBOARD_TEST_DOCKER") or not shutil.which("docker") or not shutil.which("ssh"),
    reason="set RUNBOARD_TEST_DOCKER=1 with Docker and ssh available")

IMAGE, NAME = "runboard-test-remote", "runboard-test-remote"
HERE = Path(__file__).with_name("docker")


def sh(*args, check=True, timeout=600):
    return subprocess.run(args, capture_output=True, text=True, check=check, timeout=timeout)


@pytest.fixture(scope="module")
def machine(tmp_path_factory):
    d = tmp_path_factory.mktemp("ssh")
    key = d / "key"
    sh("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key))
    for attempt in (1, 2):  # the image downloads packages: a mirror that fails for a moment gets a second try
        r = sh("docker", "build", "-q", "-t", IMAGE, str(HERE), timeout=1800, check=False)
        if r.returncode == 0:
            break
    else:
        raise AssertionError("the test image does not build:\n" + (r.stderr or r.stdout)[-3000:])
    sh("docker", "rm", "-f", NAME, check=False)
    # --privileged: slurmd makes its own cgroup inside the container (tests/docker/cgroup.conf)
    sh("docker", "run", "-d", "--privileged", "--name", NAME, "--hostname", "rbnode", "-p", "127.0.0.1::22",
       "-e", f"AUTHORIZED_KEY={(d / 'key.pub').read_text().strip()}", IMAGE)
    try:
        port = sh("docker", "port", NAME, "22").stdout.split()[0].rsplit(":", 1)[1]
        cfg = {"host": "rb@127.0.0.1", "port": int(port), "python": "python3",
               "ssh_options": ["-i", str(key), "-o", "StrictHostKeyChecking=no", "-o", f"UserKnownHostsFile={d / 'known'}"]}
        from runboard.backends.remote import Remote
        rm, end, out = Remote(cfg), time.time() + 120, ""
        while time.time() < end:  # sshd answers and the node is idle
            r = rm.run("sinfo -h -o %t", timeout=10)
            out = r.stdout.decode().strip()
            if r.returncode == 0 and out == "idle":
                break
            time.sleep(2)
        else:
            raise AssertionError(f"the test machine did not come up: {out!r}\n" + sh("docker", "logs", NAME, check=False).stdout[-2000:])
        yield cfg
    finally:
        sh("docker", "rm", "-f", NAME, check=False)


def docker_exec(cmd):
    return sh("docker", "exec", NAME, "bash", "-c", cmd, check=False)


def project(tmp_path, name, kind, cfg, command):
    extra = {"sbatch": {"partition": "debug", "time": "00:05:00"}} if kind == "slurm" else {}
    return make(tmp_path / name, {kind: {**cfg, **extra, "command": command, "output": "runs/{name}",
                                         "output_dir": f"runs/{kind}"}})


def test_ssh_on_a_real_machine(machine, tmp_path):
    from runboard.backends.remote import SSHBackend
    # the run is told its name and output folder (RUNBOARD_RUN, RUNBOARD_OUT): what it writes there comes home
    cmd = 'echo "$RUNBOARD_RUN" > "$RUNBOARD_OUT"/who.txt; "{python}" -u train.py {id}'
    p, b = project(tmp_path, "sshp", "ssh", machine, cmd), SSHBackend()
    st = b.submit(p, "A", p.info("A"))
    assert st["pid"]
    assert wait(lambda: b.status(p, "A", st), {"COMPLETE", "ERROR"}, 60) == ("COMPLETE", None)
    sink = []
    b.stream(p, "A", st, sink, lambda: True)
    assert sink == ["epoch 0", "epoch 1", "epoch 2"]
    b.fetch(p, "A", st)
    assert (p.root / "runs" / "ssh" / "A" / "summary.json").read_text() == '{"map": 42.0}'
    assert (p.root / "runs" / "ssh" / "A" / "who.txt").read_text().strip() == "A"


def test_ssh_failure_and_cancel_on_a_real_machine(machine, tmp_path):
    from runboard.backends.remote import SSHBackend
    p, b = project(tmp_path, "sshf", "ssh", machine, 'FAIL=3 "{python}" -u train.py {id}'), SSHBackend()
    st = b.submit(p, "A", p.info("A"))
    assert wait(lambda: b.status(p, "A", st), {"COMPLETE", "ERROR"}, 60) == ("ERROR", "exit code 3")
    p = project(tmp_path, "sshc", "ssh", machine, 'NAP=20 "{python}" -u train.py {id}')
    st = b.submit(p, "B", p.info("B"))
    assert wait(lambda: b.status(p, "B", st), {"RUNNING"}, 30)[0] == "RUNNING"
    b.cancel(p, "B", st)
    assert wait(lambda: b.status(p, "B", st), {"CANCELLED"}, 30)[0] == "CANCELLED"
    assert docker_exec("pgrep -f 'train.py B'").stdout.strip() == ""  # the whole run stopped, not only its shell


def test_slurm_on_a_real_cluster(machine, tmp_path):
    from runboard.backends.remote import SlurmBackend
    p, b = project(tmp_path, "slurmp", "slurm", machine, '"{python}" -u train.py {id}'), SlurmBackend()
    st = b.submit(p, "A", p.info("A"))
    assert st["job"] > 0
    assert wait(lambda: b.status(p, "A", st), {"COMPLETE", "ERROR"}, 90) == ("COMPLETE", None)
    sink = []
    b.stream(p, "A", st, sink, lambda: True)
    assert sink == ["epoch 0", "epoch 1", "epoch 2"]
    b.fetch(p, "A", st)
    assert (p.root / "runs" / "slurm" / "A" / "summary.json").read_text() == '{"map": 42.0}'


def test_slurm_failure_and_cancel_on_a_real_cluster(machine, tmp_path):
    from runboard.backends.remote import SlurmBackend
    b = SlurmBackend()
    p = project(tmp_path, "slurmf", "slurm", machine, 'FAIL=3 "{python}" -u train.py {id}')
    st = b.submit(p, "A", p.info("A"))
    state, why = wait(lambda: b.status(p, "A", st), {"COMPLETE", "ERROR"}, 90)
    # sacct says FAILED; when its accounting lags behind the job's end, the exit code the script wrote says the same
    assert state == "ERROR" and ("FAILED" in why or "exit code 3" in why)
    p = project(tmp_path, "slurmc", "slurm", machine, 'NAP=30 "{python}" -u train.py {id}')
    st = b.submit(p, "B", p.info("B"))
    assert wait(lambda: b.status(p, "B", st), {"RUNNING"}, 60)[0] == "RUNNING"
    b.cancel(p, "B", st)
    assert wait(lambda: b.status(p, "B", st), {"CANCELLED"}, 60)[0] == "CANCELLED"


def test_linux_autostart_starts_with_the_session_and_after_a_crash(machine, tmp_path, monkeypatch):
    # the same image booted with systemd: runboard's user service, written as autostart.enable() writes it, starts
    # when the user's session does, without its own watchdog, and systemd brings it back after a crash. A stand-in
    # `python3 -m runboard` notes how it was started: the image has no runboard installed.
    from runboard import autostart
    monkeypatch.setattr(autostart, "kind", lambda: "systemd")
    monkeypatch.setattr(autostart, "_python", lambda: "/usr/bin/python3")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    unit = tmp_path / "runboard.service"
    unit.write_text(autostart.text(), newline="")
    name = NAME + "-systemd"
    sh("docker", "rm", "-f", name, check=False)
    sh("docker", "run", "-d", "--privileged", "--name", name, "--entrypoint", "/lib/systemd/systemd", IMAGE)
    try:
        sh("docker", "cp", str(unit), f"{name}:/root/runboard.service")
        user = "/home/rb/.config/systemd/user"
        stand_in = ("import os, time\\nopen(os.path.expanduser('~/started.txt'), 'a')"
                    ".write(os.environ.get('RUNBOARD_NO_WATCHDOG', '-'))\\ntime.sleep(600)\\n")
        r = sh("docker", "exec", name, "bash", "-c",
               f"sleep 3; mkdir -p /home/rb/runboard {user}/default.target.wants && printf \"{stand_in}\" > /home/rb/runboard/__main__.py"
               f" && cp /root/runboard.service {user}/ && ln -s {user}/runboard.service {user}/default.target.wants/"
               f" && chown -R rb:rb /home/rb && loginctl enable-linger rb", check=False)
        assert r.returncode == 0, r.stderr
        ask = f"runuser -u rb -- env XDG_RUNTIME_DIR=/run/user/$(id -u rb) systemctl --user show runboard.service -p ActiveState -p NRestarts"
        end = time.time() + 60
        while time.time() < end and "ActiveState=active" not in sh("docker", "exec", name, "bash", "-c", ask, check=False).stdout:
            time.sleep(1)
        assert sh("docker", "exec", name, "cat", "/home/rb/started.txt", check=False).stdout == "1"  # no watchdog of its own
        sh("docker", "exec", name, "bash", "-c", "pkill -9 -u rb -f 'python3 -m runboard'")
        end = time.time() + 40
        while time.time() < end and "NRestarts=1" not in sh("docker", "exec", name, "bash", "-c", ask, check=False).stdout:
            time.sleep(1)
        out = sh("docker", "exec", name, "bash", "-c", ask, check=False).stdout
        assert "NRestarts=1" in out and "ActiveState=active" in out, out
    finally:
        sh("docker", "rm", "-f", name, check=False)


def test_slurm_without_accounting_still_sees_a_job_end(machine, tmp_path):
    # many clusters keep no accounting: sacct knows nothing and squeue forgets a job once it ends
    from runboard.backends.remote import SlurmBackend
    docker_exec("pkill -x slurmdbd; sleep 1")
    try:
        p, b = project(tmp_path, "slurmn", "slurm", machine, '"{python}" -u train.py {id}'), SlurmBackend()
        st = b.submit(p, "A", p.info("A"))
        assert wait(lambda: b.status(p, "A", st), {"COMPLETE", "ERROR"}, 90) == ("COMPLETE", None)
    finally:
        docker_exec("slurmdbd; sleep 2")


def test_a_queued_slurm_job_keeps_the_code_it_was_sent_with(machine, tmp_path):
    """A job waits in the queue while the code changes and another job is sent: it still runs its own version."""
    from runboard.backends.remote import SlurmBackend
    p, b = project(tmp_path, "queued", "slurm", machine, '"{python}" -u v.py'), SlurmBackend()
    (p.root / "v.py").write_text("print('code v1', flush=True)\n")
    p.m["backends"]["slurm"]["sbatch"]["begin"] = "now+20"  # A waits in the queue
    a = b.submit(p, "A", p.info("A"))
    assert b.status(p, "A", a)[0] == "QUEUED"
    (p.root / "v.py").write_text("print('code v2', flush=True)\n")
    del p.m["backends"]["slurm"]["sbatch"]["begin"]
    bb = b.submit(p, "B", p.info("B"))  # sends v2 into the same work folder while A still waits
    assert wait(lambda: b.status(p, "B", bb), {"COMPLETE", "ERROR"}, 90) == ("COMPLETE", None)
    assert wait(lambda: b.status(p, "A", a), {"COMPLETE", "ERROR"}, 120) == ("COMPLETE", None)
    assert b.final_log(p, "A", a) == ["code v1"] and b.final_log(p, "B", bb) == ["code v2"]
