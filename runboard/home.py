"""runboard's own directory (~/.runboard): project registry, paired devices, per-project state.

Nothing here ever lives inside a project repository, so projects stay clean and nothing private gets committed.
Override the location with the RUNBOARD_HOME environment variable.
"""
from __future__ import annotations

import copy
import json
import os
import threading
import time
from pathlib import Path

import yaml

HOME = Path(os.environ.get("RUNBOARD_HOME", Path.home() / ".runboard"))
CONFIG = HOME / "config.yaml"
_lock = threading.Lock()
_cache_lock = threading.Lock()  # its own: register() reads the config while holding _lock
_file_locks: dict[str, threading.RLock] = {}


def file_lock(p: Path) -> threading.RLock:
    """One lock per file for the whole process. Objects that read and write the same file (a project is rebuilt for
    every request) must share it, or two writers can each save their own copy and one update is lost."""
    key = os.path.normcase(os.path.abspath(p))
    with _lock:
        return _file_locks.setdefault(key, threading.RLock())


def _retry(fn, tries: int = 20):
    """Windows refuses to replace or open a file another thread or process has open at that moment; it clears in ms."""
    for i in range(tries):
        try:
            return fn()
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.02 * (i + 1))


def read_json(p: Path, default):
    return _retry(lambda: json.loads(p.read_text(encoding="utf-8")) if p.exists() else default)


def write_json(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(p):
        tmp = p.with_name(f"{p.name}.{os.getpid()}.{threading.get_ident()}.tmp")  # never shared between writers
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        try:
            _retry(lambda: tmp.replace(p))
        finally:
            tmp.unlink(missing_ok=True)


_yaml_cache: dict[str, tuple] = {}
_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)  # the C parser when PyYAML has it


def load_yaml(p: Path):
    """A YAML file, parsed once until it changes on disk. Callers get their own copy and may change it freely."""
    key = os.path.normcase(os.path.abspath(p))
    st = Path(p).stat()
    sig = (st.st_mtime_ns, st.st_size)
    hit = _yaml_cache.get(key)
    if not hit or hit[0] != sig:
        hit = (sig, yaml.load(_retry(lambda: Path(p).read_text(encoding="utf-8")), Loader=_LOADER))
        with _cache_lock:
            _yaml_cache[key] = hit
    return copy.deepcopy(hit[1])


def config() -> dict:
    cfg = load_yaml(CONFIG) if CONFIG.exists() else None
    return cfg or {"projects": [], "port": 8000}


def save_config(cfg: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")


def project_paths() -> list[Path]:
    return [Path(p) for p in config().get("projects", [])]


def register(path: Path) -> None:
    path = path.resolve()
    with _lock:
        cfg = config()
        projects = cfg.setdefault("projects", [])  # a config written by hand may leave it out
        if str(path) not in projects:
            projects.append(str(path))
            save_config(cfg)


def unregister(path: Path) -> None:
    with _lock:
        cfg = config()
        cfg["projects"] = [p for p in cfg.get("projects", []) if Path(p).resolve() != path.resolve()]
        save_config(cfg)


class State:
    """Per-project state: run records, live logs on disk, dataset mapping, runs-file backups."""

    def __init__(self, key: str):
        self.dir = HOME / "state" / key
        self.file = self.dir / "state.json"
        self.logs = self.dir / "logs"
        self.lock = file_lock(self.file)  # shared by every State of this project, not one per object

    def all(self) -> dict:
        return read_json(self.file, {})

    def get(self, run_id: str) -> dict:
        return self.all().get(run_id, {})

    def update(self, run_id: str, **fields) -> None:
        with self.lock:
            data = self.all()
            rec = data.get(run_id)
            if rec is not None and all(k in rec and rec[k] == v for k, v in fields.items()):
                return  # every poll reports the same status; the file is written only when something changed
            data.setdefault(run_id, {}).update(fields)
            write_json(self.file, data)

    def set(self, run_id: str, record: dict) -> None:
        """Replaces a run's record (an empty record removes it)."""
        with self.lock:
            data = self.all()
            if record:
                data[run_id] = record
            else:
                data.pop(run_id, None)
            write_json(self.file, data)

    def remove(self, run_id: str) -> None:
        with self.lock:
            data = self.all()
            data.pop(run_id, None)
            write_json(self.file, data)

    def datasets(self, defaults: dict) -> dict:
        return {**defaults, **read_json(self.dir / "datasets.json", {})}

    def set_dataset(self, package: str, name: str) -> None:
        with file_lock(self.dir / "datasets.json"):
            data = read_json(self.dir / "datasets.json", {})
            data[package] = name
            write_json(self.dir / "datasets.json", data)
