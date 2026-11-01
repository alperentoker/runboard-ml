# runboard.yaml reference

Every key is optional unless marked **required**. Texts shown in the UI (`description`, `title`, `subtitle`, `rule`,
`label`, `note`) can be a string or a `{en: …, tr: …}` map.

## Templates

Commands, names and paths are templates over the run's fields (its `defaults` merged with its own entry, plus `id`):

| Syntax | Meaning |
| :--- | :--- |
| `{id}`, `{seed}` | a field |
| `{model\|stem}` | filters: `stem` (file name without extension), `lower`, `upper`, `strip:PREFIX` |
| `{python}` | the interpreter runboard runs on (quote it: `'"{python}" train.py'`) |
| `{yaml:path/file.yaml:key.sub}` | a value read from a YAML file in the project |
| `{out}` | (results, jobs) the run's output directory |

## Project

```yaml
name: Thermal Detector          # shown on the card
id: thermal                    # stable key (state lives in ~/.runboard/state/<id>); defaults to the name
description: …
color: "#2c6b5a"               # card colour when there is no logo
logo: docs/logo.png            # optional image inside the project
```

## runs **required**

```yaml
runs:
  file: configs/runs.yaml      # **required** — YAML file that holds the runs
  section: runs                # mapping of run id -> fields inside that file
  defaults: train              # optional section merged under every run
  name: "{id}-{model|stem}-s{seed}"   # output folder name of a run
  fields: [package, model, seed]      # shown in lists and tables
  required: [model]            # a run with one of these null is "waiting" (e.g. for a decision)
  locked: true                 # pre-registered plan: planned runs are read-only (decisions and extras still work)
  show: [train, eval]          # file sections displayed as shared settings
  schema:                      # rules for editing runs from the dashboard (forms are built from these)
    model: {choices: [a.pt, b.pt]}          # one of a list; `$existing` = values already used by runs
    seed: {int: [0, 99], default: 0}        # whole number in a range
    lr0: {float: [0.0001, 0.1]}             # decimal number in a range
    cos_lr: {bool: true}                    # true / false
    data: {file: "*.yaml"}                  # a file inside the project matching the pattern
    note: {}                                # any value (read the way YAML reads it: "0.1" is a number)
    # add `required: true` to any rule to refuse an empty value
  extras:                      # allow extra runs from the UI (inserted after the last run)
    prefix: X                  # X1, X2 …
    heading: "Extra runs …"    # comment written above them
    fields:
      package: {choices: $existing, default: A}
      model: {choices: [a.pt, b.pt]}
      seed: {int: [0, 99], default: 0}
```

### Editing the plan from the dashboard

Fields listed in `schema`, in `extras.fields` or in `fields` can be edited; anything else in the runs file is never
touched. The rules:

- **A run that has started keeps its settings.** Its settings are saved when it starts; editing or removing it is
  refused, and *Copy* makes a new run from it instead. If the file is changed by hand afterwards, the run shows which
  fields differ from what it ran with.
- **A locked plan** (`locked: true`) is changed only through its decisions; copying one of its runs adds an extra run.
- **Only the edited run's lines change.** The value is rewritten in the style it was written in (`{…}` or one field
  per line); comments, blank lines, key order and line endings elsewhere stay byte for byte. A new run goes right
  after the last one, so the runs section does not have to be the last section of the file. Every edit is parsed back
  and compared with what was asked before anything is written.
- **No silent overwrites.** Each edit carries the version of the file the page was showing; if the file changed in the
  meantime (an editor, `git pull`), the edit is refused with `409` and the page reloads it. Any edit can be previewed
  as a diff first (`dry`).
- **A trail.** The file is backed up to `~/.runboard/state/<id>/backup/` before every change, and each change is logged
  with who made it (this computer or a paired device) in `~/.runboard/state/<id>/plan-log.jsonl`.

- **Shared settings.** The `defaults` section and the sections in `show` are edited key by key: in a block section
  only the changed key's line changes and a trailing comment keeps its column; a `{…}` section is rewritten on its
  line. Before saving, the dashboard lists which runs the change reaches: defaults reach runs that do not set the key
  themselves, `show` sections (read by the training code) reach every run; runs that already started keep what they
  ran with.
- **The whole file.** A text editor for what the forms cannot do, checked as you type: it must stay valid YAML (the
  error names its line), keep a mapping of runs, pass the schema rules, let every run resolve its name, and leave
  started runs exactly as they ran.
- In a locked plan the shared settings and the file are read-only too.

