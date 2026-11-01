"""runboard demo: evaluates every finished run on two fixed sets, the way the hypotheses need it.

  clean    new moons from the same distribution as the training data
  shifted  the same kind of data, turned by 30 degrees and noisier: a small change of domain

Every item is scored 100 (right) or 0 (wrong); runboard draws the bootstrap replicates from these per-item scores
with each set's shared resampling plan (eval/resample-<set>.json), so every run is compared on the same items.

    python evaluate.py            # every run that has finished and has no evaluation yet
    python evaluate.py --again    # all of them again
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

import rb
from train import features, moons

HERE = Path(__file__).resolve().parent


def sets() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    x, y = moons(400, np.random.default_rng(12345), 0.2)
    xs, ys = moons(400, np.random.default_rng(54321), 0.3)
    a = np.radians(30)
    turn = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    return {"clean": (x, y), "shifted": ((xs - 0.5) @ turn.T + 0.5, ys)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--again", action="store_true")
    a = ap.parse_args()
    data = sets()
    eval_dir = HERE / "eval"
    for name, (x, _) in data.items():
        rb.resample_plan(name, ids=[f"{name}-{i:04d}" for i in range(len(x))], seed=0, replicates=200, root=str(eval_dir))
    done = 0
    for weights in sorted((HERE / "out").glob("*/weights.npz")):
        run = weights.parent.name
        if not a.again and all((eval_dir / run / f"{s}.json").exists() for s in data):
            continue
        m = np.load(weights)
        for name, (x, y) in data.items():
            right = ((features(x, int(m["degree"])) @ m["w"] > 0) == y) * 100.0
            rb.write_samples(run, name, {"acc": right.tolist()}, root=str(eval_dir))
        print(f"{run}: clean {np.mean(((features(data['clean'][0], int(m['degree'])) @ m['w'] > 0) == data['clean'][1])) * 100:.1f} %")
        done += 1
    print(f"evaluated {done} run(s); open the Hypotheses page")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
