"""Training lists with a growing share of one source: a data-size curve.

Takes the images of PARAMS["add"] (a list, as split.py writes it) and keeps the fractions in PARAMS["fractions"] of
them, nested: the 10 % list is part of the 25 % list, which is part of the 50 % list, so the curve measures the data
and not which images happened to be drawn. Every image of PARAMS["base"] (another list, optional) goes into every
subset whole. With PARAMS["group"], images that give the same key (as in split.py) are kept or dropped together.

Writes, into PARAMS["out"]: <prefix><percent>.txt and <prefix><percent>.yaml (a data.yaml whose train is that list;
val, test and names copied from PARAMS["data"]), and subsets.json with the counts and the SHA-256 of each list.

    python subsets.py
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
from pathlib import Path

PARAMS = {}  # runboard: params


def read(lst: Path) -> list[Path]:
    return [(lst.parent / ln.strip()[2:]) if ln.strip().startswith("./") else Path(ln.strip())
            for ln in lst.read_text(encoding="utf-8").splitlines() if ln.strip()]


def main() -> int:
    import yaml
    out = Path(PARAMS["out"]).resolve()
    add = read(Path(PARAMS["add"]))
    base = read(Path(PARAMS["base"])) if PARAMS.get("base") else []
    rx = re.compile(PARAMS["group"]) if PARAMS.get("group") else None

    def key(f: Path) -> str:
        m = rx.search(f.name) if rx else None
        return (m.group(1) if m.groups() else m.group(0)) if m else f.as_posix()

    groups: dict[str, list[Path]] = {}
    for f in add:
        groups.setdefault(key(f), []).append(f)
    order = sorted(groups)
    random.Random(int(PARAMS["seed"])).shuffle(order)
    data = yaml.safe_load(Path(PARAMS["data"]).read_text(encoding="utf-8")) if PARAMS.get("data") else {}
    data_dir = Path(PARAMS["data"]).resolve().parent if PARAMS.get("data") else out
    out.mkdir(parents=True, exist_ok=True)
    summary = {"params": PARAMS, "base": len(base), "pool": len(add), "subsets": {}}
    for frac in sorted(float(x) for x in PARAMS["fractions"]):
        want, picked = round(len(add) * frac), []
        for k in order:  # the same order for every fraction: smaller subsets are prefixes of larger ones
            if len(picked) >= want:
                break
            picked += groups[k]
        name = f"{PARAMS['prefix']}{round(frac * 100)}"
        lines = []
        for f in sorted(base) + sorted(picked):
            try:
                lines.append(f"./{f.resolve().relative_to(out).as_posix()}")
            except ValueError:  # not under the output folder: keep it absolute
                lines.append(f.resolve().as_posix())
        text = "\n".join(lines) + "\n"
        (out / f"{name}.txt").write_text(text, encoding="utf-8", newline="\n")
        y = {"train": f"{name}.txt"}
        for k in ("val", "test"):  # relative to this yaml, so the folder can move (to Kaggle, say)
            if data.get(k):
                y[k] = Path(os.path.relpath((data_dir / data[k]).resolve(), out)).as_posix()
        if data.get("names"):
            y["names"] = data["names"]
        (out / f"{name}.yaml").write_text(yaml.safe_dump(y, allow_unicode=True, sort_keys=False), encoding="utf-8")
        summary["subsets"][name] = {"fraction": frac, "added": len(picked), "train": len(lines),
                                    "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        print(f"{name}: {len(base)} + {len(picked)} = {len(lines)} images")
    (out / "subsets.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
