"""Machines reached over SSH: a rented GPU or a lab server (`ssh`), and a SLURM cluster's login node (`slurm`).

runboard calls the system's own `ssh` with BatchMode, so it never sees a password: it uses your keys and agent, and
whatever ~/.ssh/config says about the host. The remote side needs a POSIX shell and tar (SLURM: sbatch, sacct, scancel).

    backends:
      ssh:
        host: gpu-box                      # an alias from ~/.ssh/config, or user@host
        workdir: ~/runboard/{project}      # where the code goes; default as shown
        python: python3
        setup: ["pip install -q ultralytics"]
        command: '"{python}" -u train.py --run {id}'
        output: runs/{name}                # the run's outputs, relative to workdir; fetched into output_dir
        output_dir: runs/ssh
        upload: [train.py, runs.yaml]      # default: the project's code files (as on the Code page)
      slurm:
        host: login.cluster.edu
        sbatch: {partition: gpu, gres: "gpu:1", time: "12:00:00", mem: 32G, cpus-per-task: 8}
        ... the rest as for ssh

Each run keeps its log, exit code and process id (or job id) in <workdir>/.runboard/, so the dashboard can be
restarted, and the run followed from another computer, without losing it.
"""
from __future__ import annotations

import io
import os
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Callable

from ..errors import Invalid
from .base import Backend

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
END = "@@rb-end@@"


