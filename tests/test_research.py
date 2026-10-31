"""The research wizard: designs become runs, phases, tables and groups; hypotheses are checked before anything is
written; the project comes out as a version 2 plan with its evaluation scripts (RB-3)."""
import pytest
import yaml

from runboard import home
from runboard.errors import Invalid


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    monkeypatch.setattr(home, "CONFIG", tmp_path / ".rb" / "config.yaml")
    root = tmp_path / "study"
    for key in ("ground", "aerial"):
        d = root / "data" / key
        (d / "images").mkdir(parents=True)
        (d / "train.txt").write_text("./images/a.jpg\n")
        (d / "data.yaml").write_text(f"train: train.txt\nval: val.txt\nnames: [person, vehicle]\n")
    return root


def spec(root, **research):
    r = {"packages": [{"key": "ground", "data": "data/ground/data.yaml"}, {"key": "aerial", "data": "data/aerial/data.yaml"}],
         "model": "yolov8s.pt", "epochs": 100,
         "questions": [{"id": "S1", "text": "How far does a specialist collapse?"}, {"id": "S2", "text": "How much aerial data?"}],
         "designs": [{"type": "transfer", "question": "S1", "seeds": "0, 1, 2"},
                     {"type": "curve", "question": "S2", "base": "ground", "add": "aerial", "fractions": "0.1, 0.25, 0.5"},
                     {"type": "architecture", "models": ["yolov8s.pt", "yolo11s.pt"]},
                     {"type": "ablation", "package": "ground", "field": "mosaic", "values": "1.0, 0.0"}],
         "protocol": {"sets": "ground=data/ground/val.txt, aerial=data/aerial/val.txt", "sealed": ""},
         "hypotheses": [{"id": "H1", "question": "S1", "criterion": "collapse(R1, ground, aerial) > collapse(R2, aerial, ground)"},
                        {"id": "H1s", "question": "S1", "criterion": "R1_seeds.ground > R2_seeds.ground"},
                        {"id": "H2", "question": "S2", "text": "25 % reaches 90 % of the specialist",
                         "criterion": "R4.aerial >= 0.9 * R2.aerial"}]}
    r.update(research)
    return {"path": str(root), "kind": "research", "name": "Study", "backends": ["local", "kaggle"], "research": r}


def test_designs_become_runs_phases_tables_and_groups(folder):
    from runboard import wizard
    files, meta = wizard.build_all(spec(folder))
    runs = yaml.safe_load(files["runboard_runs.yaml"])["runs"]
    assert list(runs) == ["R1", "R1s1", "R1s2", "R2", "R2s1", "R2s2", "R3", "R4", "R5", "R6", "R7", "R8", "R9"]
    assert runs["R1"]["data"] == "data/ground/data.yaml" and runs["R2s2"] == {**runs["R2"], "seed": 2}
    assert runs["R4"]["data"] == "data/aerial/curve2_25.yaml" and runs["R8"]["train"] == {"mosaic": 1.0}
    assert runs["R9"]["train"] == {"mosaic": 0.0} and runs["R7"]["model"] == "yolo11s.pt"
    m = yaml.safe_load(files["runboard.yaml"])
    assert next(iter(m)) == "version" and m["version"] == 2
    assert [p["runs"] for p in m["phases"]][:2] == [["R1", "R2"], ["R3", "R4", "R5"]]
    assert m["tables"][2]["curve"]["x"] == {"R3": 10, "R4": 25, "R5": 50}
    assert m["templates"] == {"scripts/subsets_2.py": "subsets", "scripts/evaluate.py": "evaluate"}
    assert set(m["jobs"]) == {"smoke", "subsets", "evaluate"} and m["data"]["packages"] == [{"key": "data", "dir": "data"}]
    pl = yaml.safe_load(files["plan.yaml"])
    assert pl["groups"] == {"R1_seeds": ["R1", "R1s1", "R1s2"], "R2_seeds": ["R2", "R2s1", "R2s2"]}
    assert pl["protocol"]["sets"] == ["ground", "aerial"] and [h["id"] for h in pl["hypotheses"]] == ["H1", "H1s", "H2"]
    assert "'add': 'data/aerial/train.txt'" in files["scripts/subsets_2.py"] and "'base': 'data/ground/train.txt'" in files["scripts/subsets_2.py"]
    assert meta["problems"] == {} and {s["criterion"] for s in meta["suggest"]} >= {
        "collapse(R1, ground, aerial) > collapse(R2, aerial, ground)", "log_fit({R3: 10, R4: 25, R5: 50}, aerial).r2 >= 0.9"}


