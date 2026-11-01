"""Paper output: what a pre-registered study needs to report, written from the project's own files.

`runboard export` (or *Export for the paper* on the Hypotheses page) writes into paper/:
  tables.md, tables.tex          the results tables of runboard.yaml (groups as mean ± sd over their runs)
  hypotheses.md, hypotheses.tex  every hypothesis with its criterion, margin, 95 % interval and verdict
  methods.md                     a draft of the methods section: pre-registration, design, settings, evaluation, rule
  deviations.md                  the deviations section (or a sentence saying there were none)
  checklist.md                   a reproducibility checklist filled from the files (✓ / ✗ / –, with the reason)
  report.html                    one self-contained page with all of the above, for a reviewer or a supervisor
  provenance.json                what each run started from (commit, fingerprints, data)
  archive.zip                    plan, lock, deviations, runs, scripts, evaluation files and the above; no data,
                                 no weights. Ready for Zenodo.
Drafts are drafts: they say what the files say, and the author writes the paper.
"""
from __future__ import annotations

import html
import json
import math
import zipfile
from datetime import datetime
from pathlib import Path

from . import __version__
from .project import text

OUT = "paper"
MARK = {"supported": "supported", "refuted": "refuted", "indistinguishable": "indistinguishable",
        "not_ready": "not evaluated yet", "invalid": "criterion error", "no_criterion": "no criterion"}


def _num(v, d: int = 2) -> str:
    return "–" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.{d}f}"


def _tex(s) -> str:
    rep = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{",
           "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}", "–": "--", "±": r"$\pm$", "→": r"$\rightarrow$"}
    return "".join(rep.get(c, c) for c in str(s))


def _md_table(head: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(head) + " |", "| " + " | ".join([":---"] + ["---:"] * (len(head) - 1)) + " |"]
    return "\n".join(out + ["| " + " | ".join(r) + " |" for r in rows])


def _tex_table(title: str, head: list[str], rows: list[list[str]]) -> str:
    cols = "l" + "r" * (len(head) - 1)
    body = "\n".join("  " + " & ".join(_tex(c) for c in r) + r" \\" for r in rows)
    return (f"% {title}\n\\begin{{table}}[t]\n\\centering\n\\caption{{{_tex(title)}}}\n\\begin{{tabular}}{{{cols}}}\n"
            f"\\toprule\n  {' & '.join(_tex(h) for h in head)} \\\\\n\\midrule\n{body}\n\\bottomrule\n\\end{{tabular}}\n\\end{{table}}\n")


# ---------------------------------------------------------------- the pieces

def results_tables(project) -> list[tuple[str, list[str], list[list[str]]]]:
    labels = (project.m.get("results") or {}).get("labels") or {}
    lp, ls = text(labels.get("primary")) or "primary", text(labels.get("secondary")) or "secondary"
    fields = [f for f in (project.m.get("runs") or {}).get("fields", [])][:2]
    met = {i: project.metrics(i) or {} for i in project.run_ids()}
    out = []
    for t in project.m.get("tables") or [{"title": "All runs", "runs": project.run_ids()}]:
        title = text(t.get("title"))
        if t.get("groups"):
            rows = []
            for g in t["groups"]:
                vals = [met.get(r, {}).get("primary") for r in g["runs"]]
                vals = [v for v in vals if v is not None]
                mean = sum(vals) / len(vals) if vals else None
                sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)) if len(vals) > 1 else None
                rows.append([text(g.get("label")), ", ".join(g["runs"]), f"{_num(mean)} ± {_num(sd)}" if sd is not None else _num(mean), str(len(vals))])
            out.append((title, ["Group", "Runs", f"{lp} (mean ± sd)", "n"], rows))
        else:
            rows = []
            for r in t.get("runs") or []:
                if r not in met:
                    continue
                spec = project.spec(r)
                rows.append([r, *[str(spec.get(f, "–")) for f in fields], _num(met[r].get("primary")), _num(met[r].get("secondary"))])
            out.append((title, ["Run", *fields, lp, ls], rows))
    return out


