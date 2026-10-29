import pytest
import yaml

from runboard import home
from runboard.project import Project
from runboard.runsfile import Conflict, RunsFile

RUNS = """\
# Plan of the study. Comments must survive every edit.
defaults: {epochs: 50, lr: 0.01, seed: 0}

runs:
  base: {model: small.pt, seed: 0}   # the reference run
  big:
    model: big.pt        # block style, with a comment
    lr: 0.005

  # extras below
  X1: {model: small.pt, seed: 3}

notes: this section comes after the runs
"""


def project(tmp_path, monkeypatch, locked=False, runs=RUNS, crlf=False):
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    (tmp_path / "runs.yaml").write_bytes((runs.replace("\n", "\r\n") if crlf else runs).encode())
    (tmp_path / "data.yaml").write_text("x: 1\n")
    m = {"name": "Plan", "runs": {"file": "runs.yaml", "section": "runs", "defaults": "defaults", "locked": locked,
                                  "fields": ["model", "seed", "epochs", "lr"],
                                  "schema": {"model": {"choices": ["small.pt", "big.pt"]}, "seed": {"int": [0, 9]},
                                             "epochs": {"int": [1, 500]}, "lr": {"float": [0.0001, 1]},
                                             "aug": {"bool": True}, "data": {"file": "*.yaml"}},
                                  "extras": {"prefix": "X", "fields": {"model": {"choices": ["small.pt", "big.pt"]},
                                                                       "seed": {"int": [0, 9], "default": 0}}}}}
    (tmp_path / "runboard.yaml").write_text(yaml.safe_dump(m))
    return Project(tmp_path)


def test_edit_changes_only_that_line(tmp_path, monkeypatch):
    p = project(tmp_path, monkeypatch)
    before, v = p.runs_file.read_text(), p.plan()["version"]
    res = p.edit_run("base", {"seed": 4, "lr": "0.02"}, v)
    after = p.runs_file.read_text()
    changed = [(a, b) for a, b in zip(before.splitlines(), after.splitlines()) if a != b]
    assert changed == [("  base: {model: small.pt, seed: 0}   # the reference run",
                        "  base: {model: small.pt, seed: 4, lr: 0.02}   # the reference run")]
    assert res["version"] == p.plan()["version"] != v
    assert p.spec("base")["lr"] == 0.02 and p.spec("base")["epochs"] == 50


def test_block_style_stays_block_and_none_restores_default(tmp_path, monkeypatch):
    p = project(tmp_path, monkeypatch)
    p.edit_run("big", {"lr": None, "seed": 2}, None)
    text = p.runs_file.read_text()
    assert "  big:\n    model: big.pt\n    seed: 2\n\n  # extras below" in text
    assert p.spec("big")["lr"] == 0.01  # back to the shared default
    assert "# Plan of the study" in text and "# extras below" in text


def test_add_copy_remove_roundtrip_is_byte_identical(tmp_path, monkeypatch):
    p = project(tmp_path, monkeypatch, crlf=True)
    original = p.runs_file.read_bytes()
    res = p.add_run(None, {"seed": 5}, None, copy_from="base", note="copy # of base")
    assert res["id"] == "base-copy" and p.spec("base-copy")["model"] == "small.pt" and p.spec("base-copy")["seed"] == 5
    assert b"\r\n" in p.runs_file.read_bytes() and b"\n\n" not in p.runs_file.read_bytes().replace(b"\r\n", b"\r")
    assert yaml.safe_load(p.runs_file.read_text())["notes"] == "this section comes after the runs"
    p.remove_run("base-copy", None)
    assert p.runs_file.read_bytes() == original


def test_values_are_checked_and_typed(tmp_path, monkeypatch):
    p = project(tmp_path, monkeypatch)
    rules = p.schema()
    assert p.coerce("seed", "7", rules["seed"]) == 7
    assert p.coerce("lr", "0.5", rules["lr"]) == 0.5
    assert p.coerce("aug", "yes", rules["aug"]) is True
    assert p.coerce("data", "data.yaml", rules["data"]) == "data.yaml"
    for field, value in [("seed", 42), ("seed", "abc"), ("model", "huge.pt"), ("lr", 5), ("data", "../x.yaml"),
                         ("data", "runs.txt")]:
        with pytest.raises(ValueError):
            p.coerce(field, value, rules[field])
    with pytest.raises(ValueError, match="Not an editable field"):
        p.edit_run("base", {"secret": 1}, None)
    with pytest.raises(ValueError):
        p.edit_run("base", {"seed": 99}, None)