- **Sweeps.** *Settings → Sweep* takes several values per field (ticked or comma-separated) and adds one draft run per
  combination in a single edit, named after its values (`prefix-yolo11n-0`) and built on an optional base run; at most
  48 at once. In a locked plan the combinations become extra runs.

### Queue

One queue for all projects (`~/.runboard/queue.json`), added from a run's page (*Add to queue*) or right after a sweep.
Each backend runs one thing at a time: when it is free, the first entry for it starts by itself (checked every 20 s and
whenever something is added). An entry that cannot start yet stays and says why: the backend is busy or unavailable, or
the weekly Kaggle quota left is below the run's estimate (hours per epoch of the project's finished runs × its epochs).
A failed start keeps the entry with the error; a run removed from the plan leaves the queue. Entries can be moved up and
down or removed. API: `GET /api/queue`, `POST /api/queue` (`project`, `run` or `runs`, `backend`),
`DELETE /api/queue/<entry>`, `POST /api/queue/<entry>/move` (`by`: -1 or 1).

### Error messages

API errors carry a `code` and its values (`{"detail": "...", "code": "range", "params": {...}}`); `detail` is English
and the dashboard shows the same code in the interface language. The catalog is `runboard/errors.py`.

API: `POST /api/p/<id>/plan/sweep` (`grid`, `base`, `prefix`), `GET /api/p/<id>/plan`, `POST /api/p/<id>/plan/runs` (`id`, `values`, `copy_from`, `note`), `PUT` and `DELETE`
`/api/p/<id>/plan/runs/<run>`, `PUT /api/p/<id>/plan/section/<name>` (`values`, `null` removes a key) and
`PUT /api/p/<id>/plan/raw` (`text`); all writes take `version` and `dry`.

## backends

```yaml
default_backend: kaggle
backends:
  kaggle:
    kernel: "thermal-{id|lower}"         # kernel slug (private script kernel per run)
    files: {train.py: scripts/train.py}  # copied into the kernel (destination: source)
    setup: ["pip install -q ultralytics=={yaml:configs/runs.yaml:ultralytics}"]
    command: "python -u train.py --run {id}"   # runs inside the kernel's code folder
    resume: "python -u train.py --run {id} --resume {resume}"   # optional, see "Resuming" below
    accelerator: NvidiaTeslaT4
    internet: true
    output_dir: runs/kaggle              # where outputs are downloaded (the kernel writes to /kaggle/working)
  local:
    command: '"{python}" -u scripts/train.py --run {id}'
    output_dir: runs/local
    python: C:/envs/train/python.exe     # optional: {python} in the commands is this interpreter, and its folder
                                         # comes first on PATH (default: the one runboard runs on)
```

A machine over SSH (a rented GPU, a lab server) and a SLURM cluster use the system's own `ssh`, with your keys and
agent; runboard never sees a password (it runs ssh with `BatchMode=yes`). The remote side needs a POSIX shell and tar,
and SLURM its `sbatch`, `sacct` and `scancel`.

```yaml
  ssh:
    host: gpu-box                        # an alias from ~/.ssh/config, or user@host (port: 2222 if needed)
    workdir: ~/runboard/{project}        # where the code is copied at each start (default as shown)
    python: python3                      # {python} in the commands
    setup: ["pip install -q ultralytics"]
    command: '"{python}" -u train.py --run {id}'
    output: runs/{name}                  # the run's outputs, relative to workdir
    output_dir: runs/ssh                 # where they are brought home
    upload: [train.py, configs]          # optional; default: the files of the Code page (no data, no outputs)
  slurm:
    host: login.cluster.edu
    sbatch: {partition: gpu, gres: "gpu:1", time: "12:00:00", mem: 32G, cpus-per-task: 8, account: mylab}
    command: '"{python}" -u train.py --run {id}'   # the rest as for ssh
```

Data is not copied: put it on the remote machine once, at the same path relative to `workdir` as in the project. Each
run keeps its log, exit code and process (or job) id in `<workdir>/.runboard/`, so it survives a dashboard restart.

One run at a time per backend; for SSH, one per host; a SLURM cluster takes as many jobs as you queue and runs them
in its own order. Kaggle runs cannot be cancelled through the API (use *Open on Kaggle*); local, SSH and SLURM runs
can.

### Resuming

