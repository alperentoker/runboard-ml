"""Code templates: ordinary Python files written into a project, tracked so runboard never overwrites your changes
(docs/design-v2.md, section 4).

A generated file starts with three comment lines: the template and its version, the parameters, and the SHA-256 of
the text below them. While the text still matches, the file is *pristine*: a newer template version is offered as a
diff. Once you change it, it is *owned*: runboard does not write it again and only shows a newer template's diff.
Generated files are listed under `templates:` in runboard.yaml (path: template); a template that is meant to run as a
job adds one under `jobs:`. Under a lock, a tracked file changes only as a recorded deviation.
"""
from __future__ import annotations

import hashlib
import json
import pprint
import re
from pathlib import Path

from .errors import Invalid

HERE = Path(__file__).parent / "templates"
MARK = "PARAMS = {}  # runboard: params"
HEAD = re.compile(r"# runboard-template: (?P<name>[\w-]+) (?P<version>[\d.]+)[^\n]*\n# params: (?P<params>.*)\n"
                  r"# sha256: (?P<sha>[0-9a-f]{64})\n")

TEMPLATES = {
    "convert": {
        "version": "1.0", "file": "convert.py", "target": "scripts/convert.py",
        "title": {"en": "Convert COCO / VOC to YOLO", "tr": "COCO / VOC'u YOLO'ya dönüştür"},
        "desc": {"en": "Boxes from a COCO .json or a folder of VOC .xml files, as YOLO images/ and labels/ with classes.txt.",
                 "tr": "COCO .json'daki ya da VOC .xml klasöründeki kutular; YOLO images/ ve labels/ klasörleri ve classes.txt."},
        "params": {"format": {"choices": ["coco", "voc"], "default": "coco"},
                   "source": {"text": True, "default": "raw/annotations.json"}, "images": {"text": True, "default": "raw/images"},
                   "out": {"text": True, "default": "data"}, "classes": {"text": True, "default": ""},
                   "skip_difficult": {"bool": True, "default": False}},
        "job": {"title": {"en": "Convert the annotations", "tr": "Etiketleri dönüştür"}},
    },
    "split": {
        "version": "1.0", "file": "split.py", "target": "scripts/split.py",
        "title": {"en": "Split train / val / test", "tr": "Eğitim / doğrulama / test bölme"},
        "desc": {"en": "Reproducible lists from a YOLO image folder; groups (video, scene) stay in one split.",
                 "tr": "YOLO görüntü klasöründen tekrarlanabilir listeler; gruplar (video, sahne) tek bir kümede kalır."},
        "params": {"images": {"text": True, "default": "data/images"}, "out": {"text": True, "default": "data"},
                   "val": {"float": [0, 0.5], "default": 0.1}, "test": {"float": [0, 0.5], "default": 0.1},
                   "seed": {"int": [0, 2**31 - 1], "default": 0}, "group": {"text": True, "default": ""},
                   "names": {"text": True, "default": ""}},
        "job": {"title": {"en": "Split the dataset", "tr": "Veri setini böl"}},
    },
    "check": {
        "version": "1.0", "file": "check.py", "target": "scripts/check.py",
        "title": {"en": "Check labels and leaks", "tr": "Etiket ve sızıntı kontrolü"},
        "desc": {"en": "Broken labels, the same image in two splits, and look-alike images across splits (Pillow).",
                 "tr": "Bozuk etiketler, iki kümede aynı görüntü ve kümeler arası benzer görüntüler (Pillow)."},
        "params": {"data": {"text": True, "default": "data/data.yaml"}, "report": {"text": True, "default": "reports/check.json"},
                   "near": {"bool": True, "default": True}, "near_bits": {"int": [0, 16], "default": 4}},
        "job": {"title": {"en": "Check the dataset", "tr": "Veri setini kontrol et"}},
    },
    "subsets": {
        "version": "1.0", "file": "subsets.py", "target": "scripts/subsets.py",
        "title": {"en": "Data-size subsets", "tr": "Veri miktarı alt kümeleri"},
        "desc": {"en": "Nested training lists with 10 / 25 / 50 % of one source added to another, for a data-size curve.",
                 "tr": "Bir kaynağın %10 / 25 / 50'si eklenmiş iç içe eğitim listeleri; veri miktarı eğrisi için."},
        "params": {"add": {"text": True, "default": "data/train.txt"}, "base": {"text": True, "default": ""},
                   "fractions": {"floats": [0, 1], "default": [0.1, 0.25, 0.5]}, "seed": {"int": [0, 2**31 - 1], "default": 0},
                   "group": {"text": True, "default": ""}, "data": {"text": True, "default": "data/data.yaml"},
                   "out": {"text": True, "default": "data"}, "prefix": {"text": True, "default": "train_"}},
        "job": {"title": {"en": "Build the subsets", "tr": "Alt kümeleri oluştur"}},
    },
    "evaluate": {
        "version": "1.0", "file": "evaluate.py", "target": "scripts/evaluate.py",
        "title": {"en": "Evaluate for the hypotheses (YOLO)", "tr": "Hipotezler için değerlendirme (YOLO)"},
        "desc": {"en": "Each evaluation set with bootstrap replicates every run shares; writes what the verdicts read.",
                 "tr": "Her değerlendirme kümesi, bütün koşuların paylaştığı bootstrap turlarıyla; kararların okuduğu dosyaları yazar."},
        "params": {"data": {"text": True, "default": "data/data.yaml"}, "sets": {"map": True, "default": {"val": "data/val.txt"}},
                   "sealed": {"list": True, "default": []}, "out": {"text": True, "default": "eval"},
                   "replicates": {"int": [10, 10000], "default": 200}, "seed": {"int": [0, 2**31 - 1], "default": 0},
                   "imgsz": {"int": [32, 4096], "default": 640}, "batch": {"int": [1, 1024], "default": 16},
                   "conf": {"float": [0, 1], "default": 0.001}, "iou": {"float": [0, 1], "default": 0.7},
                   "half": {"bool": True, "default": False}},
        "job": {"title": {"en": "Evaluate for the hypotheses", "tr": "Hipotezler için değerlendir"}, "per_run": True,
                "args": '--run {id} --weights "{out}/weights/best.pt"'},
    },
    "speed": {
        "version": "1.0", "file": "speed.py", "target": "scripts/speed.py",
        "title": {"en": "Inference speed (YOLO)", "tr": "Çıkarım hızı (YOLO)"},
        "desc": {"en": "Milliseconds per image, batch 1: preprocessing, inference, postprocessing; median, p90 and FPS.",
                 "tr": "Görüntü başına milisaniye, batch 1: ön işleme, çıkarım, son işleme; medyan, p90 ve FPS."},
        "params": {"imgsz": {"int": [32, 4096], "default": 640}, "half": {"bool": True, "default": False},
                   "device": {"text": True, "default": ""}, "warmup": {"int": [0, 1000], "default": 10},
                   "iterations": {"int": [5, 100000], "default": 100}, "out": {"text": True, "default": "reports/speed"}},
        "job": {"title": {"en": "Measure the speed", "tr": "Hızı ölç"}, "per_run": True,
                "args": '--run {id} --weights "{out}/weights/best.pt"'},
    },
}


