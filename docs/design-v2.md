# Design: manifest v2 and the pre-registration core

Status: built in RB-0 and RB-1; the reference is [manifest.md](manifest.md#planyaml-version-2) (see [ROADMAP.md](../ROADMAP.md)). Four decisions are fixed here because
changing them later would break projects and results.

## 1. Files: science apart from infrastructure

A lock fingerprints files. If one file mixed "what we test" with "how we run it", switching a GPU or a backend
would look like a deviation, or a real change of a hypothesis could hide among infrastructure edits. So:

| File | Holds | Locked |
|---|---|---|
| `runboard.yaml` | infrastructure and presentation: name, backends, commands, data upload, results paths, jobs, progress patterns, **phases and tables** (how the dashboard groups and shows runs) | no |
| `plan.yaml` | science: **questions, hypotheses, evaluation protocol, groups, decisions** | yes |
| `runs.yaml` (any name) | the runs and their shared training settings | yes, except extra runs |
| `plan.lock.json` | the lock record (RB-1) | written once |
| `deviations.md` | every change after the lock, with its reason (RB-1) | appended |

`runboard.yaml` says `version: 2` and names the plan file (`plan: plan.yaml`, the default). A project without
`plan.yaml` is a plain v1 project and keeps working: decisions and `runs.locked` are read from `runboard.yaml` as
before.

`plan.yaml`:

```yaml
questions:
  - id: S2
    text: {en: How much aerial data closes the gap?, tr: Ne kadar hava verisi açığı kapatır?}
hypotheses:
  - id: H2b
    question: S2
    text: {en: 25 % of the aerial data reaches 90 % of the aerial specialist.}
    criterion: "R7.aerial >= 0.9 * R5.aerial"        # read by RB-1; plain text until then
protocol:
  metric: map50_95                                     # what R7.aerial means
  sets: [ground, aerial]                               # evaluation sets, each with its own resampling plan
  replicates: 200
groups:
  ground_only: [R4, R9, R10]                           # seed groups; a group name works wherever a run does
decisions:                                             # moved here from runboard.yaml
  - {id: A3, candidates: [R1, R2, R3], field: model, tie: 1.0, log: reports/decisions.md}
locked: true                                           # until RB-1 replaces it with plan.lock.json
```

`runboard migrate <folder>` turns a v1 project into v2: it moves `decisions` and `runs.locked` into a new
`plan.yaml`, adds `version: 2`, keeps every comment of the moved text, backs up the old manifest and checks that the
two files together mean exactly what the old one meant. It is optional and runs only when asked.

Editing from the dashboard: `plan.yaml` from any paired device (it holds no commands; criteria are parsed, never
run), `runboard.yaml` from this computer only (it holds commands, so editing it is running code). Both are previewed as
a diff, checked against concurrent edits, backed up and logged, like the runs file. A locked plan is not edited; after
RB-1 a change of a locked plan is a deviation with a reason.

## 2. Evaluation output: replicate values on a shared resampling plan

A verdict needs to know how much each number would move on other images. The evaluation therefore reports, for every
run, set and metric, the value on the full set **and** on each bootstrap replicate. A summary number alone cannot give
an interval; raw predictions would be large and different for every task.

Comparisons between models must be paired: replicate 17 of R4 and replicate 17 of R7 have to be measured on the same
images, or the interval of their difference is too wide and real differences look indistinguishable. So runboard, not
each evaluation script, owns the resampling:

`eval/resample-<set>.json`, written once per set and part of the lock:

```json
{"format": "runboard-resample/1", "set": "aerial", "ids_sha256": "…", "ids": ["img_0001", "…"],
 "replicates": 200, "seed": 20261031, "generator": "numpy.random.default_rng(seed).integers(0, n, n) per replicate"}
```

`ids_sha256` is the SHA-256 of the ids joined by newlines. `rb.replicates(set)` in `rb.py` returns the same index
lists in any script. A changed image list is detected by its hash and refused.

`eval/<run>/<set>.json`, written by the evaluation (the RB-2 template writes it; any script may):

```json
{"format": "runboard-eval/1", "run": "R7", "set": "aerial", "resample": "<ids_sha256>",
 "metrics": {"map50_95": {"point": 47.21, "replicates": [47.0, 47.6, "… 200 values"]},
             "map50_95@person": {"point": 41.3, "replicates": ["…"]}},
 "n": 1247, "code": {"file": "scripts/evaluate.py", "sha256": "…", "commit": "…"}}
```

Metrics that are means over images (accuracy) may instead give `samples`, one value per image in `ids` order; runboard
then draws the replicates itself.

A criterion is computed on the full-set values (the point) and on every replicate (the interval, 2.5 and 97.5
percentiles). For `a >= b` the margin `a − b` decides: *supported* if its whole interval is on the right side,
*refuted* if its whole interval is on the wrong side, *indistinguishable* otherwise. Missing evaluations give
*not ready*. With a seed group the replicate value is the mean over the group's runs on the same images, and the
seed spread (the standard deviation of the runs' values) is reported beside the verdict for the reader to weigh;
the interval itself covers the images, not the seeds.

## 3. Criterion language: comparisons, arithmetic and a small fixed library

Hypotheses must be checkable by a machine, readable by a reviewer and safe to edit from a tablet.

- References: `R7.aerial` (the protocol's metric), `R7.aerial.map50`, `R7.aerial@person` (one class), and a group
  name in place of a run.
- Numbers, `+ - * /`, parentheses, `< <= > >=`, `and`.
- Functions, each documented, versioned and tested:
  `collapse(run, from, to)` = 100 · (run.from − run.to) / run.from;
  `mean(...)`, `min(...)`, `max(...)`, `abs(x)`;
  `log_fit({R6: 10, R7: 25, R8: 50, R1: 100}, aerial)` with `.slope` and `.r2` (x must be above 0).

It is parsed with Python's `ast` against a whitelist and evaluated by runboard's own walker; `eval` is never used.
Every verdict shows the criterion with its functions written out, so the reviewer sees what was computed.

The language also makes vague hypotheses visible: "grows logarithmically" cannot be checked until it says how well
the curve must fit (`log_fit(...).r2 >= 0.9`), which is exactly what a pre-registration should pin down.

## 4. Templates: tracked, never overwriting a file you changed

A generated file starts with a header:

```python
# runboard-template: split 1.2
# params: {"seed": 0, "val": 0.1, "test": 0.1}
# sha256: 3f7a…  (of the generated text below this header)
```

- If the text still matches the hash, the file is **pristine**: when the template gets a new version, the dashboard
  offers the update as a diff.
- If it differs, the file is **owned** by the user and is never written again; a newer template only shows its diff
  for the user to apply by hand.
- Regenerating a file the lock covers (the split, the evaluation) is a deviation and needs a reason.
- Every run records the template names, versions and file hashes it used (RB-5).
