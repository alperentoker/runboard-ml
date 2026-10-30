"""A project = a folder with a runboard.yaml manifest. Everything project-specific lives in that file.

See docs/manifest.md for the full reference; examples/ has a minimal project.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import yaml

from .errors import Denied, Err, Invalid
from .home import State, load_yaml, read_json

MANIFEST = "runboard.yaml"
FILTERS = {
    "lower": lambda v, a: v.lower(),
    "upper": lambda v, a: v.upper(),
    "stem": lambda v, a: Path(v).stem,
    "strip": lambda v, a: v.removeprefix(a),
}


def text(v, lang: str = "en") -> str:
    """Manifest texts may be plain strings or {en: …, tr: …}."""
    if isinstance(v, dict):
        return v.get(lang) or v.get("en") or next(iter(v.values()), "")
    return "" if v is None else str(v)


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "project"


class Project:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.m = load_yaml(self.root / MANIFEST) or {}
        self.key = slugify(self.m.get("id") or self.m.get("name") or self.root.name)
        self.state = State(self.key)
        r = self.m.get("runs", {})
        self.runs_file = self.root / r.get("file", "runs.yaml")
        self.section = r.get("section", "runs")
        self.defaults_section = r.get("defaults")
        self.extras = r.get("extras") or {}

    # ------------------------------------------------------------ templates

    def render(self, tpl: str, ctx: dict) -> str:
        """{field}, {field|filter|filter:arg} and {yaml:relative/file.yaml:key}."""
        def rep(m):
            parts = m[1].split("|")
            head = parts[0]
            if head.startswith("yaml:"):
                _, rel, key = head.split(":", 2)
                v = yaml.safe_load((self.root / rel).read_text(encoding="utf-8"))
                for k in key.split("."):
                    v = v[k]
            elif head == "python":  # the interpreter runboard runs on
                v = ctx.get("python", sys.executable)
            else:
                v = ctx.get(head, "")
            v = "" if v is None else str(v)
            for f in parts[1:]:
                name, _, arg = f.partition(":")
                v = FILTERS[name](v, arg)
            return v
        return re.sub(r"\{([^{}]+)\}", rep, tpl)

    # ------------------------------------------------------------ runs

    def doc(self) -> dict:
        return load_yaml(self.runs_file) or {}

    def run_ids(self) -> list[str]:
        return list((self.doc().get(self.section) or {}).keys())

    def is_extra(self, run_id: str) -> bool:
        p = self.extras.get("prefix")
        return bool(p) and bool(re.fullmatch(rf"{re.escape(p)}\d+", run_id))

    def spec(self, run_id: str, doc: dict | None = None) -> dict:
        doc = doc or self.doc()
        base = dict(doc.get(self.defaults_section) or {}) if self.defaults_section else {}
        return {**base, **(doc[self.section][run_id] or {}), "id": run_id}

    def info(self, run_id: str, doc: dict | None = None) -> dict:
        s = self.spec(run_id, doc)
        r = self.m.get("runs", {})
        required = r.get("required", [])
        ready = all(s.get(k) is not None for k in required)
        fields = {k: s.get(k) for k in r.get("fields", [])}
        return {"id": run_id, **fields, "fields": fields, "ready": ready,
                "missing": [k for k in required if s.get(k) is None],
                "name": self.render(r.get("name", "{id}"), s) if ready else None,
                "locked": bool(r.get("locked")) and not self.is_extra(run_id), "extra": self.is_extra(run_id)}

    def infos(self) -> list[dict]:
        doc = self.doc()
        return [self.info(k, doc) for k in (doc.get(self.section) or {})]

    def backup(self) -> None:
        d = self.state.dir / "backup"
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.runs_file, d / f"{self.runs_file.stem}-{datetime.now():%Y%m%d-%H%M%S}{self.runs_file.suffix}")

    def _newline(self) -> str:
        """Keep the file's own line endings (CRLF or LF)."""
        return "\r\n" if b"\r\n" in self.runs_file.read_bytes() else "\n"

    def _write(self, content: str) -> None:
        nl = self._newline()
        self.backup()
        self.runs_file.write_text(content, encoding="utf-8", newline=nl)

    def add_extra(self, values: dict, note: str = "") -> str:
        """Appends an extra run (prefix + number). Pre-registered runs and shared settings are never touched."""
        if not self.extras:
            raise Invalid("no_extras")
        doc = self.doc()
        clean = {k: self.coerce(k, values.get(k, rule.get("default")), {**rule, "required": True}, doc)
                 for k, rule in (self.extras.get("fields") or {}).items()}
        prefix = self.extras["prefix"]
        n = 1 + max([int(k[len(prefix):]) for k in doc[self.section] if self.is_extra(k)] or [0])
        run_id = f"{prefix}{n}"
        from .runsfile import RunsFile
        f = RunsFile(self.runs_file, self.section)
        new = f.add_run(run_id, clean, note)  # right after the last run, wherever the section sits in the file
        heading = self.extras.get("heading", "Extra runs: added from runboard, not part of the pre-registered plan.")
        if f"# {heading}" not in f.text:
            new = re.sub(rf"\n( *){re.escape(run_id)}: ", lambda m: f"\n\n{m[1]}# {heading}\n{m[1]}{run_id}: ", new, count=1)
        f.verify(new, {run_id: clean})
        self.backup()
        f.save(new, None)
        return run_id

    def remove_extra(self, run_id: str) -> None:
        if not self.is_extra(run_id):
            raise Invalid("not_extra")
        if self.state.get(run_id).get("status"):
            raise Invalid("launched")
        from .runsfile import RunsFile
        f = RunsFile(self.runs_file, self.section)
        content = f.remove_run(run_id)  # found by its key, whatever the file's indentation
        if not any(self.is_extra(k) for k in yaml.safe_load(content)[self.section]):
            heading = self.extras.get("heading", "Extra runs: added from runboard, not part of the pre-registered plan.")
            content = re.sub(rf"\n*[ \t]*# {re.escape(heading)}\n", "\n", content)
        f.verify(content, {run_id: None})
        self._write(content)

    # ------------------------------------------------------------ editing the plan

    def schema(self) -> dict:
        """Rules per field for forms and checks: runs.schema, then the extras rules; listed fields take any value."""
        r = self.m.get("runs", {})
        rules = {k: dict(v or {}) for k, v in (self.extras.get("fields") or {}).items()}
        for k, v in (r.get("schema") or {}).items():
            rules[k] = dict(v or {})
        for f in r.get("fields", []):
            rules.setdefault(f, {})
        return rules

    def choices(self, field: str, rule: dict, doc: dict | None = None) -> list | None:
        c = rule.get("choices")
        if c == "$existing":
            doc = doc or self.doc()
            return sorted({self.spec(i, doc).get(field) for i in doc[self.section]} - {None}, key=str)
        return c

    def coerce(self, field: str, value, rule: dict, doc: dict | None = None):
        """A form value checked against its rule and given its proper type; None/"" means "use the default"."""
        if value is None or value == "":
            if rule.get("required"):
                raise Invalid("required", field=field)
            return None
        if "choices" in rule:
            choices = self.choices(field, rule, doc)
            match = next((c for c in choices if c == value or str(c) == str(value)), None)
            if match is None:
                raise Invalid("one_of", field=field, choices=choices)
            return match
        for kind, cast in (("int", int), ("float", float)):
            if kind in rule:
                try:
                    v = cast(str(value).strip())
                except (TypeError, ValueError):
                    raise Invalid("number", field=field)
                lo, hi = rule[kind]
                if not lo <= v <= hi:
                    raise Invalid("range", field=field, lo=lo, hi=hi)
                return v
        if rule.get("bool"):
            if isinstance(value, bool):
                return value
            if str(value).lower() in ("true", "yes", "1", "on", "false", "no", "0", "off"):
                return str(value).lower() in ("true", "yes", "1", "on")
            raise Invalid("bool", field=field)
        if "file" in rule:
            p = (self.root / str(value)).resolve()
            if not p.is_file() or self.root not in p.parents or not Path(str(value)).match(rule["file"] or "*"):
                raise Invalid("file", field=field, pattern=rule["file"] or "")
            return Path(str(value)).as_posix()
        if isinstance(value, str):  # untyped: read it the way YAML would ("0.01" → 0.01, "true" → True)
            try:
                v = yaml.safe_load(value)
            except yaml.YAMLError:
                return value
            return v if isinstance(v, (str, int, float, bool)) else value
        return value

    def why_locked(self, run_id: str) -> str | None:
        """None if the run's settings may be edited. A started run keeps the settings it ran with; a pre-registered
        plan is changed only through its decisions."""
        if self.state.get(run_id).get("status"):
            return "started"
        try:
            if self.metrics(run_id):  # finished outside runboard: its results exist
                return "started"
        except Exception:
            pass
        if bool((self.m.get("runs") or {}).get("locked")) and not self.is_extra(run_id):
            return "locked"
        return None

    def plan(self) -> dict:
        from .runsfile import RunsFile
        f = RunsFile(self.runs_file, self.section)
        doc = self.doc()
        rules = self.schema()
        return {"version": f.version, "locked": bool((self.m.get("runs") or {}).get("locked")),
                "extra_fields": list((self.extras.get("fields") or {})), "order": list((self.m.get("runs") or {}).get("fields", [])),
                "file": self.runs_file.relative_to(self.root).as_posix(),
                "fields": {k: {**v, "choices": self.choices(k, v, doc)} if "choices" in v else v for k, v in rules.items()},
                "defaults": dict(doc.get(self.defaults_section) or {}) if self.defaults_section else {},
                "runs": [{"id": rid, "own": dict(own or {}), "effective": self.spec(rid, doc),
                          "why_locked": self.why_locked(rid), "extra": self.is_extra(rid)}
                         for rid, own in (doc.get(self.section) or {}).items()],
                "sections": {s: dict(doc.get(s) or {}) for s in self.shared_sections(doc)}, "raw": f.text,
                "defaults_name": self.defaults_section}

    # ------------------------------------------------------------ shared settings and the whole file

    def shared_sections(self, doc: dict | None = None) -> list[str]:
        """The defaults merged under every run, then the sections listed in runs.show (read by the training code)."""
        doc = doc if doc is not None else self.doc()
        names = ([self.defaults_section] if self.defaults_section else []) + list((self.m.get("runs") or {}).get("show") or [])
        return [s for i, s in enumerate(names) if s not in names[:i] and isinstance(doc.get(s), dict)]

    def _plan_locked(self) -> bool:
        return bool((self.m.get("runs") or {}).get("locked"))

    def affects(self, section: str, keys: list[str], doc: dict | None = None) -> dict:
        """Which runs a change of these shared keys reaches. Defaults reach runs that do not set the key themselves;
        other shared sections are read by the training code, so they reach every run."""
        doc = doc or self.doc()
        out = {"drafts": [], "started": []}
        for rid, own in (doc.get(self.section) or {}).items():
            if section == self.defaults_section and all(k in (own or {}) for k in keys):
                continue
            out["started" if self.why_locked(rid) == "started" else "drafts"].append(rid)
        return out

    def edit_section(self, name: str, changes: dict, version: str | None, dry: bool = False, who: str = "") -> dict:
        from .runsfile import RunsFile
        if self._plan_locked():
            raise Denied("locked")
        doc = self.doc()
        if name not in self.shared_sections(doc):
            raise Invalid("not_section", name=name)
        rules = self.schema() if name == self.defaults_section else {}
        clean = {}
        for k, v in changes.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,60}", str(k)):
                raise Invalid("bad_key", key=k)
            clean[k] = None if v is None else self.coerce(k, v, rules.get(k, {}), doc)
            if clean[k] is None and v not in (None, ""):
                raise Invalid("empty", field=k)
        f = RunsFile(self.runs_file, self.section)
        new = f.set_section(name, clean)
        want = {**doc[name], **{k: v for k, v in clean.items() if v is not None}}
        for k, v in clean.items():
            if v is None:
                want.pop(k, None)
        self._expect_doc(new, {**doc, name: want})
        res = self._commit(f, new, None, version, dry, f"edit {name}", who)
        return {**res, "affects": self.affects(name, list(clean), doc)}

    def _expect_doc(self, new: str, want: dict) -> None:
        if (yaml.safe_load(new) or {}) != want:
            raise Invalid("not_as_intended", file=self.runs_file.name)

    def edit_raw(self, text: str, version: str | None, dry: bool = False, who: str = "") -> dict:
        """The whole runs file as text, for what the forms cannot do. It is checked like a form edit: it must parse,
        every run must still resolve, schema fields must pass their rules and started runs must stay as they ran."""
        from .runsfile import RUN_ID, RunsFile
        if self._plan_locked():
            raise Denied("locked")
        text = text.replace("\r\n", "\n")
        try:
            doc = yaml.safe_load(text) or {}
        except yaml.YAMLError as e:
            mark = getattr(e, "problem_mark", None)
            raise (Invalid("yaml_line", line=mark.line + 1, problem=getattr(e, "problem", e)) if mark
                   else Invalid("yaml", problem=e))
        if not isinstance(doc, dict) or not isinstance(doc.get(self.section), dict):
            raise Invalid("keep_runs", section=self.section)
        if self.defaults_section and self.defaults_section in doc and not isinstance(doc[self.defaults_section], dict):
            raise Invalid("stay_mapping", section=self.defaults_section)
        old = self.doc().get(self.section) or {}
        rules = self.schema()
        for rid, own in doc[self.section].items():
            if not RUN_ID.fullmatch(str(rid)):
                raise Invalid("bad_run_id", run=rid)
            if own is not None and not isinstance(own, dict):
                raise Invalid("run_mapping", run=rid)
            for k, v in (own or {}).items():
                if k in rules and v is not None:
                    try:
                        self.coerce(k, v, rules[k], doc)
                    except Err as e:
                        raise e.at(rid)
        for rid in old:
            if self.why_locked(rid) == "started" and (rid not in doc[self.section] or (doc[self.section][rid] or {}) != (old[rid] or {})):
                raise Invalid("started_entry", run=rid)
        for rid in doc[self.section]:
            try:
                self.info(rid, doc)
            except Exception as e:
                raise Invalid("broken", rid, problem=e)
        f = RunsFile(self.runs_file, self.section)
        return self._commit(f, text, None, version, dry, "edit file", who)

    def _clean(self, values: dict, doc: dict) -> dict:
        rules = self.schema()
        unknown = [k for k in values if k not in rules]
        if unknown:
            raise Invalid("not_editable", fields=unknown)
        return {k: self.coerce(k, v, rules[k], doc) for k, v in values.items()}

    def _commit(self, f, new: str, expect: dict | None, version: str | None, dry: bool, what: str, who: str) -> dict:
        if expect is not None:  # run edits: everything but the expected runs must come out unchanged
            f.verify(new, expect)
        diff = f.diff(new)
        if dry:
            return {"diff": diff, "version": f.version}
        if not diff:
            return {"diff": "", "version": f.version}
        self.backup()
        v = f.save(new, version)
        log = self.state.dir / "plan-log.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as out:
            out.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), "who": who, "what": what,
                                  "diff": diff}, ensure_ascii=False) + "\n")
        return {"diff": diff, "version": v}

    def edit_run(self, run_id: str, values: dict, version: str | None, dry: bool = False, who: str = "") -> dict:
        """Changes the run's own fields; None clears a field so the shared default applies again."""
        from .runsfile import RunsFile
        why = self.why_locked(run_id)
        if why:
            raise Denied(why)
        f = RunsFile(self.runs_file, self.section)
        doc = self.doc()
        own = dict(doc[self.section][run_id] or {})
        for k, v in self._clean(values, doc).items():
            if v is None:
                own.pop(k, None)
            else:
                own[k] = v
        return self._commit(f, f.set_run(run_id, own), {run_id: own}, version, dry, f"edit {run_id}", who)

    def add_run(self, run_id: str | None, values: dict, version: str | None, copy_from: str | None = None,
                note: str = "", dry: bool = False, who: str = "") -> dict:
        """A new run that has not started (a draft). Copying takes the source run's own fields first."""
        from .runsfile import RunsFile
        doc = self.doc()
        runs = doc.get(self.section) or {}
        if copy_from and copy_from not in runs:
            raise Invalid("unknown_run", run=copy_from)
        if bool((self.m.get("runs") or {}).get("locked")):
            if not self.extras:
                raise Denied("locked")
            src = self.spec(copy_from, doc) if copy_from else {}
            vals = {k: src.get(k) for k in (self.extras.get("fields") or {}) if src.get(k) is not None} | values
            if dry:
                raise Invalid("extras_direct")
            rid = self.add_extra(vals, note)
            return {"id": rid, "diff": "", "version": RunsFile(self.runs_file, self.section).version}
        own = dict(runs[copy_from] or {}) if copy_from else {}
        for k, v in self._clean(values, doc).items():
            if v is None:
                own.pop(k, None)
            else:
                own[k] = v
        if not run_id:
            base = f"{copy_from}-copy" if copy_from else "run"
            run_id = next(c for c in [base] + [f"{base}{i}" for i in range(2, 1000)] if c not in runs)
        f = RunsFile(self.runs_file, self.section)
        res = self._commit(f, f.add_run(run_id, own, note), {run_id: own}, version, dry, f"add {run_id}", who)
        return {"id": run_id, **res}

    def remove_run(self, run_id: str, version: str | None, dry: bool = False, who: str = "") -> dict:
        from .runsfile import RunsFile
        why = self.why_locked(run_id)
        if why:
            raise Denied(why)
        f = RunsFile(self.runs_file, self.section)
        return self._commit(f, f.remove_run(run_id), {run_id: None}, version, dry, f"remove {run_id}", who)

    SWEEP_LIMIT = 48

    def add_sweep(self, grid: dict, base: str | None, prefix: str, version: str | None, note: str = "",
                  dry: bool = False, who: str = "") -> dict:
        """Every combination of the listed values becomes a draft run, named after its values (prefix-a-b) and
        built on the base run's own fields. A pre-registered plan gets them as extra runs."""
        from itertools import product

        from .runsfile import RunsFile
        doc = self.doc()
        runs = doc.get(self.section) or {}
        if base and base not in runs:
            raise Invalid("unknown_run", run=base)
        locked = self._plan_locked()
        if locked and not self.extras:
            raise Denied("locked")
        allowed = (self.extras.get("fields") or {}) if locked else self.schema()
        unknown = [k for k in grid if k not in allowed]
        if unknown:
            raise Invalid("not_editable", fields=unknown)
        clean = {}
        for k, vals in grid.items():
            vals = [v for v in (vals if isinstance(vals, list) else [vals]) if v not in (None, "")]
            typed = [self.coerce(k, v, allowed[k], doc) for v in vals]
            clean[k] = [v for i, v in enumerate(typed) if v not in typed[:i]]
        if not clean or not all(clean.values()):
            raise Invalid("sweep_empty")
        n = 1
        for vals in clean.values():
            n *= len(vals)
        if n > self.SWEEP_LIMIT:
            raise Invalid("sweep_too_many", n=n, limit=self.SWEEP_LIMIT)
        combos = [dict(zip(clean, c)) for c in product(*clean.values())]
        if locked:
            src = self.spec(base, doc) if base else {}
            first = {k: src.get(k) for k in allowed if src.get(k) is not None}
            if dry:  # extras are numbered when they are written; show what they will hold
                return {"ids": [], "runs": [first | c for c in combos], "diff": ""}
            ids = [self.add_extra(first | c, note) for c in combos]
            return {"ids": ids, "diff": "", "version": RunsFile(self.runs_file, self.section).version}
        f = RunsFile(self.runs_file, self.section)
        text, expect, taken = f.text, {}, set(runs)
        name = lambda v: Path(v).stem if isinstance(v, str) and Path(v).suffix in (".pt", ".pth", ".yaml", ".ckpt") else str(v)
        for c in combos:
            own = (dict(runs[base] or {}) if base else {}) | c
            rid = re.sub(r"[^A-Za-z0-9_.-]+", "-", "-".join([prefix or base or "sweep"] + [name(v) for v in c.values()]))
            rid = rid.strip("-.")[:38] or "sweep"
            rid = next(x for x in [rid] + [f"{rid}-{i}" for i in range(2, 100)] if x not in taken)
            taken.add(rid)
            step = RunsFile(self.runs_file, self.section)
            step.text = text
            text = step.add_run(rid, own, note)
            expect[rid] = own
        res = self._commit(f, text, expect, version, dry, f"sweep: {', '.join(expect)}", who)
        return {"ids": list(expect), **res}

    def changed_since_start(self, run_id: str, st: dict, doc: dict | None = None) -> list[str]:
        """Fields whose value in the runs file differs from the one the run started with."""
        snap = st.get("spec")
        if not snap or run_id not in ((doc or self.doc()).get(self.section) or {}):
            return []
        now = self.spec(run_id, doc)
        return sorted(k for k in set(snap) | set(now) if snap.get(k) != now.get(k))

    # ------------------------------------------------------------ decisions

    def decisions(self, lang: str = "en") -> list[dict]:
        out = []
        content = self.runs_file.read_text(encoding="utf-8")
        for d in self.m.get("decisions", []):
            cands = []
            for rid in d["candidates"]:
                inf = self.info(rid)
                cands.append({**inf, "metrics": self.metrics(rid, inf)})
            out.append({"id": d["id"], "title": text(d.get("title"), lang), "rule": text(d.get("rule"), lang),
                        "field": d["field"], "metric": d.get("metric", "primary"), "tie": d.get("tie"),
                        "candidates": cands, "done": f"{d['field']}: null" not in content,
                        "ready": all(c["metrics"] for c in cands)})
        return out

    def decide(self, decision_id: str, value: str, reason: str) -> None:
        d = next((x for x in self.m.get("decisions", []) if x["id"] == decision_id), None)
        if not d:
            raise Invalid("unknown_decision")
        cands = [(rid, self.info(rid)) for rid in d["candidates"]]
        mets = {rid: self.metrics(rid, inf) for rid, inf in cands}
        if not all(mets.values()):
            raise Invalid("finish_first")
        if value not in {inf.get(d["field"]) for _, inf in cands}:
            raise Invalid("from_candidates")
        if len(reason.strip()) < 10:
            raise Invalid("reason_short")
        content = self.runs_file.read_text(encoding="utf-8")
        # every run still waiting for this field gets the value; another field ending in the same name
        # (teacher_model) and comments are left alone, and the result is read back before it is written
        field = re.compile(rf"(?<![\w.-]){re.escape(d['field'])}: null\b")
        lines = content.splitlines(keepends=True)
        for i, ln in enumerate(lines):
            if not ln.lstrip().startswith("#"):
                code, hash_, comment = ln.partition(" #")
                lines[i] = field.sub(f"{d['field']}: {value}", code) + hash_ + comment
        new = "".join(lines)
        if new == content:
            raise Invalid("decided")
        before, after = yaml.safe_load(content), yaml.safe_load(new)
        filled = yaml.safe_load(f"v: {value}")["v"]

        def fill(node):
            if isinstance(node, dict):
                return {k: filled if k == d["field"] and v is None else fill(v) for k, v in node.items()}
            return [fill(v) for v in node] if isinstance(node, list) else node
        if after != fill(before):
            raise Invalid("decided")
        self._write(new)
        log = self.root / d.get("log", "decisions.md")
        log.parent.mkdir(parents=True, exist_ok=True)
        keys = [k for k in ("primary", "secondary", "best_epoch", "hours") if any(k in m for m in mets.values())]
        rows = "\n".join(f"| {rid} | {inf.get(d['field'])} | " + " | ".join(str(mets[rid].get(k, "")) for k in keys) + " |"
                         for rid, inf in cands)
        head = "" if log.exists() else "# Decision log\n\nDecisions of the pre-registered plan, with the numbers they were based on.\n"
        with open(log, "a", encoding="utf-8", newline="\n") as f:
            f.write(f"{head}\n## {datetime.now():%Y-%m-%d %H:%M} — {decision_id}: {value}\n\n"
                    f"| Run | {d['field']} | " + " | ".join(keys) + " |\n| :--- | :--- |" + " ---: |" * len(keys) +
                    f"\n{rows}\n\n**Reason:** {reason.strip()}\n")

    # ------------------------------------------------------------ results

    def output_dir(self, run_id: str, info: dict | None = None, backend: str | None = None) -> Path | None:
        info = info or self.info(run_id)
        if not info["name"]:
            return None
        backend = backend or self.state.get(run_id).get("backend") or self.m.get("default_backend", "kaggle")
        cfg = (self.m.get("backends") or {}).get(backend, {})
        return self.root / cfg.get("output_dir", f"runs/{backend}") / info["name"]

    def _res(self) -> dict:
        return self.m.get("results") or {}

    def report(self, run_id: str, info: dict | None = None) -> dict | None:
        info = info or self.info(run_id)
        tpl = self._res().get("report")
        if not tpl or not info["name"]:
            return None
        return read_json(self.root / self.render(tpl, {**info, "out": self.output_dir(run_id, info)}), None)

    def metrics(self, run_id: str, info: dict | None = None) -> dict | None:
        """The run's summary numbers under generic keys (primary, secondary, best_epoch, epochs, hours)."""
        rep = self.report(run_id, info)
        if not rep:
            return None
        return {k: rep.get(src) for k, src in (self._res().get("metrics") or {}).items()} | {"_raw": rep}

    def final(self, run_id: str, info: dict | None = None) -> dict | None:
        info = info or self.info(run_id)
        tpl = self._res().get("final")
        out = self.output_dir(run_id, info)
        return read_json(Path(self.render(tpl, {**info, "out": out})), None) if tpl and out else None

    def curves(self, run_id: str, info: dict | None = None) -> list[dict] | None:
        info = info or self.info(run_id)
        c = self._res().get("curves") or {}
        out = self.output_dir(run_id, info)
        if not c or not out:
            return None
        p = Path(self.render(c["file"], {**info, "out": out}))
        if not p.exists():
            return None
        with open(p, encoding="utf-8") as f:
            rows = [{k.strip(): v for k, v in r.items()} for r in csv.DictReader(f)]
        cols = c.get("columns") or ULTRALYTICS_COLUMNS
        scale = set(c.get("percent", ["map", "map50", "p", "r"] if not c.get("columns") else []))
        out_rows = []
        for r in rows:
            d = {}
            for src, key in cols.items():
                if r.get(src) not in (None, ""):
                    d[key] = round(100 * float(r[src]), 3) if key in scale else float(r[src])
            if "e" in d:
                d["e"] = int(d["e"])
                out_rows.append(d)
        return out_rows

    def catalog(self) -> list[dict]:
        """Data packages: rows of a CSV catalog (prebuilt zips) and/or folders zipped at upload time."""
        data = self.m.get("data") or {}
        rows = []
        for pk in data.get("packages") or []:
            d = (self.root / pk["dir"]).resolve()
            size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) if d.is_dir() else 0
            rows.append({"_key": pk["key"], "_dir": str(d), "_zip": str(self.state.dir / "packages" / f"{pk['key']}.zip"),
                         "folder": pk["dir"], "size_mb": round(size / 2**20, 1)})
        if not data.get("catalog"):
            return rows
        key = data.get("key", "package")
        with open(self.root / data["catalog"], encoding="utf-8") as f:
            for r in csv.DictReader(f):
                r["_key"] = r[key]
                r["_zip"] = str(self.root / data.get("dir", ".") / r.get("zip", f"{r[key]}.zip"))
                rows.append(r)
        return rows


ULTRALYTICS_COLUMNS = {
    "epoch": "e", "time": "t", "metrics/mAP50-95(B)": "map", "metrics/mAP50(B)": "map50",
    "metrics/precision(B)": "p", "metrics/recall(B)": "r", "train/box_loss": "box_loss", "train/cls_loss": "cls_loss",
    "train/dfl_loss": "dfl_loss", "val/box_loss": "val_box_loss", "val/cls_loss": "val_cls_loss",
    "val/dfl_loss": "val_dfl_loss", "lr/pg0": "lr",
}
