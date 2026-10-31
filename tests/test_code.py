"""Code in the dashboard: which files show, what may be written, checks before saving, the lock, and the syntax
check before a Kaggle run (RB-4)."""
import pytest
import yaml
from fastapi.testclient import TestClient

from runboard import home
from runboard.errors import Invalid


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    monkeypatch.setattr(home, "CONFIG", tmp_path / ".rb" / "config.yaml")
    home.save_config({"projects": [], "port": 8000, "lan": True})
    root = tmp_path / "p"
    for d in ("scripts", "runs/kaggle/R1", "data/pkg", ".git", "venv/lib", "configs"):
        (root / d).mkdir(parents=True)
    (root / "scripts" / "train.py").write_text("print('train')\n")
    (root / "configs" / "aug.yaml").write_text("mosaic: 1.0\n")
    (root / "runs" / "kaggle" / "R1" / "args.yaml").write_text("x: 1\n")
    (root / "data" / "pkg" / "data.yaml").write_text("train: t.txt\n")
    (root / ".git" / "config").write_text("[core]\n")
    (root / "venv" / "lib" / "site.py").write_text("x = 1\n")
    (root / "notes.txt").write_text("x" * (600 * 1024))
    (root / "raw" / "labels").mkdir(parents=True)
    (root / "raw" / "labels" / "a.txt").write_text("0 0.5 0.5 0.1 0.1\n")  # a YOLO dataset: not code
    (root / "raw" / "frames").mkdir()
    for i in range(501):
        (root / "raw" / "frames" / f"{i}.txt").write_text("0")
    (root / "runs.yaml").write_text("runs:\n  R1: {seed: 0}\n")
    (root / "plan.yaml").write_text("questions: []\n")
    (root / "runboard.yaml").write_text(yaml.safe_dump({
        "version": 2, "name": "P", "runs": {"file": "runs.yaml", "fields": ["seed"]},
        "backends": {"kaggle": {"kernel": "p-{id|lower}", "files": {"train.py": "scripts/train.py"}, "command": "python train.py",
                                "output_dir": "runs/kaggle"}},
        "data": {"packages": [{"key": "pkg", "dir": "data/pkg"}]}}))
    return root


def project(root):
    from runboard.project import Project
    return Project(root)


def test_the_list_shows_code_and_leaves_out_data_outputs_and_environments(proj):
    from runboard import code
    files = {f["path"]: f for f in code.listing(project(proj))["files"]}
    assert {"scripts/train.py", "configs/aug.yaml", "runs.yaml", "plan.yaml", "runboard.yaml", "notes.txt"} == set(files)
    assert files["plan.yaml"]["special"] == "plan" and files["runboard.yaml"]["special"] == "manifest"
    assert files["notes.txt"]["big"] and not files["scripts/train.py"]["big"]


@pytest.mark.parametrize("path", ["../outside.py", ".git/config", "venv/lib/site.py", "data/pkg/img.jpg", "scripts/../../x.py"])
def test_paths_outside_the_code_are_refused(proj, path):
    from runboard import code
    with pytest.raises(Invalid) as e:
        code.save(project(proj), path, "x = 1\n", None, dry=True)
    assert e.value.code == "bad_code_path"


def test_files_are_checked_before_they_are_written(proj):
    from runboard import code
    p = project(proj)
    with pytest.raises(Invalid) as e:
        code.save(p, "scripts/train.py", "def f(:\n    pass\n", None)
    assert e.value.code == "syntax" and e.value.params["line"] == 1
    with pytest.raises(Invalid) as e:
        code.save(p, "configs/aug.yaml", "a: [1,\n", None)
    assert e.value.code == "syntax"
    with pytest.raises(Invalid) as e:
        code.save(p, "plan.yaml", "questions: []\n", None)
    assert e.value.code == "use_editor"
    with pytest.raises(Invalid) as e:
        code.read(p, "notes.txt")
    assert e.value.code == "too_big"
    assert (proj / "scripts" / "train.py").read_text() == "print('train')\n"


