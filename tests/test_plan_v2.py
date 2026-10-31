"""Manifest v2: plan.yaml holds the science, runboard.yaml the infrastructure (docs/design-v2.md)."""
import pytest
import yaml
from fastapi.testclient import TestClient

from runboard import home
from runboard.errors import Denied, Invalid

V1 = """# header comment
name: T
runs:
  file: runs.yaml
  section: runs
  locked: true   # pre-registered
  fields: [model]

# the winning model
decisions:
  - id: D
    candidates: [a, b]   # both
    field: model

# shown on the results page
tables:
  - {title: All, runs: [a, b]}
"""
RUNS = "runs:\n  a: {model: x}\n  b: {model: y}\n  c: {model: null}\n"


@pytest.fixture
def rb(tmp_path, monkeypatch):
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    monkeypatch.setattr(home, "CONFIG", tmp_path / ".rb" / "config.yaml")
    home.save_config({"projects": [], "port": 8000, "lan": True})
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "runs.yaml").write_text(RUNS, encoding="utf-8")
    (proj / "runboard.yaml").write_text(V1, encoding="utf-8")
    return proj


def project(root):
    from runboard.project import Project
    return Project(root)


def test_v1_reads_lock_and_decisions_from_the_manifest(rb):
    p = project(rb)
    assert not p.v2 and p.locked and [d["id"] for d in p.decision_specs()] == ["D"]


def test_migrate_moves_decisions_and_lock_with_their_comments(rb):
    from runboard.planfile import migrate
    out = migrate(rb, rb / "bak")
    assert out == {"plan": "plan.yaml", "moved": ["decisions", "runs.locked"]}
    plan, man = (rb / "plan.yaml").read_text(encoding="utf-8"), (rb / "runboard.yaml").read_text(encoding="utf-8")
    assert "locked: true   # pre-registered" in plan and "# the winning model\ndecisions:" in plan
    assert "candidates: [a, b]   # both" in plan
    assert "decisions" not in man and "locked" not in man and "# shown on the results page\ntables:" in man
    assert man.startswith("# header comment\nversion: 2\nname: T\n")
    assert len(list((rb / "bak").iterdir())) == 1
    p = project(rb)
    assert p.v2 and p.locked and [d["id"] for d in p.decision_specs()] == ["D"]
    assert p.why_locked("a") == "locked"
    with pytest.raises(Invalid) as e:
        migrate(rb)
    assert e.value.code == "already_v2"


def test_migrate_keeps_crlf_files_crlf(rb):
    from runboard.planfile import migrate
    (rb / "runboard.yaml").write_bytes(V1.replace("\n", "\r\n").encode())
    migrate(rb)
    assert b"\r\n" in (rb / "plan.yaml").read_bytes() and b"\n" not in (rb / "runboard.yaml").read_bytes().replace(b"\r\n", b"")


def test_migrate_from_the_command_line(rb, capsys):
    from runboard.cli import main
    assert main(["migrate", str(rb)]) == 0
    assert "runboard.yaml is version 2" in capsys.readouterr().out
    assert main(["migrate", str(rb)]) == 1


def v2(rb, plan="questions: []\n"):
    (rb / "runboard.yaml").write_text("version: 2\nname: T\nruns: {file: runs.yaml, fields: [model]}\n", encoding="utf-8")
    (rb / "plan.yaml").write_text(plan, encoding="utf-8")
    return project(rb)


GOOD = """questions:
  - {id: S1, text: "Does it collapse?"}
hypotheses:
  - {id: H1, question: S1, criterion: "a.aerial >= 0.9 * b.aerial"}
groups:
  pair: [a, b]
decisions:
  - {id: D, candidates: [a, b], field: model}
protocol: {metric: map50_95, sets: [ground, aerial]}
"""


def test_plan_edit_is_checked_and_saved_with_a_diff(rb):
    p = v2(rb)
    f = p.files()["files"]["plan"]
    dry = p.edit_file("plan", GOOD, f["version"], dry=True)
    assert "+hypotheses:" in dry["diff"] and (rb / "plan.yaml").read_text() == "questions: []\n"
    p.edit_file("plan", GOOD, f["version"])
    assert yaml.safe_load((rb / "plan.yaml").read_text())["groups"] == {"pair": ["a", "b"]}
    assert [d["id"] for d in project(rb).decision_specs()] == ["D"]