def test_started_runs_and_preregistered_plans_are_locked(tmp_path, monkeypatch):
    p = project(tmp_path, monkeypatch)
    p.state.set("base", {"status": "RUNNING", "spec": p.spec("base")})
    with pytest.raises(PermissionError, match="started"):
        p.edit_run("base", {"seed": 1}, None)
    with pytest.raises(PermissionError, match="started"):
        p.remove_run("base", None)
    (tmp_path / "l").mkdir()
    locked = project(tmp_path / "l", monkeypatch, locked=True)
    with pytest.raises(PermissionError, match="pre-registered"):
        locked.edit_run("base", {"seed": 1}, None)
    locked.edit_run("X1", {"seed": 4}, None)  # extras of a locked plan stay editable until they start
    res = locked.add_run("anything", {}, None, copy_from="big")  # a locked plan only grows by extra runs
    assert res["id"] == "X2" and locked.spec("X2")["model"] == "big.pt"


def test_conflict_and_dry_run_write_nothing(tmp_path, monkeypatch):
    p = project(tmp_path, monkeypatch)
    v = p.plan()["version"]
    before = p.runs_file.read_bytes()
    dry = p.edit_run("base", {"seed": 3}, v, dry=True)
    assert "+  base: {model: small.pt, seed: 3}" in dry["diff"] and p.runs_file.read_bytes() == before
    p.runs_file.write_bytes(before + b"# edited elsewhere\n")
    with pytest.raises(Conflict):
        p.edit_run("base", {"seed": 3}, v)
    assert p.runs_file.read_bytes() == before + b"# edited elsewhere\n"


def test_every_write_is_backed_up_and_logged(tmp_path, monkeypatch):
    p = project(tmp_path, monkeypatch)
    p.edit_run("base", {"seed": 1}, None, who="this computer")
    assert list((p.state.dir / "backup").iterdir())
    assert '"who": "this computer"' in (p.state.dir / "plan-log.jsonl").read_text(encoding="utf-8")


def test_changed_since_start(tmp_path, monkeypatch):
    p = project(tmp_path, monkeypatch)
    st = {"status": "COMPLETE", "spec": p.spec("big")}
    assert p.changed_since_start("big", st) == []
    f = RunsFile(p.runs_file)
    p.runs_file.write_text(f.set_run("big", {"model": "big.pt", "lr": 0.1}))  # edited by hand after it ran
    assert p.changed_since_start("big", st) == ["lr"]


def test_plan_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    p = project(tmp_path, monkeypatch)
    monkeypatch.setattr(home, "CONFIG", tmp_path / ".rb" / "config.yaml")
    home.save_config({"projects": [str(p.root)], "port": 8000})
    from runboard import server
    c = TestClient(server.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 1))
    plan = c.get(f"/api/p/{p.key}/plan").json()
    assert plan["fields"]["model"]["choices"] == ["small.pt", "big.pt"] and plan["runs"][0]["id"] == "base"
    r = c.put(f"/api/p/{p.key}/plan/runs/base", json={"values": {"seed": 2}, "version": plan["version"]})
    assert r.status_code == 200 and "seed: 2" in r.json()["diff"]
    assert c.put(f"/api/p/{p.key}/plan/runs/base", json={"values": {"seed": 3}, "version": plan["version"]}).status_code == 409
    assert c.put(f"/api/p/{p.key}/plan/runs/base", json={"values": {"seed": 99}}).status_code == 400
    p.state.set("big", {"status": "COMPLETE"})
    assert c.delete(f"/api/p/{p.key}/plan/runs/big").status_code == 403
    r = c.post(f"/api/p/{p.key}/plan/runs", json={"copy_from": "big", "values": {"seed": 1}})
    assert r.status_code == 200 and r.json()["id"] == "big-copy"


def test_run_with_results_but_no_record_counts_as_started(tmp_path, monkeypatch):
    import json
    p = project(tmp_path, monkeypatch)
    m = yaml.safe_load((tmp_path / "runboard.yaml").read_text())
    m["results"] = {"report": "out/{id}.json", "metrics": {"primary": "score"}}
    (tmp_path / "runboard.yaml").write_text(yaml.safe_dump(m))
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "base.json").write_text(json.dumps({"score": 1}))
    assert Project(tmp_path).why_locked("base") == "started"


SHARED = RUNS.replace("defaults: {epochs: 50, lr: 0.01, seed: 0}\n", """defaults: {epochs: 50, lr: 0.01, seed: 0}
train:
  imgsz: 640             # image size
  optimizer: auto        # chosen per model family
  cache: false
""")


