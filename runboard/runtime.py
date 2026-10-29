"""The engine: keeps track of every registered project's runs, streams live logs and collects finished runs."""
from __future__ import annotations

import os
import re
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import home
from .backends import ACTIVE, BACKENDS, DONE
from .errors import Busy, Invalid, Missing
from .progress import Parser, redact
from .project import MANIFEST, Project

POLL_SECONDS = 20
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Job:
    """A local command with a live log (validation, tests, packaging, uploads …)."""

    def __init__(self, key: str, title, cmd: list[str] | str, cwd: Path, shell: bool = False):
        self.key, self.title, self.cmd, self.cwd, self.shell = key, title, cmd, cwd, shell
        self.lines: list[str] = []
        self.status, self.started, self.ended, self.code = "running", time.time(), None, None
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            proc = subprocess.Popen(self.cmd, cwd=self.cwd, shell=self.shell, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, creationflags=NO_WINDOW,
                                    env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
            buf = b""
            while chunk := proc.stdout.read1(4096):
                buf += chunk
                *done, buf = re.split(rb"[\r\n]+", buf)
                self.lines.extend(x.decode("utf-8", "replace") for x in done if x.strip())
                del self.lines[:-2000]
            if buf.strip():
                self.lines.append(buf.decode("utf-8", "replace"))
            self.code = proc.wait()
            self.status = "ok" if self.code == 0 else "error"
        except Exception as e:
            self.lines.append(f"ERROR: {e}")
            self.status = "error"
        self.ended = time.time()

    def view(self, tail: int = 400) -> dict:
        return {"key": self.key, "title": self.title, "status": self.status, "code": self.code,
                "seconds": round((self.ended or time.time()) - self.started), "lines": [redact(x) for x in self.lines[-tail:]]}


class Runtime:
    def __init__(self):
        self.lock = threading.Lock()
        self.start_lock = threading.Lock()
        self.queue_lock = threading.Lock()
        self.logs: dict[tuple[str, str], list[str]] = {}
        self.streams: dict[tuple[str, str], threading.Thread] = {}
        self.jobs: dict[tuple[str, str], Job] = {}
        self.backend_info: dict[str, dict] = {}
        self.errors: dict[str, str] = {}

    # ------------------------------------------------------------ projects

    def projects(self) -> dict[str, Project]:
        out, self.errors = {}, {}
        for path in home.project_paths():
            try:
                p = Project(path)
                out[p.key] = p
            except Exception as e:
                self.errors[str(path)] = f"{type(e).__name__}: {e}"
        return out

    def project(self, key: str) -> Project:
        p = self.projects().get(key)
        if not p:
            raise KeyError(key)
        return p

    @staticmethod
    def add_project(path: Path) -> Project:
        path = Path(path).expanduser().resolve()
        if not (path / MANIFEST).exists():
            raise Invalid("no_manifest", path=path / MANIFEST)
        p = Project(path)
        home.register(path)
        return p

    # ------------------------------------------------------------ runs

    def run_state(self, project: Project, info: dict, saved: dict | None = None) -> dict:
        """Saved record; a run with a local report but no record (e.g. launched by hand) counts as complete."""
        st = dict((saved if saved is not None else project.state.all()).get(info["id"], {}))
        if st.get("status") in (None, "COMPLETE") and info["name"]:
            met = project.metrics(info["id"], info)
            if met:
                st.setdefault("status", "COMPLETE")
                st.setdefault("collected", True)
                st["metrics"] = {k: v for k, v in met.items() if k != "_raw"}
        return st

    def log(self, project: Project, run_id: str) -> list[str]:
        with self.lock:
            live = self.logs.get((project.key, run_id))
        if live:
            return list(live)
        p = project.state.logs / f"{run_id}.log"
        return p.read_text(encoding="utf-8").splitlines() if p.exists() else []

    def save_log(self, project: Project, run_id: str, lines: list[str]) -> None:
        if lines:
            project.state.logs.mkdir(parents=True, exist_ok=True)
            (project.state.logs / f"{run_id}.log").write_text("\n".join(lines), encoding="utf-8")

    def progress(self, project: Project, run_id: str) -> dict:
        return Parser(project.m.get("progress")).parse(self.log(project, run_id))

    def start(self, project: Project, run_id: str, backend: str) -> dict:
        info = project.info(run_id)
        if not info["ready"]:
            raise Invalid("not_ready", run=run_id, fields=info["missing"])
        b = BACKENDS.get(backend)
        if not b:
            raise Invalid("unknown_backend", backend=backend)
        if backend not in (project.m.get("backends") or {}):
            raise Invalid("not_configured", backend=backend)
        # The run is recorded as STARTING before anything is launched, under a lock, so a second click (or a
        # second tab) sees the backend as busy; a failed launch restores the previous record.
        with self.start_lock:
            busy = [f"{k}:{r}" for k, p in self.projects().items() for r, s in p.state.all().items()
                    if s.get("status") in ACTIVE and s.get("backend") == backend]
            if busy:
                raise Busy("busy", backend=b.label, runs=busy)
            previous = project.state.get(run_id)
            # the settings it starts with are kept: later edits to the runs file never rewrite what a run was
            project.state.set(run_id, {"backend": backend, "status": "STARTING", "collected": False,
                                       "pushed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                       "spec": project.spec(run_id)})
        try:
            fields = b.submit(project, run_id, info)
        except Exception:
            project.state.set(run_id, previous)
            raise
        with self.lock:
            self.logs[(project.key, run_id)] = []
        project.state.update(run_id, **{"status": "QUEUED", **fields})
        return fields

    def collect(self, project: Project, run_id: str) -> None:
        """Brings outputs home and runs the project's post-run command (results.after)."""
        st = project.state.get(run_id)
        b = BACKENDS[st.get("backend", "kaggle")]
        b.fetch(project, run_id, st)
        info = project.info(run_id)
        after = (project.m.get("results") or {}).get("after")
        check = None
        if after:
            cmd = project.render(after, {**info, "out": project.output_dir(run_id, info)})
            proc = subprocess.run(cmd, shell=True, cwd=project.root, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", creationflags=NO_WINDOW)
            if proc.returncode:
                check = {"error": (proc.stdout[-800:] + proc.stderr[-800:]).strip()}
        project.state.update(run_id, collected=True, check=check)

    def _stream(self, project: Project, run_id: str) -> None:
        key = (project.key, run_id)
        for _ in range(50):
            st = project.state.get(run_id)
            b = BACKENDS[st.get("backend", "kaggle")]
            buf: list[str] = []
            with self.lock:
                self.logs[key] = buf
            try:
                b.stream(project, run_id, st, buf, lambda: project.state.get(run_id).get("status") in ACTIVE)
                self.save_log(project, run_id, buf)
                return
            except Exception:
                time.sleep(10)
                if project.state.get(run_id).get("status") not in ACTIVE:
                    return

    def poll_once(self) -> None:
        for name, b in BACKENDS.items():
            ok, why = b.available()
            info = {}
            if ok:
                try:
                    info = b.info()
                except Exception as e:
                    why = str(e)
            self.backend_info[name] = {"name": name, "label": b.label, "ok": ok, "error": why, **info,
                                       "can_cancel": b.can_cancel, "has_data": b.has_data}
        for project in self.projects().values():
            for run_id, st in project.state.all().items():
                if st.get("status") in DONE and (st.get("collected") or st.get("status") != "COMPLETE"):
                    continue
                b = BACKENDS.get(st.get("backend", "kaggle"))
                if not b or not self.backend_info.get(b.name, {}).get("ok"):
                    continue
                try:
                    status, failure = b.status(project, run_id, st)
                except Exception:
                    continue
                project.state.update(run_id, status=status, failure=failure)
                key = (project.key, run_id)
                if status in ACTIVE:
                    t = self.streams.get(key)
                    if not t or not t.is_alive():
                        self.streams[key] = threading.Thread(target=self._stream, args=(project, run_id), daemon=True)
                        self.streams[key].start()
                elif status in DONE:
                    try:
                        lines = b.final_log(project, run_id, st)
                        if lines:
                            with self.lock:
                                self.logs[key] = lines
                            self.save_log(project, run_id, lines)
                    except Exception:
                        pass
                    if status == "COMPLETE" and not st.get("collected"):
                        try:
                            self.collect(project, run_id)
                        except Exception as e:
                            project.state.update(run_id, check={"error": f"collect: {e}"})

    def loop(self) -> None:
        while True:
            try:
                self.poll_once()
                self.run_queue()
            except Exception as e:
                print("poll error:", e, file=sys.stderr)
            time.sleep(POLL_SECONDS)

    # ------------------------------------------------------------ queue
    # One list for all projects (~/.runboard/queue.json). Each backend runs one thing at a time; when it is free the
    # first entry for it starts. An entry that cannot start yet stays with the reason (busy, quota, backend down).

    def queue(self) -> list[dict]:
        return home.read_json(home.HOME / "queue.json", [])

    def _save_queue(self, q: list[dict]) -> None:
        home.write_json(home.HOME / "queue.json", q)

    def enqueue(self, project: Project, run_id: str, backend: str, who: str = "") -> dict:
        if run_id not in project.run_ids():
            raise Invalid("unknown_run", run=run_id)
        info = project.info(run_id)
        if not info["ready"]:
            raise Invalid("not_ready", run=run_id, fields=info["missing"])
        if backend not in BACKENDS or backend not in (project.m.get("backends") or {}):
            raise Invalid("not_configured", backend=backend)
        if project.state.get(run_id).get("status") in ACTIVE:
            raise Busy("busy", backend=BACKENDS[backend].label, runs=[run_id])
        with self.queue_lock:
            q = self.queue()
            if any(e["project"] == project.key and e["run"] == run_id for e in q):
                raise Invalid("queue_has", run=run_id)
            entry = {"id": secrets.token_hex(4), "project": project.key, "run": run_id, "backend": backend,
                     "added": time.strftime("%Y-%m-%dT%H:%M:%S"), "who": who, "waiting": None}
            q.append(entry)
            self._save_queue(q)
        return entry

    def forget(self, project_key: str, run_id: str) -> None:
        """A run removed from the plan leaves the queue too."""
        with self.queue_lock:
            self._save_queue([e for e in self.queue() if not (e["project"] == project_key and e["run"] == run_id)])

    def dequeue(self, entry_id: str) -> None:
        with self.queue_lock:
            q = self.queue()
            keep = [e for e in q if e["id"] != entry_id]
            if len(keep) == len(q):
                raise Missing("queue_unknown", run=entry_id)
            self._save_queue(keep)

    def move(self, entry_id: str, by: int) -> None:
        with self.queue_lock:
            q = self.queue()
            i = next((i for i, e in enumerate(q) if e["id"] == entry_id), None)
            if i is None:
                raise Missing("queue_unknown", run=entry_id)
            j = max(0, min(len(q) - 1, i + by))
            q.insert(j, q.pop(i))
            self._save_queue(q)

    @staticmethod
    def estimate_hours(project: Project, run_id: str) -> float | None:
        """Hours a run will take: hours per epoch of the project's finished runs times this run's epochs."""
        rates = []
        for rid in project.run_ids():
            met = project.metrics(rid) or {}
            if met.get("hours") and met.get("epochs"):
                rates.append(met["hours"] / met["epochs"])
        epochs = project.spec(run_id).get("epochs")
        if not rates or not epochs:
            return None
        rates.sort()
        return round(rates[len(rates) // 2] * float(epochs), 2)

    def queue_view(self) -> list[dict]:
        ps = self.projects()
        out = []
        for e in self.queue():
            p = ps.get(e["project"])
            out.append({**e, "project_name": p.m.get("name", p.key) if p else e["project"],
                        "hours": self.estimate_hours(p, e["run"]) if p and e["run"] in p.run_ids() else None,
                        "backend_label": BACKENDS[e["backend"]].label if e["backend"] in BACKENDS else e["backend"]})
        return out

    def run_queue(self) -> list[str]:
        """Starts the first waiting entry of every free backend. Returns what it started."""
        started = []
        with self.queue_lock:
            q = self.queue()
            if not q:
                return started
            ps = self.projects()
            busy = {s.get("backend") for p in ps.values() for s in p.state.all().values() if s.get("status") in ACTIVE}
            for e in list(q):
                b = e["backend"]
                p = ps.get(e["project"])
                if not p or e["run"] not in p.run_ids():  # gone from the plan: it must not hold up the others
                    e["waiting"] = "missing"
                    continue
                if b in busy:
                    e["waiting"] = "busy"
                    continue
                busy.add(b)  # the first entry of a backend blocks the ones behind it, even when it cannot start
                if not self.backend_info.get(b, {}).get("ok"):
                    e["waiting"] = "backend"
                    continue
                quota = self.backend_info.get(b, {}).get("quota") if b == "kaggle" else None
                need = self.estimate_hours(p, e["run"]) if quota else None
                if quota and need and quota["total_h"] - quota["used_h"] < need:
                    e["waiting"] = "quota"
                    continue
                try:
                    self.start(p, e["run"], b)
                except Exception as ex:
                    e["waiting"] = f"error: {ex}"[:300]
                    continue
                q.remove(e)
                started.append(f"{p.key}:{e['run']}")
            self._save_queue(q)
        return started

    # ------------------------------------------------------------ jobs

    def start_job(self, project: Project, kind: str, run_id: str | None = None) -> Job:
        jobs = project.m.get("jobs") or {}
        if kind not in jobs:
            raise Invalid("unknown_job")
        running = [j for (k, _), j in self.jobs.items() if k == project.key and j.status == "running"]
        if running:
            raise Busy("job_running", job=running[0].key)
        spec = jobs[kind]
        ctx = {}
        if spec.get("per_run"):
            info = project.info(run_id or "")
            ctx = {**info, "out": project.output_dir(run_id, info)}
        job = Job(kind, spec.get("title", kind), project.render(spec["cmd"], ctx), project.root, shell=True)
        self.jobs[(project.key, kind)] = job
        return job

    def upload_job(self, project: Project, keys: list[str]) -> Job:
        running = [j for (k, _), j in self.jobs.items() if k == project.key and j.status == "running"]
        if running:
            raise Busy("job_running", job=running[0].key)
        job = Job("upload", {"en": "Upload to Kaggle", "tr": "Kaggle'a yükleme"},
                  [sys.executable, "-u", "-m", "runboard", "upload", str(project.root), *keys], project.root)
        self.jobs[(project.key, "upload")] = job
        return job