def test_save_shows_the_diff_creates_files_and_refuses_stale_versions(proj):
    from runboard import code
    p = project(proj)
    f = code.read(p, "scripts/train.py")
    dry = code.save(p, "scripts/train.py", "print('train v2')\n", f["version"], dry=True)
    assert "+print('train v2')" in dry["diff"] and (proj / "scripts" / "train.py").read_text() == "print('train')\n"
    code.save(p, "scripts/train.py", "print('train v2')\n", f["version"])
    assert (proj / "scripts" / "train.py").read_text() == "print('train v2')\n"
    with pytest.raises(Exception) as e:
        code.save(p, "scripts/train.py", "print('v3')\n", f["version"])
    assert getattr(e.value, "code", "") == "conflict"
    code.save(p, "tools/new/helper.py", "X = 1\n", None)
    assert (proj / "tools" / "new" / "helper.py").read_text() == "X = 1\n"


def test_a_locked_template_script_changes_only_as_a_deviation(proj):
    from runboard import code, prereg, templating
    templating.write(project(proj), "check", {})
    prereg.lock(project(proj))
    p = project(proj)
    f = code.read(p, "scripts/check.py")
    assert f["template"]["state"] == "pristine"
    new = f["text"] + "# stricter\n"
    with pytest.raises(Invalid) as e:
        code.save(p, "scripts/check.py", new, f["version"])
    assert e.value.code == "deviation_reason"
    assert code.save(p, "scripts/check.py", new, f["version"], reason="Stricter near-duplicate threshold")["deviation"]
    st = prereg.status(project(proj))
    assert st["code_ok"] and st["deviations"][-1]["file"] == "scripts/check.py"
    assert code.read(project(proj), "scripts/check.py")["template"]["state"] == "owned"
    assert not code.save(project(proj), "scripts/train.py", "print(1)\n", None).get("deviation")  # not covered


def test_reading_from_a_tablet_writing_from_this_computer(proj):
    from runboard import server
    home.register(proj)
    local = TestClient(server.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    key = next(iter(server.rt.projects()))
    assert local.get(f"/api/p/{key}/code").json()["can_write"]
    code = local.post("/api/devices/pair").json()["code"]
    tablet = TestClient(server.app, base_url="http://192.168.1.10:8000", client=("192.168.1.50", 50000))
    tablet.post("/api/pair", json={"code": code, "name": "t"})
    assert tablet.get(f"/api/p/{key}/code").json()["can_write"] is False
    assert tablet.get(f"/api/p/{key}/code/file", params={"path": "scripts/train.py"}).json()["text"] == "print('train')\n"
    r = tablet.put(f"/api/p/{key}/code/file", json={"path": "scripts/train.py", "text": "print(2)\n"})
    assert r.json()["code"] == "local_only" and (proj / "scripts" / "train.py").read_text() == "print('train')\n"
    r = local.put(f"/api/p/{key}/code/file", json={"path": "scripts/train.py", "text": "print(2)\n", "dry": True})
    assert r.status_code == 200 and "+print(2)" in r.json()["diff"]


def test_a_broken_script_does_not_reach_kaggle(proj, monkeypatch):
    from runboard.backends import BACKENDS
    from runboard.runtime import Runtime
    (proj / "scripts" / "train.py").write_text("for x in range(3)\n    print(x)\n")
    sent = []
    monkeypatch.setattr(BACKENDS["kaggle"], "submit", lambda *a: sent.append(a) or {"kernel": "k", "url": None})
    rt = Runtime()
    p = rt.add_project(proj)
    with pytest.raises(Invalid) as e:
        rt.start(p, "R1", "kaggle")
    assert e.value.code == "syntax" and e.value.params["file"] == "train.py" and not sent
    assert not p.state.get("R1").get("status")
    (proj / "scripts" / "train.py").write_text("for x in range(3):\n    print(x)\n")
    rt.start(p, "R1", "kaggle")
    assert sent


def test_wizard_projects_get_a_smoke_test(tmp_path):
    from runboard import wizard
    ds = tmp_path / "w" / "data"
    ds.mkdir(parents=True)
    (ds / "data.yaml").write_text("train: t.txt\nval: v.txt\nnames: [a]\n")
    files = wizard.build({"path": str(tmp_path / "w"), "kind": "yolo", "yolo": {"data": "data/data.yaml", "models": ["yolo11n.pt"]}})
    job = yaml.safe_load(files["runboard.yaml"])["jobs"]["smoke"]
    assert job["per_run"] and job["cmd"].endswith("--run {id} --smoke")
    assert "--smoke" in files["runboard_train.py"] and "fraction=0.02" in files["runboard_train.py"]
