"""Code templates: tracked files that runboard never overwrites once changed, and the scripts themselves (RB-2)."""
import importlib.util
import json
import subprocess
import sys

import pytest
import yaml

from runboard import home
from runboard.errors import Invalid


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    monkeypatch.setattr(home, "CONFIG", tmp_path / ".rb" / "config.yaml")
    root = tmp_path / "p"
    root.mkdir()
    (root / "runs.yaml").write_text("runs:\n  A: {seed: 0}\n  B: {seed: 1}\n", encoding="utf-8")
    (root / "runboard.yaml").write_text("version: 2\nname: P\nruns: {file: runs.yaml, fields: [seed]}\n", encoding="utf-8")
    (root / "plan.yaml").write_text("questions: []\n", encoding="utf-8")
    return root


def project(root):
    from runboard.project import Project
    return Project(root)


def run(root, script):
    return subprocess.run([sys.executable, script], cwd=root, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120)


def dataset(root, n=40):
    """n tiny "images" (bytes are enough for splitting) in 10 videos, with labels and class names."""
    img, lab = root / "data" / "images", root / "data" / "labels"
    img.mkdir(parents=True)
    lab.mkdir(parents=True)
    for i in range(n):
        (img / f"vid{i % 10}_f{i:03d}.jpg").write_bytes(f"image {i}".encode())
        (lab / f"vid{i % 10}_f{i:03d}.txt").write_text(f"{i % 2} 0.5 0.5 0.2 0.2\n")
    (root / "data" / "classes.txt").write_text("person\nvehicle\n")


# ---------------------------------------------------------------- tracking

def test_written_files_are_tracked_and_never_overwritten_once_changed(proj):
    from runboard import templating
    out = templating.write(project(proj), "split", {"seed": 3}, dry=True)
    assert "+# runboard-template: split 1.0" in out["diff"] and "+templates:" in out["diff"] and not (proj / "scripts").exists()
    templating.write(project(proj), "split", {"seed": 3})
    f = proj / "scripts" / "split.py"
    info = templating.inspect(f)
    assert info["state"] == "pristine" and info["params"]["seed"] == 3 and info["params"]["val"] == 0.1
    m = yaml.safe_load((proj / "runboard.yaml").read_text())
    assert m["templates"] == {"scripts/split.py": "split"} and m["jobs"]["split"]["cmd"] == '"{python}" -u scripts/split.py'
    assert "'seed': 3" in f.read_text()

    templating.write(project(proj), "split", {"seed": 4})  # unchanged: new settings are written
    assert templating.inspect(f)["params"]["seed"] == 4
    assert list(yaml.safe_load((proj / "runboard.yaml").read_text())["jobs"]) == ["split"]
    assert templating.write(project(proj), "split", {"seed": 4})["diff"] == ""

    f.write_text(f.read_text() + "# mine\n")
    assert templating.inspect(f)["state"] == "owned"
    with pytest.raises(Invalid) as e:
        templating.write(project(proj), "split", {"seed": 5})
    assert e.value.code == "owned"
    assert [x["state"] for x in templating.files(project(proj))] == ["owned"]


@pytest.mark.parametrize("path, code", [("../x.py", "bad_path"), ("scripts/x.txt", "bad_path"), ("runs.yaml", "bad_path")])
def test_paths_stay_inside_the_project(proj, path, code):
    from runboard import templating
    with pytest.raises(Invalid) as e:
        templating.write(project(proj), "check", {}, path, dry=True)
    assert e.value.code == code


def test_a_file_runboard_did_not_write_is_left_alone(proj):
    from runboard import templating
    (proj / "scripts").mkdir()
    (proj / "scripts" / "check.py").write_text("print('mine')\n")
    with pytest.raises(Invalid) as e:
        templating.write(project(proj), "check", {}, dry=True)
    assert e.value.code == "not_template"
    templating.write(project(proj), "split", {}, "scripts/other.py")
    with pytest.raises(Invalid) as e:  # another template's file
        templating.write(project(proj), "check", {}, "scripts/other.py", dry=True)
    assert e.value.code == "not_template"


