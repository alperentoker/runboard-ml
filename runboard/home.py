"""runboard's own directory (~/.runboard): project registry, paired devices, per-project state.

Nothing here ever lives inside a project repository, so projects stay clean and nothing private gets committed.
Override the location with the RUNBOARD_HOME environment variable.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import yaml

HOME = Path(os.environ.get("RUNBOARD_HOME", Path.home() / ".runboard"))
CONFIG = HOME / "config.yaml"
_lock = threading.Lock()


def read_json(p: Path, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def write_json(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(p)


def config() -> dict:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else None
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
        if str(path) not in cfg["projects"]:
            cfg["projects"].append(str(path))
            save_config(cfg)


def unregister(path: Path) -> None:
    with _lock:
        cfg = config()
        cfg["projects"] = [p for p in cfg["projects"] if Path(p).resolve() != path.resolve()]
        save_config(cfg)


class State:
    """Per-project state: run records, live logs on disk, dataset mapping, runs-file backups."""

    def __init__(self, key: str):
        self.dir = HOME / "state" / key
        self.file = self.dir / "state.json"
        self.logs = self.dir / "logs"
        self.lock = threading.Lock()

    def all(self) -> dict:
        return read_json(self.file, {})

    def get(self, run_id: str) -> dict:
        return self.all().get(run_id, {})

    def update(self, run_id: str, **fields) -> None:
        with self.lock:
            data = self.all()
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
        with self.lock:
            data = read_json(self.dir / "datasets.json", {})
            data[package] = name
            write_json(self.dir / "datasets.json", data)
