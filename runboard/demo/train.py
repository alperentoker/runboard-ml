"""runboard demo: one run trains a small classifier on two interleaving half-moons (synthetic, made here).

The model is logistic regression on polynomial features: "linear" (degree 1) can only draw a straight boundary,
"cubic" (degree 3) can bend around the moons. The seed changes the training sample and the starting weights.
Progress goes to runboard through rb.py; the run writes out/<run>/weights.npz, summary.json and history.csv.

    python train.py --run R1
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from pathlib import Path

import numpy as np
import yaml

import rb

HERE = Path(__file__).resolve().parent
DEGREE = {"linear": 1, "cubic": 3}


def moons(n: int, rng, noise: float) -> tuple[np.ndarray, np.ndarray]:
    """Two interleaving half circles with Gaussian noise; labels 0 and 1."""
    t = rng.uniform(0, np.pi, n)
    y = rng.integers(0, 2, n)
    x = np.where(y[:, None] == 0, np.c_[np.cos(t), np.sin(t)], np.c_[1 - np.cos(t), 0.5 - np.sin(t)])
    return x + rng.normal(0, noise, x.shape), y


def features(x: np.ndarray, degree: int) -> np.ndarray:
    cols = [np.ones(len(x))]
    for d in range(1, degree + 1):
        for i in range(d + 1):
            cols.append(x[:, 0] ** (d - i) * x[:, 1] ** i)
    return np.stack(cols, 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    a = ap.parse_args()
    doc = yaml.safe_load((HERE / "runs.yaml").read_text(encoding="utf-8"))
    spec = {**doc["defaults"], **doc["runs"][a.run]}
    epochs, seed, degree = int(spec["epochs"]), int(spec["seed"]), DEGREE[spec["model"]]
    nap = 0.0 if os.environ.get("RB_DEMO_FAST") else 0.25  # about 10 s a run: slow enough to watch it live

    rng = np.random.default_rng(seed)
    x, y = moons(600, rng, 0.2)
    xv, yv = moons(300, np.random.default_rng(1000 + seed), 0.2)
    f, fv = features(x, degree), features(xv, degree)
    w = rng.normal(0, 0.1, f.shape[1])
    rb.start(epochs=epochs, batches=1, optimizer="gradient descent", lr0=float(spec["lr"]))
    out = HERE / "out" / a.run
    out.mkdir(parents=True, exist_ok=True)
    hist, best, t0 = [], 0.0, time.time()
    for e in range(1, epochs + 1):
        te = time.time()
        p = 1 / (1 + np.exp(-f @ w))
        loss = float(-np.mean(y * np.log(p + 1e-9) + (1 - y) * np.log(1 - p + 1e-9)))
        w -= float(spec["lr"]) * f.T @ (p - y) / len(y)
        acc = float(100 * np.mean((fv @ w > 0) == yv))
        best = max(best, acc)
        time.sleep(nap)
        hist.append({"epoch": e, "val_acc": round(acc, 2), "loss": round(loss, 4)})
        rb.epoch(e, epochs=epochs, secs=round(time.time() - te, 2), best=round(best, 2), loss={"loss": round(loss, 4)},
                 metrics={"map": round(acc, 2)})
        print(f"epoch {e}/{epochs}  loss {loss:.4f}  val accuracy {acc:.1f} %")

    np.savez(out / "weights.npz", w=w, degree=degree)
    with open(out / "history.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=["epoch", "val_acc", "loss"])
        wr.writeheader()
        wr.writerows(hist)
    (out / "summary.json").write_text(json.dumps({"acc": round(acc, 2), "best": round(best, 2), "epochs": epochs,
                                                  "hours": round((time.time() - t0) / 3600, 4)}), encoding="utf-8")
    rb.done(f"val accuracy {acc:.1f} %")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
