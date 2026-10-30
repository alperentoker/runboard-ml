# Changelog

All notable changes to runboard. Versions follow [semantic versioning](https://semver.org/).

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
