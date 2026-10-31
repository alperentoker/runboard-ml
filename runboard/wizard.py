"""New-project wizard: browse folders, inspect a folder, and write a ready runboard project from a few answers.

Three kinds of project:
- "yolo": no code needed. runboard writes runboard_train.py (+ rb.py) and a runs file from the chosen dataset,
  models, epochs and seeds.
- "research": a YOLO project planned as a pre-registered study: questions, experiment designs, an evaluation
  protocol and hypotheses (research.py), with plan.yaml and the evaluation scripts.
- "script": the user's own training script; each run is a set of command-line arguments.
"""
from __future__ import annotations

import os
import re
import shutil
import string
from pathlib import Path

import yaml

from .errors import Invalid
from .project import MANIFEST, slugify

HERE = Path(__file__).resolve().parent
RUNS_FILE = "runboard_runs.yaml"
YOLO_MODELS = [f"{f}{s}.pt" for f in ("yolo11", "yolo26", "yolov8") for s in "nsmlx"]
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "env", ".idea", ".vscode", "runs", "wandb"}


# ------------------------------------------------------------ folder browser

def roots() -> list[dict]:
    out = [{"name": "~", "path": str(Path.home())}]
    for name in ("Desktop", "Documents", "Downloads"):
        p = Path.home() / name
        if p.exists():
            out.append({"name": name, "path": str(p)})
    if os.name == "nt":
        out += [{"name": f"{d}:", "path": f"{d}:\\"} for d in string.ascii_uppercase if Path(f"{d}:\\").exists()]
    else:
        out.append({"name": "/", "path": "/"})
    return out


def commands(root: Path) -> list[str]:
    """Everything an existing runboard.yaml would run on this computer, shown before the project is added: a project
    brings commands with it, like a Makefile does."""
    try:
        m = yaml.safe_load((root / MANIFEST).read_text(encoding="utf-8")) or {}
    except Exception as e:
        return [f"(runboard.yaml could not be read: {e})"]
    out = [f"{name}: {(cfg or {}).get('command')}" for name, cfg in (m.get("backends") or {}).items()
           if name == "local" and (cfg or {}).get("command")]
    out += [f"job {k}: {v.get('cmd')}" for k, v in (m.get("jobs") or {}).items() if isinstance(v, dict)]
    if (m.get("results") or {}).get("after"):
        out.append(f"after a run: {m['results']['after']}")
    return out


def listdir(path: str) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.is_dir():
        raise Invalid("not_folder", path=p)
    dirs = []
    try:
        for c in sorted(p.iterdir(), key=lambda x: x.name.lower()):
            if c.is_dir() and not c.name.startswith((".", "$")):
                dirs.append({"name": c.name, "path": str(c), "project": (c / MANIFEST).exists()})
    except PermissionError:
        pass
    return {"path": str(p), "parent": str(p.parent) if p.parent != p else None, "dirs": dirs[:500],
            "project": (p / MANIFEST).exists()}


# ------------------------------------------------------------ inspection

def _walk(root: Path, max_depth: int = 4, limit: int = 4000):
    n = 0
    for dp, dns, fns in os.walk(root):
        rel = Path(dp).relative_to(root)
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".")]
        if len(rel.parts) >= max_depth:
            dns[:] = []
        for f in fns:
            n += 1
            if n > limit:
                return
            yield Path(dp) / f


def scan(path: str) -> dict:
    """What is in the folder: scripts, YOLO dataset files, existing manifest, likely training entry point."""
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise Invalid("not_folder", path=root)
    scripts, datasets, configs, uses_ultra = [], [], [], False
    for f in _walk(root):
        rel = f.relative_to(root).as_posix()
        if f.suffix == ".py":
            scripts.append(rel)
            try:
                head = f.read_text(encoding="utf-8", errors="ignore")[:20000]
                uses_ultra = uses_ultra or "ultralytics" in head
            except OSError:
                pass
        elif f.suffix in (".yaml", ".yml") and f.name != MANIFEST:
            try:
                cfg = yaml.safe_load(f.read_text(encoding="utf-8", errors="ignore")[:20000])
            except Exception:
                cfg = None
            if isinstance(cfg, dict) and "names" in cfg and ("train" in cfg or "val" in cfg):
                n = cfg["names"]
                datasets.append({"file": rel, "classes": list(n.values()) if isinstance(n, dict) else list(n)})
            else:
                configs.append(rel)
    train_like = sorted(scripts, key=lambda s: (not re.search(r"train", s, re.I), s.count("/"), s))
    req = next((r for r in ("requirements.txt", "environment.yml", "pyproject.toml") if (root / r).exists()), None)
    return {"path": str(root), "name": root.name, "has_manifest": (root / MANIFEST).exists(),
            "commands": commands(root) if (root / MANIFEST).exists() else [],
            "scripts": train_like[:200], "datasets": datasets[:50], "configs": configs[:100],
            "ultralytics": uses_ultra, "requirements": req,
            "suggest": "yolo" if datasets else ("script" if scripts else "yolo")}