def shared_project(tmp_path, monkeypatch, **kw):
    p = project(tmp_path, monkeypatch, runs=SHARED, **kw)
    m = yaml.safe_load((tmp_path / "runboard.yaml").read_text())
    m["runs"]["show"] = ["train"]
    (tmp_path / "runboard.yaml").write_text(yaml.safe_dump(m))
    return Project(tmp_path)


def test_shared_settings_keep_comments_and_report_reach(tmp_path, monkeypatch):
    p = shared_project(tmp_path, monkeypatch)
    assert p.shared_sections() == ["defaults", "train"]
    p.state.set("big", {"status": "COMPLETE"})
    res = p.edit_section("train", {"optimizer": "SGD", "cache": None, "cos_lr": "true"}, p.plan()["version"])
    text = p.runs_file.read_text()
    assert "  optimizer: SGD         # chosen per model family\n" in text and "cache" not in text
    assert "  imgsz: 640             # image size" in text and yaml.safe_load(text)["train"]["cos_lr"] is True
    assert res["affects"] == {"drafts": ["base", "X1"], "started": ["big"]}
    res = p.edit_section("defaults", {"lr": "0.02"}, None, dry=True)  # big sets lr itself, so it is not reached
    assert res["affects"] == {"drafts": ["base", "X1"], "started": []}
    with pytest.raises(ValueError):
        p.edit_section("defaults", {"seed": 42}, None)  # schema rules apply to defaults too
    with pytest.raises(ValueError):
        p.edit_section("runs", {"x": 1}, None)
    with pytest.raises(ValueError):
        p.edit_section("train", {"bad key!": 1}, None)


def test_raw_edit_is_checked_like_a_form(tmp_path, monkeypatch):
    p = shared_project(tmp_path, monkeypatch)
    p.state.set("big", {"status": "COMPLETE"})
    text = p.runs_file.read_text()
    with pytest.raises(ValueError, match="line"):
        p.edit_raw(text.replace("runs:\n", "runs:\n  oops: [\n"), None)
    with pytest.raises(ValueError, match="big has started"):
        p.edit_raw(text.replace("lr: 0.005", "lr: 0.5"), None)
    with pytest.raises(ValueError, match="seed"):
        p.edit_raw(text.replace("base: {model: small.pt, seed: 0}", "base: {model: small.pt, seed: 77}"), None)
    with pytest.raises(ValueError, match="runs"):
        p.edit_raw("notes: nothing else\n", None)
    new = text.replace("# extras below", "# extras below (edited by hand)")
    res = p.edit_raw(new, p.plan()["version"], dry=True)
    assert "+  # extras below (edited by hand)" in res["diff"] and p.runs_file.read_text() == text
    p.edit_raw(new.replace("\n", "\r\n"), p.plan()["version"])  # a textarea may send CRLF
    assert p.runs_file.read_bytes() == new.encode()


def test_locked_plan_shared_and_raw_are_read_only(tmp_path, monkeypatch):
    p = shared_project(tmp_path, monkeypatch, locked=True)
    with pytest.raises(PermissionError):
        p.edit_section("train", {"imgsz": 320}, None)
    with pytest.raises(PermissionError):
        p.edit_raw(p.runs_file.read_text(), None)


def test_sweep_makes_named_drafts_in_one_edit(tmp_path, monkeypatch):
    p = project(tmp_path, monkeypatch)
    res = p.add_sweep({"model": ["small.pt", "big.pt"], "seed": ["1", 2, 2]}, "base", "s", p.plan()["version"])
    assert res["ids"] == ["s-small-1", "s-small-2", "s-big-1", "s-big-2"]
    assert p.spec("s-big-2")["model"] == "big.pt" and p.spec("s-big-2")["seed"] == 2
    assert yaml.safe_load(p.runs_file.read_text())["notes"] == "this section comes after the runs"
    with pytest.raises(ValueError, match="limit"):
        p.add_sweep({"seed": list(range(10)), "lr": [0.001 * i for i in range(1, 10)]}, None, "x", None, dry=True)
    with pytest.raises(ValueError, match="at least one"):
        p.add_sweep({"seed": []}, None, "x", None, dry=True)
    with pytest.raises(ValueError):
        p.add_sweep({"seed": [42]}, None, "x", None, dry=True)


def test_sweep_on_a_locked_plan_adds_extras(tmp_path, monkeypatch):
    p = project(tmp_path, monkeypatch, locked=True)
    res = p.add_sweep({"seed": [5, 6]}, "big", "", None)
    assert res["ids"] == ["X2", "X3"] and p.spec("X3")["model"] == "big.pt" and p.spec("X3")["seed"] == 6
    with pytest.raises(ValueError, match="Not an editable field"):
        p.add_sweep({"lr": [0.1]}, None, "", None)
