"""Projects that are not YOLO: a script made into a project by the wizard, run for real on this computer, reports
any metric by name through rb.py and its results through rb.report(); runboard reads the curves (from the log and
from the script's own CSV) and the score."""
import sys
import time

import pytest

from runboard import home, wizard
from runboard.progress import Parser

TRAIN = '''import csv, sys
import rb
lr = float(sys.argv[sys.argv.index("--lr") + 1])
rows = []
for e in range(1, 4):
    acc, loss = 0.5 + lr * e, 1.0 / e
    rb.epoch(e, epochs=3, accuracy=acc, val_accuracy=acc - 0.05, loss=loss)
    rows.append({"epoch": e, "f1": round(acc - 0.1, 3), "rmse": round(loss / 2, 3), "note": "ok"})
with open(rb.out() / "history.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
rb.report(score=round(100 * (0.5 + 3 * lr), 2), best_epoch=3)
'''


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    monkeypatch.setattr(home, "CONFIG", tmp_path / ".rb" / "config.yaml")
    root = tmp_path / "mine"
    root.mkdir()
    (root / "train.py").write_text(TRAIN)
    spec = {"path": str(root), "name": "Mine", "kind": "script", "backends": ["local"], "default_backend": "local",
            "script": {"file": "train.py", "runs": [{"id": "fast", "args": "--lr 0.1"}], "report": "{out}/summary.json",
                       "metric": "score", "curves": "{out}/history.csv", "epoch_column": "epoch"}}
    wizard.create(spec)
    from runboard.project import Project
    p = Project(root)
    p.m["backends"]["local"]["python"] = sys.executable  # this test's Python runs the script
    return p


def test_a_script_project_reports_any_metric_and_its_score(project):
    from runboard.backends.local import LocalBackend
    p, b = project, LocalBackend()
    assert (p.root / "rb.py").is_file()  # the wizard put the helper next to the script
    st = b.submit(p, "fast", p.info("fast"))
    end = time.time() + 60
    while b.status(p, "fast", st)[0] in ("RUNNING", "STARTING") and time.time() < end:
        time.sleep(0.3)
    assert b.status(p, "fast", st) == ("COMPLETE", None), b.final_log(p, "fast", st)
    # the score and the best epoch, from what rb.report() wrote into the run's own output folder
    m = p.metrics("fast")
    assert m["primary"] == 80.0 and (p.output_dir("fast") / "summary.json").is_file()
    # curves from the log: every number of rb.epoch() under its own name, a single loss included
    hist = Parser(p.m.get("progress")).parse(b.final_log(p, "fast", st))["history"]
    assert [h["e"] for h in hist] == [1, 2, 3]
    assert {"accuracy", "val_accuracy", "loss"} <= set(hist[0]) and hist[2]["accuracy"] == 0.8
    # curves from the script's own CSV: every number column, by its name; a text column is left out
    rows = p.curves("fast")
    assert [r["e"] for r in rows] == [1, 2, 3] and rows[0]["f1"] == 0.5 and rows[2]["rmse"] == 0.167
    assert "note" not in rows[0]


EVALUATE = '''import random
import rb
ids = [f"item{i}" for i in range(200)]
rb.resample_plan("val", ids)
for run, p in (("run1", 0.6), ("run2", 0.9)):  # run2 gets nine items in ten right, run1 six
    rng = random.Random(run)
    rb.write_samples(run, "val", {"acc": [1.0 if rng.random() < p else 0.0 for _ in ids]})
print("evaluated")
'''


def code_spec(root, criterion):
    return {"path": str(root), "name": "Mine", "kind": "script", "backends": ["local"], "default_backend": "local",
            "script": {"file": "train.py", "runs": [{"id": "run1", "args": "--lr 0.1"}, {"id": "run2", "args": "--lr 0.2"}]},
            "research": {"questions": [{"id": "S1", "text": "Does a larger step help?"}],
                         "hypotheses": [{"id": "H1", "question": "S1", "text": "run2 beats run1", "criterion": criterion}],
                         "protocol": {"sets": "val", "metric": "acc", "script": "evaluate.py"}, "lock": True}}


def test_your_own_code_pre_registered_from_the_wizard_to_the_verdict(tmp_path, monkeypatch):
    import subprocess
    from runboard import prereg
    from runboard.project import Project
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    monkeypatch.setattr(home, "CONFIG", tmp_path / ".rb" / "config.yaml")
    root = tmp_path / "mine"
    root.mkdir()
    (root / "train.py").write_text(TRAIN)
    (root / "evaluate.py").write_text(EVALUATE)
    # a criterion that names a run the project does not have is shown before anything is written
    files, meta = wizard.build_all(code_spec(root, "run9.val > run1.val"))
    assert "H1" in meta["problems"] and [r["id"] for r in meta["runs"]] == ["run1", "run2"] and meta["sets"] == ["val"]
    wizard.create(code_spec(root, "run2.val > run1.val"))
    p = Project(root)
    assert p.v2 and p.locked and (root / "plan.lock.json").is_file()
    assert p.m["jobs"]["evaluate"]["cmd"].endswith("evaluate.py")
    assert subprocess.run([sys.executable, "evaluate.py"], cwd=root, capture_output=True, text=True).returncode == 0
    h = {x["id"]: x for x in prereg.hypotheses(p)["hypotheses"]}["H1"]
    assert h["verdict"] == "supported" and h["parts"][0]["margin"] > 0.2  # about 0.9 against 0.6


def test_malformed_progress_lines_are_skipped():
    """Lines come from the user's own code: a broken one is skipped, the rest of the log still counts."""
    from runboard.progress import Parser
    lines = ['@@rb {"t": "epoch", "epoch": 1, "map": 0.5, "loss": 0.3}',
             '@@rb {"t": "epoch", "map": 0.9}',                    # no epoch
             '@@rb {"t": "epoch", "epoch": "two", "map": 0.9}',    # not a number
             '@@rb {"t": "epoch", "epoch": 2, "map": "high", "loss": {"box": "x"}}',  # text metrics
             '@@rb {"t": "beat", "epoch": 2}',                     # half a heartbeat
             '@@rb [1, 2]', '@@rb "text"', '@@rb {"t": ["epoch"]}',
             '@@rb {"t": "epoch", "epoch": 3, "map": 0.7}']
    p = Parser(None).parse(lines)
    assert [h["e"] for h in p["history"]] == [1, 2, 3]
    assert p["history"][1] == {"e": 2} and p["epoch"] == 3 and p["best"] == 0.7