def _safe(run_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", run_id)


class Remote:
    """One host, through the system's ssh. Commands run in the remote user's POSIX shell."""

    def __init__(self, cfg: dict):
        if not cfg.get("host"):
            raise Invalid("remote_config", backend="ssh", problem="backends.<name>.host is not set")
        self.host = str(cfg["host"])
        ssh = cfg.get("ssh") or "ssh"
        self.ssh = ssh if isinstance(ssh, list) else shlex.split(str(ssh), posix=os.name != "nt")
        self.opts = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=30"]
        if cfg.get("port"):
            self.opts += ["-p", str(cfg["port"])]
        self.opts += [str(o) for o in cfg.get("ssh_options") or []]

    def run(self, cmd: str, data: bytes | None = None, timeout: float = 120) -> subprocess.CompletedProcess:
        try:
            return subprocess.run([*self.ssh, *self.opts, self.host, cmd], input=data, capture_output=True,
                                  timeout=timeout, creationflags=NO_WINDOW)
        except FileNotFoundError:
            raise Invalid("no_ssh") from None
        except subprocess.TimeoutExpired:
            raise Invalid("ssh_error", host=self.host, problem=f"no answer within {int(timeout)} s") from None

    def check(self, cmd: str, data: bytes | None = None, timeout: float = 120) -> str:
        r = self.run(cmd, data, timeout)
        if r.returncode:
            msg = (r.stderr or r.stdout).decode("utf-8", "replace").strip().splitlines()
            raise Invalid("ssh_error", host=self.host, problem=(msg[-1] if msg else f"exit code {r.returncode}")[:300])
        return r.stdout.decode("utf-8", "replace")


def rpath(p: str) -> str:
    """A remote path for the shell: ~ is expanded by the remote shell, everything else quoted."""
    p = str(p)
    if p == "~":
        return '"$HOME"'
    if p.startswith("~/"):
        return '"$HOME"/' + shlex.quote(p[2:])
    return shlex.quote(p)


class SSHBackend(Backend):
    name = "ssh"
    label = "SSH"
    can_cancel = True

    def available(self):
        return (True, None) if shutil.which("ssh") else (False, "ssh not found (install OpenSSH)")

    def cfg(self, project) -> dict:
        return dict((project.m.get("backends") or {}).get(self.name) or {})

    def remote(self, project) -> Remote:
        return Remote(self.cfg(project))

    def slot(self, project) -> str | None:
        """What a run occupies: one run at a time per host (a cluster queues its own)."""
        return f"{self.name}:{self.cfg(project).get('host')}"

    def workdir(self, project) -> str:
        return str(self.cfg(project).get("workdir") or "~/runboard/{project}").replace("{project}", project.key)

    def files(self, project, run_id: str) -> dict[str, str]:
        d, r = self.workdir(project), _safe(run_id)
        return {k: f"{d}/.runboard/{r}.{k}" for k in ("log", "code", "pid", "sbatch")}

    # ------------------------------------------------------------ upload

    def upload_list(self, project) -> list[str]:
        up = self.cfg(project).get("upload")
        if up:
            return [str(u) for u in up]
        from ..code import listing
        return [f["path"] for f in listing(project)["files"] if not f["big"]]

    def bundle(self, project, extra: dict[str, str] | None = None) -> bytes:
        """The files to send, as a gzipped tar. Folders are sent whole; nothing outside the project."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for rel in self.upload_list(project):
                src = (project.root / rel).resolve()
                if project.root != src and project.root not in src.parents:
                    raise Invalid("remote_config", backend=self.name, problem=f"{rel} is outside the project")
                if src.exists():
                    tar.add(src, arcname=src.relative_to(project.root).as_posix())
            for name, text in (extra or {}).items():
                data = text.encode("utf-8")
                info = tarfile.TarInfo(name)
                info.size, info.mtime, info.mode = len(data), int(time.time()), 0o644
                tar.addfile(info, io.BytesIO(data))
        return buf.getvalue()

    def push(self, project, run_id: str, extra: dict[str, str] | None = None) -> Remote:
        rm, d = self.remote(project), self.workdir(project)
        rm.check(f"mkdir -p {rpath(d)}/.runboard && tar xzf - -C {rpath(d)}", self.bundle(project, extra), timeout=600)
        return rm

    def command(self, project, run_id: str, info: dict) -> str:
        cfg = self.cfg(project)
        tpl = cfg.get("resume") if info.get("resume") else cfg.get("command")
        if not tpl:
            raise Invalid("remote_config", backend=self.name, problem=f"backends.{self.name}.command is not set")
        return project.render(tpl, {**info, "python": cfg.get("python") or "python3"})

    def setup(self, project) -> str:
        return " && ".join(str(s) for s in self.cfg(project).get("setup") or [])

    # ------------------------------------------------------------ the run

    def submit(self, project, run_id, info):
        f, d = self.files(project, run_id), self.workdir(project)
        cmd, setup = self.command(project, run_id, info), self.setup(project)
        rm = self.push(project, run_id)
        body = (f"{setup} && " if setup else "") + f"( {cmd} ); echo $? > {rpath(f['code'])}"
        # its own process group (set -m), all output to the log and no terminal: ssh returns at once and the run
        # outlives the connection; cancel ends the whole group
        # only the run goes to the background (a backgrounded `a && b &` list would keep ssh's output open, and
        # with it the connection, until the run ends)
        out = rm.check(f"cd {rpath(d)} || exit 1; rm -f {rpath(f['code'])} {rpath(f['log'])}; set -m; "
                       f"nohup sh -c {shlex.quote(body)} > {rpath(f['log'])} 2>&1 < /dev/null & "
                       f"echo $! > {rpath(f['pid'])}; cat {rpath(f['pid'])}")
        pid = out.strip().splitlines()[-1] if out.strip() else ""
        return {"pid": int(pid) if pid.isdigit() else None, "host": rm.host, "command": cmd, "url": None}

    def status(self, project, run_id, st):
        f = self.files(project, run_id)
        out = self.remote(project).check(
            f"if [ -f {rpath(f['code'])} ]; then cat {rpath(f['code'])}; "
            f"elif kill -0 $(cat {rpath(f['pid'])} 2>/dev/null) 2>/dev/null; then echo RUNNING; else echo LOST; fi").strip()
        return self.read_code(out)

    @staticmethod
    def read_code(out: str) -> tuple[str, str | None]:
        if out == "RUNNING":
            return "RUNNING", None
        if out == "LOST":
            return "ERROR", "the process ended without an exit code (was the machine restarted?)"
        if out == "cancelled":
            return "CANCELLED", None
        return ("COMPLETE", None) if out == "0" else ("ERROR", f"exit code {out}")

    def stream(self, project, run_id, st, sink: list[str], alive: Callable[[], bool]):
        f, pos, rm, rest = self.files(project, run_id), 0, self.remote(project), b""
        while True:
            out = rm.run(f"tail -c +{pos + 1} {rpath(f['log'])} 2>/dev/null; printf '\\n{END}'; cat {rpath(f['code'])} 2>/dev/null",
                         timeout=60).stdout
            i = out.rfind(("\n" + END).encode())
            chunk, code = (out[:i], out[i + len(END) + 1:]) if i >= 0 else (b"", b"")
            pos += len(chunk)
            text = (rest + chunk).replace(b"\r", b"\n")
            *lines, rest = text.split(b"\n")
            sink.extend(ln.decode("utf-8", "replace").rstrip() for ln in lines if ln.strip())
            if code.strip() or not alive():
                if rest.strip():
                    sink.append(rest.decode("utf-8", "replace").rstrip())
                return
            time.sleep(5)

    def final_log(self, project, run_id, st):
        out = self.remote(project).run(f"cat {rpath(self.files(project, run_id)['log'])}", timeout=120).stdout
        return [ln.rstrip() for ln in out.decode("utf-8", "replace").replace("\r", "\n").split("\n") if ln.strip()]

    def cancel(self, project, run_id, st):
        f = self.files(project, run_id)
        self.remote(project).check(f"echo cancelled > {rpath(f['code'])}; p=$(cat {rpath(f['pid'])} 2>/dev/null); "
                                   f'[ -n "$p" ] && (kill -TERM -- -"$p" 2>/dev/null || kill -TERM "$p" 2>/dev/null); true')

    def may_still_run(self, project, run_id, st):
        return False

    # ------------------------------------------------------------ outputs

    def fetch(self, project, run_id, st):
        """The run's output folder (backends.<name>.output, relative to workdir) into output_dir/<name>."""
        cfg, info = self.cfg(project), project.info(run_id)
        remote_out = project.render(str(cfg.get("output") or "runs/{name}"), info)
        target = project.root / str(cfg.get("output_dir") or f"runs/{self.name}") / info["name"]
        data = self.remote(project).run(f"cd {rpath(self.workdir(project))} && tar czf - -C {rpath(remote_out)} .", timeout=1800)
        if data.returncode:
            msg = data.stderr.decode("utf-8", "replace").strip().splitlines()
            raise Invalid("ssh_error", host=self.cfg(project).get("host"), problem=(msg[-1] if msg else "no outputs")[:300])
        extract(data.stdout, target)

    def _resume_info(self, project, run_id, st, info):
        cfg = self.cfg(project)
        return {"resume": f"{self.workdir(project)}/{project.render(str(cfg.get('output') or 'runs/{name}'), info)}"}


def extract(data: bytes, target: Path) -> None:
    """Unpacks a tar from the remote side, refusing anything that would land outside target (or be a link)."""
    target.mkdir(parents=True, exist_ok=True)
    root = target.resolve()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        members = []
        for m in tar.getmembers():
            dest = (root / m.name).resolve()
            if (dest != root and root not in dest.parents) or m.issym() or m.islnk() or m.isdev():
                raise Invalid("ssh_error", host="", problem=f"refused a file from the remote side: {m.name}")
            members.append(m)
        tar.extractall(root, members=members)


# ---------------------------------------------------------------- SLURM

SLURM_STATES = {"PENDING": "QUEUED", "CONFIGURING": "STARTING", "RUNNING": "RUNNING", "COMPLETING": "RUNNING",
                "SUSPENDED": "RUNNING", "REQUEUED": "QUEUED", "RESIZING": "RUNNING", "COMPLETED": "COMPLETE",
                "CANCELLED": "CANCELLED"}


class SlurmBackend(SSHBackend):
    name = "slurm"
    label = "SLURM"

    def slot(self, project) -> str | None:
        return None  # the cluster queues the jobs; runboard sends as many as you queue

    def script(self, project, run_id: str, info: dict) -> str:
        cfg, f, d = self.cfg(project), self.files(project, run_id), self.workdir(project)
        opts = {"job-name": f"rb-{project.key}-{_safe(run_id)}"[:60], **{str(k): v for k, v in (cfg.get("sbatch") or {}).items()}}
        lines = ["#!/bin/bash"] + [f"#SBATCH --{k}={v}" for k, v in opts.items() if v not in (None, "", False)]
        setup = self.setup(project)
        lines += ["set -o pipefail", f"cd {rpath(d)}"] + ([setup] if setup else []) + [self.command(project, run_id, info),
                                                                                    f"echo $? > {rpath(f['code'])}"]
        return "\n".join(lines) + "\n"

    def submit(self, project, run_id, info):
        f, d = self.files(project, run_id), self.workdir(project)
        rel = f".runboard/{_safe(run_id)}.sbatch"
        rm = self.push(project, run_id, {rel: self.script(project, run_id, info)})
        out = rm.check(f"cd {rpath(d)} && rm -f {rpath(f['code'])} {rpath(f['log'])} && "
                       f"sbatch --parsable --output={rpath(f['log'])} {shlex.quote(rel)}")
        job = out.strip().splitlines()[-1].split(";")[0] if out.strip() else ""
        if not job.isdigit():
            raise Invalid("ssh_error", host=rm.host, problem=f"sbatch did not return a job id: {out.strip()[:200]}")
        return {"job": int(job), "host": rm.host, "command": self.command(project, run_id, info), "url": None}

    def status(self, project, run_id, st):
        job = st.get("job")
        if not job:
            return "ERROR", "no SLURM job id"
        out = self.remote(project).check(f"sacct -j {int(job)} -n -X -P -o State,ExitCode 2>/dev/null || "
                                         f"squeue -h -j {int(job)} -o %T").strip()
        return self.read_state(out)

    @staticmethod
    def read_state(out: str) -> tuple[str, str | None]:
        if not out:
            return "QUEUED", None  # sacct can lag behind sbatch for a few seconds
        first = out.splitlines()[0].split("|")
        state = first[0].split()[0].upper()  # "CANCELLED by 1234"
        if state in SLURM_STATES:
            s = SLURM_STATES[state]
            return s, None
        return "ERROR", f"SLURM: {state}" + (f" (exit {first[1]})" if len(first) > 1 and first[1] else "")

    def cancel(self, project, run_id, st):
        f = self.files(project, run_id)
        self.remote(project).check(f"echo cancelled > {rpath(f['code'])}; scancel {int(st.get('job') or 0)}")