def test_parameters_are_typed(proj):
    from runboard import templating
    p = templating.coerce("evaluate", {"sets": "val=data/val.txt, test=data/test.txt", "sealed": "test", "half": "true"})
    assert p["sets"] == {"val": "data/val.txt", "test": "data/test.txt"} and p["sealed"] == ["test"] and p["half"] is True
    assert templating.coerce("subsets", {"fractions": "0.1, 0.5"})["fractions"] == [0.1, 0.5]
    for bad in ({"seed": "x"}, {"val": "0.9"}):
        with pytest.raises(Invalid):
            templating.coerce("split", bad)
    with pytest.raises(Invalid):
        templating.coerce("evaluate", {"sets": "val"})


def test_under_a_lock_code_changes_are_deviations(proj):
    from runboard import prereg, templating
    templating.write(project(proj), "split", {})
    rec = prereg.lock(project(proj))
    assert list(rec["code"]) == ["scripts/split.py"]
    with pytest.raises(Invalid) as e:
        templating.write(project(proj), "split", {"seed": 9})
    assert e.value.code == "deviation_reason"
    assert templating.write(project(proj), "split", {"seed": 9}, reason="Seed 0 put one video in test")["deviation"]
    st = prereg.status(project(proj))
    assert st["code_ok"] and st["deviations"][-1]["file"] == "scripts/split.py"
    f = proj / "scripts" / "split.py"
    f.write_text(f.read_text() + "# tweak\n")
    st = prereg.status(project(proj))
    assert st["code_ok"] is False and st["code_changed"] == ["scripts/split.py"]
    prereg.record_deviation(project(proj), "Fixed a typo by hand in split.py", "me")
    assert prereg.status(project(proj))["code_ok"] is True


