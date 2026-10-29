# Changelog

All notable changes to runboard. Versions follow [semantic versioning](https://semver.org/).

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
