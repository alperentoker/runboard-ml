"""Check a YOLO dataset before training on it: broken labels, and images that leak between train, val and test.

Reads the lists of PARAMS["data"] (a data.yaml, as split.py writes it) and checks:
  labels      every line is a class and a box (or a polygon) with coordinates between 0 and 1, the class is one of
              the names, boxes are not empty; images without a label file count as background
  duplicates  the same file (SHA-256 of its bytes) in two splits is a leak; twice in one split, a duplicate
  near        with Pillow installed and PARAMS["near"], images that look the same (a 64-bit difference hash at most
              PARAMS["near_bits"] bits apart) in two different splits: resized or re-encoded copies, video neighbours

Writes PARAMS["report"] (JSON) and exits with 1 when there are label errors or leaks, so it can stop a pipeline.

    python check.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from itertools import combinations
from pathlib import Path

PARAMS = {}  # runboard: params

SPLITS = ("train", "val", "test")
SHOW = 50  # examples kept per problem in the report


def read_lists(data: Path) -> tuple[dict[str, list[Path]], list[str]]:
    import yaml
    d = yaml.safe_load(data.read_text(encoding="utf-8")) or {}
    base = data.parent if not d.get("path") else (data.parent / d["path"]).resolve()
    names = d.get("names") or []
    names = [names[k] for k in sorted(names)] if isinstance(names, dict) else list(names)
    out = {}
    for s in SPLITS:
        if not d.get(s):
            continue
        src = base / d[s]
        if src.is_dir():
            out[s] = sorted(f for f in src.rglob("*") if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"})
        else:
            lines = [ln.strip() for ln in src.read_text(encoding="utf-8").splitlines() if ln.strip()]
            out[s] = [(src.parent / ln[2:]) if ln.startswith("./") else (base / ln) for ln in lines]
    return out, names


def label_of(img: Path) -> Path:
    parts = list(img.parts)
    if "images" not in parts:
        return img.with_suffix(".txt")
    i = len(parts) - 1 - parts[::-1].index("images")
    return Path(*parts[:i], "labels", *parts[i + 1:]).with_suffix(".txt")


def check_label(f: Path, nc: int) -> list[str]:
    errors = []
    for n, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        v = ln.split()
        if not v:
            continue
        try:
            c, xs = float(v[0]), [float(x) for x in v[1:]]
        except ValueError:
            errors.append(f"{f}:{n}: not numbers")
            continue
        if c != int(c) or not 0 <= c < max(nc, 1):
            errors.append(f"{f}:{n}: class {v[0]} is not one of the {nc} names")
        if len(xs) == 4:
            if not all(0 <= x <= 1 for x in xs) or xs[2] <= 0 or xs[3] <= 0:
                errors.append(f"{f}:{n}: box outside 0..1 or empty")
        elif len(xs) >= 6 and len(xs) % 2 == 0:
            if not all(0 <= x <= 1 for x in xs):
                errors.append(f"{f}:{n}: polygon outside 0..1")
        else:
            errors.append(f"{f}:{n}: {len(xs)} numbers after the class (4 for a box, an even 6+ for a polygon)")
    return errors


def dhash(f: Path) -> int | None:
    from PIL import Image
    try:
        with Image.open(f) as im:
            px = list(im.convert("L").resize((9, 8)).getdata())
    except OSError:
        return None
    return sum(1 << i for i, (a, b) in enumerate((px[r * 9 + c], px[r * 9 + c + 1]) for r in range(8) for c in range(8)) if a > b)


def main() -> int:
    lists, names = read_lists(Path(PARAMS["data"]))
    report = {"counts": {s: len(v) for s, v in lists.items()}, "missing_images": [], "label_errors": [],
              "background": 0, "leaks": [], "duplicates": [], "near": [], "near_checked": False}
    by_hash: dict[str, list[tuple[str, Path]]] = {}
    for s, files in lists.items():
        for f in files:
            if not f.is_file():
                report["missing_images"].append(str(f))
                continue
            by_hash.setdefault(hashlib.sha256(f.read_bytes()).hexdigest(), []).append((s, f))
            lab = label_of(f)
            if lab.is_file():
                report["label_errors"] += check_label(lab, len(names))
            else:
                report["background"] += 1
    for h, seen in by_hash.items():
        if len(seen) > 1:
            where = sorted({s for s, _ in seen})
            entry = {"splits": where, "files": [str(f) for _, f in seen]}
            (report["leaks"] if len(where) > 1 else report["duplicates"]).append(entry)

    if PARAMS.get("near"):
        try:
            import PIL  # noqa: F401
        except ImportError:
            print("Pillow is not installed: near-duplicates are not checked")
        else:
            report["near_checked"] = True
            hashes = [(s, f, dhash(f)) for s, files in lists.items() for f in files if f.is_file()]
            buckets: dict[tuple[int, int], list[int]] = {}  # four 16-bit bands: two close hashes share one
            for i, (_, _, h) in enumerate(hashes):
                if h is not None:
                    for b in range(4):
                        buckets.setdefault((b, (h >> (16 * b)) & 0xFFFF), []).append(i)
            pairs = set()
            for idx in buckets.values():
                for i, j in combinations(idx, 2):
                    (si, fi, hi), (sj, fj, hj) = hashes[i], hashes[j]
                    if si != sj and (i, j) not in pairs and bin(hi ^ hj).count("1") <= int(PARAMS["near_bits"]):
                        pairs.add((i, j))
                        report["near"].append({"splits": [si, sj], "files": [str(fi), str(fj)], "bits": bin(hi ^ hj).count("1")})

    out = Path(PARAMS["report"])
    out.parent.mkdir(parents=True, exist_ok=True)
    full = {k: (len(v) if isinstance(v, list) else v) for k, v in report.items()}
    out.write_text(json.dumps({"summary": full, **{k: v[:SHOW] if isinstance(v, list) else v for k, v in report.items()}},
                              indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(", ".join(f"{k} {v}" for k, v in report["counts"].items()) + f", background {report['background']}")
    for k in ("missing_images", "label_errors", "leaks", "duplicates", "near"):
        if report[k]:
            print(f"{k.replace('_', ' ')}: {len(report[k])}  e.g. {report[k][0]}")
    bad = report["label_errors"] or report["leaks"] or report["missing_images"]
    print("FAILED: see " + str(out) if bad else "ok")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
