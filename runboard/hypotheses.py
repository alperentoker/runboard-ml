"""Hypotheses checked by machine (docs/design-v2.md, sections 2 and 3).

A criterion such as `R7.aerial >= 0.9 * R5.aerial` is parsed with `ast` against a whitelist and computed by the walker
below, never by `eval`. Every number in it is a Vec: its value on the whole evaluation set and on each bootstrap
replicate of the shared resampling plan, so replicate k of every run was measured on the same images and any
combination of runs is paired. A comparison decides through its margin (left − right for > and >=): supported when
the whole 95 % interval of the margin is above zero, refuted when it is below, indistinguishable otherwise.

Evidence lives under protocol.dir (default `eval/`):
  resample-<set>.json   runboard-resample/1: image ids, seed, number of replicates
  <run>/<set>.json      runboard-eval/1: per metric {point, replicates}
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path

from .errors import Invalid

FUNCTIONS = {
    "collapse": "collapse(R, a, b) = 100 · (R.a − R.b) / R.a: the share of R's score on a that is lost on b",
    "mean": "mean(x, y, …): the average, replicate by replicate",
    "min": "min(x, y, …)", "max": "max(x, y, …)", "abs": "abs(x)",
    "log_fit": "log_fit({R: x, …}, set): least-squares fit of score = a + slope · ln(x); .slope and .r2",
}
OPS = {ast.Gt: ">", ast.GtE: ">=", ast.Lt: "<", ast.LtE: "<="}
NAN = float("nan")


# ---------------------------------------------------------------- numbers with replicates

def percentile(xs: list[float], q: float) -> float:
    """numpy.nanpercentile with the default (linear) method, to the last bit: the same interval as a numpy script."""
    v = sorted(x for x in xs if x is not None and not math.isnan(x))
    if not v:
        return NAN
    pos = (len(v) - 1) * (q / 100)  # numpy's virtual index for "linear", in its order of operations
    lo = min(max(math.floor(pos), 0), len(v) - 1)
    hi = min(lo + 1, len(v) - 1)
    t = pos - math.floor(pos)
    a, b = v[lo], v[hi]
    d = b - a
    return b - d * (1 - t) if t >= 0.5 else a + d * t


class Vec:
    """A value on the full set and on each replicate (None: the same on every replicate, a constant)."""
    __slots__ = ("point", "reps")

    def __init__(self, point: float, reps: list[float] | None = None):
        self.point, self.reps = float(point), reps

    @staticmethod
    def of(x) -> "Vec":
        return x if isinstance(x, Vec) else Vec(x)

    def each(self, n: int) -> list[float]:
        return self.reps if self.reps is not None else [self.point] * n

    @staticmethod
    def apply(f, *vs: "Vec") -> "Vec":
        vs = [Vec.of(v) for v in vs]
        n = next((len(v.reps) for v in vs if v.reps is not None), None)
        point = _safe(f, *(v.point for v in vs))
        if n is None:
            return Vec(point)
        if any(v.reps is not None and len(v.reps) != n for v in vs):
            raise Invalid("criterion", problem="replicate counts differ between the runs compared")
        return Vec(point, [_safe(f, *xs) for xs in zip(*(v.each(n) for v in vs))])

    def interval(self) -> list[float] | None:
        return None if self.reps is None else [percentile(self.reps, 2.5), percentile(self.reps, 97.5)]


def _safe(f, *xs):
    if any(x is None or math.isnan(x) for x in xs):
        return NAN
    try:
        return float(f(*xs))
    except (ZeroDivisionError, ValueError, OverflowError):
        return NAN


def _num(x):
    return NAN if x is None else float(x)


# ---------------------------------------------------------------- evidence on disk

def ids_hash(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


_JSON: dict[str, tuple] = {}


def _read(p: Path):
    st = p.stat()
    sig = (st.st_mtime_ns, st.st_size)
    hit = _JSON.get(str(p))
    if not hit or hit[0] != sig:
        hit = (sig, json.loads(p.read_text(encoding="utf-8")))
        _JSON[str(p)] = hit
        while len(_JSON) > 256:
            _JSON.pop(next(iter(_JSON)))
    return hit[1]


class Evidence:
    """The protocol's evaluation files. Missing files are collected (the hypothesis is not ready); files that do not
    belong to the resampling plan are errors."""

    def __init__(self, root: Path, protocol: dict):
        self.dir = Path(root) / str(protocol.get("dir") or "eval")
        self.metric = str(protocol.get("metric") or "map50_95")
        sets = protocol.get("sets") or []
        self.sets = {str(s): {} for s in sets} if isinstance(sets, list) else {str(k): dict(v or {}) for k, v in sets.items()}
        self.missing: list[str] = []

    def plan(self, s: str) -> dict | None:
        f = self.dir / f"resample-{s}.json"
        if not f.is_file():
            return None
        p = _read(f)
        if p.get("format") != "runboard-resample/1" or ids_hash(p.get("ids") or []) != p.get("ids_sha256"):
            raise Invalid("evidence", file=f.relative_to(self.dir.parent).as_posix(), problem="not a valid resampling plan")
        return p

    def get(self, run: str, s: str, metric: str | None) -> Vec:
        if self.sets and s not in self.sets:
            raise Invalid("criterion", problem=f"'{s}' is not an evaluation set of the protocol ({', '.join(self.sets)})")
        metric = metric or self.metric
        f = self.dir / run / f"{s}.json"
        plan = self.plan(s)
        if not f.is_file() or plan is None:
            self.missing.append(f"{run}.{s}")
            return Vec(NAN, None)
        rel = f.relative_to(self.dir.parent).as_posix()
        d = _read(f)
        if d.get("format") != "runboard-eval/1":
            raise Invalid("evidence", file=rel, problem="not runboard-eval/1")
        if d.get("resample") != plan["ids_sha256"]:
            raise Invalid("evidence", file=rel, problem=f"measured on other images than resample-{s}.json")
        m = (d.get("metrics") or {}).get(metric)
        if m is None:
            raise Invalid("evidence", file=rel, problem=f"no metric '{metric}' (has {', '.join(d.get('metrics') or {})})")
        if m.get("replicates") is not None:
            reps = [_num(x) for x in m["replicates"]]
        elif m.get("samples") is not None:  # a mean over images: the replicates are drawn here
            reps = self._draw([_num(x) for x in m["samples"]], plan)
        else:
            raise Invalid("evidence", file=rel, problem=f"'{metric}' has neither replicates nor samples")
        if len(reps) != plan["replicates"]:
            raise Invalid("evidence", file=rel, problem=f"{len(reps)} replicates, the plan has {plan['replicates']}")
        return Vec(_num(m["point"]), reps)

    @staticmethod
    def _draw(samples: list[float], plan: dict) -> list[float]:
        try:
            import numpy as np
        except ImportError:
            raise Invalid("evidence", file="", problem="per-image samples need numpy to draw the replicates") from None
        rng, n = np.random.default_rng(plan["seed"]), len(samples)
        arr = np.array(samples, float)
        return [float(np.nanmean(arr[rng.integers(0, n, n)])) for _ in range(plan["replicates"])]


# ---------------------------------------------------------------- the criterion language

ALLOWED = (ast.Expression, ast.BoolOp, ast.And, ast.Compare, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div,
           ast.MatMult, ast.UnaryOp, ast.USub, ast.UAdd, ast.Constant, ast.Name, ast.Attribute, ast.Call, ast.Dict,
           ast.Load, *OPS)


def parse(text: str) -> ast.Expression:
    try:
        tree = ast.parse(str(text).strip(), mode="eval")
    except SyntaxError as e:
        raise Invalid("criterion", problem=f"cannot read it ({e.msg})") from None
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED):
            raise Invalid("criterion", problem=f"'{type(node).__name__}' is not part of the criterion language")
        if isinstance(node, ast.Constant) and (isinstance(node.value, bool) or not isinstance(node.value, (int, float))):
            raise Invalid("criterion", problem=f"only numbers are allowed as values, not {node.value!r}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise Invalid("criterion", problem=f"'{node.attr}' is not a set or a metric")
        if isinstance(node, ast.Compare) and len(node.ops) != 1:
            raise Invalid("criterion", problem="one comparison at a time; join them with 'and'")
        if isinstance(node, ast.Call) and (not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS
                                           or node.keywords):
            raise Invalid("criterion", problem=f"unknown function (known: {', '.join(FUNCTIONS)})")
    body = tree.body
    parts = body.values if isinstance(body, ast.BoolOp) else [body]
    if not all(isinstance(p, ast.Compare) for p in parts):
        raise Invalid("criterion", problem="a criterion is a comparison, or several joined with 'and'")
    return tree


class Walker:
    def __init__(self, ev: Evidence, groups: dict, src: str):
        self.ev, self.groups, self.src = ev, groups, src
        self.used_groups: dict[str, list] = {}
        self.functions: set[str] = set()

    def value(self, n) -> Vec:
        if isinstance(n, ast.Constant):
            return Vec(n.value)
        if isinstance(n, ast.UnaryOp):
            v = self.value(n.operand)
            return Vec.apply(lambda x: -x, v) if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.BinOp) and not isinstance(n.op, ast.MatMult):
            f = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
                 ast.Div: lambda a, b: a / b}[type(n.op)]
            return Vec.apply(f, self.value(n.left), self.value(n.right))
        if isinstance(n, ast.Call):
            return self.call(n)
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Call) and n.value.func.id == "log_fit":
            if n.attr not in ("slope", "r2"):
                raise Invalid("criterion", problem="log_fit(...) has .slope and .r2")
            return self.log_fit(n.value)[n.attr]
        run, s, metric, cls = self.ref(n)
        return self.score(run, s, metric, cls)

    def ref(self, n) -> tuple[str, str, str | None, str | None]:
        """R7.aerial, R7.aerial.map50, R7.aerial@person, R7.aerial.map50@person"""
        cls = None
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.MatMult):
            if not isinstance(n.right, ast.Name):
                raise Invalid("criterion", problem="a class follows '@' by name: R7.aerial@person")
            n, cls = n.left, n.right.id
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
            return n.value.id, n.attr, None, cls
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Attribute) and isinstance(n.value.value, ast.Name):
            return n.value.value.id, n.value.attr, n.attr, cls
        if isinstance(n, ast.Name):
            raise Invalid("criterion", problem=f"{n.id} needs an evaluation set, as in {n.id}.{next(iter(self.ev.sets), 'val')}")
        raise Invalid("criterion", problem=f"cannot read '{ast.get_source_segment(self.src, n) or ast.dump(n)}'")

    def score(self, run: str, s: str, metric: str | None, cls: str | None) -> Vec:
        name = (metric or self.ev.metric) + (f"@{cls}" if cls else "")
        if run in self.groups:  # a seed group: the mean of its runs, replicate by replicate (same images)
            vs = [self.ev.get(str(r), s, name) for r in self.groups[run]]
            self.used_groups.setdefault(f"{run}.{s}" + (f".{metric}" if metric else "") + (f"@{cls}" if cls else ""),
                                        [(str(r), v.point) for r, v in zip(self.groups[run], vs)])
            return Vec.apply(lambda *xs: sum(xs) / len(xs), *vs)
        return self.ev.get(run, s, name)

    def run_arg(self, n) -> tuple[str, str | None]:
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.MatMult) and isinstance(n.left, ast.Name) \
                and isinstance(n.right, ast.Name):
            return n.left.id, n.right.id
        if isinstance(n, ast.Name):
            return n.id, None
        raise Invalid("criterion", problem="collapse takes a run (or run@class) and two sets: collapse(R4, ground, aerial)")

    def call(self, n: ast.Call) -> Vec:
        f = n.func.id
        self.functions.add(f)
        if f == "collapse":
            if len(n.args) != 3 or not all(isinstance(a, ast.Name) for a in n.args[1:]):
                raise Invalid("criterion", problem="collapse(run, from_set, to_set)")
            run, cls = self.run_arg(n.args[0])
            a, b = self.score(run, n.args[1].id, None, cls), self.score(run, n.args[2].id, None, cls)
            return Vec.apply(lambda x, y: 100 * (x - y) / x, a, b)
        if f == "log_fit":
            raise Invalid("criterion", problem="use log_fit(...).slope or log_fit(...).r2")
        vs = [self.value(a) for a in n.args]
        if not vs or (f == "abs" and len(vs) != 1):
            raise Invalid("criterion", problem=f"{f} needs {'one value' if f == 'abs' else 'values'}")
        fn = {"mean": lambda *xs: sum(xs) / len(xs), "min": min, "max": max, "abs": abs}[f]
        return Vec.apply(fn, *vs)

    def log_fit(self, n: ast.Call) -> dict[str, Vec]:
        self.functions.add("log_fit")
        if len(n.args) != 2 or not isinstance(n.args[0], ast.Dict) or not isinstance(n.args[1], ast.Name):
            raise Invalid("criterion", problem="log_fit({R6: 10, R7: 25, …}, set)")
        pts = []
        for k, v in zip(n.args[0].keys, n.args[0].values):
            if not isinstance(k, (ast.Name, ast.BinOp)) or not isinstance(v, ast.Constant) or v.value <= 0:
                raise Invalid("criterion", problem="log_fit points are run: x with x above 0")
            run, cls = self.run_arg(k)
            pts.append((math.log(v.value), self.score(run, n.args[1].id, None, cls)))
        if len(pts) < 3:
            raise Invalid("criterion", problem="log_fit needs at least three points")
        xs = [x for x, _ in pts]

        def fit(*ys):
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            sxx = sum((x - mx) ** 2 for x in xs)
            slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
            ss_tot = sum((y - my) ** 2 for y in ys)
            ss_res = sum((y - (my + slope * (x - mx))) ** 2 for x, y in zip(xs, ys))
            return slope, (1 - ss_res / ss_tot) if ss_tot else NAN
        ys = [v for _, v in pts]
        return {"slope": Vec.apply(lambda *y: fit(*y)[0], *ys), "r2": Vec.apply(lambda *y: fit(*y)[1], *ys)}


def verdict_of(margin: Vec) -> str:
    ci = margin.interval()
    lo, hi = (ci if ci else [margin.point, margin.point])
    if math.isnan(lo) or math.isnan(hi):
        return "indistinguishable"
    return "supported" if lo > 0 else "refuted" if hi < 0 else "indistinguishable"


def decide(criterion: str, ev: Evidence, groups: dict) -> dict:
    """One hypothesis: a verdict per comparison and for the whole criterion."""
    tree = parse(criterion)
    src = str(criterion).strip()
    w = Walker(ev, {str(k): list(v) for k, v in (groups or {}).items()}, src)
    body = tree.body
    parts = []
    ev.missing = []
    for cmp in (body.values if isinstance(body, ast.BoolOp) else [body]):
        op = OPS[type(cmp.ops[0])]
        left, right = w.value(cmp.left), w.value(cmp.comparators[0])
        margin = Vec.apply(lambda a, b: a - b, left, right) if op in (">", ">=") else \
            Vec.apply(lambda a, b: b - a, left, right)
        ci = margin.interval()
        share = None if margin.reps is None else \
            round(100 * sum(1 for x in margin.reps if not math.isnan(x) and x > 0) / len(margin.reps), 1)
        parts.append({"text": ast.get_source_segment(src, cmp), "op": op,
                      "left": _r(left.point), "right": _r(right.point), "margin": _r(margin.point),
                      "ci": [_r(x) for x in ci] if ci else None, "share": share, "verdict": verdict_of(margin)})
    missing = sorted(set(ev.missing))
    if missing:
        verdict = "not_ready"
    elif any(p["verdict"] == "refuted" for p in parts):
        verdict = "refuted"
    elif all(p["verdict"] == "supported" for p in parts):
        verdict = "supported"
    else:
        verdict = "indistinguishable"
    groups_out = {k: {"runs": [r for r, _ in v], "points": [_r(p) for _, p in v], "sd": _r(_sd([p for _, p in v]))}
                  for k, v in w.used_groups.items()}
    return {"verdict": verdict, "parts": [] if missing else parts, "missing": missing, "groups": groups_out,
            "functions": {f: FUNCTIONS[f] for f in sorted(w.functions)}}


def _r(x: float | None, d: int = 3):
    return None if x is None or math.isnan(x) else round(x, d)


def _sd(xs: list[float]) -> float:
    xs = [x for x in xs if not math.isnan(x)]
    if len(xs) < 2:
        return NAN
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))
