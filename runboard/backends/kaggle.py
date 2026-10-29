"""Kaggle Notebooks: each run becomes a private single-file script kernel; data packages become private datasets.

The API token stays on this machine (~/.kaggle/access_token or KAGGLE_API_TOKEN) and is never sent to the browser.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import zipfile
from datetime import timezone
from pathlib import Path
from typing import Callable

from ..errors import Invalid
from ..home import write_json
from ..progress import fix_text, log_lines
from .base import Backend

STATUS = {"QUEUED": "QUEUED", "RUNNING": "RUNNING", "NEW_SCRIPT": "STARTING", "COMPLETE": "COMPLETE", "ERROR": "ERROR",
          "CANCEL_REQUESTED": "CANCELLING", "CANCEL_ACKNOWLEDGED": "CANCELLED"}


def api():
    from kaggle.api.kaggle_api_extended import KaggleApi

    a = KaggleApi()
    a.authenticate()
    return a


def user(a) -> str:
    return a.get_config_value(a.CONFIG_NAME_USER)


class KaggleBackend(Backend):
    name = "kaggle"
    label = "Kaggle"
    has_data = True
    has_quota = True

    def available(self):
        try:
            import kaggle  # noqa: F401
        except ImportError:
            return False, "pip install kaggle"
        try:
            api()
            return True, None
        except Exception as e:  # missing or invalid token
            return False, (str(e).strip().splitlines() or [type(e).__name__])[-1]

    def info(self) -> dict:
        a = api()
        out = {"user": user(a)}
        try:
            q = a.quota_view()
            g = q.gpu_quota
            out["quota"] = {"used_h": round(g.time_used.total_seconds() / 3600, 1),
                            "total_h": round(g.total_time_allowed.total_seconds() / 3600, 1),
                            "refresh": q.quota_refresh_time.replace(tzinfo=timezone.utc).isoformat() if q.quota_refresh_time else None}
        except Exception:
            pass
        return out

    # ------------------------------------------------------------ runs

    def _cfg(self, project) -> dict:
        return (project.m.get("backends") or {}).get("kaggle") or {}

    def ref(self, project, run_id: str, st: dict, a=None) -> str:
        r = f"{user(a or api())}/{st.get('kernel') or self.slug(project, run_id)}"
        return f"{r}/{st['version']}" if st.get("version") else r

    def slug(self, project, run_id: str) -> str:
        return re.sub(r"[^a-z0-9-]+", "-", project.render(self._cfg(project).get("kernel", project.key + "-{id|lower}"),
                                                          {"id": run_id}).lower())

    def dataset_for(self, project, info: dict) -> str | None:
        data = project.m.get("data") or {}
        field = self._cfg(project).get("data_field") or data.get("field")
        if not field:
            return None
        value = info.get(field, project.spec(info["id"]).get(field))  # the field need not be a displayed one
        return project.state.datasets(data.get("datasets") or {}).get(value)

    def build(self, project, run_id: str, info: dict, folder: Path, owner: str) -> None:
        cfg = self._cfg(project)
        files = {dst: base64.b64encode((project.root / src).read_bytes()).decode()
                 for dst, src in (cfg.get("files") or {}).items()}
        setup = [project.render(s, info) for s in cfg.get("setup", [])]
        command = project.render(cfg.get("command", ""), info)
        code = (f"# runboard · {project.m.get('name', project.key)} · {run_id} — generated, do not edit.\n"
                "import base64, json, os, pathlib, subprocess, sys\n"
                f"FILES = json.loads({json.dumps(json.dumps(files))})\n"
                "d = pathlib.Path('/tmp/runboard-code'); d.mkdir(parents=True, exist_ok=True)\n"
                "for name, b in FILES.items():\n"
                "    (d / name).parent.mkdir(parents=True, exist_ok=True); (d / name).write_bytes(base64.b64decode(b))\n"
                f"for cmd in {json.dumps(setup)}:\n"
                "    subprocess.check_call(cmd, shell=True)\n"
                "os.environ['PYTHONUNBUFFERED'] = '1'\n"
                f"sys.exit(subprocess.call({json.dumps(command)}, shell=True, cwd=d))\n")
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
        (folder / "run.py").write_text(code, encoding="utf-8")
        ds = self.dataset_for(project, info)
        slug = self.slug(project, run_id)
        write_json(folder / "kernel-metadata.json", {
            "id": f"{owner}/{slug}", "title": slug, "code_file": "run.py", "language": "python", "kernel_type": "script",
            "is_private": True, "enable_gpu": bool(cfg.get("accelerator", "NvidiaTeslaT4")), "enable_tpu": False,
            "enable_internet": cfg.get("internet", True), "machine_shape": cfg.get("accelerator", "NvidiaTeslaT4"),
            "dataset_sources": [f"{owner}/{ds}"] if ds else [], "competition_sources": [], "kernel_sources": [],
            "model_sources": []})

    def submit(self, project, run_id, info):
        data = project.m.get("data") or {}
        field = self._cfg(project).get("data_field") or data.get("field")
        if field and not self.dataset_for(project, info):
            raise Invalid("not_on_kaggle", data=project.spec(run_id).get(field))
        a = api()
        folder = project.state.dir / "push" / self.slug(project, run_id)
        self.build(project, run_id, info, folder, user(a))
        res = a.kernels_push(str(folder))
        if res.error:
            raise RuntimeError(res.error)
        return {"kernel": self.slug(project, run_id), "version": res.version_number, "url": res.url}

    def status(self, project, run_id, st):
        res = api().kernels_status(self.ref(project, run_id, st))
        s = res.status.name if hasattr(res.status, "name") else str(res.status)
        return STATUS.get(s, s), res.failure_message or None

    def stream(self, project, run_id, st, sink, alive: Callable[[], bool]):
        for ev in api().kernels_logs_stream(self.ref(project, run_id, st)):
            for line in re.split(r"[\r\n]+", fix_text(ev.get("data", ""))):
                if line.strip() and not re.search(r"Debugger warning|frozen modules|PYDEVD|debugger miss", line):
                    sink.append(line.rstrip())

    def final_log(self, project, run_id, st):
        return log_lines(api().kernels_logs(self.ref(project, run_id, st)))

    def fetch(self, project, run_id, st):
        a = api()
        target = project.root / self._cfg(project).get("output_dir", "runs/kaggle")
        token = None
        while True:
            _, token = a.kernels_output(self.ref(project, run_id, st, a), str(target), page_token=token, force=True)
            if not token:
                break

    def delete(self, project, run_id, st):
        a = api()
        a.kernels_delete(f"{user(a)}/{st.get('kernel') or self.slug(project, run_id)}", no_confirm=True)

    # ------------------------------------------------------------ data

    def datasets(self, project) -> list[dict]:
        a = api()
        owner = user(a)
        mine = {d.ref.split("/")[1]: d for d in (a.dataset_list(mine=True) or []) if d}
        data = project.m.get("data") or {}
        out = []
        for pkg, name in project.state.datasets(data.get("datasets") or {}).items():
            d = mine.get(name)
            try:
                st = a.dataset_status(f"{owner}/{name}") if d else None
            except Exception:
                st = None
            out.append({"key": pkg, "dataset": name, "exists": bool(d), "status": st,
                        "version": getattr(d, "current_version_number", None),
                        "gb": round((getattr(d, "total_bytes", 0) or 0) / 2**30, 2),
                        "private": getattr(d, "is_private", None)})
        return out

    @staticmethod
    def zip_folder(src: Path, dst: Path, forbid: list, say=print) -> Path:
        files = [f for f in src.rglob("*") if f.is_file()]
        keep = [f for f in files if not any(rx.search(f.relative_to(src).as_posix()) for rx in forbid)]
        say(f"▶ zipping {src} ({len(keep)} files" + (f", {len(files) - len(keep)} left out by the forbidden-path rules" if len(keep) < len(files) else "") + ")…")
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:  # images are already compressed
            for i, f in enumerate(keep, 1):
                z.write(f, f.relative_to(src).as_posix())
                if i % 2000 == 0:
                    say(f"  {i}/{len(keep)}")
        tmp.replace(dst)
        return dst

    def upload(self, project, keys: list[str], say=print) -> int:
        """Uploads each package to its own private dataset (new version if it exists). Runs as a background job."""
        data = project.m.get("data") or {}
        forbid = [re.compile(p) for p in data.get("forbid", [])]
        catalog = {r["_key"]: r for r in project.catalog()}
        a = api()
        owner = user(a)
        mine = {d.ref.split("/")[1] for d in (a.dataset_list(mine=True) or []) if d}
        dmap = project.state.datasets(data.get("datasets") or {})
        prefix = data.get("dataset_prefix", project.key + "-")
        for key in keys:
            row = catalog.get(key, {})
            z = Path(row["_zip"]) if row else project.root / data.get("dir", ".") / f"{key}.zip"
            if row.get("_dir"):  # a folder package: zip it now, leaving out forbidden paths (e.g. the test split)
                z = self.zip_folder(Path(row["_dir"]), z, forbid, say)
            if not z.exists():
                say(f"ERROR: {z} not found")
                return 1
            if forbid:
                say(f"▶ {key}: checking the archive against forbidden paths…")
                with zipfile.ZipFile(z) as f:
                    bad = [n for n in f.namelist() if any(rx.search(n) for rx in forbid)]
                if bad:
                    say(f"ERROR: {key} contains forbidden files (e.g. {bad[0]}); not uploaded")
                    return 1
            name = dmap.get(key) or re.sub(r"[^a-z0-9-]+", "-", f"{prefix}{key}".lower())
            folder = project.state.dir / "upload" / name
            shutil.rmtree(folder, ignore_errors=True)
            folder.mkdir(parents=True)
            try:
                os.link(z, folder / z.name)
            except OSError:
                shutil.copy2(z, folder / z.name)
            write_json(folder / "dataset-metadata.json", {"title": name, "id": f"{owner}/{name}", "licenses": [{"name": "other"}]})
            gb = z.stat().st_size / 2**30
            if name in mine:
                say(f"▶ {key}: new version of {owner}/{name} ({gb:.2f} GB, private)…")
                res = a.dataset_create_version(str(folder), f"{key} · runboard", quiet=False)
            else:
                say(f"▶ {key}: creating private dataset {owner}/{name} ({gb:.2f} GB)…")
                res = a.dataset_create_new(str(folder), public=False, quiet=False)
            shutil.rmtree(folder, ignore_errors=True)
            if res.error:
                say(f"ERROR: {key}: {res.error}")
                return 1
            project.state.set_dataset(key, name)
            say(f"✔ {key} uploaded: {res.url} (Kaggle processes it for a few minutes)")
        return 0
