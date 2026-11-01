# Roadmap

runboard is becoming a **pre-registration tool for machine-learning experiments**. A researcher writes questions and
hypotheses, builds the data pipeline and evaluation from templates, locks the plan, runs it locally, on Kaggle, over
SSH or on a SLURM cluster, and gets every hypothesis decided with a confidence interval, plus the methods, results and
deviations sections of the paper.

Principles that do not change:

1. **Everything is a readable file** in the project folder and goes into git. No hidden database, no account.
2. **No hidden code.** Templates (and, later, AI help) write ordinary files a reviewer can read.
3. **A lock is a lock.** After it, every change of the plan is a recorded deviation.
4. **The test split is sealed.** It never goes to the cloud, and every use of it is written down.
5. **Local first.** No server, account or subscription.

The design behind the first stages is in [docs/design-v2.md](docs/design-v2.md).

| Stage | What | Release |
|---|---|---|
| **RB-0** · groundwork ✓ | `plan.yaml` (manifest v2) with migration, plan and manifest editable from the dashboard, page script in separate files, CI on Linux, macOS and Windows | 0.2 |
| **RB-1** · pre-registration core ✓ | hypotheses with machine-checked criteria, the evaluation format with a shared resampling plan, verdicts (*supported*, *refuted*, *indistinguishable*) with confidence intervals, seed groups, the lock record, deviations, the test ledger | 0.2 |
| **RB-2** · code templates ✓ | split and leakage check, evaluation, conversion, packaging and subsets, speed; tracked templates that never overwrite a file you changed | 0.3 |
| **RB-3** · research wizard ✓ | questions → hypotheses → data pipeline → experiment designs (domain transfer, data-size curve, architecture, ablation, seeds) → protocol → lock | 0.3 |
| **RB-4** · code in the dashboard ✓ | view and edit the project's code (this computer only), smoke test before a run uses cloud quota | 0.4 |
| **RB-5** · provenance and paper output ✓ | per-run commit, data and template fingerprints; LaTeX/Markdown tables (figures still to come), methods and deviations sections, a reproducibility checklist, a registered-report page, an archive for Zenodo | 0.4 |
| **RB-6** · where research computes | SSH and SLURM backends; full Linux and macOS support | 0.5 |
| **RB-7** · AI help (optional) | a script from a description, written only after the diff is approved, saved with its prompt | later |
| **RB-8** · visibility | PyPI, documentation site, a five-minute CPU demo, `CITATION.cff` and a DOI, a case study, a workshop paper, then JOSS | 0.2 → 1.0 |

Not planned: competing with experiment trackers on logging and charts, a hosted service, multi-user lab features
(unless real users ask for them).

Validation: Ground2Air-LWIR, a pre-registered thermal-detection study run with
runboard, is the reference project. RB-1 must reproduce its hand-made verdicts exactly before it ships.