def catalog(lang: str = "en") -> list[dict]:
    from .project import text
    return [{"name": n, "version": t["version"], "target": t["target"], "title": text(t["title"], lang),
             "desc": text(t["desc"], lang), "params": t["params"]} for n, t in TEMPLATES.items()]


def coerce(name: str, raw: dict) -> dict:
    """Form values (strings) to the parameters' types, defaults for what is missing."""
    out = {}
    for k, rule in TEMPLATES[name]["params"].items():
        v = raw.get(k, rule["default"])
        try:
            if "int" in rule or "float" in rule:
                kind = int if "int" in rule else float
                v = kind(str(v).strip())
                lo, hi = rule.get("int") or rule["float"]
                if not lo <= v <= hi:
                    raise Invalid("range", field=k, lo=lo, hi=hi)
            elif "floats" in rule:
                v = [float(x) for x in (v if isinstance(v, list) else str(v).replace(";", ",").split(",")) if str(x).strip()]
                lo, hi = rule["floats"]
                if not v or not all(lo < x <= hi for x in v):
                    raise Invalid("range", field=k, lo=lo, hi=hi)
            elif "list" in rule:
                v = [str(x).strip() for x in (v if isinstance(v, list) else str(v).split(",")) if str(x).strip()]
            elif "map" in rule:  # "val=data/val.txt, test=data/test.txt"
                if not isinstance(v, dict):
                    pairs = [p.split("=", 1) for p in str(v).split(",") if p.strip()]
                    if not pairs or any(len(p) != 2 or not p[0].strip() or not p[1].strip() for p in pairs):
                        raise Invalid("template_param", field=k, shape="name=path, name=path")
                    v = {a.strip(): b.strip() for a, b in pairs}
            elif "choices" in rule:
                if str(v) not in rule["choices"]:
                    raise Invalid("one_of", field=k, choices=rule["choices"])
                v = str(v)
            elif "bool" in rule:
                v = v if isinstance(v, bool) else str(v).lower() in ("true", "yes", "1", "on")
            else:
                v = str(v)
        except (TypeError, ValueError):
            raise Invalid("number", field=k) from None
        out[k] = v
    return out


def body(name: str, params: dict) -> str:
    src = (HERE / TEMPLATES[name]["file"]).read_text(encoding="utf-8").replace("\r\n", "\n")
    if src.count(MARK) != 1:
        raise RuntimeError(f"template {name} has no parameter line")
    return src.replace(MARK, "PARAMS = " + pprint.pformat(params, width=110, sort_dicts=False))


