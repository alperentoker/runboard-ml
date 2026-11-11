# Changelog

All notable changes to runboard. Versions follow [semantic versioning](https://semver.org/).

## 0.4.4 — 2026-11-11

A decision rule for studies that pre-registered separate confidence intervals.

### Added
- A decision rule chosen in the plan: `protocol: {rule: separate}` decides a comparison on the two sides' own 95 %
  intervals (supported or refuted only when they do not overlap), as studies that compare confidence intervals are
  pre-registered; `paired`, the margin's interval, stays the default. The Hypotheses page, `runboard verdicts` and the
  exported methods and tables show both sides' intervals and say which rule decided. An unknown rule is refused when
  the plan is saved. On Ground2Air-LWIR's held-out test it gives the study's own verdicts in 10 of 10 comparisons.

### Changed
- The tests on a real machine build their Docker image a second time when a package mirror fails for a moment,
  and show Docker's output when the build still fails.

## 0.4.3 — 2026-11-10

Notifications on Linux and macOS, and an easy way to report a problem.

### Added
- Notifications when a run finishes, fails or is stopped on Linux (`notify-send`) and macOS (`osascript`, or
  `terminal-notifier` when it is installed, which also opens the run on a click), as on Windows. The text is passed
  as arguments, never as part of a script, so no quote in a project's name can change what runs.
- `runboard doctor`: a report to paste into an issue — the versions, the system, the settings that matter, whether
  the dashboard and its watchdog run, each project (or why it cannot be read), the backends, the GPU, notifications
  and the end of the dashboard's log. Keys and tokens are masked; the user folder, the user name, e-mail and network
  addresses are replaced.
- Issue forms on GitHub for a problem (asking for the `runboard doctor` output) and for an idea; security problems
  are sent to a private advisory instead.
- The documentation site, https://alperentoker.github.io/runboard-ml/ (built from the repository's own files), the
  README's pictures made from the real dashboard (`tools/capture_docs.py`), and `CITATION.cff`.

### Fixed
- The files the dashboard reads while it runs (`runs.yaml`, `plan.yaml`, `runboard.yaml`, `config.yaml`, the lock
  record, and what `rb.py` writes: a run's summary, the resampling plan, evaluations) are written aside and then
  moved in. A save used to empty the file first, and a read in that instant saw it empty or half written: the
  project looked broken for a moment, and a browser test failed now and then on Linux because of it.
- The demo records each run's best epoch, so its results table shows it.

## 0.4.2 — 2026-11-07

Fixes from an independent review of 0.4.1. Upgrade if you use Kaggle, edit runs files by hand or pair devices.

### Fixed
- A provider that never answers no longer freezes the dashboard. Each call to a backend (a run's status, its
  availability, the Kaggle quota) gets 60 seconds in a thread of its own: the Kaggle client sets no timeout, and a
  half-open connection used to stop the status of every project and the queue until the dashboard was restarted
  (while the page, and so the watchdog, saw nothing wrong). A call still stuck is not made again; why a run's status
  cannot be read is written to `~/.runboard/server.log`.
- A runs file broken by hand no longer takes the whole project list down (a 500 with no projects shown): that
  project is listed with its error, the others as usual.
- A status the Kaggle client does not know is an error naming it, instead of a state outside runboard's contract
  that the page showed raw.
- Status chips and verdicts escape what the server sends.
- A plan's evaluation folder (`protocol.dir`) must be inside the project: `plan.yaml` can be edited from a paired
  device, and the folder could point anywhere on the computer.
- An error message missing one of its values is still an error message, not a crash (a 500).
- Local runs and jobs start whether or not runboard is installed where they start: their runner is started by its
  file, isolated, not as `python -m runboard.localrun` from the project folder (where a folder named `runboard`,
  or a source checkout that was not installed, broke it).

### Changed
- Turning on tablet access says that the connection is plain HTTP, not encrypted, and to use it only on a network
  you trust or through a VPN; README says so too.
- A release waits for the real-machine tests (SSH, SLURM, systemd) as well, not only the unit tests.

### Tests
- Cancelling a local run is tested for real: the run and a process it started are both gone afterwards.

## 0.4.1 — 2026-11-07

Fixes from two reviews of 0.4.0, and jobs that no longer end with the dashboard. Upgrade if other devices are
paired with your dashboard, or if you run long jobs (an evaluation, packaging) from it.

### Changed
- Jobs (validation, tests, packaging, uploads, an evaluation …) run on their own, like local runs: when the
  dashboard restarts, crashes or is stopped, they go on, and the next dashboard shows them where they are. Their
  log and exit code are files in the project's state folder (`jobs/`) instead of the dashboard's memory; a job whose
  process disappeared without an exit code is shown as an error, not as running forever.
- The local GPU card shows how busy the GPU is: load, memory in use and temperature (from `nvidia-smi`), instead
  of the free memory alone, which read like the amount in use. Asking `nvidia-smi` also keeps the dashboard from
  taking GPU memory of its own.

### Fixed
- Windows: `runboard stop` ended the dashboard together with every process it had started, local runs included,
  which are meant to go on without it. It now ends the dashboard alone.
- A finished run's notification is given before the run stops counting as "being collected", and a notification
  that fails can no longer leave it in that state. (This also made two notification tests fail now and then.)
- Two clicks on a job no longer start it twice.
- A local run or job no longer opens a console window of its own on Windows.
- Security: a paired device could read any `.log` file on the computer through the run log page, with a run name
  that climbs out of the logs folder (`..%5C..`). A run name from the address is now checked before it reaches
  a file.
- A malformed progress line from your own code (`@@rb` without an epoch, or text where a number belongs) no longer
  stops the whole log from being read: that line is skipped and the rest still counts.
- The best score of a run whose log names none is the highest of all epochs, not the first epoch's.
- Only one dashboard runs for a runboard folder (`RUNBOARD_HOME`): a second one on another port says which one is
  running and stops, instead of both polling and writing the same runs.
- SSH and SLURM: a run's outputs come home through a file on disk, not memory, so large checkpoints no longer
  need their size in RAM.
- SLURM: a job that waits in the queue starts from the code it was sent with, not from whatever a later job sent
  into the same work folder.
- Names, paths and versions shown in the page (protocol, export folder, template version, Kaggle status) are
  escaped; the compare list no longer carries runs of another project with the same name.

### Documentation
- The browsers the dashboard needs (2023 or later; `/mini` works from 2020 on), and that runs and jobs outlive the
  dashboard.

## 0.4.0 — 2026-11-05

runboard as a dashboard first: SSH and SLURM tested on a real machine (with two SLURM fixes: a failed run no
longer shows as finished, and a run on a cluster without accounting no longer stays queued), start with the
computer on Linux and macOS, Windows notifications, a wizard that says what each choice does, and projects that
are not YOLO. Upgrade from 0.3.0 if you use SLURM.

### Added
- Projects that are not YOLO: every number a run reports (`rb.epoch(3, accuracy=0.91, loss=0.31)`, or a column of
  its own CSV) gets a chart under its own name, `x` and `val_x` together; a single `loss` is charted too.
- Every run knows its output folder and name (`RUNBOARD_OUT`, `RUNBOARD_RUN`; `rb.out()`) on every backend, and
  `rb.report(score=…)` writes the result the results table reads. The wizard copies `rb.py` next to your script.
- `curves: {file: …, epoch: <column>}` reads any CSV, one row an epoch, without a column map; the wizard asks for it.
- A pre-registered experiment around your own training code: the wizard asks for questions, evaluation sets and
  hypotheses, checks the criteria against your runs, and adds your evaluation script as a job; your script writes
  the results with `rb.write_samples` or `rb.write_eval`.
- A clearer new-project wizard: every step opens with what is decided in it; each kind of project lists what it
  does, what it does not do and what it needs; a design shows the runs it will make as you change it, with the
  models picked from a list; *My own training code* shows the command each run gets, how to follow it and where
  the score comes from; the last step lists every file it will write with what it is for, and what to do after.
- Start with the computer on Linux and macOS too: *System → Start runboard when I sign in* writes a systemd user
  service or a launchd agent (Windows keeps its startup script). The service manager restarts a crashed dashboard,
  so runboard's own watchdog stays off there (`RUNBOARD_NO_WATCHDOG`).
- Windows notifications when a run finishes (with its score), fails or is stopped, from the dashboard's own loop,
  so no page has to be open; once per start of a run, in the dashboard's language, with a switch and a test button
  on the System page.
- The SSH and SLURM backends, and the Linux autostart, are tested against a real machine: a container
  (`tests/docker`) with sshd, a one-node SLURM cluster that keeps accounting, and systemd. CI runs it on every
  change.

### Changed
- runboard is described as what it is first: a dashboard for training runs (start them anywhere, watch them live,
  queue, compare and edit them). Pre-registered experiments stay, as an optional part for projects that need them;
  the README, the PyPI description, the tutorial's introduction and the roadmap say so. The roadmap's next stages
  are real SSH and SLURM machines, start-up on Linux and macOS, notifications, and projects that are not YOLO.

### Fixed
- SLURM: a run that failed was shown as finished: the job's last line (writing the exit code down) succeeded, so
  SLURM recorded the job as completed. The job now ends with the run's own exit status.
- SLURM: on a cluster without accounting a finished run stayed *queued* for good (sacct knew nothing and squeue
  forgets a job once it ends). When neither knows the job, the exit code its script wrote decides.
- SSH: a run that finished exactly while the dashboard looked at it could be marked failed ("the process ended
  without an exit code"): its exit code was looked for, then the process, and the run could end in between. The
  code is now looked for again once the process is gone. On every backend the exit code is written aside and moved
  into place, so it is never read half written.

## 0.3.0 — 2026-11-02

A redesigned dashboard (dark by default, charts that show the verdicts and their uncertainty) and a security fix:
upgrade from 0.2.0, where a paired device could run a command on the dashboard's computer.

### Security
- A paired device could run a command on the dashboard's computer: a run's field value went into the run's
  command line as it was, so `a.pt & other-command` in a field ran `other-command` when the run started. Every
  value is now checked before it goes into a command (training on every backend, setup lines, jobs, the post-run
  check); one that could end the command or start another is refused with `unsafe_value`. A run's name can no
  longer lead its outputs out of the output folder (`..` parts are dropped).

### Added
- *Verdicts at a glance* on the Hypotheses page: a forest plot of every comparison, its margin and 95 % interval on
  one axis centred on zero (each row on its own scale when the margins differ too much), coloured and marked by
  verdict; a row opens its hypothesis.
- The bootstrap distribution of every comparison under its table, with its 95 % interval and where zero lies. The
  verdicts carry it as `hist` (30 bins over the replicates).
- Results: a group of runs (seeds) is drawn as rings over its mean with ± one standard deviation; the main score of a
  run table has a bar against the table's highest; a data-size curve marks every point and goes to a log axis when
  its sizes spread over decades.
- Run charts: the best point is ringed and written in the chart's title, a lone series has a light fill under it,
  and *Loss: train and validation* puts the two totals side by side.
- A theme switch (dark, light, or the system's own) in the sidebar; dark is the default.
- The study's steps on the Overview of a pre-registered project: plan, lock, runs, evaluation, verdicts, paper, each
  with how far it is and a link to where it is done; the next one is marked.
- Overview: a timeline of when each run ran (a running one with its estimated rest), and the Kaggle GPU week split
  into this project's runs and other work, with when it renews.
- Results: one small panel per class with the same runs on one scale; tick runs in a table to compare them side by
  side, with each one's difference from the first and a button to see their curves together.
- Quick search (Ctrl+K, or *Search* at the top): projects, pages, runs and actions such as the theme or language.
- Run charts: the learning rate as a strip under the main chart.
- Empty pages say what goes there and offer the next step (no hypotheses yet, no finished run yet).

### Changed
- One colour system: each colour has one job (verdicts, run states, series), verdicts carry a mark as well as a
  colour, series follow an order colour-blind readers can still tell apart, numbers in tables are monospaced, and
  chart axes are labelled with round values.
- New project: the three kinds say what each is for, when to pick it and what it gives (*Train and compare models*,
  *Pre-registered experiment*, *My own training code*); the tutorial's screenshots show the new look.

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
