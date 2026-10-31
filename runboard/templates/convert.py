"""Convert COCO or Pascal VOC box annotations into a YOLO dataset.

PARAMS["format"] is "coco" (PARAMS["source"] is the annotations .json) or "voc" (PARAMS["source"] is the folder of
.xml files). Images are taken from PARAMS["images"] and placed in <out>/images/ (hard links when the disk allows,
copies otherwise), labels written to <out>/labels/ with the same names: one "class x y w h" line per box, relative to
the image size. PARAMS["classes"] (comma-separated) keeps only those classes, in that order; empty keeps them all.
Crowd regions (COCO iscrowd) and, with PARAMS["skip_difficult"], VOC "difficult" objects are left out; images without
boxes stay as background.

Writes <out>/classes.txt (one name per line, which split.py reads) and <out>/convert.json with the counts.

    python convert.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PARAMS = {}  # runboard: params


def yolo_line(cls: int, x0: float, y0: float, x1: float, y1: float, w: float, h: float) -> str | None:
    x0, x1 = max(0.0, min(x0, w)), max(0.0, min(x1, w))
    y0, y1 = max(0.0, min(y0, h)), max(0.0, min(y1, h))
    if x1 <= x0 or y1 <= y0:
        return None
    return f"{cls} {(x0 + x1) / 2 / w:.6f} {(y0 + y1) / 2 / h:.6f} {(x1 - x0) / w:.6f} {(y1 - y0) / h:.6f}"


def read_coco(src: Path) -> tuple[list[str], dict[str, tuple[float, float, list]]]:
    d = json.loads(src.read_text(encoding="utf-8"))
    names = {c["id"]: c["name"] for c in d["categories"]}
    images = {im["id"]: (im["file_name"], float(im["width"]), float(im["height"]), []) for im in d["images"]}
    for a in d.get("annotations", []):
        if a.get("iscrowd"):
            continue
        x, y, bw, bh = a["bbox"]
        images[a["image_id"]][3].append((names[a["category_id"]], x, y, x + bw, y + bh))
    return [names[k] for k in sorted(names)], {f: (w, h, boxes) for f, w, h, boxes in images.values()}


def read_voc(src: Path) -> tuple[list[str], dict[str, tuple[float, float, list]]]:
    seen, out = [], {}
    for f in sorted(src.glob("*.xml")):
        root = ET.parse(f).getroot()
        size = root.find("size")
        w, h = float(size.findtext("width")), float(size.findtext("height"))
        boxes = []
        for o in root.iter("object"):
            if PARAMS.get("skip_difficult") and o.findtext("difficult", "0").strip() == "1":
                continue
            name, b = o.findtext("name").strip(), o.find("bndbox")
            if name not in seen:
                seen.append(name)
            # VOC counts pixels from 1 and includes the last one
            boxes.append((name, float(b.findtext("xmin")) - 1, float(b.findtext("ymin")) - 1,
                          float(b.findtext("xmax")), float(b.findtext("ymax"))))
        out[root.findtext("filename") or f.with_suffix(".jpg").name] = (w, h, boxes)
    return sorted(seen), out


def place(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def main() -> int:
    fmt, src, images, out = PARAMS["format"], Path(PARAMS["source"]), Path(PARAMS["images"]), Path(PARAMS["out"])
    if fmt not in ("coco", "voc"):
        sys.exit(f"format must be coco or voc, not {fmt}")
    found, items = read_coco(src) if fmt == "coco" else read_voc(src)
    keep = [c.strip() for c in str(PARAMS.get("classes") or "").split(",") if c.strip()] or found
    index = {n: i for i, n in enumerate(keep)}
    counts = {n: 0 for n in keep}
    missing, dropped, background = [], 0, 0
    for name, (w, h, boxes) in sorted(items.items()):
        img = images / name
        if not img.is_file():
            missing.append(name)
            continue
        lines = []
        for cls, x0, y0, x1, y1 in boxes:
            line = yolo_line(index[cls], x0, y0, x1, y1, w, h) if cls in index else None
            if line is None:
                dropped += 1
                continue
            lines.append(line)
            counts[cls] += 1
        background += not lines
        place(img, out / "images" / name)
        lab = (out / "labels" / name).with_suffix(".txt")
        lab.parent.mkdir(parents=True, exist_ok=True)
        lab.write_text("".join(ln + "\n" for ln in lines), encoding="utf-8", newline="\n")
    (out / "classes.txt").write_text("".join(n + "\n" for n in keep), encoding="utf-8", newline="\n")
    summary = {"params": PARAMS, "images": len(items) - len(missing), "background": background, "boxes": counts,
               "dropped_boxes": dropped, "missing_images": missing[:50], "missing_count": len(missing)}
    (out / "convert.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{summary['images']} images, {sum(counts.values())} boxes in {len(keep)} classes, {dropped} left out, "
          f"{len(missing)} images missing")
    return 1 if missing and len(missing) == len(items) else 0


if __name__ == "__main__":
    raise SystemExit(main())
