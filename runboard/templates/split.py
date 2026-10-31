"""Split a YOLO dataset into train, val and test lists, the same way every time.

Images under PARAMS["images"] (jpg, jpeg, png, bmp, tif, tiff, webp); their labels follow the YOLO convention, the
same path with /images/ replaced by /labels/ and the extension by .txt. With PARAMS["group"], a regular expression
on the file name, images that give the same key (its first group, or the whole match) stay in one split, so frames of
one video or shots of one scene cannot leak from training into evaluation.

The test list is the held-out set: keep it out of the cloud (runboard's data.forbid) and evaluate on it once per final
model. Writes, into PARAMS["out"] (a folder that contains the images folder):
  train.txt, val.txt, test.txt   one image per line, relative to the list ("./images/...")
  data.yaml                      for Ultralytics: the three lists and the class names
  split.json                     the settings, the counts and the SHA-256 of each list

    python split.py
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from pathlib import Path

PARAMS = {}  # runboard: params

EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def label_of(img: Path) -> Path:
    parts = list(img.parts)
    i = len(parts) - 1 - parts[::-1].index("images")
    return Path(*parts[:i], "labels", *parts[i + 1:]).with_suffix(".txt")


def class_names(images: Path, files: list[Path]) -> list[str]:
    if PARAMS.get("names"):
        return [n.strip() for n in str(PARAMS["names"]).split(",") if n.strip()]
    for f in (images.parent / "classes.txt", images / "classes.txt"):
        if f.is_file():
            return [ln.strip() for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
    top = -1
    for img in files:
        lab = label_of(img)
        if lab.is_file():
            for ln in lab.read_text(encoding="utf-8").splitlines():
                if ln.split():
                    top = max(top, int(float(ln.split()[0])))
    return [str(i) for i in range(top + 1)]


def main() -> int:
    images, out = Path(PARAMS["images"]).resolve(), Path(PARAMS["out"]).resolve()
    if images.name != "images" and "images" not in images.parts:
        sys.exit(f"{images}: YOLO finds labels by replacing /images/ with /labels/, so the folder must be named images")
    if out != images and out not in images.parents:
        sys.exit(f"{out} must contain {images}: the lists name images relative to themselves")
    files = sorted(f for f in images.rglob("*") if f.suffix.lower() in EXT)
    if not files:
        sys.exit(f"no images under {images}")
    rx = re.compile(PARAMS["group"]) if PARAMS.get("group") else None

    def key(f: Path) -> str:
        if not rx:
            return f.relative_to(images).as_posix()
        m = rx.search(f.name)
        return (m.group(1) if m.groups() else m.group(0)) if m else f.relative_to(images).as_posix()

    groups: dict[str, list[Path]] = {}
    for f in files:
        groups.setdefault(key(f), []).append(f)
    keys = sorted(groups)
    random.Random(int(PARAMS["seed"])).shuffle(keys)
    want = {"test": round(len(files) * float(PARAMS["test"])), "val": round(len(files) * float(PARAMS["val"]))}
    split: dict[str, list[Path]] = {"train": [], "val": [], "test": []}
    for k in keys:  # whole groups, test first, then val, the rest to train
        to = "test" if len(split["test"]) < want["test"] else "val" if len(split["val"]) < want["val"] else "train"
        split[to] += groups[k]

    out.mkdir(parents=True, exist_ok=True)
    digest = {}
    for name, fs in split.items():
        text = "".join(f"./{f.relative_to(out).as_posix()}\n" for f in sorted(fs))
        (out / f"{name}.txt").write_text(text, encoding="utf-8", newline="\n")
        digest[name] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    names = class_names(images, files)
    (out / "data.yaml").write_text("# written by split.py\ntrain: train.txt\nval: val.txt\ntest: test.txt\nnames:\n"
                                   + "".join(f"  {i}: {json.dumps(n, ensure_ascii=False)}\n" for i, n in enumerate(names)),
                                   encoding="utf-8", newline="\n")
    summary = {"params": PARAMS, "images": len(files), "groups": len(groups),
               "counts": {k: len(v) for k, v in split.items()},
               "unlabelled": sum(1 for f in files if not label_of(f).is_file()), "sha256": digest, "names": names}
    (out / "split.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(", ".join(f"{k} {v}" for k, v in summary["counts"].items()) + f" ({len(groups)} groups, seed {PARAMS['seed']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
