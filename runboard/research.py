"""The research wizard: questions, experiment designs, an evaluation protocol and hypotheses become a pre-registered
runboard project (manifest v2) in one step.

Designs turn into runs, phases, tables and seed groups:
  transfer      one specialist per data package (how far does each fall on the others?)
  curve         a base package plus growing, nested shares of another (written by the subsets template)
  architecture  several models on one package
  ablation      one training setting at several values
Every design can repeat its runs with more seeds; the repeats form a group (R4_seeds) a criterion can name.

The evaluation template is always written (it produces what the verdicts read); subsets when a curve needs it, check
on request. Criteria are checked against the planned runs and sets before anything is written.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

from .errors import Invalid
from .project import slugify

DESIGNS = ("transfer", "curve", "architecture", "ablation")
TITLES = {"transfer": {"en": "Specialists", "tr": "Uzmanlar"}, "curve": {"en": "Data-size curve", "tr": "Veri miktarı eğrisi"},
          "architecture": {"en": "Architectures", "tr": "Mimariler"}, "ablation": {"en": "Ablation", "tr": "Ablasyon"}}


def _ints(v) -> list[int]:
    return [int(x) for x in (v if isinstance(v, list) else str(v or "").replace(";", ",").split(",")) if str(x).strip()]


def _floats(v) -> list[float]:
    return [float(x) for x in (v if isinstance(v, list) else str(v or "").replace(";", ",").split(",")) if str(x).strip()]


def _yaml_value(s: str):
    try:
        return yaml.safe_load(s)
    except yaml.YAMLError:
        return s


def _train_list(root: Path, data_yaml: str) -> str:
    """A package's training list, relative to the project (what the subsets template samples from)."""
    f = root / data_yaml
    d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    base = f.parent / d["path"] if d.get("path") else f.parent
    return Path(os.path.relpath((base / d["train"]).resolve(), root)).as_posix()


