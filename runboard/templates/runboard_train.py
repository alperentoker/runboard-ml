"""YOLO training script written by the runboard project wizard. Trains one run of runboard_runs.yaml.

    python runboard_train.py --run yolo11n-s0

Works locally and on Kaggle (finds the dataset under /kaggle/input and copies it to fast local disk first).
Progress goes to runboard through rb.py; results land in <out>/<run-name>/ with summary.json for the dashboard.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rb  # noqa: E402

ON_KAGGLE = Path("/kaggle/input").exists()


def dataset_root(yaml_path: Path) -> Path:
    cfg = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    p = cfg.get("path")
    if p and Path(p).is_absolute() and Path(p).exists():
        return Path(p)
    return (yaml_path.parent / p).resolve() if p else yaml_path.parent


def find_on_kaggle(name: str) -> Path:
    """The dataset's own data.yaml under /kaggle/input (Kaggle unzips uploads)."""
    hits = sorted(Path("/kaggle/input").rglob(name))
    if not hits:
        raise SystemExit(f"{name} not found under /kaggle/input — is the dataset attached?")
    return hits[0]


def copy_fast(src: Path, dst: Path) -> None:
    files = [p for p in src.rglob("*") if p.is_file()]
    for d in {dst / p.parent.relative_to(src) for p in files}:
        d.mkdir(parents=True, exist_ok=True)
    rb.stage(f"Copying dataset to local disk ({len(files)} files)")
    with ThreadPoolExecutor(32) as ex:
        list(ex.map(lambda p: shutil.copyfile(p, dst / p.relative_to(src)), files))


def prepare_data(rel: str) -> Path:
    """Returns a data.yaml whose 'path' points at a real local folder."""
    if ON_KAGGLE:
        src_yaml = find_on_kaggle(Path(rel).name)
        root = src_yaml.parent
        work = Path("/tmp/rb-data")
        if not work.exists():
            copy_fast(root, work)
        root, src_yaml = work, work / src_yaml.name
    else:
        src_yaml = (HERE / rel).resolve()
        root = dataset_root(src_yaml)
    cfg = yaml.safe_load(src_yaml.read_text(encoding="utf-8"))
    cfg["path"] = str(root)
    out = Path(os.environ.get("TMPDIR", "/tmp" if ON_KAGGLE else HERE / ".runboard-tmp")) / "data.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", default="/kaggle/working" if ON_KAGGLE else str(HERE / "runs" / "local"))
    a = ap.parse_args()
    doc = yaml.safe_load((HERE / "runboard_runs.yaml").read_text(encoding="utf-8"))
    spec = {**(doc.get("defaults") or {}), **doc["runs"][a.run]}
    name = a.run

    rb.stage("Preparing data")
    data = prepare_data(spec["data"])
    from ultralytics import YOLO

    rb.stage(f"Loading {spec['model']}")
    model = YOLO(spec["model"])
    rb.ultralytics(model)
    t0 = time.time()
    model.train(data=str(data), epochs=int(spec.get("epochs", 50)), imgsz=int(spec.get("imgsz", 640)),
                batch=spec.get("batch", 16), seed=int(spec.get("seed", 0)), deterministic=True,
                project=a.out, name=name, exist_ok=True, verbose=False, device=0 if _cuda() else "cpu")
    hours = (time.time() - t0) / 3600
    run_dir = Path(a.out) / name
    rb.stage("Final validation of best.pt")
    res = YOLO(run_dir / "weights" / "best.pt").val(data=str(data), verbose=False, plots=False,
                                                    project=str(run_dir), name="final", exist_ok=True)
    best_epoch = None
    try:
        import csv
        with open(run_dir / "results.csv", encoding="utf-8") as f:
            rows = [{k.strip(): v for k, v in r.items()} for r in csv.DictReader(f)]
        best_epoch = int(float(max(rows, key=lambda r: float(r["metrics/mAP50-95(B)"]))["epoch"]))
    except Exception:
        pass
    summary = {"map50_95": round(100 * float(res.box.map), 2), "map50": round(100 * float(res.box.map50), 2),
               "precision": round(float(res.box.mp), 4), "recall": round(float(res.box.mr), 4),
               "best_epoch": best_epoch, "epochs": int(spec.get("epochs", 50)), "hours": round(hours, 2),
               "per_class": {res.names[int(c)]: {"map50_95": float(res.box.maps[int(c)])} for c in res.box.ap_class_index}}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    rb.done(f"mAP50-95 {summary['map50_95']} · mAP50 {summary['map50']}")
    print(f"done: {run_dir}")
    return 0


def _cuda() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
