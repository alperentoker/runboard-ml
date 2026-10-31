"""Training-side helper: report progress to runboard. Standalone (stdlib only), so it can be copied next to a
training script or embedded into a Kaggle kernel.

    import rb
    rb.start(epochs=100, batches=798, optimizer="SGD", lr0=0.01)
    rb.stage("Training · epoch 3/100", epoch=3)
    rb.beat(epoch=3, batch=400, batches=798, its=4.9)          # every ~15 s while training
    rb.epoch(3, epochs=100, secs=171, map=48.2, map50=79.5, best=48.2, loss={"box_loss": 1.27})
    rb.done("val mAP50-95 50.79")

For Ultralytics: rb.ultralytics(model) adds callbacks that do all of the above.

Each call prints one line: "@@rb " + JSON. Your own human-readable log lines are unaffected.
"""
from __future__ import annotations

import json
import threading
import time

PREFIX = "@@rb "


def emit(kind: str, **fields) -> None:
    print(PREFIX + json.dumps({"t": kind, "ts": round(time.time(), 1), **fields}, ensure_ascii=False), flush=True)


def start(**fields) -> None:
    emit("start", **fields)


def stage(text: str, **fields) -> None:
    emit("stage", text=text, **fields)


def beat(epoch: int, batch: int, batches: int, its: float) -> None:
    emit("beat", epoch=epoch, batch=batch, batches=batches, its=round(its, 2))


def epoch(e: int, **fields) -> None:
    emit("epoch", epoch=e, **fields)


def done(text: str = "") -> None:
    emit("done", text=text)


def ultralytics(model, every: float = 15.0) -> None:
    """Adds runboard callbacks to an Ultralytics YOLO model before model.train()."""
    st = {"i": 0, "t_ep": 0.0, "durations": [], "trainer": None, "on": False}

    def heartbeat():
        while True:
            time.sleep(every)
            t = st["trainer"]
            if st["on"] and t is not None and st["i"]:
                dt = time.time() - st["t_ep"]
                beat(t.epoch + 1, st["i"], len(t.train_loader), st["i"] / dt if dt > 0 else 0)

    threading.Thread(target=heartbeat, daemon=True).start()

    def on_train_start(t):
        st["trainer"] = t
        opt = getattr(t, "optimizer", None)
        g = opt.param_groups if opt else []
        lrs = sorted({round(x.get("initial_lr", x.get("lr", 0)), 6) for x in g})
        start(epochs=t.epochs, batches=len(t.train_loader), optimizer=type(opt).__name__ if opt else None,
              lr0=lrs[0] if lrs else None)

    def on_train_epoch_start(t):
        st.update(i=0, t_ep=time.time(), on=True)
        stage(f"Training · epoch {t.epoch + 1}/{t.epochs}", epoch=t.epoch + 1)

    def on_train_batch_end(t):
        st["i"] += 1

    def on_train_epoch_end(t):
        st["on"] = False
        stage(f"Validation · epoch {t.epoch + 1}/{t.epochs}")

    def on_fit_epoch_end(t):
        e = t.epoch + 1
        if e <= len(st["durations"]) or e > t.epochs:
            return
        took = time.time() - st["t_ep"]
        st["durations"].append(took)
        m = t.metrics or {}
        left = (t.epochs - e) * sum(st["durations"]) / len(st["durations"])
        epoch(e, epochs=t.epochs, secs=round(took, 1), best=round(100 * (t.best_fitness or 0), 3),
              eta=round(time.time() + left), loss={k: round(float(v), 4) for k, v in (t.tloss or {}).items()},
              metrics={"map": round(100 * m.get("metrics/mAP50-95(B)", 0), 3), "map50": round(100 * m.get("metrics/mAP50(B)", 0), 3),
                       "p": round(100 * m.get("metrics/precision(B)", 0), 3), "r": round(100 * m.get("metrics/recall(B)", 0), 3)})

    def on_train_end(t):
        stage("Training finished; final validation")

    for name, fn in list(locals().items()):
        if name.startswith("on_"):
            model.add_callback(name, fn)


# ---------------------------------------------------------------- evaluation for pre-registered hypotheses
# The evaluation side of docs/design-v2.md: every run is measured on the same bootstrap replicates of a set, so
# runboard can decide hypotheses that compare runs.
#
#     idx = rb.replicates("aerial", ids=[image names in evaluation order])   # list of index lists
#     rb.write_eval("R7", "aerial", {"map50_95": (47.2, [values per replicate])})


def _hash(ids) -> str:
    import hashlib
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


def resample_plan(set_name: str, ids=None, seed: int = 0, replicates: int = 200, root: str = "eval") -> dict:
    """The shared resampling plan of a set: written by the first evaluation (with its image ids), read by the rest,
    which must evaluate the same images."""
    from pathlib import Path
    f = Path(root) / f"resample-{set_name}.json"
    if f.exists():
        plan = json.loads(f.read_text(encoding="utf-8"))
        if ids is not None and sorted(ids) != sorted(plan["ids"]):
            raise ValueError(f"{f}: other images than the plan's")
        return plan
    if ids is None:
        raise ValueError(f"{f} does not exist yet: pass the image ids")
    ids = [str(i) for i in ids]
    plan = {"format": "runboard-resample/1", "set": set_name, "ids_sha256": _hash(ids), "ids": ids,
            "replicates": replicates, "seed": seed,
            "generator": "numpy.random.default_rng(seed).integers(0, n, n) per replicate"}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return plan


def replicates(set_name: str, ids=None, root: str = "eval", **plan_args) -> list:
    """Index lists into the plan's ids, one per replicate (needs numpy). Reorder your per-image results to
    resample_plan(...)["ids"] before using them."""
    import numpy as np
    plan = resample_plan(set_name, ids, root=root, **plan_args)
    rng, n = np.random.default_rng(plan["seed"]), len(plan["ids"])
    return [rng.integers(0, n, n) for _ in range(plan["replicates"])]


def write_eval(run: str, set_name: str, metrics: dict, root: str = "eval", **extra) -> None:
    """metrics: {name: (value on the whole set, [value per replicate])}; a class as "map50_95@person"."""
    from pathlib import Path
    plan = resample_plan(set_name, root=root)
    out = {"format": "runboard-eval/1", "run": run, "set": set_name, "resample": plan["ids_sha256"],
           "metrics": {k: {"point": float(p), "replicates": [None if x != x else float(x) for x in reps]}
                       for k, (p, reps) in metrics.items()}, "n": len(plan["ids"]), **extra}
    f = Path(root) / run / f"{set_name}.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


def sealed(set_name: str, run: str, weights_sha256: str, root: str = "eval", again: bool = False) -> None:
    """Call before evaluating a sealed set (the held-out test): refuses a second use of the same weights unless
    again=True, and writes every use to the ledger runboard shows."""
    import csv
    from datetime import datetime
    from pathlib import Path
    f = Path(root) / "ledger.csv"
    rows = list(csv.DictReader(open(f, encoding="utf-8"))) if f.exists() else []
    if not again and any(r["set"] == set_name and r["weights"] == weights_sha256 for r in rows):
        raise SystemExit(f"{run}: these weights were already evaluated on {set_name}; pass again=True to do it anyway")
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "a", encoding="utf-8", newline="") as out:
        w = csv.writer(out)
        if not rows and (not f.exists() or f.stat().st_size == 0):
            w.writerow(["time", "run", "set", "weights", "again"])
        w.writerow([datetime.now().astimezone().isoformat(timespec="seconds"), run, set_name, weights_sha256,
                    "yes" if again else ""])