def hypotheses_rows(h: dict) -> list[list[str]]:
    parts = h.get("parts") or [{}]
    rows = []
    for i, p in enumerate(parts):
        ci = p.get("ci")
        rows.append([h["id"] if i == 0 else "", p.get("text") or h.get("criterion") or "–", _num(p.get("margin")),
                     f"[{_num(ci[0])}, {_num(ci[1])}]" if ci else "–", MARK.get(p.get("verdict") or h["verdict"], h["verdict"])])
    if len(parts) > 1:
        rows.append(["", "all", "", "", MARK.get(h["verdict"], h["verdict"])])
    return rows


def methods(project, hyp: dict) -> str:
    st, pl, rec = hyp["status"], project.pl, hyp["status"].get("record")
    lines = ["# Methods (draft written by runboard from the project's files)", ""]
    lines += ["## Pre-registration", ""]
    if rec:
        git = rec.get("git") or {}
        devs = st.get("deviations") or []
        lines.append(f"The questions, hypotheses and evaluation protocol were written in `{rec['plan']}` and locked on "
                     f"{rec['locked_at'][:10]}" + (f" at commit `{git['commit'][:10]}`" if git.get("commit") else "")
                     + (" (the folder had uncommitted changes at that moment)" if git.get("dirty") else "")
                     + f". The lock records SHA-256 fingerprints of the plan "
                     f"(`{rec['plan_sha256'][:12]}`) and of the runs (`{rec['runs_sha256'][:12]}`). "
                     + (f"{len(devs)} deviation{'s' if len(devs) != 1 else ''} were recorded after the lock; see Deviations."
                        if devs else "No deviation from the locked plan was recorded."))
    else:
        lines.append("The plan has not been locked: these hypotheses are not pre-registered.")
    lines += ["", "## Questions and hypotheses", ""]
    by_q = {}
    for h in hyp["hypotheses"]:
        by_q.setdefault(h.get("question") or "", []).append(h)
    for q in hyp["questions"]:
        lines.append(f"**{q['id']}.** {text(q.get('text'))}")
        for h in by_q.pop(q["id"], []):
            lines.append(f"- *{h['id']}*: {text(h.get('text')) or '(no text)'} Criterion: `{h.get('criterion') or 'none'}`.")
        lines.append("")
    for h in [x for v in by_q.values() for x in v]:
        lines.append(f"- *{h['id']}*: {text(h.get('text')) or '(no text)'} Criterion: `{h.get('criterion') or 'none'}`.")
    lines += ["## Experiments", ""]
    doc = project.doc()
    defaults = dict(doc.get(project.defaults_section) or {}) if project.defaults_section else {}
    if defaults:
        lines.append("Shared settings: " + ", ".join(f"{k} = {v}" for k, v in defaults.items() if v is not None) + ".")
    for ph in project.m.get("phases") or []:
        runs = ph.get("runs") or []
        desc = "; ".join(f"{r} (" + ", ".join(f"{k} {v}" for k, v in project.spec(r).items()
                                              if k not in ("id",) and k not in defaults and v is not None) + ")"
                         for r in runs if r in doc.get(project.section, {}))
        lines.append(f"- **{ph.get('id')} · {text(ph.get('title'))}**: {desc}.")
    groups = pl.get("groups") or {}
    if groups:
        lines.append("")
        lines.append("Seed repeats: " + "; ".join(f"{g} = {', '.join(map(str, rs))}" for g, rs in groups.items()) + ".")
    pr = hyp["protocol"]
    sealed = [s for s, o in pr["sets"].items() if (o or {}).get("sealed")] if isinstance(pr["sets"], dict) else []
    plans = []
    from .hypotheses import Evidence
    ev = Evidence(project.root, pl.get("protocol") or {})
    for s in ev.sets:
        p = ev.plan(s)
        if p:
            plans.append(f"{s}: {len(p['ids'])} images, {p['replicates']} replicates, seed {p['seed']}")
    lines += ["", "## Evaluation and decision rule", "",
              f"Every run is evaluated on each evaluation set ({', '.join(ev.sets) or 'none named'}) with the metric "
              f"`{pr['metric']}`. Uncertainty comes from an image-level bootstrap: each set has one resampling plan "
              f"({'; '.join(plans) or 'not written yet'}), shared by every run, so the k-th replicate of every run is "
              "measured on the same images and comparisons between runs are paired. "
              "A criterion is computed on the full set (the reported value) and on every replicate; for a comparison "
              "the margin (left − right for > and ≥) is *supported* when its whole 95 % percentile interval is above "
              "zero, *refuted* when it is below zero and *indistinguishable* otherwise. A criterion joined with *and* "
              "is refuted if any part is and supported only if all parts are. For seed groups the replicate value is "
              "the mean over the group's runs; the spread over seeds is reported beside the verdict."]
    if sealed:
        lines.append(f"\nThe sets {', '.join(sealed)} are sealed (held-out): each final model is evaluated on them once, "
                     "and every use is written to a ledger.")
    lines += ["", "## Software", "",
              f"Runs were planned, launched and decided with runboard {__version__}; the analysis code is in the "
              "project's repository" + (f" (commit `{(rec.get('git') or {}).get('commit', '')[:10]}` at the lock)."
                                       if rec and (rec.get("git") or {}).get("commit") else ".")]
    return "\n".join(lines) + "\n"


