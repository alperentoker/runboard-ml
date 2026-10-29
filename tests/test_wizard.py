import json
import re
import zipfile

import pytest

from runboard import home, wizard
from runboard.backends.kaggle import KaggleBackend
from runboard.project import Project


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    root = tmp_path / "birds"
    for split in ("train", "val", "test"):
        (root / "data" / "images" / split).mkdir(parents=True)
        (root / "data" / "images" / split / "a.jpg").write_bytes(b"x")
    (root / "data" / "birds.yaml").write_text("path: .\ntrain: images/train\nval: images/val\ntest: images/test\nnames: {0: bird}\n")
    (root / "notes.py").write_text("print(1)\n")
    return root


def test_scan_finds_dataset(folder):
    sc = wizard.scan(str(folder))
    assert sc["datasets"] == [{"file": "data/birds.yaml", "classes": ["bird"]}]
    assert sc["suggest"] == "yolo" and not sc["has_manifest"]


def test_yolo_project_end_to_end(folder):
    spec = {"path": str(folder), "name": "Birds", "kind": "yolo", "backends": ["local", "kaggle"],
            "yolo": {"data": "data/birds.yaml", "models": ["yolo11n.pt", "yolo11s.pt"], "seeds": [0, 1], "epochs": 3}}
    wizard.create(spec)
    with pytest.raises(FileExistsError):
        wizard.create(spec)
    p = Project(folder)
    assert sorted(p.run_ids()) == ["yolo11n-s0", "yolo11n-s1", "yolo11s-s0", "yolo11s-s1"]
    info = p.info("yolo11n-s1")
    assert info["ready"] and info["name"] == "yolo11n-s1" and info["epochs"] == 3
    assert "runboard_train.py --run yolo11n-s1" in p.render(p.m["backends"]["local"]["command"], info)
    # data: the folder is zipped at upload time without the test split
    row = p.catalog()[0]
    z = KaggleBackend.zip_folder(__import__("pathlib").Path(row["_dir"]), p.state.dir / "x.zip",
                                 [re.compile(r) for r in p.m["data"]["forbid"]], say=lambda *_: None)
    names = zipfile.ZipFile(z).namelist()
    assert "birds.yaml" in names and "images/train/a.jpg" in names and not any("test" in n for n in names)
    # kernel embeds the generated trainer, rb.py and the runs file
    kb = KaggleBackend()
    p.state.set_dataset(row["_key"], "birds-data")
    folder_k = p.state.dir / "k"
    kb.build(p, "yolo11n-s0", p.info("yolo11n-s0"), folder_k, "someone")
    code = (folder_k / "run.py").read_text()
    compile(code, "run.py", "exec")
    files = json.loads(json.loads(re.search(r"FILES = json.loads\((.*)\)\n", code)[1]))
    assert set(files) == {"runboard_train.py", "rb.py", "runboard_runs.yaml"}
    meta = json.loads((folder_k / "kernel-metadata.json").read_text())
    assert meta["dataset_sources"] == ["someone/birds-data"] and meta["is_private"]


def test_script_project(folder):
    spec = {"path": str(folder), "kind": "script", "backends": ["local"],
            "script": {"file": "notes.py", "runs": [{"id": "Fast LR", "args": "--lr 0.1"}, {"id": "", "args": "--lr 0.01"}]}}
    files = wizard.build(spec)
    wizard.create(spec)
    p = Project(folder)
    assert p.run_ids() == ["fast-lr", "run2"]
    assert p.render(p.m["backends"]["local"]["command"], p.info("fast-lr")).endswith("notes.py --lr 0.1")
    assert "runboard.yaml" in files


def test_bad_specs(folder):
    with pytest.raises(ValueError):
        wizard.build({"path": str(folder), "kind": "yolo", "yolo": {"data": "missing.yaml"}})
    with pytest.raises(ValueError):
        wizard.build({"path": str(folder), "kind": "script", "script": {"file": "nope.py", "runs": [{"id": "a"}]}})
