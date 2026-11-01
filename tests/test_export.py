"""Provenance and paper output (RB-5)."""
import json
import shutil
import zipfile
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from runboard import home

DATA = Path(__file__).parent / "data" / "g2a_s1"


@pytest.fixture
def study(tmp_path, monkeypatch):
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    monkeypatch.setattr(home, "CONFIG", tmp_path / ".rb" / "config.yaml")
    home.save_config({"projects": [], "port": 8000, "lan": True})
    root = tmp_path / "study"
    shutil.copytree(DATA / "eval", root / "eval")
    (root / "pkg" / "ground").mkdir(parents=True)
    (root / "pkg" / "ground" / "a.txt").write_text("x")
    (root / "runs.yaml").write_text("train: {epochs: 100, imgsz: 640}\nruns:\n  R1: {package: combined, model: yolov8s.pt}\n"
                                    "  R4: {package: ground, model: yolov8s.pt}\n  R5: {package: aerial, model: yolov8s.pt}\n")
    for r, v in (("R1", 55.1), ("R4", 56.2), ("R5", 49.7)):
        (root / "out" / r).mkdir(parents=True)
        (root / "out" / r / "summary.json").write_text(json.dumps({"map": v, "map50": v + 30, "hours": 4.5}))
    (root / "runboard.yaml").write_text(yaml.safe_dump({
        "version": 2, "name": "Study_1 & co", "runs": {"file": "runs.yaml", "defaults": "train", "fields": ["package", "model"], "name": "{id}"},
        "backends": {"local": {"command": "echo {id}", "output_dir": "out"}}, "default_backend": "local",
        "data": {"field": "package", "packages": [{"key": "ground", "dir": "pkg/ground"}]},
        "results": {"report": "{out}/summary.json", "metrics": {"primary": "map", "secondary": "map50", "hours": "hours"},
                    "labels": {"primary": "mAP50-95", "secondary": "mAP50"}},
        "phases": [{"id": "A4", "title": "Specialists", "runs": ["R4", "R5"]}],
        "tables": [{"title": "S1 · specialists", "runs": ["R4", "R5"]},
                   {"title": "Variance", "groups": [{"label": "all", "runs": ["R1", "R4", "R5"]}]}]}))
    (root / "plan.yaml").write_text(yaml.safe_dump({
        "questions": [{"id": "S1", "text": "How far does a specialist collapse?"}],
        "hypotheses": [{"id": "H1b", "question": "S1", "text": "People collapse more than vehicles.",
                        "criterion": "collapse(R4@person, ground, aerial) > collapse(R4@vehicle, ground, aerial) and "
                                     "collapse(R5@person, aerial, ground) > collapse(R5@vehicle, aerial, ground)"},
                       {"id": "P", "question": "S1", "criterion": "R1.ground > R4.ground"}],
        "protocol": {"dir": "eval", "metric": "map50_95", "sets": ["ground", "aerial"]},
        "groups": {"all3": ["R1", "R4", "R5"]}}, sort_keys=False))
    return root


def project(root):
    from runboard.project import Project
    return Project(root)


def test_a_run_records_what_it_started_from(study, monkeypatch):
    from runboard.backends import BACKENDS
    from runboard.runtime import Runtime
    monkeypatch.setattr(BACKENDS["local"], "submit", lambda *a: {"pid": 1, "url": None})
    rt = Runtime()
    p = rt.add_project(study)
    rt.start(p, "R4", "local")
    prov = p.state.get("R4")["provenance"]
    assert prov["git"] is None and prov["runs_sha256"] and prov["plan_sha256"] and prov["locked"] is False
    assert prov["data"]["key"] == "ground" and prov["data"]["files"] == 1 and len(prov["data"]["listing_sha256"]) == 64


def test_export_writes_the_paper_files(study):
    from runboard import prereg
    from runboard.export import export
    prereg.lock(project(study), "test")
    out = export(project(study))
    d = study / "paper"
    assert set(out["files"]) == {"tables.md", "tables.tex", "hypotheses.md", "hypotheses.tex", "methods.md", "deviations.md",
                                 "checklist.md", "report.html", "provenance.json", "archive.zip"}
    tables = (d / "tables.md").read_text(encoding="utf-8")
    assert "| R4 | ground | yolov8s.pt | 56.20 | 86.20 |" in tables and "53.67 ± 3.48" in tables
    tex = (d / "tables.tex").read_text(encoding="utf-8")
    assert r"\toprule" in tex and r"S1 · specialists" in tex and r"$\pm$" in tex
    hyp = (d / "hypotheses.md").read_text(encoding="utf-8")
    assert "| H1b |" in hyp and "refuted" in hyp and "[-0.13, 0.40]" in hyp
    methods = (d / "methods.md").read_text(encoding="utf-8")
    assert "locked on" in methods and "No deviation" in methods and "1144 images, 200 replicates, seed 0" in methods
    assert "all3 = R1, R4, R5" in methods and "epochs = 100" in methods
    check = (d / "checklist.md").read_text(encoding="utf-8")
    assert "| ✓ | Hypotheses fixed before the experiments |" in check and "| ✗ | Code is under version control |" in check
    report = (d / "report.html").read_text(encoding="utf-8")
    assert "<script" not in report and "Study_1 &amp; co" in report and "refuted" in report
    names = set(zipfile.ZipFile(d / "archive.zip").namelist())
    assert {"plan.yaml", "plan.lock.json", "runs.yaml", "runboard.yaml", "eval/R4/ground.json", "paper/report.html"} <= names
    assert not any(n.startswith(("pkg/", "out/")) for n in names)


def test_export_and_report_from_the_dashboard(study):
    from runboard import server
    home.register(study)
    local = TestClient(server.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    key = next(iter(server.rt.projects()))
    j = local.post(f"/api/p/{key}/export").json()
    assert "report.html" in j["files"]
    r = local.get(f"/api/p/{key}/paper/report.html")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html") and "default-src 'none'" in r.headers["content-security-policy"]
    assert "attachment" in local.get(f"/api/p/{key}/paper/archive.zip").headers["content-disposition"]
    assert local.get(f"/api/p/{key}/paper/..%2Fplan.yaml").status_code == 404
    code = local.post("/api/devices/pair").json()["code"]
    tablet = TestClient(server.app, base_url="http://192.168.1.10:8000", client=("192.168.1.50", 50000))
    tablet.post("/api/pair", json={"code": code, "name": "t"})
    assert tablet.post(f"/api/p/{key}/export").json()["code"] == "local_only"
    assert tablet.get(f"/api/p/{key}/paper/report.html").status_code == 200


def test_export_from_the_command_line(study, capsys):
    from runboard.cli import main
    assert main(["export", str(study)]) == 0
    assert "wrote paper/" in capsys.readouterr().out