def plan_runs(r: dict, root: Path) -> dict:
    """Runs, phases, tables, groups and suggested hypotheses from the designs."""
    pk = {p["key"]: p["data"] for p in r.get("packages") or []}
    if not pk:
        raise Invalid("research", problem="add at least one data package (a YOLO data.yaml)")
    model0 = r.get("model") or "yolo11s.pt"
    runs, phases, tables, groups, suggest, templates = {}, [], [], {}, [], {}
    n = 0

    def add(spec: dict, seeds: list[int]) -> str:
        nonlocal n
        n += 1
        rid = f"R{n}"
        runs[rid] = dict(spec)
        if len(seeds) > 1:
            runs[rid]["seed"] = seeds[0]
            for s in seeds[1:]:
                runs[f"{rid}s{s}"] = {**spec, "seed": s}
            groups[f"{rid}_seeds"] = [rid] + [f"{rid}s{s}" for s in seeds[1:]]
        elif seeds and seeds[0]:
            runs[rid]["seed"] = seeds[0]
        return rid

    for i, d in enumerate(r.get("designs") or [], 1):
        kind = d.get("type")
        if kind not in DESIGNS:
            raise Invalid("research", problem=f"design {i}: unknown type {kind!r}")
        seeds = _ints(d.get("seeds")) or [0]
        model = d.get("model") or model0
        title = {k: f"{v} ({d['question']})" if d.get("question") else v for k, v in TITLES[kind].items()}
        made: list[str] = []

        def need(key):
            if key not in pk:
                raise Invalid("research", problem=f"design {i}: no data package called {key!r}")
            return pk[key]
        if kind == "transfer":
            keys = d.get("packages") or list(pk)
            for key in keys:
                made.append(add({"data": need(key), "model": model, "package": key}, seeds))
            if len(keys) >= 2:
                a, b = keys[0], keys[1]
                ra, rb = made[0], made[1]
                suggest.append({"question": d.get("question"), "text": f"{a} → {b} collapses more than {b} → {a}",
                                "criterion": f"collapse({ra}, {a}, {b}) > collapse({rb}, {b}, {a})", "sets": [a, b]})
        elif kind == "curve":
            base, extra = d.get("base"), d.get("add")
            fr = sorted(_floats(d.get("fractions") or "0.1, 0.25, 0.5"))
            if not fr or not all(0 < f <= 1 for f in fr):
                raise Invalid("research", problem=f"design {i}: fractions between 0 and 1")
            need(extra)
            prefix = f"curve{i}_"
            templates[f"scripts/subsets_{i}.py"] = ("subsets", {
                "add": _train_list(root, pk[extra]), "base": _train_list(root, need(base)) if base else "",
                "fractions": fr, "seed": 0, "group": d.get("group") or "", "data": pk[extra],
                "out": Path(pk[extra]).parent.as_posix() or ".", "prefix": prefix})
            xs = {}
            for f in fr:
                out_dir = Path(pk[extra]).parent
                rid = add({"data": (out_dir / f"{prefix}{round(f * 100)}.yaml").as_posix(), "model": model,
                           "package": f"{base or ''}+{extra} {round(f * 100)}%"}, seeds)
                made.append(rid)
                xs[rid] = round(f * 100)
            if len(made) >= 3:
                pts = ", ".join(f"{k}: {v}" for k, v in xs.items())
                suggest.append({"question": d.get("question"), "text": f"{extra} accuracy grows with the logarithm of the {extra} data",
                                "criterion": f"log_fit({{{pts}}}, {extra}).r2 >= 0.9", "sets": [extra]})
            if len(made) >= 2:
                suggest.append({"question": d.get("question"), "text": f"more {extra} data helps on {extra}",
                                "criterion": f"{made[-1]}.{extra} > {made[0]}.{extra}", "sets": [extra]})
            tables.append({"title": title, "runs": made, "curve": {"x": xs, "label": {"en": f"{extra} share (%)", "tr": f"{extra} payı (%)"}}})
        elif kind == "architecture":
            key = d.get("package") or next(iter(pk))
            for m in d.get("models") or [model]:
                made.append(add({"data": need(key), "model": m, "package": key}, seeds))
        else:  # ablation
            key, field = d.get("package") or next(iter(pk)), str(d.get("field") or "").strip()
            values = [_yaml_value(v.strip()) for v in str(d.get("values") or "").split(",") if v.strip()]
            if not field or len(values) < 2:
                raise Invalid("research", problem=f"design {i}: a setting and at least two values")
            for v in values:
                made.append(add({"data": need(key), "model": model, "package": key, "train": {field: v}}, seeds))
            set0 = key
            suggest.append({"question": d.get("question"), "text": f"{field}={values[0]} beats {field}={values[1]}",
                            "criterion": f"{made[0]}.{set0} > {made[1]}.{set0}", "sets": [set0]})
        phases.append({"id": d.get("question") or f"D{i}", "title": title, "subtitle": kind, "runs": made})
        if kind != "curve":
            tables.append({"title": title, "runs": made})
        mine = [g for g in groups if g.split("_seeds")[0] in made]
        if mine:
            tables.append({"title": {k: f"{v} · seeds" for k, v in title.items()},
                           "groups": [{"label": g, "runs": groups[g]} for g in mine]})
    if not runs:
        raise Invalid("research", problem="add at least one experiment design")
    return {"runs": runs, "phases": phases, "tables": tables, "groups": groups, "suggest": suggest, "templates": templates}


