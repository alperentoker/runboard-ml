"""Trains one run from runs.yaml and reports progress to runboard through rb.py."""
import argparse
import json
import sys
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))                    # Kaggle: rb.py is copied next to this file
sys.path.insert(0, str(HERE.parent.parent))      # local: use the package in this repository
try:
    import rb
except ImportError:
    from runboard import rb


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", default=str(HERE / "runs" / "local"))
    a = ap.parse_args()
    doc = yaml.safe_load((HERE / "runs.yaml").read_text())
    spec = {**doc["defaults"], **doc["runs"][a.run]}
    name = f"{a.run}-{Path(spec['model']).stem}-s{spec['seed']}"

    from ultralytics import YOLO

    rb.stage("Loading model")
    model = YOLO(spec["model"])
    rb.ultralytics(model)
    t0 = time.time()
    model.train(data="coco8.yaml", epochs=spec["epochs"], imgsz=spec["imgsz"], seed=spec["seed"],
                project=a.out, name=name, exist_ok=True, verbose=False)
    m = model.trainer.metrics or {}
    summary = {"map50_95": round(100 * m.get("metrics/mAP50-95(B)", 0), 2), "map50": round(100 * m.get("metrics/mAP50(B)", 0), 2),
               "best_epoch": None, "epochs": spec["epochs"], "hours": round((time.time() - t0) / 3600, 3)}
    (Path(a.out) / name / "summary.json").write_text(json.dumps(summary, indent=1))
    rb.done(f"mAP50-95 {summary['map50_95']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
