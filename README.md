# runboard

**Pre-registered machine-learning experiments, from the plan to the paper.** Write your questions and hypotheses,
lock the plan, run the experiments on your own GPU, Kaggle, a machine over SSH or a SLURM cluster, watch them live, and
get every hypothesis decided with a bootstrap confidence interval, plus the tables, methods and deviations sections
for the paper. One self-hosted dashboard for all your projects; everything stays in readable files in your repository.

**New here?** `pip install runboard-ml numpy`, then `runboard demo`: a five-minute pre-registered study on any CPU,
walked through in the [tutorial](https://github.com/alperentoker/runboard-ml/blob/main/docs/tutorial.md).

[Türkçe](https://github.com/alperentoker/runboard-ml/blob/main/README.tr.md) · [![tests](https://github.com/alperentoker/runboard-ml/actions/workflows/tests.yml/badge.svg)](https://github.com/alperentoker/runboard-ml/actions/workflows/tests.yml)

![Hypotheses decided with confidence intervals](https://raw.githubusercontent.com/alperentoker/runboard-ml/main/docs/images/tutorial-7-verdicts.png)

<table><tr>
<td width="50%">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/alperentoker/runboard-ml/main/docs/images/run-dark.png">
  <img alt="A run's page: live progress, results and training curves" src="https://raw.githubusercontent.com/alperentoker/runboard-ml/main/docs/images/run-light.png">
</picture>

<sub>A run, live</sub>
</td>
<td width="50%">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/alperentoker/runboard-ml/main/docs/images/plan-dark.png">
  <img alt="Editing the run plan: every change is previewed as the lines it changes" src="https://raw.githubusercontent.com/alperentoker/runboard-ml/main/docs/images/plan-light.png">
</picture>

<sub>Editing the plan: a preview of the exact lines that change</sub>
</td>
</tr></table>

- **Hypotheses a machine can check** — `R7.aerial >= 0.9 * R5.aerial`, `collapse(R4, ground, aerial) > ...`, seed groups,
  `log_fit(...)`: each comparison is decided on paired bootstrap replicates as *supported*, *refuted* or
  *indistinguishable*, with its 95 % interval.
- **A lock that means something** — `plan.lock.json` records when, at which commit and the fingerprints of the plan,
  the runs and the scripts; every later change needs a reason and is listed as a deviation. A sealed test set is
  evaluated once per model, on the record.
- **Research wizard** — questions, experiment designs (specialists, data-size curves, architectures, ablations,
  seeds), the evaluation protocol and hypotheses checked as you type become a ready project.
- **Code templates** — split, leakage check, conversion, data-size subsets, evaluation and speed scripts, written into
  your project as ordinary files that runboard never overwrites once you change them.
- **Paper output** — Markdown and LaTeX tables, the hypotheses, a methods draft, the deviations section, a
  reproducibility checklist, a registered-report page and an archive for Zenodo.
- **Live runs anywhere** — your GPU, Kaggle (private kernels, weekly quota, private datasets), a machine over SSH and a
  SLURM cluster (your own SSH keys; runboard never sees a password); logs, second-by-second progress, charts, a queue.
- **Provenance** — every run records the commit, uncommitted changes and the fingerprints of what it started from.
- **Tablet view**, a Code page, English and Türkçe.

Secrets never leave your machine: the Kaggle token stays in `~/.kaggle`, paired devices and all state live in
`~/.runboard`, never inside a project repository.

## Install

```bash
pip install runboard-ml            # or: pip install "runboard-ml[kaggle]" for Kaggle
runboard                           # http://localhost:8000 — this computer only, no password
```

The package is called `runboard-ml` on PyPI (`runboard` belongs to another project); the command and the Python module
are `runboard`. Do not install both in one environment: they would share the module name. Python 3.11 or newer.

Then, in the dashboard:

1. **System → Connections → Kaggle** (only if you want cloud GPUs): the panel walks you through creating a token on
   kaggle.com and pasting it once. It is saved to `~/.kaggle/access_token` on this machine, tested, and never shown again.
2. **New project**: pick a folder and choose *Pre-registered study (YOLO)*, *YOLO training (no code)* or *My own training
   script*, then where to run (this computer, Kaggle, SSH, SLURM). runboard writes `runboard.yaml`, the runs file and,
   for YOLO, the training and evaluation scripts into the folder; it never changes your own files.

A folder that already has a `runboard.yaml` can be added from the same wizard or with `runboard add PATH`.

## Tablet access

By default runboard listens only on this computer (`127.0.0.1`) and asks for nothing. To follow runs from a tablet on
the same Wi-Fi, turn on **System → Tablet access** (the dashboard restarts on all network interfaces), press
**Pair a device** and scan the QR code with the tablet, or open the address shown and type the 6-digit code. The code
works once and for two minutes. Paired devices are listed there and can be removed at any time.

A paired device can follow, start and stop runs. Entering the Kaggle token, adding projects, changing code and the
project file, the folder browser and startup settings stay on this computer. Outside your home network, use a VPN such
as Tailscale and add its machine name to `allowed_hosts` in `~/.runboard/config.yaml`. See
[SECURITY.md](https://github.com/alperentoker/runboard-ml/blob/main/SECURITY.md).

## A project by hand

The wizard covers the common cases. Under the hood a project is any folder with a `runboard.yaml` (and, for a
pre-registered study, a `plan.yaml`). runboard does not own your code or configs; the manifest just tells it where
things are:

```yaml
version: 2
name: My detector
runs:
  file: configs/runs.yaml          # your runs, in your own format: a mapping of run id -> fields
  section: runs
  defaults: train
  name: "{id}-{model|stem}-s{seed}"
backends:
  local:  {command: '"{python}" train.py --run {id}', output_dir: runs/local}
  kaggle: {files: {train.py: train.py, runs.yaml: configs/runs.yaml}, command: "python train.py --run {id}"}
results:
  report: "{out}/summary.json"
  metrics: {primary: map50_95}
```

See [the manifest reference](https://github.com/alperentoker/runboard-ml/blob/main/docs/manifest.md) for every option,
including `plan.yaml`, criteria, evaluation files, the lock and the backends, and
[the design notes](https://github.com/alperentoker/runboard-ml/blob/main/docs/design-v2.md) for how verdicts are
computed.

## Reporting progress

Print one line per event from your training script, or use `rb.py` (stdlib only; `runboard demo` and the wizard put a
copy next to your scripts):

```python
import rb
rb.ultralytics(model)            # Ultralytics: one line adds everything below
rb.start(epochs=100, batches=798)
rb.beat(epoch=3, batch=400, batches=798, its=4.9)
rb.epoch(3, epochs=100, secs=171, metrics={"map": 48.2}, best=48.2, eta=time.time() + 3600)
```

Each call prints `@@rb {json}`; your own log lines are untouched. Projects with existing plain-text logs can describe
them with regular expressions instead (`progress.patterns`).

## Run it permanently

*System → Start runboard when Windows starts* (Windows), or a systemd/launchd service running `runboard serve`.
`runboard serve` also starts a small watchdog: if the dashboard stops answering for 20 s it is started again, and every
start, stop and unexpected error is written with its time to `~/.runboard/server.log`. `runboard stop` stops both and
keeps them stopped until the next `runboard serve` (set `watchdog: false` in `~/.runboard/config.yaml` to go without).
To reach it from outside your home network, put it behind a private network such as Tailscale rather than exposing the port.

## Development

```bash
git clone https://github.com/alperentoker/runboard-ml
cd runboard-ml
pip install -e .[dev]
pytest
```

MIT licensed. Changes: [CHANGELOG.md](https://github.com/alperentoker/runboard-ml/blob/main/CHANGELOG.md) ·
plans: [ROADMAP.md](https://github.com/alperentoker/runboard-ml/blob/main/ROADMAP.md).
