"""Hypotheses, verdicts, the lock, deviations and the sealed-set ledger (RB-1, docs/design-v2.md)."""
import json
import shutil
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from runboard import home
from runboard.errors import Invalid

DATA = Path(__file__).parent / "data" / "g2a_s1"
H1A = ("collapse(R4@person, ground, aerial) > collapse(R5@person, aerial, ground) and "
       "collapse(R4@vehicle, ground, aerial) > collapse(R5@vehicle, aerial, ground)")
H1B = ("collapse(R4@person, ground, aerial) > collapse(R4@vehicle, ground, aerial) and "
       "collapse(R5@person, aerial, ground) > collapse(R5@vehicle, aerial, ground)")


@pytest.fixture
def g2a(tmp_path, monkeypatch):
    """Ground2Air's S1: R1 (combined), R4 (ground only), R5 (aerial only), evaluated on ground and aerial val with
    200 shared bootstrap replicates by its own 08_test.py (image names replaced by their position)."""
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    monkeypatch.setattr(home, "CONFIG", tmp_path / ".rb" / "config.yaml")
    home.save_config({"projects": [], "port": 8000, "lan": True})
    root = tmp_path / "g2a"
    shutil.copytree(DATA / "eval", root / "eval")
    (root / "runs.yaml").write_text("train: {epochs: 100, model: null}\nruns:\n  R1: {package: combined}\n"
                                    "  R4: {package: ground}\n  R5: {package: aerial}\n  R9: {package: ground}\n",
                                    encoding="utf-8")
    (root / "runboard.yaml").write_text("version: 2\nname: G\nruns: {file: runs.yaml, defaults: train, fields: [package],"
                                        " extras: {prefix: X, fields: {package: {}}}}\n", encoding="utf-8")
    (root / "plan.yaml").write_text(yaml.safe_dump({
        "questions": [{"id": "S1", "text": "How far does a single-view detector collapse?"}],
        "hypotheses": [{"id": "H1a", "question": "S1", "criterion": H1A},
                       {"id": "H1b", "question": "S1", "criterion": H1B},
                       {"id": "H1a-map", "question": "S1",
                        "criterion": "collapse(R4, ground, aerial) > collapse(R5, aerial, ground)"},
                       {"id": "pair", "criterion": "R1.ground > R4.ground and R1.aerial > R5.aerial"},
                       {"id": "later", "criterion": "R9.aerial > R4.aerial"},
                       {"id": "open"}],
        "protocol": {"dir": "eval", "metric": "map50_95", "sets": ["ground", "aerial"]},
        "decisions": [{"id": "A3", "candidates": ["R1"], "field": "model"}]}, sort_keys=False), encoding="utf-8")
    return root


def project(root):
    from runboard.project import Project
    return Project(root)


def verdicts(root):
    from runboard import prereg
    return {h["id"]: h for h in prereg.hypotheses(project(root))["hypotheses"]}


# ---------------------------------------------------------------- the golden test

def test_ground2air_s1_verdicts_match_its_own_analysis(g2a):
    v = verdicts(g2a)
    # paired differences, exactly as 08_test.py printed them (reports/eval/val/paired/R1_R4_R5.json)
    ground, aerial = v["pair"]["parts"]
    assert (ground["margin"], ground["ci"], ground["share"]) == (0.134, [-0.126, 0.401], 84.5)
    assert (aerial["margin"], aerial["ci"], aerial["share"]) == (-0.368, [-1.35, 0.555], 22.0)
    assert v["pair"]["verdict"] == "indistinguishable"
    # H1a by class: person collapses more from ground to air, vehicle cannot be told apart -> indistinguishable,
    # the verdict of the article; the same hypothesis on the mean over classes would be supported (0.82 points)
    person, vehicle = v["H1a"]["parts"]
    assert (person["left"], person["right"], person["verdict"]) == (98.586, 96.196, "supported")
    assert (vehicle["left"], vehicle["right"], vehicle["verdict"]) == (99.525, 99.725, "indistinguishable")
    assert v["H1a"]["verdict"] == "indistinguishable"
    assert (v["H1a-map"]["verdict"], v["H1a-map"]["parts"][0]["margin"]) == ("supported", 0.824)
    # H1b: people do not collapse more than vehicles; from the air to the ground clearly the reverse
    assert [p["verdict"] for p in v["H1b"]["parts"]] == ["indistinguishable", "refuted"]
    assert v["H1b"]["verdict"] == "refuted"
    assert v["later"]["verdict"] == "not_ready" and v["later"]["missing"] == ["R9.aerial"]
    assert v["open"]["verdict"] == "no_criterion"


