"""Local GPU: runs the project's command on this machine, detached from the dashboard.

A small runner (python -m runboard.localrun) writes the log, a heartbeat file and the exit code, so runs survive a
dashboard restart and their status is known without keeping a process handle.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from typing import Callable

from ..errors import Invalid
from ..proc import pid_alive, popen_detached
from .base import Backend


class LocalBackend(Backend):
    name = "local"
    label = "Local GPU"
    can_cancel = True

    def info(self) -> dict:
        try:
            import torch
        except ImportError:
            return {"gpu": None}
        if not torch.cuda.is_available():
            return {"gpu": None}
        free, total = torch.cuda.mem_get_info()
        return {"gpu": torch.cuda.get_device_name(0), "free_gb": round(free / 2**30, 1), "total_gb": round(total / 2**30, 1)}

    def _files(self, project, run_id):
        d = project.state.dir / "local"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{run_id}.log", d / f"{run_id}.code", d / f"{run_id}.alive"

    def submit(self, project, run_id, info):
        cfg = (project.m.get("backends") or {}).get("local") or {}
        if not cfg.get("command"):
            raise Invalid("no_local_command")
        log, code, alive = self._files(project, run_id)
        for f in (log, code, alive):
            f.unlink(missing_ok=True)
        cmd = project.render(cfg["resume"] if info.get("resume") else cfg["command"], info)
        python = cfg.get("python") or sys.executable
        proc = popen_detached([sys.executable, "-m", "runboard.localrun", str(log), str(code), str(alive), python, cmd],
                              cwd=project.root)
        return {"pid": proc.pid, "command": cmd, "url": None}

    def status(self, project, run_id, st):
        log, code, alive = self._files(project, run_id)
        if code.exists():
            c = code.read_text().strip()
            if c == "cancelled":
                return "CANCELLED", None
            return ("COMPLETE", None) if c == "0" else ("ERROR", f"exit code {c}")
        if alive.exists() and time.time() - alive.stat().st_mtime < 60:
            return "RUNNING", None
        if pid_alive(st.get("pid")):  # the heartbeat is old but the runner lives: the computer was asleep
            return "RUNNING", None
        if alive.exists() or log.exists():
            return "ERROR", "process stopped without an exit code (machine restarted?)"
        if st.get("pid"):  # launched, but gone before it wrote a line (blocked by antivirus, a broken Python)
            return "ERROR", "the runner exited before the run started"
        return "STARTING", None

    def _resume_info(self, project, run_id, st, info):
        out = project.output_dir(run_id, info, self.name)
        if not out or not out.is_dir():
            raise Invalid("resume_missing", run=run_id, path=out)
        return {"resume": str(out)}

    def may_still_run(self, project, run_id, st):
        _, code, _ = self._files(project, run_id)
        return not code.exists() and pid_alive(st.get("pid"))

    def stream(self, project, run_id, st, sink, alive: Callable[[], bool]):
        log, code, _ = self._files(project, run_id)
        pos = 0
        while True:
            if log.exists():
                with open(log, encoding="utf-8", errors="replace") as f:
                    f.seek(pos)
                    chunk = f.read()
                    pos = f.tell()
                sink.extend(ln.rstrip() for ln in chunk.replace("\r", "\n").split("\n") if ln.strip())
            if code.exists() or not alive():
                return
            time.sleep(1)

    def final_log(self, project, run_id, st):
        log, _, _ = self._files(project, run_id)
        return [ln.rstrip() for ln in log.read_text(encoding="utf-8", errors="replace").replace("\r", "\n").split("\n")
                if ln.strip()] if log.exists() else []

    def cancel(self, project, run_id, st):
        """Stops the runner and everything it started (the training process is its child)."""
        _, code, _ = self._files(project, run_id)
        code.write_text("cancelled")  # first, so the runner does not overwrite it with an exit code
        pid = st.get("pid")
        if not pid:
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            try:
                os.killpg(pid, signal.SIGTERM)  # the runner leads its own session/process group
            except OSError:
                pass
