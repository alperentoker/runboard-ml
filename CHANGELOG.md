# Changelog

All notable changes to runboard. Versions follow [semantic versioning](https://semver.org/).

## 0.2.0 — 2026-11-01

First release on PyPI, as `runboard-ml` (`pip install runboard-ml`; the command is still `runboard`).
A version tag tests, builds and publishes it (RELEASING.md); the README is written for the PyPI page too.

Pre-registered experiments: the groundwork (RB-0) and the core (RB-1); see [ROADMAP.md](ROADMAP.md) and
[docs/design-v2.md](docs/design-v2.md).

### Added
- Hypotheses checked by machine: a criterion in `plan.yaml` (`R7.aerial >= 0.9 * R5.aerial`,
  `collapse(R4@person, ground, aerial) > ...`, groups of seed repeats, `log_fit(...)`) is decided from the evaluation
  files as *supported*, *refuted* or *indistinguishable*, with the margin's 95 % interval over bootstrap replicates
  every run shares. The language is parsed against a whitelist and never run as Python.
- Evaluation format (`runboard-eval/1`) and a shared resampling plan, with helpers in `rb.py`; per-image samples work
  too. Checked against Ground2Air's own analysis: the paired differences come out to the last digit.
- `runboard lock` and *Lock the plan*: `plan.lock.json` with the commit and fingerprints. A locked plan or runs file
  then changes only with a reason, recorded in `deviations.md`; the page shows whether the files match.
- A ledger of sealed-set (held-out test) evaluations; the same weights twice are refused unless asked for, and marked.
- The project's Hypotheses page, and `runboard verdicts` on the command line.
- Code templates (RB-2): `convert` (COCO / VOC to YOLO), `split` (seeded, group-aware train / val / test), `check`
  (label errors, leaks between splits, look-alike images), `subsets` (nested data-size lists), `evaluate` (YOLO,
  writing the verdicts' evaluation files) and `speed` (milliseconds per stage, FPS).
- Research wizard (RB-3): *Pre-registered study* in the new-project wizard asks for questions, data packages,
  experiment designs (specialists, a data-size curve, architectures, an ablation; seed repeats as groups), the
  evaluation protocol and the hypotheses, suggests criteria from the designs and checks every criterion against the
  planned runs while it is typed. It writes a version 2 project with its runs, phases, tables, `plan.yaml` and the
  evaluation (and subsets, check) scripts, and can lock the plan at once.
- `plan.yaml` edits check each criterion against the runs, groups and sets that exist, not only when its verdict is
  due. The YOLO training script passes a run's `train:` settings to Ultralytics.
- Code page (RB-4): the project's scripts and configs, with syntax colours, readable from paired devices and changed
  on this computer only. Python must compile and YAML / JSON parse before a save; every save is a diff first,
  refused after a concurrent change, backed up and logged. A script written from a template becomes the user's once
  changed; under a lock, a covered script changes only as a deviation. The plan, the runs file and runboard.yaml keep
  their own editors.
- The Python files of a Kaggle run are compiled before it is sent, so a typo does not cost quota.
- Smoke test for wizard projects: `runboard_train.py --smoke` trains one short epoch on 2 % of the data and keeps
  nothing; it is a per-run job (*Smoke test*).
- Provenance (RB-5): every run records what it started from: the commit and whether the folder had uncommitted
  changes, the fingerprints of the plan, the runs, the tracked scripts and the files sent with it, and a fingerprint
  of its data package. The run page shows it.
- `runboard demo` (RB-8): a five-minute pre-registered study on synthetic data (numpy only, any CPU): six runs, two
  hypotheses (one comes out supported, one refuted), an evaluation job, the paper export. docs/tutorial.md walks
  through it with screenshots.
- Every per-run job has a button on the run page (the smoke test, an evaluation) and the project's own jobs one on
  the Overview, each with its live output; the run list queues every run not started yet in one click.
- Local runs show as running the moment they start, and while one is going local runs and the queue are checked
  every 2 s instead of 20 (remote backends keep 20 s).
- SSH and SLURM backends (RB-6): a rented GPU or a lab server over SSH, and a cluster through `sbatch` on its login
  node. The system's ssh with your keys (never a password); the code is sent as a tar at each start, runs are detached
  with their own log, exit code and id on the remote side, logs stream live, outputs come home as a tar (nothing may
  land outside the output folder), runs can be stopped. One run per SSH host; a cluster takes as many jobs as queued.
  Both can be chosen in the new-project wizard.
- Paper output: `runboard export` (or *Export for the paper* on the Hypotheses page) writes paper/ with Markdown and
  LaTeX (booktabs) tables, the hypotheses with margins, intervals and verdicts, a methods draft, the deviations
  section, a reproducibility checklist filled from the files, a self-contained registered-report page, the runs'
  provenance and an archive (plan, lock, deviations, runs, scripts, evaluation files; no data, no weights) for Zenodo. Written from the Settings page or `runboard template`, listed in `runboard.yaml` with a job,
  rewritten only while unchanged; under a lock a rewrite is a deviation and a hand edit shows until it is recorded.
- Manifest version 2: questions, hypotheses, the evaluation protocol, seed groups, decisions and the lock live in
  `plan.yaml`, apart from how runs are started (`runboard.yaml`). Version 1 projects keep working unchanged.
- `runboard migrate` moves a project's decisions and lock into `plan.yaml`, comments included, and checks that the
  two files mean exactly what the old one did.
- `plan.yaml` and `runboard.yaml` are edited on the Settings page like the runs file: checked while typing, shown as
  a diff, refused after a concurrent change, backed up. The project file only on this computer, since it holds
  commands; a locked plan read-only.
- CI on macOS as well as Linux and Windows.

### Fixed
- A project can be removed from the dashboard (Settings, on this computer; its folder stays); before, only
  `runboard remove` could.
- Phones: inside a project the bottom bar holds the project's pages (New project and System stay on the home bar),
  scrolls sideways when they do not fit, and shows the open page.
- A project without a secondary metric no longer shows an empty column or figure; short runs show their duration in
  minutes or seconds instead of "0 h"; the six figures of a run fit the run pane (two rows of three).
- The Code page leaves out raw and downloaded datasets (raw/, datasets/); the Data page says it is loading while it
  asks Kaggle; unused interface texts are gone.
- `runboard[kaggle]` also installs `six`: newer Kaggle clients import it without depending on it, so connecting
  to Kaggle failed on a fresh install.

### Changed
- GPU memory reads "3.2 GB free of 4 GB" instead of "3.2 / 4 GB", which looked like memory in use.
- The page script is served as nine files under `/js/` instead of one inline block; the content security policy
  allows this server's scripts only.

## 0.1.3 — 2026-10-31

### Fixed
- `{python}` in a local command was always the dashboard's interpreter, so with `backends.local.python` set the
  training ran in the wrong environment; it is now the configured interpreter.
- A decision whose value needs quotes in YAML (`"a: b"`) was written without them and broke the runs file; values
  are written as YAML now, and a file that does not parse is reported with a code.
- Stopping a run that never started was sent to Kaggle and answered with a raw error; it is refused with a message.
- A Kaggle log stream never looked whether it should stop, so its thread could outlive the run.
- A process that exited with code 259 counted as running on Windows (259 also means "still active").
- Two watchdogs started at the same moment could both run; the pid file is now claimed atomically.
- An error code without a text, or a plan with 999 copies of one run, ended in an empty error.

### Security
- A project logo outside the project folder is not served; a colour from the manifest reaches the page only when
  it is a colour. SECURITY.md says that a paired device can restart the dashboard.

### Performance
- Starting a queued run (a network call) no longer holds the queue: adding, moving or removing entries meanwhile
  is not delayed. Downloading a finished run's outputs runs beside the status poll instead of stopping it.
- `results.csv`, `{yaml:...}` values and `devices.json` are read again only when they change; a run record is
  written only when it changes; the System page loads every project at once.

### Changed
- The results table takes the column after the run from `results.column` (default: the plan's second field) and
  reads it by name, so runs with different fields line up. Initials and the mini view upper-case Turkish letters
  correctly.
- Packaging: SPDX license field, Python 3.11–3.13 classifiers, pytest settings in `pyproject.toml`.
- Tests for the QR encoder (checked with OpenCV where it is installed), the command line, the local runner and
  each fix above.

## 0.1.2 — 2026-10-30

### Fixed
- Without a Kaggle token the System page did not load: newer Kaggle clients print a sign-in guide and call
  `exit(1)` instead of raising, which ended the request. The missing token is now shown as "not connected".

## 0.1.1 — 2026-10-30

### Fixed
- Run records could lose an update when two parts of the dashboard wrote them at the same moment (a project is
  rebuilt for every request, so each had its own lock); writes now share one lock per file and retry on Windows.
- A local run whose computer slept for over a minute was marked as failed and never checked again; the runner process
  is now asked directly, and a run marked lost while it still lives is picked up again.
- On Windows, a dashboard (and its local runs) started from the terminal of another app, such as an editor or an AI
  assistant, ended when that app closed: the app's job ends every process in it. The dashboard, its watchdog and
  local runs now leave that job when it allows it.
- `runboard serve` and `runboard stop` failed on a computer where runboard had never run (no `~/.runboard` yet).
- Adding a project could hang that request for good: registering held a lock that reading the changed config
  needed again. The YAML cache has its own lock now; a `config.yaml` written by hand without `projects:` works too.
- A Kaggle run was started from the queue even with the quota used up when the project had no finished run to
  estimate from; it now needs at least an hour left.
- Queueing several runs (a sweep) stopped at the first refused run and left the ones before it queued; every run is
  checked first now, and runs already waiting are skipped.
- A local run whose runner died before writing anything stayed STARTING for good; it is an error now.
- A decision also filled fields whose name ends in the decided one (`teacher_model: null` for `model`) and text in
  comments; only the field itself changes now, and the file is read back before it is written. Removing an extra
  run no longer depends on two-space indentation. A runs file without its section no longer breaks the plan page.
- Logs of finished runs no longer stay in memory for good, and clock times of a saved log are placed by when it was
  written instead of today.
- The README says a Kaggle run cannot be cancelled from the dashboard.

- `localhost` answered only after an IPv6 attempt failed (0.2 s in browsers, 2 s in Python); the server listens on
  IPv4 and IPv6 now.
- Pages read and parsed the runs file up to 17 times per view; YAML files are now parsed once until they change and
  parsed progress is kept until the log grows (a project view: 0.21 s → 0.013 s).
- The overview chart showed "No data" until the run's details arrived; untranslated chart titles and labels.
- After a restart a running run showed epoch 0 until its log had streamed again; the running log is now saved
  every poll and the longer copy is used.
- Kaggle's refusals and YAML syntax errors are framed in the interface language.
- The large chart was hard to use on a tablet: a pinch stopped after the first redraw (the element under the fingers
  was replaced) and a zoomed view could not be moved at all. Fingers, mouse and pen now share one set of gestures
  on an element that stays: drag moves a zoomed view, two fingers zoom and move together, a tap shows the values
  above the finger, a double tap zooms in or shows everything. New: zoom and move buttons, and a strip of the whole
  run under the chart whose window can be dragged and resized. The axis is the chosen range itself, so moving is
  smooth, and smoothing no longer changes when zooming.

### Security
- Pages run only their own scripts: the content security policy names each page script by its SHA-256 and the
  inline click handlers are gone, so an injected script or `onclick` is refused by the browser.

### Added
- Resume: a run that stopped gets *Resume* when its backend has a `resume:` command (local and Kaggle; see
  docs/manifest.md).
- Tablets: one finger reads chart values, two fingers zoom, double tap shows everything.
- The dashboard's own dialogs and notices replace the browser's confirm and alert boxes.
- Keyboard: every link, chart title and legend item can be reached with Tab and used with Enter or Space.
- Browser tests: the page is checked in a real headless Chrome/Edge (no script errors, no policy violations, charts,
  plan editing, translated errors).
- Watchdog: the dashboard is started again if it stops answering; starts, stops and unexpected errors are logged with
  their time. `runboard stop` and `runboard --version`.
- Charts: hover values with differences, a large view (switch charts, wheel/drag/keys to zoom, smoothing, log scale,
  best points, values at the cursor, CSV), legend clicks hide series.

## 0.1.0 — 2026-10-30

First public release.
Requires Python 3.11 or newer (the Kaggle client needs it).

### Projects and runs
- A project is any folder with a `runboard.yaml`; its runs live in the project's own runs file
  ([docs/manifest.md](docs/manifest.md)).
- New-project wizard: pick a folder, choose *YOLO training (no code)* or *my own training script*, choose where to run.
- Backends: **Kaggle** (private script kernels, live logs, weekly GPU quota, private dataset upload with forbidden-path
  checks) and the **local GPU** (detached runner that survives dashboard restarts; cancel stops the whole process tree).
- Live progress protocol (`@@rb` events) plus regex patterns for plain-text logs; per-second progress between log lines.
- Results tables, seed-variance summaries, curves, run-to-run comparison, and a decisions log for pre-registered plans.

### Live dashboard
- Server-sent events: pages receive only what changed and patch themselves in place, so scroll positions, open menus
  and half-typed inputs survive updates; logs and job output are appended, never redrawn.
- English and Turkish interface; API errors carry a code and are shown in the interface language.
- Compact `/mini` view with picture-in-picture for a tablet or a second screen.

### Editing the plan
- Edit, copy, add and remove runs from the dashboard; typed field rules (`runs.schema`); only the changed run's lines
  are rewritten, in the style they were written in.
- Shared settings edited key by key (comments keep their column) and a checked whole-file editor.
- Started runs keep the settings they ran with; pre-registered (locked) plans change only through decisions and extras.
- Every change is previewed as a diff, checked against concurrent edits (`409`), backed up and logged.

### Sweeps and queue
- Sweeps: one draft run per combination of values, in a single edit.
- One queue across projects; each backend starts its next entry when free and waits when the Kaggle quota left would
  not cover the run's estimate.

### Access and security
- This computer needs no login; other devices only when tablet access is on, after pairing once with a one-time QR
  link or 6-digit code. Paired devices can be removed at any time.
- Host-header (DNS rebinding) and cross-site request checks, security headers, credentials and new projects only from
  this computer, secrets masked in logs. See [SECURITY.md](SECURITY.md).
