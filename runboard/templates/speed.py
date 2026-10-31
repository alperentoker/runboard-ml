"""Measure how fast a YOLO model runs: milliseconds per image for preprocessing, inference and postprocessing.

One image at a time (batch 1, the deployment case) at PARAMS["imgsz"], after PARAMS["warmup"] runs that are not
counted, PARAMS["iterations"] times on random images of that size. Reports the median and the 90th percentile of each
stage and of their sum, frames per second from the median, and the software and device it ran on, into
<PARAMS["out"]>/<run>.json. Compare models only on the same device and settings.

    python speed.py --run R7 --weights runs/R7/weights/best.pt
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
from datetime import datetime
from pathlib import Path

PARAMS = {}  # runboard: params


def measure(model, imgsz: int, warmup: int, iterations: int, half: bool, device: str) -> dict:
    import numpy as np
    rng = np.random.default_rng(0)
    stages: dict[str, list[float]] = {"preprocess": [], "inference": [], "postprocess": [], "total": []}
    kw = {"imgsz": imgsz, "half": half, "verbose": False, **({"device": device} if device else {})}
    for i in range(warmup + iterations):
        img = rng.integers(0, 256, (imgsz, imgsz, 3), dtype=np.uint8)
        sp = model.predict(img, **kw)[0].speed
        if i >= warmup:
            for k in ("preprocess", "inference", "postprocess"):
                stages[k].append(float(sp[k]))
            stages["total"].append(sum(float(sp[k]) for k in ("preprocess", "inference", "postprocess")))
    q90 = lambda xs: statistics.quantiles(xs, n=10)[-1] if len(xs) > 1 else xs[0]
    out = {k: {"median_ms": round(statistics.median(v), 3), "p90_ms": round(q90(v), 3)} for k, v in stages.items()}
    out["fps"] = round(1000 / out["total"]["median_ms"], 1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--weights", required=True, type=Path)
    a = ap.parse_args()
    if not a.weights.is_file():
        sys.exit(f"{a.weights} does not exist (has the run finished and been collected?)")
    import torch
    import ultralytics
    from ultralytics import YOLO
    res = measure(YOLO(str(a.weights)), int(PARAMS["imgsz"]), int(PARAMS["warmup"]), int(PARAMS["iterations"]),
                  bool(PARAMS["half"]), str(PARAMS.get("device") or ""))
    env = {"ultralytics": ultralytics.__version__, "torch": torch.__version__, "python": platform.python_version(),
           "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() and PARAMS.get("device") != "cpu"
           else platform.processor() or "cpu"}
    out = Path(PARAMS["out"]) / f"{a.run}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"run": a.run, "weights": str(a.weights), "params": PARAMS, "env": env, **res,
                               "created": datetime.now().astimezone().isoformat(timespec="seconds")},
                              indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{a.run}: {res['total']['median_ms']} ms per image (p90 {res['total']['p90_ms']}), {res['fps']} FPS on {env['device']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
