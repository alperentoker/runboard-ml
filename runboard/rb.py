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