With a `resume:` command, a run that stopped (error or cancelled) gets *Resume* on its page. The new attempt runs the
`resume` command with `{resume}` set to the stopped attempt's output, keeps the settings the run first started with and
counts attempts. On the **local** backend `{resume}` is the run's output folder. On **Kaggle** the attempt is a new
kernel `<kernel>-r2`, `-r3` … with the stopped kernel's output attached, and `{resume}` is
`/kaggle/input/<stopped kernel>/<run name>`; this works only if Kaggle kept the stopped version's output (check the version's *Output* tab first). Your training script decides what
resuming means, for example Ultralytics `model.train(resume=True)` from `weights/last.pt`.

## data (Kaggle)

```yaml
data:
  dir: data/packages                 # where the zips are
  catalog: reports/packages.csv      # one row per package
  key: package                       # catalog column with the package name (zip: <key>.zip or column "zip")
  field: package                     # run field that names the package a run uses
  columns: {train: train_images, val: val_images, size_mb: size_mb}
  build_job: package                 # job that rebuilds the packages
  forbid: ['(^|/)(images|labels)/test/']   # regexes; an archive containing a match is never uploaded
  datasets: {Combined: thermal-packages}   # existing datasets
  dataset_prefix: thermal-pkg-       # name for new ones
```

Each package is its own **private** Kaggle dataset; a kernel mounts only the one its run uses.

## results

```yaml
results:
  report: "reports/runs/{name}.json"       # a run counts as finished when this exists
  metrics: {primary: val_map, secondary: val_map50, best_epoch: best_epoch, epochs: epochs_completed, hours: train_hours}
  labels: {primary: val mAP50-95, secondary: mAP50}
  final: "{out}/final_val.json"
  per_class: {path: per_class, metric: map50_95, scale: 100, names: [person, vehicle]}
  curves: {file: "{out}/results.csv", format: ultralytics}   # or columns: {csv column: key}
  after: '"{python}" scripts/check_run.py "{out}"'             # runs after outputs are downloaded
  column: model                          # optional: the field shown after the run in the results table
  note: …
```

## phases, decisions, tables

```yaml
phases:                      # roadmap on the overview; also groups the run list
  - {id: A3, title: Architecture, subtitle: three models, runs: [R1, R2, R3]}

decisions:
  - id: A3
    title: Winning architecture
    rule: "Choose by validation mAP only; below 1 point pick the fastest."
    candidates: [R1, R2, R3]
    field: model             # every "model: null" in the runs file becomes the chosen value
    tie: 1.0                 # warn when the gap is below this
    log: reports/decisions.md

tables:
  - {title: Table 1, runs: [R1, R2, R3]}
  - {title: Data efficiency, runs: [R4, R6], curve: {x: {R4: 0, R6: 10}, label: aerial %}}
  - {title: Variance, groups: [{label: Ground, runs: [R4, R9, R10]}]}
```

In a version 2 project, `decisions` live in `plan.yaml` (below); `phases` and `tables` stay here.

## plan.yaml (version 2)

`version: 2` in `runboard.yaml` moves the science of the project into its own file, so that a lock can cover what is
tested without covering how it is run ([design](design-v2.md)). `runboard migrate` turns a version 1 project into
version 2: it moves `decisions` and `runs.locked` with their comments and checks that nothing else changed.

```yaml
# runboard.yaml
version: 2
plan: plan.yaml              # the default
```

```yaml
# plan.yaml
questions:
  - {id: S1, text: {en: Does a ground-trained detector collapse from the air?}}
hypotheses:
  - id: H1
    question: S1
    text: {en: The ground model loses most of its accuracy on aerial images.}
    criterion: "collapse(R4, ground, aerial) > 50"
protocol:
  dir: eval                   # where the evaluation files are (the default)
  metric: map50_95            # what R4.aerial means
  sets: [ground, aerial]      # or {ground: {}, test: {sealed: true}}
groups:
  ground_only: [R4, R9, R10]  # seed repeats; a group name can stand where a run does
decisions:                    # as above
  - {id: A3, candidates: [R1, R2, R3], field: model, tie: 1.0}
```

Both files can be edited on the project's Settings page. Every edit is checked before it is written (ids are
unique, every run and question named exists), shown as a diff first, refused if the file changed meanwhile, and
backed up. The manifest cannot point a lock at another runs file. `runboard.yaml` holds the commands runboard runs, so
it is edited only on the computer runboard runs on.

### Criteria

A criterion is one comparison, or several joined with `and`. It is checked whenever `plan.yaml` is saved: it must
parse, and every run, group and set it names must exist.