def sha(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def render(name: str, params: dict) -> str:
    t = TEMPLATES[name]
    b = body(name, params)
    return (f"# runboard-template: {name} {t['version']} (written by runboard; once you change it, runboard leaves it to you)\n"
            f"# params: {json.dumps(params, ensure_ascii=False)}\n# sha256: {sha(b)}\n{b}")


def inspect(path: Path) -> dict | None:
    """None for a file runboard did not write; otherwise its template, parameters and state."""
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    m = HEAD.match(text)
    if not m:
        return None
    name = m["name"]
    state = "pristine" if sha(text[m.end():]) == m["sha"] else "owned"
    latest = TEMPLATES.get(name, {}).get("version")
    try:
        params = json.loads(m["params"])
    except ValueError:
        params = {}
    return {"template": name, "version": m["version"], "params": params, "state": state, "latest": latest,
            "update": bool(latest) and _v(latest) > _v(m["version"])}


def _v(s: str) -> tuple:
    return tuple(int(x) for x in s.split("."))


# ---------------------------------------------------------------- in a project

def tracked(project) -> dict[str, str]:
    return {str(k): str(v) for k, v in (project.m.get("templates") or {}).items()}


def files(project) -> list[dict]:
    out = []
    for path, name in tracked(project).items():
        info = inspect(project.root / path)
        out.append({"path": path, "template": name, **(info or {"state": "missing" if not (project.root / path).exists()
                                                                 else "untracked"})})
    return out


def _manifest_with(project, path: str, name: str) -> str:
    """runboard.yaml with the file listed under templates: and, the first time, the template's job."""
    from .runsfile import RunsFile, scalar
    f = RunsFile(project.root / "runboard.yaml", "templates")
    text = f.text
    if isinstance(project.m.get("templates"), dict):
        text = f.set_section("templates", {path: name})
    elif path not in (project.m.get("templates") or {}):
        text = text.rstrip("\n") + f"\n\ntemplates:                # code written from runboard's templates (path: template)\n  {scalar(path)}: {name}\n"
    job = TEMPLATES[name].get("job")
    jobs = project.m.get("jobs")
    if job and name not in (jobs or {}):
        cmd = f'"{{python}}" -u {path}' + (f" {job['args']}" if job.get("args") else "")
        value = {"title": job["title"], "cmd": cmd, **({"per_run": True} if job.get("per_run") else {})}
        if isinstance(jobs, dict) and jobs:
            step = RunsFile(project.root / "runboard.yaml", "jobs")
            step.text = text
            text = step.set_section("jobs", {name: value})
        elif not jobs:
            text = text.rstrip("\n") + f"\n\njobs:\n  {name}: {scalar(value)}\n"
    return text


def write(project, name: str, raw: dict, path: str | None = None, dry: bool = False, who: str = "",
          reason: str = "") -> dict:
    """Creates a file from a template, or updates a pristine one (same template, new parameters or version)."""
    import difflib

    from .planfile import check_manifest, parse
    if name not in TEMPLATES:
        raise Invalid("unknown_template", name=name)
    params = coerce(name, raw or {})
    path = (path or TEMPLATES[name]["target"]).strip().replace("\\", "/")
    f = (project.root / path).resolve()
    if not path.endswith(".py") or project.root not in f.parents:
        raise Invalid("bad_path", path=path)
    path = f.relative_to(project.root).as_posix()
    cur = inspect(f)
    if f.exists() and (cur is None or cur["template"] != name):
        raise Invalid("not_template", file=path)
    if cur and cur["state"] == "owned":
        raise Invalid("owned", file=path)
    deviation = project.v2 and project.locked and project._deviation(reason)
    old = f.read_text(encoding="utf-8").replace("\r\n", "\n") if f.exists() else ""
    new = render(name, params)
    manifest = _manifest_with(project, path, name)
    check_manifest(parse(manifest, "runboard.yaml"), project.m, project.root, project.locked)
    mf_old = (project.root / "runboard.yaml").read_text(encoding="utf-8").replace("\r\n", "\n")
    diff = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), path, path, n=2)) + \
        "".join(difflib.unified_diff(mf_old.splitlines(True), manifest.splitlines(True), "runboard.yaml", "runboard.yaml", n=1))
    if dry or old == new and manifest == mf_old:
        return {"diff": diff if old != new or manifest != mf_old else "", "path": path, "deviation": bool(deviation)}
    project.backup(f)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(new, encoding="utf-8", newline="\n")
    if manifest != mf_old:
        from .runsfile import RunsFile
        mf = RunsFile(project.root / "runboard.yaml")
        project.backup(mf.path)
        mf.save(manifest, None)
    if deviation:
        from .prereg import add_deviation
        add_deviation(project, path, reason, diff, who)
    return {"diff": diff, "path": path, "deviation": bool(deviation)}