def test_bad_criteria_are_shown_before_and_refused_at_creation(folder):
    from runboard import wizard
    s = spec(folder, hypotheses=[{"id": "H1", "criterion": "R99.ground > R1.ground"},
                                 {"id": "H2", "criterion": "R1.test > 0"}, {"id": "H3", "criterion": "R1.ground >"}])
    _, meta = wizard.build_all(s)
    assert set(meta["problems"]) == {"H1", "H2", "H3"} and "R99" in meta["problems"]["H1"]
    with pytest.raises(Invalid) as e:
        wizard.create(s)
    assert e.value.code == "criterion" and not (folder / "plan.yaml").exists()


@pytest.mark.parametrize("change, problem", [
    ({"packages": []}, "data package"), ({"designs": []}, "design"),
    ({"designs": [{"type": "curve", "add": "nope"}]}, "nope"), ({"designs": [{"type": "magic"}]}, "magic"),
    ({"designs": [{"type": "ablation", "field": "lr0", "values": "0.01"}]}, "two values"),
    ({"protocol": {"sets": ""}}, "evaluation set"), ({"protocol": {"sets": "a=x", "sealed": "b"}}, "sealed"),
])
def test_incomplete_plans_say_what_is_missing(folder, change, problem):
    from runboard import wizard
    with pytest.raises(Invalid) as e:
        wizard.build_all(spec(folder, **change))
    assert e.value.code == "research" and problem in str(e.value)


def test_created_project_is_a_locked_v2_plan_with_working_verdicts(folder):
    from runboard import prereg, wizard
    from runboard.project import Project
    wizard.create(spec(folder, lock=True, protocol={"sets": "ground=data/ground/val.txt, aerial=data/aerial/val.txt",
                                                     "sealed": "aerial"}))
    p = Project(folder)
    assert p.v2 and p.locked and p.run_ids()[:2] == ["R1", "R1s1"] and p.info("R4")["ready"]
    st = prereg.status(p)
    assert st["plan_ok"] and st["runs_ok"] and st["code_ok"] and st["sealed"] == ["aerial"]
    assert {h["id"]: h["verdict"] for h in prereg.hypotheses(p)["hypotheses"]} == {"H1": "not_ready", "H1s": "not_ready",
                                                                                   "H2": "not_ready"}
    assert "'sealed': ['aerial']" in (folder / "scripts" / "evaluate.py").read_text()


def test_plan_editor_checks_criteria_against_the_runs(folder):
    from runboard import wizard
    from runboard.project import Project
    wizard.create(spec(folder))
    p = Project(folder)
    text = p.plan_file.read_text(encoding="utf-8").replace("R4.aerial >= 0.9", "R44.aerial >= 0.9")
    with pytest.raises(Invalid) as e:
        p.edit_file("plan", text, None, dry=True)
    assert e.value.code == "criterion" and "H2" in str(e.value) and "R44" in str(e.value)


def test_preview_api_returns_the_plan(folder):
    from fastapi.testclient import TestClient

    from runboard import server
    home.save_config({"projects": [], "port": 8000})
    c = TestClient(server.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    j = c.post("/api/wizard/preview", json=spec(folder)).json()
    assert "plan.yaml" in j["files"] and len(j["research"]["runs"]) == 13 and j["research"]["sets"] == ["ground", "aerial"]
    j = c.post("/api/wizard/create", json=spec(folder)).json()
    assert j["key"] == "study" and (folder / "scripts" / "evaluate.py").is_file()