| Written | Means |
| :--- | :--- |
| `R7.aerial` | R7's protocol metric on the set `aerial` |
| `R7.aerial.map50`, `R7.aerial@person`, `R7.aerial.map50@person` | another metric, one class, both |
| `ground_only.aerial` | the mean of a group's runs, replicate by replicate |
| `+ - * /`, numbers, parentheses, `< <= > >=`, `and` | as usual |
| `collapse(R4, ground, aerial)`, `collapse(R4@person, ground, aerial)` | 100 · (R4.ground − R4.aerial) / R4.ground |
| `mean(...)`, `min(...)`, `max(...)`, `abs(x)` | replicate by replicate |
| `log_fit({R6: 10, R7: 25, R8: 50}, aerial).r2`, `.slope` | fit of score = a + slope · ln(x), x above 0 |

Nothing else is accepted: no names but runs, groups, sets, metrics and classes, no strings, no other functions.

Each comparison is decided by its margin (left − right for `>`, right − left for `<`) on the whole set and on every
bootstrap replicate: **supported** if the whole 95 % interval of the margin is above 0, **refuted** if it is below,
**indistinguishable** otherwise; a criterion is refuted if any comparison is, supported if all are. A missing
evaluation makes it **waiting**. The project's Hypotheses page and `runboard verdicts` show each comparison's
values, margin, interval and the share of replicates above 0.

### Evaluation files

```
eval/resample-ground.json   {"format": "runboard-resample/1", "ids": [...], "ids_sha256": ..., "seed": 0, "replicates": 200}
eval/R7/ground.json         {"format": "runboard-eval/1", "run": "R7", "set": "ground", "resample": <ids_sha256>,
                             "metrics": {"map50_95": {"point": 47.2, "replicates": [... 200 values]}}}
```

`ids_sha256` is the SHA-256 of the ids joined by newlines. Replicate k of every run uses the same images:
`numpy.random.default_rng(seed).integers(0, n, n)`, drawn k times in order. `rb.py` writes both files
(`rb.replicates`, `rb.write_eval`); a metric that is a mean over images may give `samples` (one value per id) instead
of `replicates`, and runboard draws them. Before evaluating a sealed set, `rb.sealed(set, run, weights_sha256)` refuses
the same weights twice and writes `eval/ledger.csv`, which the Hypotheses page lists.

### Lock and deviations

`runboard lock` (or *Lock the plan* on the Hypotheses page, on this computer) writes `plan.lock.json`: when, the git
commit and whether the folder had uncommitted changes, and the fingerprints of `plan.yaml`, of the runs (without extra
runs and without the fields decisions fill) and of each resampling plan. Commit the plan first. After the lock,
`plan.yaml` and the runs file change only with a reason; each change is appended to `deviations.md` with its diff and
the fingerprints after it, so the page can tell whether the files on disk are the locked ones plus recorded
deviations. A version 1 project, or `locked: true` without a record, keeps the older rule: only decisions and extra
runs.

## The research wizard

*New project → Pre-registered study (YOLO)* writes a version 2 project from a few answers:

| Step | Asks for | Becomes |
| :--- | :--- | :--- |
| Questions | ids and one line each | `plan.yaml` questions; phase titles |
| Design | data packages (`key` → data.yaml), model and schedule, experiment designs | runs `R1, R2, ...` with `data`, `model`, `seed` and `train:` settings; a phase and a table per design; seed repeats `R1s1, R1s2` and the group `R1_seeds` |
| Protocol | evaluation sets (`name=image list`), sealed sets, metric, replicates | `plan.yaml` protocol; `scripts/evaluate.py` |
| Hypotheses | id, question, text, criterion | `plan.yaml` hypotheses, each criterion checked against the planned runs as it is typed |

Designs: **specialists** (one run per package), **data-size curve** (a base package plus nested shares of another;
`scripts/subsets_N.py` writes the lists the runs train on), **architectures** (several models on one package),
**ablation** (one Ultralytics setting at several values). The wizard suggests criteria from them (which specialist
collapses more, a logarithmic fit of the curve, the first ablation value against the second). *Lock the plan when the
project is created* writes `plan.lock.json` right away; commit the new files after it.

## templates (code written by runboard)

The Settings page (*Code templates*, on this computer) and `runboard template NAME [folder] --set key=value` write
ordinary Python scripts into the project and list them here. Each starts with the template, its version, its
parameters and the SHA-256 of the text below; while the text matches, runboard may rewrite it (new settings, a newer
template, always after showing the diff). Once you change it, it is yours and runboard does not write it again.

```yaml
templates:
  scripts/split.py: split
  scripts/evaluate.py: evaluate
jobs:                                   # added the first time, run from the dashboard
  evaluate: {title: Evaluate for the hypotheses, cmd: '"{python}" -u scripts/evaluate.py --run {id} --weights "{out}/weights/best.pt"', per_run: true}
```