@pytest.mark.parametrize("text, code", [
    ("runs: {}\n", "plan_key"),
    ("questions: {S1: x}\n", "plan_shape"),
    ("hypotheses:\n  - {id: H1, question: S9}\n", "plan_ref"),
    ("questions:\n  - {id: S1}\nhypotheses:\n  - {id: S1}\n", "plan_dup"),
    ("groups: {g: [a, zz]}\n", "plan_ref"),
    ("groups: {a: [b]}\n", "plan_dup"),
    ("decisions:\n  - {id: D, candidates: [a, q], field: model}\n", "plan_ref"),
    ("locked: yes please\n", "plan_shape"),
    ("questions: [\n", "yaml_line"),
    ("- a\n", "file_mapping"),
])
def test_a_broken_plan_is_refused(rb, text, code):
    p = v2(rb)
    with pytest.raises(Invalid) as e:
        p.edit_file("plan", text, None, dry=True)
    assert e.value.code == code


def test_a_locked_plan_changes_only_with_a_reason_and_a_v1_project_has_no_plan(rb):
    with pytest.raises(Invalid) as e:
        project(rb).edit_file("plan", GOOD, None, dry=True)
    assert e.value.code == "not_v2"
    with pytest.raises(Denied):  # a v1 plan has no deviations: it changes through decisions and extra runs only
        project(rb).edit_raw(RUNS, None, dry=True, reason="a reason long enough")
    p = v2(rb, "locked: true\n")
    with pytest.raises(Invalid) as e:
        p.edit_file("plan", GOOD, None, dry=True)
    assert e.value.code == "deviation_reason"
    (rb / "other.yaml").write_text(RUNS, encoding="utf-8")
    with pytest.raises(Denied):  # nor can the manifest point the lock at another runs file
        p.edit_file("manifest", "version: 2\nname: T\nruns: {file: other.yaml}\n", None, dry=True)


@pytest.mark.parametrize("text, code", [
    ("version: 2\nname: T\nruns: {file: missing.yaml}\n", "manifest_runs"),
    ("name: T\nruns: {file: runs.yaml}\n", "keep_version"),
    ("version: 2\nname: T\nruns: {file: runs.yaml}\ndecisions: []\n", "in_plan"),
    ("version: 2\nname: T\nruns: {file: runs.yaml, locked: false}\n", "in_plan"),
])
def test_a_broken_manifest_is_refused(rb, text, code):
    p = v2(rb)
    with pytest.raises(Invalid) as e:
        p.edit_file("manifest", text, None, dry=True)
    assert e.value.code == code


def test_a_v1_lock_cannot_be_lifted_from_the_manifest_editor(rb):
    with pytest.raises(Denied):
        project(rb).edit_file("manifest", V1.replace("locked: true", "locked: false"), None, dry=True)


def test_manifest_edits_only_from_this_computer(rb):
    from runboard import server
    v2(rb)
    home.register(rb)
    local = TestClient(server.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    key = next(iter(server.rt.projects()))
    files = local.get(f"/api/p/{key}/files").json()
    assert files["can_edit_manifest"] and set(files["files"]) == {"plan", "manifest"}
    text = files["files"]["manifest"]["text"].replace("name: T", "name: T\ndescription: d")
    r = local.put(f"/api/p/{key}/files/manifest", json={"text": text, "version": files["files"]["manifest"]["version"]})
    assert r.status_code == 200 and "+description: d" in r.json()["diff"]
    r = local.put(f"/api/p/{key}/files/manifest", json={"text": text + "\n", "version": files["files"]["manifest"]["version"]})
    assert r.status_code == 409 and r.json()["code"] == "conflict"

    code = local.post("/api/devices/pair").json()["code"]
    tablet = TestClient(server.app, base_url="http://192.168.1.10:8000", client=("192.168.1.50", 50000))
    assert tablet.post("/api/pair", json={"code": code, "name": "tablet"}).status_code == 200
    seen = tablet.get(f"/api/p/{key}/files").json()
    assert seen["can_edit_manifest"] is False
    assert tablet.put(f"/api/p/{key}/files/manifest", json={"text": text}).json()["code"] == "local_only"
    assert tablet.put(f"/api/p/{key}/files/plan", json={"text": GOOD, "dry": True}).status_code == 200


def test_page_scripts_are_served_by_name_only(rb):
    from runboard import server
    c = TestClient(server.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    r = c.get("/js/01-i18n.js")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/javascript") and "const T" in r.text
    assert c.get("/js/..%2Fserver.py").status_code == 404 and c.get("/js/nope.js").status_code == 404
    assert "<script>" not in c.get("/").text  # no inline script: the policy allows this server's files only