def deviations_section(hyp: dict) -> str:
    devs = hyp["status"].get("deviations") or []
    if not hyp["status"].get("record"):
        return "# Deviations\n\nThe plan was not locked, so there is nothing to deviate from.\n"
    if not devs:
        return "# Deviations\n\nNo change was made to the plan, the runs or the locked scripts after the lock.\n"
    rows = [[(d.get("time") or "")[:16].replace("T", " "), d.get("file") or "", d.get("reason") or ""] for d in devs]
    return "# Deviations\n\nEvery change after the lock, with its reason (the diffs are in deviations.md).\n\n" + \
        _md_table(["When", "What", "Why"], rows) + "\n"


def checklist(project, hyp: dict) -> list[tuple[str, str, str]]:
    st, rec = hyp["status"], hyp["status"].get("record")
    hs = hyp["hypotheses"]
    states = project.state.all()
    starts = sorted(s.get("pushed_at") for s in states.values() if s.get("pushed_at"))
    out = []
    if rec:
        before = not starts or rec["locked_at"][:19] <= starts[0]
        out.append(("Hypotheses fixed before the experiments", "✓" if before else "✗",
                    f"locked {rec['locked_at'][:16]}" + ("" if before else f", but the first run started {starts[0][:16]}")))
    else:
        out.append(("Hypotheses fixed before the experiments", "✗", "the plan is not locked"))
    crit = [h for h in hs if h.get("criterion")]
    out.append(("Every hypothesis has a machine-checked criterion", "✓" if hs and len(crit) == len(hs) else "✗" if hs else "–",
                f"{len(crit)} of {len(hs)}"))
    decided = [h for h in hs if h["verdict"] in ("supported", "refuted", "indistinguishable")]
    out.append(("Verdicts come with 95 % intervals", "✓" if decided else "–", f"{len(decided)} decided"))
    groups = project.pl.get("groups") or {}
    out.append(("Variation over training seeds is measured", "✓" if groups else "✗",
                f"{len(groups)} seed group(s)" if groups else "no seed groups in plan.yaml"))
    sealed = st.get("sealed") or []
    twice = len(st.get("ledger") or []) != len({(r.get("set"), r.get("weights")) for r in st.get("ledger") or []})
    out.append(("A held-out set is evaluated once per model", "✗" if twice else "✓" if sealed else "–",
                "a model was evaluated twice (see the ledger)" if twice else f"sealed: {', '.join(sealed)}" if sealed else "no sealed set"))
    if rec:
        clean = st.get("plan_ok") and st.get("runs_ok") and st.get("code_ok") is not False
        out.append(("Every change after the lock is recorded", "✓" if clean else "✗",
                    f"{len(st.get('deviations') or [])} deviation(s)" if clean else "a file changed without a recorded deviation"))
    git = (rec or {}).get("git")
    out.append(("Code is under version control", "✓" if git else "✗", f"commit {git['commit'][:10]}" if git else "no git repository"))
    with_prov = [r for r, s in states.items() if (s.get("provenance") or {}).get("git")]
    out.append(("Each run records what it started from", "✓" if states and len(with_prov) == len(states) else "–" if not states else "✗",
                f"{len(with_prov)} of {len(states)} started runs"))
    hours = [(project.metrics(r) or {}).get("hours") for r in project.run_ids()]
    hours = [h for h in hours if isinstance(h, (int, float))]
    out.append(("Compute is reported", "✓" if hours else "–", f"{sum(hours):.1f} GPU hours over {len(hours)} runs" if hours else "no run reports its hours"))
    return out