# ------------------------------------------------------------ generation

def _run_id(model: str, seed: int, seeds: list[int]) -> str:
    stem = Path(model).stem
    return f"{stem}-s{seed}" if len(seeds) > 1 or seed else stem


def build(spec: dict) -> dict[str, str]:
    """Answers -> {relative file name: content}. Pure: nothing is written."""
    return build_all(spec)[0]


def build_all(spec: dict) -> tuple[dict[str, str], dict | None]:
    """The files, and for a research project what the wizard shows about its plan (runs, groups, suggestions)."""
    root = Path(spec["path"]).expanduser().resolve()
    research_meta = None
    if spec.get("kind") == "research":  # a YOLO project underneath; research.build adds the plan to it
        r = spec.get("research") or {}
        pk = r.get("packages") or []
        if not pk:
            raise Invalid("research", problem="add at least one data package (a YOLO data.yaml)")
        spec = {**spec, "yolo": {"data": pk[0]["data"] if pk else None, "models": [r.get("model") or "yolo11s.pt"],
                                 "seeds": [0], "epochs": r.get("epochs", 100), "imgsz": r.get("imgsz", 640),
                                 "batch": r.get("batch", 16), "exclude_test": True}}
    name = (spec.get("name") or root.name).strip()
    key = slugify(spec.get("id") or name)
    kind = spec.get("kind", "yolo")
    backends = [b for b in spec.get("backends", ["local"]) if b in ("local", "kaggle")] or ["local"]
    m: dict = {"name": name, "id": key}
    if spec.get("description"):
        m["description"] = spec["description"]
    if spec.get("color"):
        m["color"] = spec["color"]
    files: dict[str, str] = {}

    if kind in ("yolo", "research"):
        y = spec.get("yolo") or {}
        data = y.get("data")
        if not data or not (root / data).exists():
            raise Invalid("choose_dataset")
        models = [x for x in y.get("models", []) if x in YOLO_MODELS] or ["yolo11n.pt"]
        seeds = sorted({int(s) for s in (y.get("seeds") or [0])})
        runs = {_run_id(mo, s, seeds): {"model": mo, "seed": s} for mo in models for s in seeds}
        dkey = slugify(Path(data).parent.name if Path(data).parent.name else root.name)
        files[RUNS_FILE] = ("# Runs of this project (written by the runboard wizard; edit freely).\n" + yaml.safe_dump(
            {"defaults": {"data": data, "dataset": dkey, "epochs": int(y.get("epochs", 50)), "imgsz": int(y.get("imgsz", 640)),
                          "batch": int(y.get("batch", 16)), "seed": 0}, "runs": runs},
            sort_keys=False, allow_unicode=True, default_flow_style=None))
        files["runboard_train.py"] = (HERE / "templates" / "runboard_train.py").read_text(encoding="utf-8")
        files["rb.py"] = (HERE / "rb.py").read_text(encoding="utf-8")
        m["runs"] = {"file": RUNS_FILE, "section": "runs", "defaults": "defaults", "name": "{id}",
                     "fields": ["model", "seed", "epochs"],
                     "extras": {"prefix": "X", "fields": {"model": {"choices": YOLO_MODELS, "default": models[0]},
                                                          "seed": {"int": [0, 99], "default": 0},
                                                          "epochs": {"int": [1, 1000], "default": int(y.get("epochs", 50))}}}}
        m["backends"] = {}
        if "local" in backends:
            m["backends"]["local"] = {"command": '"{python}" -u runboard_train.py --run {id}', "output_dir": "runs/local"}
        if "kaggle" in backends:
            m["backends"]["kaggle"] = {
                "kernel": f"{key[:30]}-" + "{id|lower}",
                "files": {"runboard_train.py": "runboard_train.py", "rb.py": "rb.py", RUNS_FILE: RUNS_FILE},
                "setup": ["pip install -q ultralytics"], "command": "python -u runboard_train.py --run {id}",
                "accelerator": "NvidiaTeslaT4", "internet": True, "output_dir": "runs/kaggle"}
            ds_root = Path(data).parent.as_posix() or "."
            m["data"] = {"field": "dataset", "packages": [{"key": dkey, "dir": ds_root}],
                         "forbid": ['(^|/)test(/|$)'] if y.get("exclude_test", True) else [],
                         "dataset_prefix": f"{key[:30]}-"}
        m["results"] = {"report": "{out}/summary.json",
                        "metrics": {"primary": "map50_95", "secondary": "map50", "best_epoch": "best_epoch",
                                    "epochs": "epochs", "hours": "hours"},
                        "labels": {"primary": "mAP50-95", "secondary": "mAP50"}, "final": "{out}/summary.json",
                        "per_class": {"path": "per_class", "metric": "map50_95", "scale": 100},
                        "curves": {"file": "{out}/results.csv", "format": "ultralytics"}}
        m["tables"] = [{"title": {"en": "All runs", "tr": "Bütün koşular"}, "runs": list(runs)}]
        m["jobs"] = {"smoke": {"title": {"en": "Smoke test: one short epoch", "tr": "Duman testi: kısa bir epoch"},
                               "cmd": '"{python}" -u runboard_train.py --run {id} --smoke', "per_run": True}}
    else:
        s = spec.get("script") or {}
        script = s.get("file")
        if not script or not (root / script).is_file():
            raise Invalid("choose_script")
        runs = {}
        for r in s.get("runs") or []:
            rid = slugify(r["id"]) if (r.get("id") or "").strip() else f"run{len(runs) + 1}"
            runs[rid] = {"args": r.get("args", "")}
        if not runs:
            raise Invalid("add_run")
        files[RUNS_FILE] = ("# Runs of this project (written by the runboard wizard; edit freely).\n"
                            + yaml.safe_dump({"runs": runs}, sort_keys=False, allow_unicode=True))
        m["runs"] = {"file": RUNS_FILE, "section": "runs", "name": "{id}", "fields": ["args"]}
        m["backends"] = {}
        if "local" in backends:
            m["backends"]["local"] = {"command": f'"{{python}}" -u {script} {{args}}', "output_dir": s.get("output_dir") or "runs/local"}
        if "kaggle" in backends:
            extra = [f for f in s.get("files", []) if (root / f).is_file()]
            m["backends"]["kaggle"] = {
                "kernel": f"{key[:30]}-" + "{id|lower}", "files": {f: f for f in [script, *extra]},
                "setup": [f"pip install -q {p}" for p in s.get("pip", []) if re.fullmatch(r"[\w.\-\[\],=<>~ ]+", p)],
                "command": f"python -u {script} {{args}}", "accelerator": "NvidiaTeslaT4", "internet": True,
                "output_dir": "runs/kaggle"}
            if s.get("data_dir"):
                dk = slugify(Path(s["data_dir"]).name)
                m["data"] = {"field": "dataset", "packages": [{"key": dk, "dir": s["data_dir"]}], "dataset_prefix": f"{key[:30]}-"}
                files[RUNS_FILE] = files[RUNS_FILE].replace("runs:\n", f"defaults:\n  dataset: {dk}\nruns:\n", 1)
                m["runs"]["defaults"] = "defaults"
        if s.get("report"):
            m["results"] = {"report": s["report"], "metrics": {"primary": s.get("metric", "score")},
                            "labels": {"primary": s.get("metric", "score")}}
    if kind == "research":
        from . import research
        research_meta = research.build(spec, files, m, root, "runboard_train.py", RUNS_FILE)
        m = {"version": 2, **{k: v for k, v in m.items() if k != "version"}}
    m["default_backend"] = spec.get("default_backend") if spec.get("default_backend") in m["backends"] else next(iter(m["backends"]))
    files[MANIFEST] = ("# runboard project (written by the wizard). Reference: docs/manifest.md in the runboard repository.\n"
                       + yaml.safe_dump(m, sort_keys=False, allow_unicode=True, width=120))
    return files, research_meta


def create(spec: dict, overwrite: bool = False) -> Path:
    root = Path(spec["path"]).expanduser().resolve()
    files, meta = build_all(spec)
    if meta and meta["problems"]:
        raise Invalid("criterion", problem="; ".join(f"{k}: {v}" for k, v in meta["problems"].items()))
    clash = [f for f in files if (root / f).exists() and f in (MANIFEST, RUNS_FILE, "plan.yaml")]
    if clash and not overwrite:
        raise FileExistsError(f"Already exists: {', '.join(clash)}")
    for rel, content in files.items():
        dst = root / rel
        if dst.exists() and rel not in (MANIFEST, RUNS_FILE):
            shutil.copy2(dst, dst.with_suffix(dst.suffix + ".bak"))
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8", newline="\n")
    if meta and (spec.get("research") or {}).get("lock"):  # pre-registered from the first minute
        from .prereg import lock
        from .project import Project
        lock(Project(root), "wizard")
    return root