def test_each_comparison_carries_the_histogram_of_its_replicates(g2a):
    ground = verdicts(g2a)["pair"]["parts"][0]
    h = ground["hist"]
    assert len(h["n"]) == 30 and sum(h["n"]) > 100
    assert h["lo"] <= ground["ci"][0] < ground["ci"][1] <= h["hi"]
    assert verdicts(g2a)["open"].get("parts") is None  # no criterion, nothing to draw


def test_one_runs_interval_is_its_bootstrap_interval(g2a):
    from runboard.hypotheses import Evidence, decide
    ev = Evidence(g2a, {"sets": ["ground", "aerial"]})
    assert decide("R4.ground > 0", ev, {})["parts"][0]["ci"] == [55.354, 57.155]  # R4's ci95 in 08_test.py's report


def test_percentile_is_numpys():
    np = pytest.importorskip("numpy")
    from runboard.hypotheses import percentile
    rng = np.random.default_rng(3)
    for n in (1, 2, 7, 200, 201):
        xs = list(rng.normal(size=n))
        for q in (0, 2.5, 50, 97.5, 100):
            assert percentile(xs, q) == float(np.nanpercentile(xs, q))
    assert percentile([1.0, float("nan"), 3.0], 50) == 2.0


# ---------------------------------------------------------------- the language

@pytest.mark.parametrize("text", [
    "__import__('os').system('x') > 0", "R1.ground.__class__ > 0", "R1.ground > 'a'", "1 < R1.ground < 2",
    "open(R1.ground) > 0", "R1 > R4", "R1.ground", "R1.ground > 0 or R4.ground > 0", "R1.test > 0",
    "[x for x in R1] > 0", "lambda: 1 > 0", "R1.ground > True", "log_fit({R1: 0, R4: 1, R5: 2}, ground).r2 > 0",
])
def test_anything_outside_the_language_is_refused(g2a, text):
    from runboard.hypotheses import Evidence, decide
    with pytest.raises(Invalid) as e:
        decide(text, Evidence(g2a, {"sets": ["ground", "aerial"]}), {})
    assert e.value.code == "criterion"


def test_groups_logs_and_arithmetic(g2a):
    from runboard.hypotheses import Evidence, decide
    ev = Evidence(g2a, {"sets": ["ground", "aerial"]})
    r = decide("pair.ground >= 0.99 * R4.ground", ev, {"pair": ["R1", "R4"]})
    assert r["parts"][0]["left"] == round((56.332 + 56.198) / 2, 3) and r["groups"]["pair.ground"]["sd"] == 0.095
    r = decide("log_fit({R4: 1, R1: 10, R5: 100}, aerial).slope > 0", ev, {})
    assert r["functions"] and r["verdict"] == "supported"
    r = decide("abs(R1.aerial - R5.aerial) < 2 and max(R1.aerial, R5.aerial) > -R4.aerial", ev, {})
    assert r["verdict"] == "supported"


def test_evidence_from_another_image_list_is_refused(g2a):
    f = g2a / "eval" / "R4" / "aerial.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    f.write_text(json.dumps(d | {"resample": "0" * 64}), encoding="utf-8")
    h = verdicts(g2a)["H1a"]
    assert h["verdict"] == "invalid" and h["error"]["code"] == "evidence"


def test_plan_check_reads_criteria_as_text(g2a):
    from runboard.planfile import check_plan
    with pytest.raises(Invalid):
        check_plan({"hypotheses": [{"id": "H", "criterion": 3}]}, {"R1"})


# ---------------------------------------------------------------- lock, deviations, ledger

def test_lock_then_change_only_with_a_reason(g2a):
    from runboard import prereg
    p = project(g2a)
    assert not p.locked
    rec = prereg.lock(p, "test")
    assert rec["plan_sha256"] and set(rec["resample"]) == {"ground", "aerial"} and rec["git"] is None
    p = project(g2a)
    assert p.locked and p.why_locked("R4") == "locked"
    with pytest.raises(Invalid) as e:
        prereg.lock(p)
    assert e.value.code == "already_locked"
    st = prereg.status(p)
    assert st["plan_ok"] and st["runs_ok"] and st["deviations"] == []

    text = p.plan_file.read_text(encoding="utf-8").replace("How far", "How much")
    with pytest.raises(Invalid) as e:
        p.edit_file("plan", text, None, reason="short")
    assert e.value.code == "deviation_reason"
    res = p.edit_file("plan", text, None, reason="The question was worded loosely", who="test")
    assert res["deviation"] and "How much" in p.plan_file.read_text(encoding="utf-8")
    st = prereg.status(project(g2a))
    assert st["plan_ok"] and [d["reason"] for d in st["deviations"]] == ["The question was worded loosely"]
    assert "```diff" in (g2a / "deviations.md").read_text(encoding="utf-8")

    runs = (g2a / "runs.yaml").read_text(encoding="utf-8")
    res = project(g2a).edit_raw(runs.replace("epochs: 100", "epochs: 120"), None, reason="Longer schedule, see notes")
    assert res["deviation"] and prereg.status(project(g2a))["runs_ok"]

    p.plan_file.write_text(text + "# by hand\n", encoding="utf-8")  # a change that skipped the deviation log
    assert prereg.status(project(g2a))["plan_ok"] is False