# ---------------------------------------------------------------- the page

CSS = """:root{--bg:#f6f6f3;--card:#fff;--ink:#1b1b19;--muted:#6e6e68;--line:#e2e2dc;--ok:#1f7a55;--bad:#b3261e;--mid:#8a6d00}
@media(prefers-color-scheme:dark){:root{--bg:#121211;--card:#1b1b1a;--ink:#ededea;--muted:#93938c;--line:#2a2a28;--ok:#5cc596;--bad:#f2766c;--mid:#d9b84a}}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,sans-serif}main{max-width:980px;margin:0 auto;padding:28px 16px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:28px 0 10px}p.m{color:var(--muted);margin:0 0 18px}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:12px 0}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}code{font:12.5px ui-monospace,Consolas,monospace}
.v{font-weight:600;white-space:nowrap}.supported,.ok{color:var(--ok)}.refuted,.bad{color:var(--bad)}.indistinguishable,.mid{color:var(--mid)}
.wrap{overflow-x:auto}"""


def _h(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _html_table(head, rows, num_from=2) -> str:
    th = "".join(f"<th{' class=n' if i >= num_from else ''}>{_h(x)}</th>" for i, x in enumerate(head))
    trs = "".join("<tr>" + "".join(f"<td{' class=n' if i >= num_from else ''}>{_h(c)}</td>" for i, c in enumerate(r)) + "</tr>"
                  for r in rows)
    return f"<div class=wrap><table><tr>{th}</tr>{trs}</table></div>"


def report_html(project, hyp: dict, tables, checks) -> str:
    st, rec = hyp["status"], hyp["status"].get("record")
    name = project.m.get("name", project.key)
    lock = (f"Locked {_h(rec['locked_at'][:16].replace('T', ' '))}" + (f" at commit <code>{_h((rec.get('git') or {}).get('commit', '')[:10])}</code>"
            if (rec.get("git") or {}).get("commit") else "") + f" · plan <code>{_h(rec['plan_sha256'][:12])}</code>") if rec else "Not locked"
    parts = []
    by_q = {}
    for h in hyp["hypotheses"]:
        by_q.setdefault(h.get("question") or "", []).append(h)
    for q in hyp["questions"] + [{"id": "", "text": "Other hypotheses"}]:
        hs = by_q.get(q["id"], [])
        if not hs:
            continue
        rows = "".join(
            f"<tr><td><b>{_h(h['id'])}</b><br><span class=m>{_h(text(h.get('text')))}</span></td><td><code>{_h(h.get('criterion') or '–')}</code>"
            + "".join(f"<br><span class=m>{_h(p['text'])}: {_num(p.get('margin'))} [{_num((p.get('ci') or [None, None])[0])}, "
                      f"{_num((p.get('ci') or [None, None])[1])}]</span>" for p in h.get("parts") or [])
            + f"</td><td class='v {h['verdict']}'>{_h(MARK.get(h['verdict'], h['verdict']))}</td></tr>" for h in hs)
        parts.append(f"<section><h2>{_h(q['id'])} {_h(text(q.get('text')))}</h2><div class=wrap><table>"
                     f"<tr><th>Hypothesis</th><th>Criterion · margin [95 % interval]</th><th>Verdict</th></tr>{rows}</table></div></section>")
    tabs = "".join(f"<section><h2>{_h(t)}</h2>{_html_table(head, rows, len(head) - 2)}</section>" for t, head, rows in tables)
    devs = st.get("deviations") or []
    dev = _html_table(["When", "What", "Why"], [[(d.get("time") or "")[:16].replace("T", " "), d.get("file"), d.get("reason")] for d in devs], 9) \
        if devs else "<p>No deviation was recorded.</p>" if rec else "<p>The plan is not locked.</p>"
    chk = "".join(f"<tr><td class='v {'ok' if s == '✓' else 'bad' if s == '✗' else 'mid'}'>{_h(s)}</td><td>{_h(t)}</td><td class=m>{_h(d)}</td></tr>"
                  for t, s, d in checks)
    led = _html_table(["When", "Run", "Set", "Weights"], [[(r.get("time") or "")[:16], r.get("run"), r.get("set"), (r.get("weights") or "")[:12]]
                                                          for r in st.get("ledger") or []], 9) if st.get("ledger") else ""
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{_h(name)} · registered report</title><style>{CSS}</style></head><body><main>"
            f"<h1>{_h(name)}</h1><p class=m>{_h(text(project.m.get('description')))}</p>"
            f"<p class=m>Registered report written by runboard {__version__} on {datetime.now():%Y-%m-%d %H:%M} · {lock}</p>"
            f"{''.join(parts)}<h2>Results</h2>{tabs}<h2>Deviations</h2><section>{dev}</section>"
            + (f"<h2>Sealed sets</h2><section>{led}</section>" if led else "")
            + f"<h2>Reproducibility checklist</h2><section><table>{chk}</table></section></main></body></html>")


