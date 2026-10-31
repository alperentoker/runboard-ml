"""Manifest v2: the science of a project (questions, hypotheses, protocol, groups, decisions, the lock) lives in
plan.yaml, apart from runboard.yaml, which keeps how runs are started and shown. See docs/design-v2.md.

Checks for both files when they are edited from the dashboard, and `runboard migrate`, which moves a v1 project's
decisions and lock into a new plan.yaml with their comments.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml
from yaml.nodes import MappingNode

from .errors import Denied, Invalid

PLAN = "plan.yaml"
MANIFEST = "runboard.yaml"
PLAN_KEYS = ("questions", "hypotheses", "protocol", "groups", "decisions", "locked")
SCIENCE = ("decisions",)  # top-level manifest sections that move to plan.yaml
PLAN_HEADER = ("# The science of this project: what it asks, what it expects and how that is checked. runboard.yaml\n"
               "# keeps how runs are started and shown. Reference: docs/design-v2.md in the runboard repository.\n")


def parse(text: str, file: str):
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        raise (Invalid("yaml_line", line=mark.line + 1, problem=getattr(e, "problem", e)) if mark
               else Invalid("yaml", problem=e)) from None
    doc = {} if doc is None else doc
    if not isinstance(doc, dict):
        raise Invalid("file_mapping", file=file)
    return doc


def check_plan(doc: dict, runs: set[str]) -> None:
    """Sections, unique ids, and every name pointing at something that exists. Criteria stay text here; RB-1 reads them."""
    for k in doc:
        if k not in PLAN_KEYS:
            raise Invalid("plan_key", key=k)
    seen: set[str] = set()

    def entries(name: str) -> list[dict]:
        v = doc.get(name) or []
        if not isinstance(v, list) or not all(isinstance(x, dict) and x.get("id") not in (None, "") for x in v):
            raise Invalid("plan_shape", what=name, shape="a list of entries, each with an id")
        for x in v:
            if str(x["id"]) in seen:
                raise Invalid("plan_dup", id=x["id"])
            seen.add(str(x["id"]))
        return v

    questions, hypotheses, decisions = entries("questions"), entries("hypotheses"), entries("decisions")
    asked = {str(q["id"]) for q in questions}
    for h in hypotheses:
        if h.get("question") is not None and str(h["question"]) not in asked:
            raise Invalid("plan_ref", item=h["id"], ref=h["question"])
        if h.get("criterion") is not None and not isinstance(h["criterion"], str):
            raise Invalid("plan_shape", what=f"{h['id']}: criterion", shape="text")
    sets = (doc.get("protocol") or {}).get("sets") if isinstance(doc.get("protocol"), dict) else None
    for h in hypotheses:  # read now, against the runs, groups and sets that exist, not when the verdict is due
        if isinstance(h.get("criterion"), str) and h["criterion"].strip():
            from .hypotheses import check
            try:
                check(h["criterion"], runs, list(sets) if isinstance(sets, (list, dict)) else None, doc.get("groups") or {})
            except Invalid as e:
                raise Invalid("criterion", problem=f"{h['id']}: {e.params.get('problem', e)}") from None
    groups = doc.get("groups") or {}
    if not isinstance(groups, dict):
        raise Invalid("plan_shape", what="groups", shape="a mapping of names to lists of runs")
    for g, members in groups.items():
        if str(g) in runs or str(g) in seen:
            raise Invalid("plan_dup", id=g)  # a group name stands where a run name can
        if not isinstance(members, list) or not members:
            raise Invalid("plan_shape", what=f"groups: {g}", shape="a list of runs")
        for r in members:
            if str(r) not in runs:
                raise Invalid("plan_ref", item=g, ref=r)
    for d in decisions:
        if not isinstance(d.get("candidates"), list) or not d.get("field"):
            raise Invalid("plan_shape", what=d["id"], shape="candidates (a list of runs) and a field")
        for r in d["candidates"]:
            if str(r) not in runs:
                raise Invalid("plan_ref", item=d["id"], ref=r)
    if not isinstance(doc.get("protocol") or {}, dict):
        raise Invalid("plan_shape", what="protocol", shape="a mapping")
    if "locked" in doc and not isinstance(doc["locked"], bool):
        raise Invalid("plan_shape", what="locked", shape="true or false")


def check_manifest(doc: dict, old: dict, root: Path, locked: bool) -> None:
    """runboard.yaml as edited from this computer. The version and, under a lock, which plan and runs file count, stay."""
    r = doc.get("runs")
    if not isinstance(r, dict) or not r.get("file") or not (root / str(r["file"])).is_file():
        raise Invalid("manifest_runs")
    v2 = int(old.get("version") or 1) >= 2
    if int(doc.get("version") or 1) != int(old.get("version") or 1):
        raise Invalid("keep_version")
    if v2:
        for k in SCIENCE:
            if k in doc:
                raise Invalid("in_plan", key=k)
        if "locked" in r:
            raise Invalid("in_plan", key="runs.locked")
    old_r = old.get("runs") or {}
    if locked:
        same = [("plan",)] if v2 else [("decisions",)]
        if any(doc.get(k) != old.get(k) for (k,) in same) or any(
                r.get(k) != old_r.get(k) for k in ("file", "section", "defaults", "locked")):
            raise Denied("locked")


# ---------------------------------------------------------------- runboard migrate

def _top_level(text: str) -> list[tuple[str, int, object]]:
    root = yaml.compose(text)
    if root is None:
        return []
    if not isinstance(root, MappingNode) or root.flow_style:
        raise Invalid("migrate_by_hand", what=MANIFEST)
    return [(k.value, k.start_mark.line, v) for k, v in root.value]


def migrate(root: Path, backup_dir: Path | None = None) -> dict:
    """A v1 project becomes v2: decisions and runs.locked move into plan.yaml as written (comments included), the
    manifest gets `version: 2`. Both files are read back and must mean exactly what the old manifest meant."""
    root = Path(root).resolve()
    mf = root / MANIFEST
    raw = mf.read_bytes()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8").replace("\r\n", "\n")
    old = parse(text, MANIFEST)
    plan_path = root / str(old.get("plan") or PLAN)
    if int(old.get("version") or 1) >= 2 or plan_path.exists():
        raise Invalid("already_v2")
    lines = text.split("\n")
    top = _top_level(text)
    if not top:
        raise Invalid("manifest_runs")
    drop: set[int] = set()
    moved: list[str] = []

    for i, (key, line, _) in enumerate(top):  # a whole top-level section, with the comments right above it
        if key not in SCIENCE:
            continue
        start, end = line, top[i + 1][1] if i + 1 < len(top) else len(lines)
        while start > 0 and lines[start - 1].startswith("#"):
            start -= 1
        while end - 1 > line and (lines[end - 1].startswith("#") or not lines[end - 1].strip()):
            end -= 1  # comments directly above the next section belong to it
        moved.append("\n".join(lines[start:end]))
        drop.update(range(start, end))

    locked_line = None
    runs_node = next((v for k, _, v in top if k == "runs"), None)
    if isinstance(runs_node, MappingNode):
        for k, v in runs_node.value:
            if k.value == "locked":
                if runs_node.flow_style or k.start_mark.line != v.end_mark.line:
                    raise Invalid("migrate_by_hand", what="runs.locked")
                locked_line = lines[k.start_mark.line].strip()
                drop.add(k.start_mark.line)

    kept = [ln for n, ln in enumerate(lines) if n not in drop]
    out: list[str] = []
    for ln in kept:  # removed sections leave one blank line, not two
        if not ln.strip() and out and not out[-1].strip():
            continue
        out.append(ln)
    first = next(n for n, ln in enumerate(out) if ln and not ln.startswith(("#", " ")))
    out.insert(first, "version: 2")
    new_manifest = "\n".join(out)
    if not new_manifest.endswith("\n"):
        new_manifest += "\n"
    plan_text = PLAN_HEADER + ("\n" + locked_line + "\n" if locked_line else "") + \
        "".join("\n" + block.rstrip("\n") + "\n" for block in moved)

    want_m = {k: v for k, v in old.items() if k not in SCIENCE} | {"version": 2}
    if "runs" in want_m:
        want_m["runs"] = {k: v for k, v in want_m["runs"].items() if k != "locked"}
    want_p = {k: old[k] for k in SCIENCE if k in old}
    if "locked" in (old.get("runs") or {}):
        want_p["locked"] = old["runs"]["locked"]
    if parse(new_manifest, MANIFEST) != want_m or parse(plan_text, PLAN) != want_p:
        raise Invalid("migrate_by_hand", what=MANIFEST)

    if backup_dir:
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / f"runboard-v1-{datetime.now():%Y%m%d-%H%M%S}.yaml").write_bytes(raw)
    plan_path.write_bytes(plan_text.replace("\n", nl).encode("utf-8"))
    mf.write_bytes(new_manifest.replace("\n", nl).encode("utf-8"))
    return {"plan": plan_path.relative_to(root).as_posix(), "moved": [k for k in SCIENCE if k in old] +
            (["runs.locked"] if locked_line else [])}