def test_decisions_and_extra_runs_keep_the_lock(g2a):
    from runboard import prereg
    p = project(g2a)
    before = prereg.runs_hash(p)
    (g2a / "runs.yaml").write_text((g2a / "runs.yaml").read_text().replace("model: null", "model: yolov8s.pt")
                                   + "  X1: {package: ground}\n", encoding="utf-8")
    assert prereg.runs_hash(project(g2a)) == before


def test_sealed_sets_keep_a_ledger(g2a, monkeypatch):
    from runboard import prereg, rb
    monkeypatch.chdir(g2a)
    rb.sealed("test", "R4", "abc")
    with pytest.raises(SystemExit):
        rb.sealed("test", "R4", "abc")
    rb.sealed("test", "R4", "abc", again=True)
    pl = yaml.safe_load((g2a / "plan.yaml").read_text())
    pl["protocol"]["sets"] = {"ground": {}, "aerial": {}, "test": {"sealed": True}}
    (g2a / "plan.yaml").write_text(yaml.safe_dump(pl), encoding="utf-8")
    st = prereg.status(project(g2a))
    assert st["sealed"] == ["test"] and [r["again"] for r in st["ledger"]] == ["", "yes"]


def test_rb_writes_what_runboard_reads(tmp_path, monkeypatch):
    np = pytest.importorskip("numpy")
    from runboard import rb
    from runboard.hypotheses import Evidence, decide
    monkeypatch.chdir(tmp_path)
    ids = [f"im{i}" for i in range(50)]
    scores = {"A": np.linspace(0.5, 1, 50), "B": np.linspace(0.4, 0.9, 50)}
    idx = rb.replicates("val", ids=ids, replicates=100)
    for run, s in scores.items():
        rb.write_eval(run, "val", {"acc": (s.mean(), [s[i].mean() for i in idx])})
    r = decide("A.val > B.val", Evidence(tmp_path, {"metric": "acc", "sets": ["val"]}), {})
    assert r["verdict"] == "supported" and r["parts"][0]["margin"] == 0.1
    (tmp_path / "eval" / "C").mkdir()  # per-image samples instead of replicates: runboard draws them itself
    (tmp_path / "eval" / "C" / "val.json").write_text(json.dumps({
        "format": "runboard-eval/1", "run": "C", "set": "val", "resample": rb.resample_plan("val")["ids_sha256"],
        "metrics": {"acc": {"point": float(scores["A"].mean()), "samples": list(map(float, scores["A"]))}}}))
    r = decide("C.val > A.val - 0.001", Evidence(tmp_path, {"metric": "acc", "sets": ["val"]}), {})
    assert r["verdict"] == "supported"


# ---------------------------------------------------------------- dashboard and command line

def test_hypotheses_api_and_lock_from_this_computer_only(g2a):
    from runboard import server
    home.register(g2a)
    local = TestClient(server.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    key = next(iter(server.rt.projects()))
    d = local.get(f"/api/p/{key}/hypotheses").json()
    assert {h["id"]: h["verdict"] for h in d["hypotheses"]}["H1b"] == "refuted" and d["status"]["locked"] is False
    code = local.post("/api/devices/pair").json()["code"]
    tablet = TestClient(server.app, base_url="http://192.168.1.10:8000", client=("192.168.1.50", 50000))
    tablet.post("/api/pair", json={"code": code, "name": "tablet"})
    assert tablet.post(f"/api/p/{key}/lock").json()["code"] == "local_only"
    assert local.post(f"/api/p/{key}/lock").status_code == 200
    assert local.get(f"/api/p/{key}/hypotheses").json()["status"]["plan_ok"] is True


def test_verdicts_and_lock_from_the_command_line(g2a, capsys):
    from runboard.cli import main
    assert main(["verdicts", str(g2a)]) == 0
    out = capsys.readouterr().out
    assert "H1b      refuted" in out and "waiting for: R9.aerial" in out
    assert main(["lock", str(g2a)]) == 0 and "locked at" in capsys.readouterr().out
    assert main(["lock", str(g2a)]) == 1
