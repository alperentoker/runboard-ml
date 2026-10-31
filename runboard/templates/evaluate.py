"""Evaluate a YOLO detector on each evaluation set, for runboard's hypothesis verdicts.

For every set in PARAMS["sets"] (name: an image list or folder) the model is validated exactly as Ultralytics
validates it (same validator, conf, iou, imgsz), keeping each image's statistics. From them:
  point       mAP50-95, mAP50 and the per-class mAP50-95 on the whole set (checked against Ultralytics' own numbers)
  replicates  the same metrics on each bootstrap replicate of the set's shared resampling plan, so replicate k of
              every run is measured on the same images and runboard can compare runs pairwise
Writes <PARAMS["out"]>/resample-<set>.json (the first time) and <out>/<run>/<set>.json (runboard-eval/1).

Sets in PARAMS["sealed"] are the held-out test: the same weights are evaluated on them once (the ledger,
<out>/ledger.csv); --again overrides that and is written down too.

    python evaluate.py --run R7 --weights runs/R7/weights/best.pt [--sets val] [--again]

Needs numpy and Ultralytics 8.4 or newer (per-image statistics).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np

PARAMS = {}  # runboard: params


# ---------------------------------------------------------------- the shared resampling plan (runboard-resample/1)

def plan_for(set_name: str, ids: list[str]) -> dict:
    f = Path(PARAMS["out"]) / f"resample-{set_name}.json"
    if f.exists():
        plan = json.loads(f.read_text(encoding="utf-8"))
        if sorted(plan["ids"]) != sorted(ids):
            sys.exit(f"{f}: this evaluation saw other images than the plan; the runs could not be compared")
        return plan
    plan = {"format": "runboard-resample/1", "set": set_name,
            "ids_sha256": hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest(), "ids": ids,
            "replicates": int(PARAMS["replicates"]), "seed": int(PARAMS["seed"]),
            "generator": "numpy.random.default_rng(seed).integers(0, n, n) per replicate"}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return plan


def sealed_use(set_name: str, run: str, weights: Path, again: bool) -> None:
    f = Path(PARAMS["out"]) / "ledger.csv"
    sha = hashlib.sha256(weights.read_bytes()).hexdigest()
    rows = list(csv.DictReader(open(f, encoding="utf-8"))) if f.exists() else []
    if not again and any(r["set"] == set_name and r["weights"] == sha for r in rows):
        sys.exit(f"{run}: these weights were already evaluated on the sealed set {set_name} "
                 f"({next(r['time'] for r in rows if r['weights'] == sha)}); --again does it anyway, on the record")
    f.parent.mkdir(parents=True, exist_ok=True)
    new = not f.exists()
    with open(f, "a", encoding="utf-8", newline="") as out:
        w = csv.writer(out)
        if new:
            w.writerow(["time", "run", "set", "weights", "again"])
        w.writerow([datetime.now().astimezone().isoformat(timespec="seconds"), run, set_name, sha, "yes" if again else ""])


# ---------------------------------------------------------------- per-image statistics through Ultralytics

def per_image(weights: Path, images: Path, names: dict, work: Path) -> tuple[dict, list[dict]]:
    from ultralytics import YOLO
    from ultralytics.models.yolo.detect import DetectionValidator
    recs: list[dict] = []

    class Capture(DetectionValidator):
        def init_metrics(self, model):
            super().init_metrics(model)
            if not hasattr(self.metrics, "update_stats"):
                sys.exit("this Ultralytics has no per-image statistics; evaluate.py needs 8.4 or newer")
            keep = self.metrics.update_stats

            def update_stats(stat):
                keep(stat)
                recs.append({k: stat[k] for k in ("tp", "conf", "pred_cls", "target_cls", "im_name")})
            self.metrics.update_stats = update_stats

    data = work / "data.yaml"
    data.write_text(json.dumps({"train": str(images), "val": str(images), "names": names}), encoding="utf-8")
    res = YOLO(str(weights)).val(validator=Capture, data=str(data), split="val", imgsz=int(PARAMS["imgsz"]),
                                 batch=int(PARAMS["batch"]), conf=float(PARAMS["conf"]), iou=float(PARAMS["iou"]),
                                 half=bool(PARAMS["half"]), plots=False, verbose=False, project=str(work), name="val")
    return {"map50_95": 100 * float(res.box.map), "map50": 100 * float(res.box.map50)}, recs


def table(recs: list[dict], names: dict, idx=None) -> dict:
    """mAP50-95, mAP50 and per-class mAP50-95 (percent) from per-image statistics, with Ultralytics' AP routine."""
    from ultralytics.utils.metrics import ap_per_class
    rs = recs if idx is None else [recs[i] for i in idx]
    cat = lambda k, shape: np.concatenate([r[k] for r in rs]) if rs else np.zeros(shape)
    tp, conf, pc, tc = cat("tp", (0, 10)).astype(bool), cat("conf", (0,)), cat("pred_cls", (0,)), cat("target_cls", (0,))
    out = {"map50_95": float("nan"), "map50": float("nan")}
    if not len(tc):
        return out
    r = ap_per_class(tp, conf, pc, tc)
    ap, classes = r[5], r[6]
    out = {"map50_95": round(100 * float(ap.mean()), 3), "map50": round(100 * float(ap[:, 0].mean()), 3)}
    for i, c in enumerate(classes):
        out[f"map50_95@{names[int(c)]}"] = round(100 * float(ap[i].mean()), 3)
    return out


