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

Only one run per backend at a time. Kaggle runs cannot be cancelled through the API (use *Open on Kaggle*); local runs can.

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
    criterion: "collapse(R4, ground, aerial) > 50"   # checked from RB-1 on; plain text until then
protocol: {metric: map50_95, sets: [ground, aerial], replicates: 200}
groups:
  ground_only: [R4, R9, R10]  # seed repeats; a group name can stand where a run does
decisions:                    # as above
  - {id: A3, candidates: [R1, R2, R3], field: model, tie: 1.0}
locked: true                  # pre-registered: runs change only through decisions and extra runs
```

Both files can be edited on the project's Settings page. Every edit is checked before it is written (ids are
unique, every run and question named exists), shown as a diff first, refused if the file changed meanwhile, and
backed up. A locked plan is shown read-only, and the manifest cannot point the lock at another runs file.
`runboard.yaml` holds the commands runboard runs, so it is edited only on the computer runboard runs on.

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