def test_template_api_writes_from_this_computer_only(proj):
    from fastapi.testclient import TestClient

    from runboard import server
    home.save_config({"projects": [], "port": 8000, "lan": True})
    home.register(proj)
    local = TestClient(server.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    key = next(iter(server.rt.projects()))
    d = local.get(f"/api/p/{key}/templates").json()
    assert {c["name"] for c in d["catalog"]} == {"convert", "split", "check", "subsets", "evaluate", "speed"} and d["can_write"]
    r = local.post(f"/api/p/{key}/templates/check", json={"params": {"near": False}, "dry": True})
    assert r.status_code == 200 and "scripts/check.py" in r.json()["diff"]
    code = local.post("/api/devices/pair").json()["code"]
    tablet = TestClient(server.app, base_url="http://192.168.1.10:8000", client=("192.168.1.50", 50000))
    tablet.post("/api/pair", json={"code": code, "name": "t"})
    assert tablet.post(f"/api/p/{key}/templates/check", json={"params": {}}).json()["code"] == "local_only"
    assert tablet.get(f"/api/p/{key}/templates").json()["can_write"] is False


def test_template_from_the_command_line(proj, capsys):
    from runboard.cli import main
    assert main(["template", "subsets", str(proj), "--set", "fractions=0.2,0.4"]) == 0
    assert "wrote scripts/subsets.py" in capsys.readouterr().out
    assert main(["template", "nope", str(proj)]) == 1


# ---------------------------------------------------------------- the scripts

def test_split_keeps_groups_together_and_is_reproducible(proj):
    from runboard import templating
    dataset(proj)
    templating.write(project(proj), "split", {"group": r"^(vid\d+)_", "val": 0.2, "test": 0.2, "seed": 1})
    r = run(proj, "scripts/split.py")
    assert r.returncode == 0, r.stderr
    s = json.loads((proj / "data" / "split.json").read_text())
    assert sum(s["counts"].values()) == 40 and s["groups"] == 10 and s["counts"]["test"] == 8 and s["names"] == ["person", "vehicle"]
    videos = {k: {ln.split("/")[-1].split("_")[0] for ln in (proj / "data" / f"{k}.txt").read_text().split()} for k in s["counts"]}
    assert not (videos["train"] & videos["val"]) and not (videos["train"] & videos["test"]) and not (videos["val"] & videos["test"])
    assert (proj / "data" / "train.txt").read_text().startswith("./images/")
    again = run(proj, "scripts/split.py")
    assert again.returncode == 0 and json.loads((proj / "data" / "split.json").read_text())["sha256"] == s["sha256"]
    d = yaml.safe_load((proj / "data" / "data.yaml").read_text())
    assert d["train"] == "train.txt" and d["names"] == {0: "person", 1: "vehicle"} and "path" not in d


def test_check_finds_leaks_and_broken_labels(proj):
    from runboard import templating
    dataset(proj)
    templating.write(project(proj), "split", {"seed": 2})
    templating.write(project(proj), "check", {"near": False})
    assert run(proj, "scripts/split.py").returncode == 0
    ok = run(proj, "scripts/check.py")
    assert ok.returncode == 0 and "ok" in ok.stdout, ok.stdout + ok.stderr
    train = (proj / "data" / "train.txt").read_text().split()
    val = (proj / "data" / "val.txt").read_text().split()
    (proj / "data" / val[0][2:]).write_bytes((proj / "data" / train[0][2:]).read_bytes())  # the same picture twice
    lab = proj / "data" / train[1][2:].replace("images/", "labels/").replace(".jpg", ".txt")
    lab.write_text("7 0.5 0.5 1.4 0.2\n0 0.5 0.5\n")
    bad = run(proj, "scripts/check.py")
    rep = json.loads((proj / "reports" / "check.json").read_text())
    assert bad.returncode == 1 and rep["summary"]["leaks"] == 1 and rep["summary"]["label_errors"] == 3
    assert sorted(rep["leaks"][0]["splits"]) == ["train", "val"]


def test_check_finds_look_alike_images_across_splits(proj):
    Image = pytest.importorskip("PIL.Image")
    from runboard import templating
    img, lab = proj / "data" / "images", proj / "data" / "labels"
    img.mkdir(parents=True)
    lab.mkdir(parents=True)
    for i in range(6):
        im = Image.new("L", (64, 48))
        im.putdata([(x * (i + 1) * 7 + y * 13 * (i % 3 + 1)) % 256 for y in range(48) for x in range(64)])
        im.save(img / f"a{i}.png")
    Image.open(img / "a0.png").resize((128, 96)).save(img / "a0_big.jpg", quality=90)  # a resized, re-encoded copy
    (proj / "data" / "train.txt").write_text("./images/a0.png\n./images/a1.png\n./images/a2.png\n")
    (proj / "data" / "val.txt").write_text("./images/a0_big.jpg\n./images/a3.png\n")
    (proj / "data" / "data.yaml").write_text("train: train.txt\nval: val.txt\nnames: [x]\n")
    templating.write(project(proj), "check", {"near": True})
    run(proj, "scripts/check.py")
    rep = json.loads((proj / "reports" / "check.json").read_text())
    assert rep["near_checked"] and [sorted(n["files"])[0].endswith("a0.png") for n in rep["near"]] == [True]


def test_subsets_are_nested_and_keep_the_base(proj):
    from runboard import templating
    dataset(proj)
    templating.write(project(proj), "split", {"val": 0.1, "test": 0.1})
    assert run(proj, "scripts/split.py").returncode == 0
    (proj / "data" / "ground.txt").write_text("./images/vid0_f000.jpg\n")
    templating.write(project(proj), "subsets", {"base": "data/ground.txt", "fractions": "0.1,0.25,0.5", "prefix": "air"})
    r = run(proj, "scripts/subsets.py")
    assert r.returncode == 0, r.stderr
    lists = {k: set((proj / "data" / f"air{k}.txt").read_text().split()) for k in (10, 25, 50)}
    assert lists[10] < lists[25] < lists[50] and all("./images/vid0_f000.jpg" in v for v in lists.values())
    y = yaml.safe_load((proj / "data" / "air25.yaml").read_text())
    assert y["train"] == "air25.txt" and y["val"] == "val.txt" and y["names"]


def test_evaluate_writes_what_the_verdicts_read(proj, monkeypatch):
    np = pytest.importorskip("numpy")
    pytest.importorskip("ultralytics")
    from runboard import templating
    from runboard.hypotheses import Evidence, decide
    templating.write(project(proj), "evaluate", {"sets": "val=data/val.txt", "sealed": "val", "replicates": 50})
    spec = importlib.util.spec_from_file_location("evaluate_t", proj / "scripts" / "evaluate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.chdir(proj)
    rng = np.random.default_rng(0)

    def fake(hit):  # 30 images, one label and one prediction each; `hit` of them correct at every IoU
        recs = []
        for i in range(30):
            ok = rng.random() < hit
            recs.append({"tp": np.full((1, 10), ok), "conf": np.array([0.9 if ok else 0.4]), "pred_cls": np.array([0.0]),
                         "target_cls": np.array([0.0]), "im_name": f"im{i}.jpg"})
        return recs
    weights = proj / "w.pt"
    weights.write_bytes(b"w")
    for run_id, hit in (("A", 0.9), ("B", 0.3)):
        recs = fake(hit)
        point = mod.table(recs, {0: "obj"})
        monkeypatch.setattr(mod, "per_image", lambda *a, recs=recs, point=point: (point, recs))
        mod.sealed_use("val", run_id, weights, again=run_id == "B")
        mod.evaluate_set(run_id, "val", proj / "data" / "val.txt", weights, {0: "obj"})
    with pytest.raises(SystemExit):
        mod.sealed_use("val", "A", weights, again=False)
    r = decide("A.val > B.val and A.val@obj > B.val@obj", Evidence(proj, {"sets": ["val"]}), {})
    assert r["verdict"] == "supported" and len(r["parts"]) == 2


def test_convert_coco_and_voc(proj):
    from runboard import templating
    raw = proj / "raw" / "images"
    raw.mkdir(parents=True)
    for n in ("a.jpg", "b.jpg", "c.jpg"):
        (raw / n).write_bytes(b"x")
    (proj / "raw" / "annotations.json").write_text(json.dumps({
        "categories": [{"id": 3, "name": "car"}, {"id": 1, "name": "person"}],
        "images": [{"id": 1, "file_name": "a.jpg", "width": 200, "height": 100},
                   {"id": 2, "file_name": "b.jpg", "width": 100, "height": 100},
                   {"id": 3, "file_name": "gone.jpg", "width": 10, "height": 10}],
        "annotations": [{"image_id": 1, "category_id": 1, "bbox": [50, 25, 100, 50], "iscrowd": 0},
                        {"image_id": 1, "category_id": 3, "bbox": [190, 0, 40, 10], "iscrowd": 0},
                        {"image_id": 1, "category_id": 3, "bbox": [0, 0, 10, 10], "iscrowd": 1}]}))
    templating.write(project(proj), "convert", {"format": "coco"})
    r = run(proj, "scripts/convert.py")
    assert r.returncode == 0, r.stderr
    assert (proj / "data" / "labels" / "a.txt").read_text().splitlines() == [
        "0 0.500000 0.500000 0.500000 0.500000", "1 0.975000 0.050000 0.050000 0.100000"]  # clipped at the edge
    assert (proj / "data" / "labels" / "b.txt").read_text() == "" and (proj / "data" / "images" / "a.jpg").is_file()
    assert (proj / "data" / "classes.txt").read_text() == "person\ncar\n"
    s = json.loads((proj / "data" / "convert.json").read_text())
    assert s["background"] == 1 and s["missing_count"] == 1 and s["boxes"] == {"person": 1, "car": 1}

    voc = proj / "voc"
    voc.mkdir()
    (voc / "a.xml").write_text("<annotation><filename>a.jpg</filename><size><width>200</width><height>100</height></size>"
                               "<object><name>dog</name><difficult>0</difficult><bndbox><xmin>1</xmin><ymin>1</ymin>"
                               "<xmax>100</xmax><ymax>50</ymax></bndbox></object><object><name>cat</name><difficult>1</difficult>"
                               "<bndbox><xmin>1</xmin><ymin>1</ymin><xmax>10</xmax><ymax>10</ymax></bndbox></object></annotation>")
    templating.write(project(proj), "convert", {"format": "voc", "source": "voc", "out": "vocdata", "skip_difficult": True,
                                               "classes": "dog"})
    assert run(proj, "scripts/convert.py").returncode == 0
    assert (proj / "vocdata" / "labels" / "a.txt").read_text() == "0 0.250000 0.250000 0.500000 0.500000\n"
    with pytest.raises(Invalid):
        templating.coerce("convert", {"format": "yolo"})


def test_speed_reports_medians_per_stage(proj):
    pytest.importorskip("numpy")
    from runboard import templating
    templating.write(project(proj), "speed", {"warmup": 2, "iterations": 10})
    spec = importlib.util.spec_from_file_location("speed_t", proj / "scripts" / "speed.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    calls = []

    class Fake:
        def predict(self, img, **kw):
            calls.append((img.shape, kw))
            return [type("R", (), {"speed": {"preprocess": 1.0, "inference": 4.0 + len(calls) % 2, "postprocess": 0.5}})()]
    res = mod.measure(Fake(), 64, 2, 10, False, "cpu")
    assert len(calls) == 12 and calls[0][0] == (64, 64, 3) and calls[0][1]["device"] == "cpu"
    assert res["inference"]["median_ms"] == 4.5 and res["total"]["median_ms"] == 6.0 and res["fps"] == 166.7
