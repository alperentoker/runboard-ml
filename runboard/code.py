"""The project's code in the dashboard: list, read, and (on this computer only) change it.

Only text files of known kinds inside the project, outside data, outputs and environments. A Python file must
compile and a YAML or JSON file must parse before it is written; every save is shown as a diff first, refused if the
file changed meanwhile, backed up and logged. The plan, the runs file and runboard.yaml keep their own editors. Under a
lock, a script the lock covers (one written from a template) changes only as a recorded deviation.

Before a run goes to Kaggle, the Python files sent with it are compiled here, so a typo does not cost cloud quota.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

from .errors import Invalid

EXT = {".py", ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini", ".txt", ".md", ".sh", ".ps1", ".r", ".ipynb"}
SKIP = {".git", "__pycache__", "node_modules", ".venv", "venv", "env", ".idea", ".vscode", "wandb", ".runboard-tmp",
        ".pytest_cache", ".mypy_cache", "site-packages"}
DATA_DIRS = {"images", "labels", "raw", "datasets"}  # YOLO datasets and downloaded originals
CROWDED = 500  # a folder with more files than this is data, not code
MAX_BYTES = 512 * 1024
MAX_FILES = 3000


def _skipped_dirs(project) -> set[Path]:
    """Outputs of every backend and the folders of data packages: large, and not code."""
    out = set()
    for cfg in (project.m.get("backends") or {}).values():
        if isinstance(cfg, dict) and cfg.get("output_dir"):
            out.add((project.root / str(cfg["output_dir"])).resolve())
    out.add((project.root / "runs").resolve())
    data = project.m.get("data") or {}
    for pk in data.get("packages") or []:
        if pk.get("dir") and str(pk["dir"]) not in (".", ""):
            out.add((project.root / str(pk["dir"])).resolve())
    if data.get("dir"):
        out.add((project.root / str(data["dir"])).resolve())
    return out


def special(project) -> dict[str, str]:
    """Files with their own editor on the Settings page."""
    rel = lambda p: p.relative_to(project.root).as_posix()
    out = {"runboard.yaml": "manifest", rel(project.runs_file): "runs"}
    if project.v2:
        out[rel(project.plan_file)] = "plan"
    return out


def listing(project) -> dict:
    from .prereg import record
    from .templating import tracked
    skip, files, more = _skipped_dirs(project), [], False
    tpl, spc = tracked(project), special(project)
    covered = set(((record(project) or {}).get("code") or {}) if project.v2 else {})
    for dp, dns, fns in os.walk(project.root):
        d = Path(dp)
        if len(fns) > CROWDED:  # a dataset that is not declared as one
            dns[:] = []
            continue
        dns[:] = sorted(n for n in dns if n not in SKIP | DATA_DIRS and not n.startswith(".") and (d / n).resolve() not in skip)
        for f in sorted(fns):
            p = d / f
            if p.suffix.lower() not in EXT or f.startswith("."):
                continue
            if len(files) >= MAX_FILES:
                more = True
                break
            rel = p.relative_to(project.root).as_posix()
            size = p.stat().st_size
            files.append({"path": rel, "size": size, "big": size > MAX_BYTES, "template": tpl.get(rel),
                          "special": spc.get(rel), "locked": rel in covered})
    return {"files": files, "more": more}


def resolve(project, path: str) -> Path:
    p = (project.root / str(path).replace("\\", "/")).resolve()
    if project.root not in p.parents or p.suffix.lower() not in EXT:
        raise Invalid("bad_code_path", path=path)
    rel = p.relative_to(project.root).parts
    if any(part in SKIP | DATA_DIRS or part.startswith(".") for part in rel):
        raise Invalid("bad_code_path", path=path)
    return p


def read(project, path: str) -> dict:
    from .runsfile import RunsFile
    from .templating import inspect
    p = resolve(project, path)
    if not p.is_file():
        raise Invalid("bad_code_path", path=path)
    if p.stat().st_size > MAX_BYTES:
        raise Invalid("too_big", path=path, kb=MAX_BYTES // 1024)
    f = RunsFile(p)
    rel = p.relative_to(project.root).as_posix()
    return {"path": rel, "text": f.text, "version": f.version, "template": inspect(p), "special": special(project).get(rel)}


def check_text(path: Path, text: str) -> None:
    """A Python file must compile, YAML and JSON must parse."""
    suf = path.suffix.lower()
    if suf == ".py":
        try:
            compile(text, path.name, "exec", dont_inherit=True)
        except SyntaxError as e:
            raise Invalid("syntax", file=path.name, line=e.lineno or 0, problem=e.msg) from None
    elif suf in (".yaml", ".yml"):
        try:
            yaml.safe_load(text)
        except yaml.YAMLError as e:
            mark = getattr(e, "problem_mark", None)
            raise Invalid("syntax", file=path.name, line=mark.line + 1 if mark else 0,
                          problem=getattr(e, "problem", None) or str(e)) from None
    elif suf in (".json", ".ipynb"):
        try:
            json.loads(text)
        except ValueError as e:
            raise Invalid("syntax", file=path.name, line=getattr(e, "lineno", 0), problem=str(e).split(":")[0]) from None


def save(project, path: str, text: str, version: str | None, dry: bool = False, who: str = "", reason: str = "") -> dict:
    from .prereg import record
    from .runsfile import RunsFile
    p = resolve(project, path)
    rel = p.relative_to(project.root).as_posix()
    if rel in special(project):
        raise Invalid("use_editor", file=rel)
    text = text.replace("\r\n", "\n")
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise Invalid("too_big", path=rel, kb=MAX_BYTES // 1024)
    check_text(p, text)
    covered = project.v2 and rel in ((record(project) or {}).get("code") or {})
    deviation = bool(covered) and project._deviation(reason)
    f = RunsFile(p)
    if not dry:  # a new file may go into a new folder
        p.parent.mkdir(parents=True, exist_ok=True)
    res = project._commit(f, text, None, version, dry, f"edit {rel}", who)
    return project._deviate(res, p, reason, dry, who) if deviation else res


def check_files(project, paths) -> None:
    """Compiles the Python files about to be sent somewhere that costs quota."""
    for src in paths:
        p = (project.root / str(src)).resolve()
        if p.suffix == ".py" and p.is_file():
            check_text(p, p.read_text(encoding="utf-8", errors="replace"))