# ---------------------------------------------------------------- everything

def export(project, out: str = OUT) -> dict:
    from .prereg import hypotheses
    from .templating import tracked
    d = project.root / out
    d.mkdir(parents=True, exist_ok=True)
    hyp = hypotheses(project) if project.v2 else {"questions": [], "hypotheses": [], "protocol": {"metric": "", "sets": {}, "dir": "eval"},
                                                   "status": {"v2": False}}
    tables = results_tables(project)
    checks = checklist(project, hyp) if project.v2 else []
    files = {}
    files["tables.md"] = "\n\n".join(f"### {t}\n\n{_md_table(h, r)}" for t, h, r in tables) + "\n"
    files["tables.tex"] = "% needs \\usepackage{booktabs}\n" + "\n".join(_tex_table(t, h, r) for t, h, r in tables)
    hrows = [r for h in hyp["hypotheses"] for r in hypotheses_rows(h)]
    hhead = ["Hypothesis", "Criterion", "Margin", "95 % interval", "Verdict"]
    files["hypotheses.md"] = _md_table(hhead, hrows) + "\n"
    files["hypotheses.tex"] = "% needs \\usepackage{booktabs}\n" + _tex_table("Hypotheses and their verdicts", hhead, hrows)
    if project.v2:
        files["methods.md"] = methods(project, hyp)
        files["deviations.md"] = deviations_section(hyp)
        files["checklist.md"] = "# Reproducibility checklist\n\n" + _md_table(["", "Item", "Evidence"], [[s, t, e] for t, s, e in checks]) + "\n"
    files["report.html"] = report_html(project, hyp, tables, checks)
    files["provenance.json"] = json.dumps({r: s.get("provenance") for r, s in project.state.all().items()}, indent=1,
                                          ensure_ascii=False) + "\n"
    for name, content in files.items():
        (d / name).write_text(content, encoding="utf-8", newline="\n")

    rel = lambda p: p.relative_to(project.root).as_posix()
    take = [project.root / "runboard.yaml", project.runs_file]
    if project.v2:
        take += [project.plan_file, project.plan_file.parent / "plan.lock.json", project.root / "deviations.md"]
    take += [project.root / p for p in tracked(project)]
    take += [project.root / str(x.get("log", "decisions.md")) for x in project.decision_specs()]
    ev_dir = project.root / str((project.pl.get("protocol") or {}).get("dir") or "eval")
    if ev_dir.is_dir():
        take += [f for f in ev_dir.rglob("*") if f.suffix in (".json", ".csv")]
    take += [d / n for n in files]
    zpath = d / "archive.zip"
    seen = set()
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in take:
            if f.is_file() and f.resolve() != zpath.resolve() and rel(f) not in seen:
                seen.add(rel(f))
                z.write(f, rel(f))
    return {"dir": rel(d), "files": sorted([*files, "archive.zip"]), "archived": len(seen)}
