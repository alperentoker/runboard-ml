"""Pre-registration: the lock record, deviations from it, the sealed-set ledger and the hypotheses' verdicts.

plan.lock.json is written once, by `runboard lock` or the dashboard: when, by which commit, and the fingerprints of
the plan and of the runs. The runs' fingerprint leaves out extra runs and the fields decisions fill, because both are
part of a pre-registered plan's normal life. Every later change of a locked plan or runs file needs a reason and is
appended to deviations.md with the fingerprints after it, so the files on disk can always be traced back to the lock.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from .errors import Err, Invalid
from .hypotheses import Evidence, decide

LOCK = "plan.lock.json"
DEVIATIONS = "deviations.md"
MARK = re.compile(r"^<!-- runboard-deviation: (\{.*\}) -->$", re.M)


def text_hash(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() if p.is_file() else None


def runs_hash(project) -> str:
    doc = project.doc()
    fields = {d["field"] for d in project.decision_specs() if d.get("field")}

    def blank(node):
        if isinstance(node, dict):
            return {k: None if k in fields else blank(v) for k, v in node.items()}
        return [blank(v) for v in node] if isinstance(node, list) else node
    doc = dict(doc)
    doc[project.section] = {k: v for k, v in (doc.get(project.section) or {}).items() if not project.is_extra(k)}
    return hashlib.sha256(json.dumps(blank(doc), sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def code_hashes(project) -> dict[str, str | None]:
    """The fingerprints of the code written from templates (runboard.yaml, templates:), read fresh from disk."""
    from .home import load_yaml
    m = load_yaml(project.root / "runboard.yaml") or {}
    return {str(p): text_hash(project.root / str(p)) for p in (m.get("templates") or {})}


def git_info(root: Path) -> dict | None:
    def git(*a):
        return subprocess.run(["git", *a], cwd=root, capture_output=True, text=True, timeout=10,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        head = git("rev-parse", "HEAD")
        if head.returncode:
            return None
        dirty = git("status", "--porcelain").stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    return {"commit": head.stdout.strip(), "dirty": bool(dirty)}


def lock_file(project) -> Path:
    return project.plan_file.parent / LOCK


def record(project) -> dict | None:
    f = lock_file(project)
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None


def lock(project, who: str = "") -> dict:
    """Locks the plan. A pre-registration is meant to be committed: the record says whether the folder had
    uncommitted changes, so a reader knows if the commit alone shows what was locked."""
    if not project.v2:
        raise Invalid("not_v2")
    if record(project):
        raise Invalid("already_locked")
    from .planfile import check_plan
    check_plan(project.pl, set(project.run_ids()))
    ev = Evidence(project.root, project.pl.get("protocol") or {})
    rec = {"format": "runboard-lock/1", "locked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
           "by": who, "plan": project.plan_file.relative_to(project.root).as_posix(),
           "plan_sha256": text_hash(project.plan_file), "runs": project.runs_file.relative_to(project.root).as_posix(),
           "runs_sha256": runs_hash(project),
           "resample": {s: (ev.plan(s) or {}).get("ids_sha256") for s in ev.sets}, "code": code_hashes(project),
           "git": git_info(project.root)}
    lock_file(project).write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return rec


def deviations(project) -> list[dict]:
    f = project.root / DEVIATIONS
    return [json.loads(m) for m in MARK.findall(f.read_text(encoding="utf-8"))] if f.is_file() else []


def add_deviation(project, file: str, reason: str, diff: str, who: str) -> None:
    """Called after the change is written: the entry carries the fingerprints the files have now."""
    f = project.root / DEVIATIONS
    entry = {"time": datetime.now().astimezone().isoformat(timespec="seconds"), "file": file, "who": who,
             "reason": reason.strip(), "plan_sha256": text_hash(project.plan_file), "runs_sha256": runs_hash(project),
             "code": code_hashes(project)}
    head = "" if f.exists() else ("# Deviations from the pre-registered plan\n\nEvery change of the plan or the runs "
                                  "after the lock, with its reason. Written by runboard.\n")
    with open(f, "a", encoding="utf-8", newline="\n") as out:
        out.write(f"{head}\n## {entry['time'][:16].replace('T', ' ')} — {file}\n\n**Reason:** {entry['reason']}\n\n"
                  f"```diff\n{diff.rstrip()}\n```\n<!-- runboard-deviation: {json.dumps(entry, ensure_ascii=False)} -->\n")


def record_deviation(project, reason: str, who: str = "") -> None:
    """A change made outside runboard (a script edited by hand): recorded with its reason and the fingerprints now."""
    if not record(project):
        raise Invalid("not_locked")
    if len((reason or "").strip()) < 10:
        raise Invalid("deviation_reason")
    st = status(project)
    changed = ([project.plan_file.name] if not st.get("plan_ok") else []) + \
        ([project.runs_file.name] if not st.get("runs_ok") else []) + st.get("code_changed", [])
    add_deviation(project, ", ".join(changed) or "(nothing changed)", reason, "(changed outside runboard)", who)


def ledger(ev: Evidence) -> list[dict]:
    """Uses of sealed sets (the held-out test), written by the evaluation (rb.sealed)."""
    f = ev.dir / "ledger.csv"
    if not f.is_file():
        return []
    with open(f, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def status(project) -> dict:
    rec = record(project)
    devs = deviations(project)
    ev = Evidence(project.root, project.pl.get("protocol") or {})
    out = {"v2": project.v2, "locked": project.locked, "record": rec,
           "deviations": [{k: d.get(k) for k in ("time", "file", "who", "reason")} for d in devs],
           "ledger": ledger(ev), "sealed": [s for s, o in ev.sets.items() if o.get("sealed")]}
    if rec:
        want = devs[-1] if devs else rec
        out["plan_ok"] = text_hash(project.plan_file) == want.get("plan_sha256")
        out["runs_ok"] = runs_hash(project) == want.get("runs_sha256")
        if "code" in rec:
            code = next((d["code"] for d in reversed(devs) if "code" in d), rec["code"])
            now = code_hashes(project)
            out["code_ok"] = now == code
            out["code_changed"] = sorted(k for k in set(now) | set(code) if now.get(k) != code.get(k))
    return out


def hypotheses(project) -> dict:
    """Every question with its hypotheses and their verdicts (or why there is none yet)."""
    pl = project.pl
    ev = Evidence(project.root, pl.get("protocol") or {})
    groups = pl.get("groups") or {}
    out = []
    for h in pl.get("hypotheses") or []:
        item = {"id": str(h["id"]), "question": h.get("question"), "text": h.get("text"), "criterion": h.get("criterion")}
        if not h.get("criterion"):
            item["verdict"] = "no_criterion"
        else:
            try:
                item |= decide(h["criterion"], ev, groups)
            except Err as e:
                item |= {"verdict": "invalid", "error": e.body()}
        out.append(item)
    return {"questions": [{"id": str(q["id"]), "text": q.get("text")} for q in pl.get("questions") or []],
            "hypotheses": out, "protocol": {"dir": ev.dir.relative_to(project.root).as_posix(), "metric": ev.metric,
                                            "sets": ev.sets},
            "status": status(project)}
