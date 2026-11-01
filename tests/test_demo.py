"""The five-minute demo (RB-8): it installs, trains on any CPU, and its two hypotheses come out as the tutorial says."""
import os
import subprocess
import sys

import pytest

pytest.importorskip("numpy")


@pytest.fixture
def demo(tmp_path, monkeypatch):
    from runboard import home
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    monkeypatch.setattr(home, "CONFIG", tmp_path / ".rb" / "config.yaml")
    from runboard.cli import main
    target = tmp_path / "demo"
    assert main(["demo", str(target)]) == 0
    return target


def run(folder, *args):
    env = {**os.environ, "RB_DEMO_FAST": "1", "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, "-u", *args], cwd=folder, env=env, capture_output=True, text=True, encoding="utf-8",
                       timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def test_the_demo_runs_and_its_verdicts_are_the_tutorials(demo):
    from runboard import home, prereg
    from runboard.export import export
    from runboard.project import Project
    assert {"train.py", "evaluate.py", "rb.py", "runboard.yaml", "plan.yaml", "runs.yaml"} <= {f.name for f in demo.iterdir()}
    assert str(demo) in home.config()["projects"]
    p = Project(demo)
    prereg.lock(p, "test")
    for r in p.run_ids():
        assert "@@rb" in run(demo, "train.py", "--run", r)
    assert "evaluated 6 run(s)" in run(demo, "evaluate.py")
    h = {x["id"]: x for x in prereg.hypotheses(Project(demo))["hypotheses"]}
    assert h["H1"]["verdict"] == "supported" and h["H2"]["verdict"] == "refuted"
    assert Project(demo).metrics("R2")["primary"] > Project(demo).metrics("R1")["primary"]
    assert "evaluated 0 run(s)" in run(demo, "evaluate.py")
    out = export(Project(demo))
    assert "report.html" in out["files"] and "supported" in (demo / "paper" / "hypotheses.md").read_text(encoding="utf-8")


def test_the_demo_wants_an_empty_folder(tmp_path, monkeypatch, capsys):
    from runboard import home
    from runboard.cli import main
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    monkeypatch.setattr(home, "CONFIG", tmp_path / ".rb" / "config.yaml")
    (tmp_path / "busy").mkdir()
    (tmp_path / "busy" / "x.txt").write_text("mine")
    assert main(["demo", str(tmp_path / "busy")]) == 1
    assert "not empty" in capsys.readouterr().out
