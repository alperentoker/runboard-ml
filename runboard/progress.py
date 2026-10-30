"""Turns a training log into live progress.

Two sources, combined:
1. The runboard protocol: lines starting with "@@rb " followed by a JSON event (see runboard/rb.py).
2. Optional regex patterns from the manifest (progress.patterns) for plain-text logs.

Every timestamp is a Unix time, so the dashboard can extrapolate between log lines (batch, ETA) second by second.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

PREFIX = "@@rb "


def hms_secs(s: str) -> int:
    parts = [int(x) for x in s.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


class Parser:
    def __init__(self, cfg: dict | None):
        cfg = cfg or {}
        self.marker = cfg.get("marker")
        self.patterns = {k: re.compile(v) for k, v in (cfg.get("patterns") or {}).items()}
        self.clock = re.compile(cfg["clock"]) if cfg.get("clock") else None
        self.tz = timezone(timedelta(hours=cfg.get("utc_offset", 0)))

    def _clock(self, ln: str, now: datetime) -> float | None:
        m = self.clock.search(ln) if self.clock else None
        if not m:
            return None
        local = now.astimezone(self.tz)
        t = local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(seconds=hms_secs(m["clock"]))
        if t > local + timedelta(minutes=5):  # a line from before midnight
            t -= timedelta(days=1)
        return t.timestamp()

    def parse(self, lines: list[str], written: float | None = None) -> dict:
        """`written`: when a saved log was last written; its clock-only times are placed before that moment."""
        p: dict = {}
        hist: dict[int, dict] = {}
        now = datetime.fromtimestamp(written, timezone.utc) if written else datetime.now(timezone.utc)
        for ln in lines:
            if ln.startswith(PREFIX):
                try:
                    ev = json.loads(ln[len(PREFIX):])
                except json.JSONDecodeError:
                    continue
                self._event(p, hist, ev.pop("t", ""), ev)
                continue
            if not self.patterns or (self.marker and self.marker not in ln):
                continue
            at = self._clock(ln, now)
            for kind, rx in self.patterns.items():
                if m := rx.search(ln):
                    self._event(p, hist, kind, {k: v for k, v in m.groupdict().items() if v is not None}, at)
        p["history"] = [hist[k] for k in sorted(hist)]
        return p

    @staticmethod
    def _num(v):
        try:
            return float(v) if "." in str(v) else int(v)
        except (TypeError, ValueError):
            return v

    def _event(self, p: dict, hist: dict, kind: str, ev: dict, at: float | None = None) -> None:
        n = self._num
        at = ev.get("ts", at)
        if kind == "start":
            p.update({k: n(ev[k]) for k in ("epochs", "batches") if k in ev})
            p.update({k: ev[k] for k in ("optimizer", "lr0") if k in ev})
        elif kind == "epoch":
            e = int(ev["epoch"])
            metrics = {k: n(v) for k, v in (ev.get("metrics") or {}).items()}
            for k in ("map", "map50", "p", "r"):
                if k in ev:
                    metrics[k] = n(ev[k])
            loss = ev.get("loss") or {}
            if isinstance(loss, str):  # plain-text log: "box_loss 1.2 cls_loss 0.8 …"
                loss = dict(re.findall(r"(\w+_loss) ([\d.]+)", loss))
            secs = n(ev["secs"]) if "secs" in ev else hms_secs(ev["time"]) if "time" in ev else None
            hist[e] = {"e": e, **metrics, **{k: n(v) for k, v in loss.items()},
                       **({"secs": secs} if secs is not None else {})}
            p.update(epoch=e, map=metrics.get("map"), map50=metrics.get("map50"), batch=None)
            if "epochs" in ev:
                p["epochs"] = n(ev["epochs"])
            if "best" in ev:
                p["best"] = n(ev["best"])
            if secs is not None:
                p["epoch_secs"] = secs
            if "eta" in ev:
                p["eta_at"] = n(ev["eta"])
        elif kind == "eta":
            if "left" in ev and at:
                p["eta_at"] = at + hms_secs(ev["left"])
            if "eta" in ev:
                p["eta_at"] = n(ev["eta"])
        elif kind == "beat":
            p.update(current_epoch=n(ev["epoch"]), batch=n(ev["batch"]), batches=n(ev["batches"]),
                     its=n(ev.get("its", 0)), beat_at=at)
        elif kind == "stage":
            p.update(stage=ev.get("text", ""), stage_at=at)
            if "epoch" in ev:  # an epoch's training begins
                p.update(current_epoch=n(ev["epoch"]), batch=0, beat_at=at)
        elif kind == "done":
            p["done"] = ev.get("text", "")
        if p.get("best") is None and hist:
            p["best"] = max((h.get("map") or 0) for h in hist.values())

    def human(self, lines: list[str], everything: bool = False) -> list[str]:
        """Log for people: protocol lines hidden; by default only the marker lines (or no progress-bar frames)."""
        lines = [redact(ln) for ln in lines if not ln.startswith(PREFIX)]
        if everything:
            return lines
        if self.marker and any(self.marker in ln for ln in lines):
            keep = [ln for ln in lines if self.marker in ln or re.search(r"Error|Traceback|WARNING", ln)
                    or ln.startswith(("  File", "    "))]
        else:
            keep = [ln for ln in lines if "━" not in ln and "──" not in ln]
        return keep[-400:]


SECRETS = [(re.compile(r"KGAT_[A-Za-z0-9_\-]{6,}"), "KGAT_***"),
           (re.compile(r"""(?i)(api[_-]?key|token|password|secret)(\s*[=:]\s*)['"]?[^\s'"]{6,}"""), r"\1\2***")]


def redact(line: str) -> str:
    """Logs are shown on other devices too; anything that looks like a key or token is masked."""
    for rx, sub in SECRETS:
        line = rx.sub(sub, line)
    return line


def log_lines(text: str) -> list[str]:
    """Kaggle returns a finished run's log as a JSON array of {stream_name, time, data}; live logs as plain text."""
    try:
        events = json.loads(text)
        if isinstance(events, list):
            text = "".join(e.get("data", "") for e in events if isinstance(e, dict))
    except (json.JSONDecodeError, ValueError):
        pass
    return [ln.rstrip() for ln in re.split(r"[\r\n]+", fix_text(text))
            if ln.strip() and not re.search(r"Debugger warning|frozen modules|PYDEVD|debugger miss", ln)]


def fix_text(s: str) -> str:
    """The live stream decodes UTF-8 as latin-1 (EÄitim); undo it when that is what happened."""
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s