def sets_of(protocol: dict) -> dict[str, str]:
    raw = protocol.get("sets") or {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    pairs = [p.split("=", 1) for p in str(raw).split(",") if p.strip()]
    if any(len(p) != 2 for p in pairs):
        raise Invalid("research", problem="evaluation sets as name=list, name=list")
    return {a.strip(): b.strip() for a, b in pairs}


def build(spec: dict, files: dict, m: dict, root: Path, train_script: str, runs_file: str) -> dict:
    """Adds the research parts to the wizard's YOLO project: runs, plan.yaml, templates. Returns what the wizard shows."""
    from . import templating
    from .hypotheses import check
    r = spec.get("research") or {}
    plan = plan_runs(r, root)
    pr = r.get("protocol") or {}
    sets = sets_of(pr)
    sealed = [s.strip() for s in str(pr.get("sealed") or "").split(",") if s.strip()]
    if not sets:
        raise Invalid("research", problem="name at least one evaluation set (name=list of images)")
    if any(s not in sets for s in sealed):
        raise Invalid("research", problem="a sealed set must be one of the evaluation sets")

    questions = [{"id": str(q["id"]).strip(), "text": q.get("text") or ""} for q in r.get("questions") or [] if str(q.get("id") or "").strip()]
    hyps, problems = [], {}
    for h in r.get("hypotheses") or []:
        if not str(h.get("id") or "").strip():
            continue
        item = {"id": str(h["id"]).strip(), **({"question": h["question"]} if h.get("question") else {}),
                "text": h.get("text") or "", **({"criterion": h["criterion"].strip()} if (h.get("criterion") or "").strip() else {})}
        if item.get("criterion"):
            try:
                check(item["criterion"], plan["runs"], list(sets), plan["groups"])
            except Invalid as e:
                problems[item["id"]] = str(e)
        hyps.append(item)

    defaults = {"epochs": int(r.get("epochs", 100)), "imgsz": int(r.get("imgsz", 640)), "batch": int(r.get("batch", 16)),
                "seed": 0}
    if m.get("data"):  # Kaggle: one private dataset with every package's folder
        dirs = [str((root / p["data"]).resolve().parent) for p in r["packages"]]
        common = Path(os.path.relpath(os.path.commonpath(dirs), root)).as_posix()
        m["data"]["packages"] = [{"key": "data", "dir": common}]
        defaults["dataset"] = "data"
    m["runs"]["extras"]["fields"]["data"] = {"choices": "$existing", "default": r["packages"][0]["data"]}
    files[runs_file] = ("# Runs of this research project (written by the runboard wizard). Pre-registered: change them\n"
                        "# before the plan is locked, or as a recorded deviation after.\n"
                        + yaml.safe_dump({"defaults": defaults, "runs": plan["runs"]}, sort_keys=False, allow_unicode=True,
                                         default_flow_style=None))
    m["runs"]["fields"] = ["package", "model", "seed", "epochs"]
    m["runs"]["required"] = ["data", "model"]
    m["phases"], m["tables"] = plan["phases"], plan["tables"]
    pl = {"questions": questions, "hypotheses": hyps,
          "protocol": {"dir": "eval", "metric": str(pr.get("metric") or "map50_95"),
                       "sets": {s: ({"sealed": True} if s in sealed else {}) for s in sets} if sealed else list(sets)},
          **({"groups": plan["groups"]} if plan["groups"] else {})}
    files["plan.yaml"] = ("# The science of this project: questions, hypotheses and how they are checked. Lock it before\n"
                          "# training (Hypotheses page or `runboard lock`); after that every change is a deviation.\n"
                          + yaml.safe_dump(pl, sort_keys=False, allow_unicode=True, width=110))
    first = next(iter(r["packages"]))["data"]
    tpl = dict(plan["templates"])
    tpl["scripts/evaluate.py"] = ("evaluate", {"data": first, "sets": sets, "sealed": sealed, "out": "eval",
                                               "replicates": int(pr.get("replicates") or 200)})
    if r.get("check"):
        tpl["scripts/check.py"] = ("check", {"data": first})
    m["templates"] = {}
    m.setdefault("jobs", {})
    for path, (name, params) in tpl.items():
        files[path] = templating.render(name, templating.coerce(name, params))
        m["templates"][path] = name
        job = templating.TEMPLATES[name]["job"]
        key = name if name not in m["jobs"] else f"{name}_{Path(path).stem.split('_')[-1]}"
        m["jobs"][key] = {"title": job["title"], "cmd": f'"{{python}}" -u {path}' + (f" {job['args']}" if job.get("args") else ""),
                          **({"per_run": True} if job.get("per_run") else {})}
    m["version"] = 2
    return {"runs": [{"id": k, **v} for k, v in plan["runs"].items()], "groups": plan["groups"], "sets": list(sets),
            "suggest": [s for s in plan["suggest"] if set(s.pop("sets")) <= set(sets)], "problems": problems, "slug": slugify(m.get("id") or "")}