| Template | Writes |
| :--- | :--- |
| `convert` | YOLO `images/` and `labels/` (hard links or copies) with `classes.txt` from a COCO `.json` or VOC `.xml` files; crowd regions and, if asked, VOC difficult objects left out; boxes clipped to the image |
| `split` | train / val / test lists from a YOLO image folder, seeded; images with the same group key (a regex on the name: a video, a scene) stay in one split; `data.yaml`, `split.json` with the lists' SHA-256 |
| `check` | label errors, the same image in two splits (a leak), duplicates, look-alike images across splits (with Pillow); exits 1 on errors or leaks |
| `subsets` | nested training lists with 10 / 25 / 50 % of one source added to a base, each with its `data.yaml` |
| `evaluate` | every evaluation set through the Ultralytics validator, with the shared bootstrap replicates: the files the hypotheses are decided from; sealed sets once per weights (`--again` is recorded) |
| `speed` | milliseconds per image at batch 1 for preprocessing, inference and postprocessing (median, p90) and FPS, with the software and device |

Under a lock, the tracked scripts are part of what is locked: rewriting one needs a reason (a deviation), and a
script changed by hand shows on the Hypotheses page until it is recorded there as a deviation.

## The Code page

Every project has a *Code* page: the text files of the project (Python, YAML, JSON, TOML, shell, notebooks, text),
without data packages, backend outputs, environments and hidden folders, up to 512 KB each. Any paired device can
read them; only this computer can change them. Before a save, Python must compile and YAML / JSON must parse, and the
change is shown as a diff. `plan.yaml`, the runs file and `runboard.yaml` open on the Settings page instead. Under a
lock, a script the lock covers (written from a template) changes only with a reason, as a deviation.

Before a run is sent to Kaggle, the Python files in `backends.kaggle.files` are compiled; a syntax error stops it
here instead of after the kernel has started.

## Provenance and the paper

Each run records, when it starts, what it started from (`provenance` in its record, shown on the run page): the git
commit and whether the folder had uncommitted changes, the runboard version, the SHA-256 of the plan, of the runs
(as the lock counts them) and of every tracked script and every file sent to Kaggle, and its data package (key, file
count, size and a fingerprint of the file names and sizes).

`runboard export [folder]`, or *Export for the paper* on the Hypotheses page (this computer), writes `paper/`:

| File | Holds |
| :--- | :--- |
| `tables.md`, `tables.tex` | the tables of `runboard.yaml`; groups as mean ± sd (LaTeX needs `booktabs`) |
| `hypotheses.md`, `hypotheses.tex` | each hypothesis: criterion, margin, 95 % interval, verdict |
| `methods.md` | a draft: pre-registration, questions and hypotheses, experiments and settings, evaluation and decision rule |
| `deviations.md` | the deviations section |
| `checklist.md` | a reproducibility checklist filled from the files: ✓, ✗ or – with the evidence |
| `report.html` | one self-contained page with all of it, for a reviewer or a supervisor (no scripts) |
| `provenance.json` | every run's provenance |
| `archive.zip` | the plan, the lock, deviations, runs, manifest, tracked scripts, decision logs, evaluation files and the above; never data or weights |

## jobs

```yaml
jobs:
  tests: {title: Unit tests, cmd: '"{python}" -m pytest -q'}
  revalidate: {title: Re-validate, cmd: '"{python}" check.py "{out}"', per_run: true}   # offered on a finished run
```

## progress (plain-text logs)

Runs that use `rb.py` need nothing here. For existing human-readable logs, describe events with named groups:

```yaml
progress:
  marker: "■"                                   # only lines containing it are parsed / shown by default
  clock: '\[(?P<clock>\d\d:\d\d:\d\d) TSİ'       # wall-clock time on each line
  utc_offset: 3
  patterns:
    start: 'starting: (?P<epochs>\d+) epochs × (?P<batches>\d+) batches'
    epoch: 'epoch (?P<epoch>\d+)/(?P<epochs>\d+) done \((?P<time>[\d:]+)\) · (?P<loss>.*?) · map (?P<map>[\d.]+)'
    eta: 'left ~(?P<left>[\d:]+)'
    beat: 'epoch (?P<epoch>\d+)/\d+ · batch (?P<batch>\d+)/(?P<batches>\d+) · (?P<its>[\d.]+) it/s'
    stage: '▶ (?P<text>.+)'
    done: 'DONE: (?P<text>.*)'
```