def evaluate_set(run: str, set_name: str, images: Path, weights: Path, names: dict) -> None:
    with tempfile.TemporaryDirectory(prefix="rb-eval-") as tmp:
        official, recs = per_image(weights, images, names, Path(tmp))
    ids = [r["im_name"] for r in recs]
    if len(set(ids)) != len(ids):
        sys.exit(f"{set_name}: two images share a file name; the resampling plan names images by file name")
    plan = plan_for(set_name, ids)
    by = {r["im_name"]: r for r in recs}
    recs = [by[i] for i in plan["ids"]]  # the plan's order, so replicate k picks the same images for every run
    point = table(recs, names)
    if abs(point["map50_95"] - official["map50_95"]) > 1e-3 or abs(point["map50"] - official["map50"]) > 1e-3:
        sys.exit(f"{set_name}: recomputed mAP {point['map50_95']} differs from Ultralytics' {official['map50_95']:.3f}")
    rng, n = np.random.default_rng(plan["seed"]), len(recs)
    reps: dict[str, list] = {k: [] for k in point}
    for _ in range(plan["replicates"]):
        t = table(recs, names, rng.integers(0, n, n))
        for k in reps:
            v = t.get(k, float("nan"))
            reps[k].append(None if v != v else v)
    f = Path(PARAMS["out"]) / run / f"{set_name}.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"format": "runboard-eval/1", "run": run, "set": set_name, "resample": plan["ids_sha256"],
                             "metrics": {k: {"point": point[k], "replicates": reps[k]} for k in point}, "n": n,
                             "weights_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
                             "created": datetime.now().astimezone().isoformat(timespec="seconds")},
                            ensure_ascii=False), encoding="utf-8")
    print(f"{run} {set_name}: mAP50-95 {point['map50_95']:.2f} on {n} images, {plan['replicates']} replicates -> {f}")


def main() -> int:
    import yaml
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--weights", required=True, type=Path)
    ap.add_argument("--sets", nargs="+", default=None, help="default: every set in PARAMS['sets']")
    ap.add_argument("--again", action="store_true", help="evaluate a sealed set again (written to the ledger)")
    a = ap.parse_args()
    if not a.weights.is_file():
        sys.exit(f"{a.weights} does not exist (has the run finished and been collected?)")
    data = yaml.safe_load(Path(PARAMS["data"]).read_text(encoding="utf-8"))
    names = data["names"] if isinstance(data["names"], dict) else dict(enumerate(data["names"]))
    for s in a.sets or list(PARAMS["sets"]):
        if s not in PARAMS["sets"]:
            sys.exit(f"{s} is not one of the sets: {', '.join(PARAMS['sets'])}")
        if s in PARAMS.get("sealed", []):
            sealed_use(s, a.run, a.weights, a.again)
        evaluate_set(a.run, s, Path(PARAMS["sets"][s]).resolve(), a.weights, names)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
