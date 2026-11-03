# Roadmap

runboard is a **dashboard and working environment for machine-learning training runs**: start them on this
computer, Kaggle, a machine over SSH or a SLURM cluster, follow them live, queue, compare and edit them, and see the
results in one place. Pre-registered experiments (hypotheses decided with confidence intervals, a locked plan, paper
output) are an optional part for projects that need them.

Principles that do not change:

1. **Everything is a readable file** in the project folder and goes into git. No hidden database, no account.
2. **No hidden code.** Templates (and, later, AI help) write ordinary files anyone can read.
3. **Local first.** No server, account or subscription.
4. **For pre-registered projects:** a lock is a lock (every later change is a recorded deviation), and the test split
   is sealed (it never goes to the cloud, and every use of it is written down).

Stages RB-0 to RB-9 were planned around pre-registration; their design is in [docs/design-v2.md](docs/design-v2.md).

| Stage | What | Release |
|---|---|---|
| **RB-0** · groundwork ✓ | `plan.yaml` (manifest v2) with migration, plan and manifest editable from the dashboard, page script in separate files, CI on Linux, macOS and Windows | 0.2 |
| **RB-1** · pre-registration core ✓ | hypotheses with machine-checked criteria, the evaluation format with a shared resampling plan, verdicts (*supported*, *refuted*, *indistinguishable*) with confidence intervals, seed groups, the lock record, deviations, the test ledger | 0.2 |
| **RB-2** · code templates ✓ | split and leakage check, evaluation, conversion, packaging and subsets, speed; tracked templates that never overwrite a file you changed | 0.2 |
| **RB-3** · research wizard ✓ | questions → hypotheses → data pipeline → experiment designs (domain transfer, data-size curve, architecture, ablation, seeds) → protocol → lock | 0.2 |
| **RB-4** · code in the dashboard ✓ | view and edit the project's code (this computer only), smoke test before a run uses cloud quota | 0.2 |
| **RB-5** · provenance and paper output ✓ | per-run commit, data and template fingerprints; LaTeX/Markdown tables (figures still to come), methods and deviations sections, a reproducibility checklist, a registered-report page, an archive for Zenodo | 0.2 |
| **RB-6** · where research computes ✓ | SSH and SLURM backends; full Linux and macOS support | 0.2 |
| **RB-7** · AI help (optional) | a script from a description, written only after the diff is approved, saved with its prompt | later |
| **RB-8** · first contact ✓ | `runboard demo`: a five-minute pre-registered study on any CPU; the step-by-step tutorial with screenshots | 0.2 |
| **RB-9** · PyPI ✓ | published as `runboard-ml` (the name `runboard` is taken); a version tag tests, builds and publishes it through trusted publishing (RELEASING.md) | 0.2 |
| **RB-10** · the dashboard ✓ | dark by default with a theme switch, one colour system, a forest plot and bootstrap histograms of the verdicts, seed plots, per-class panels, a run timeline and the Kaggle week, the study's steps, quick search, comparing runs; a review of the whole project and its security fix | 0.3 |
| **RB-11** · on real machines | SSH and SLURM tried on real servers and clusters (so far against a stand-in); start with the computer on Linux (systemd) and macOS (launchd) as on Windows; a word when a run ends or fails even with the page closed | 0.4 |
| **RB-12** · any training code | the wizard and the results for projects that are not YOLO: your script, its metrics and curves read without a YOLO layout; a simpler wizard (models from a list, the runs and files it will write shown before it writes them) | 0.4 |
| later | a documentation site, `CITATION.cff`; for pre-registered projects, training seeds inside the interval, a correction for several hypotheses, equivalence margins and a lock stamped outside the computer | — |

Not planned: a hosted service, accounts, multi-user lab features (unless real users ask for them).

Reference project: Ground2Air-LWIR, a thermal-detection study whose fourteen Kaggle runs were managed with runboard; its
hand-made verdicts are reproduced exactly by the pre-registration part.
