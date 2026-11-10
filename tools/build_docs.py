"""The documentation site's sources, from the files the repository already has (nothing is written twice):
README.md becomes the home page, README.tr.md the Turkish one, docs/*.md and the images keep their names, and
SECURITY, ROADMAP, CHANGELOG and RELEASING become pages. Links written for GitHub (full github.com and
raw.githubusercontent.com addresses, ../ROADMAP.md) become links inside the site.

    python tools/build_docs.py          # writes site_src/ (mkdocs.yml reads it); then: mkdocs build --strict
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site_src"
REPO = "alperentoker/runboard-ml"
PAGES = {  # a file of the repository -> its page on the site
    "README.md": "index.md", "README.tr.md": "tr.md", "SECURITY.md": "security.md", "ROADMAP.md": "roadmap.md",
    "CHANGELOG.md": "changelog.md", "RELEASING.md": "releasing.md",
    **{f"docs/{p.name}": p.name for p in (ROOT / "docs").glob("*.md")},
}


def page_of(path: str) -> str | None:
    path = path.lstrip("./")
    return PAGES.get(path) or PAGES.get(f"docs/{path}")


def rewrite(text: str, source: str) -> str:
    def blob(m):  # https://github.com/<repo>/blob/main/<path>#anchor
        target = page_of(m.group(1))
        return f"]({target}{m.group(2) or ''})" if target else m.group(0)

    text = re.sub(rf"\]\(https://github\.com/{REPO}/blob/main/([^)#\s]+)(#[^)\s]*)?\)", blob, text)
    text = re.sub(rf"\]\(https://raw\.githubusercontent\.com/{REPO}/main/docs/(images/[^)\s]+)\)", r"](\1)", text)

    def relative(m):  # ../ROADMAP.md, docs/design-v2.md: relative to the source file, as GitHub reads them
        link, anchor = m.group(1), m.group(2) or ""
        if "://" in link:
            return m.group(0)
        base = Path(source).parent
        resolved = (base / link).as_posix()
        parts = []
        for p in resolved.split("/"):
            if p == "..":
                parts = parts[:-1]
            elif p not in ("", "."):
                parts.append(p)
        target = page_of("/".join(parts))
        return f"]({target}{anchor})" if target else m.group(0)

    return re.sub(r"\]\(([^)#\s]+\.md)(#[^)\s]*)?\)", relative, text)


def main() -> int:
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir()
    shutil.copytree(ROOT / "docs" / "images", OUT / "images")
    for source, target in PAGES.items():
        (OUT / target).write_text(rewrite((ROOT / source).read_text(encoding="utf-8"), source), encoding="utf-8")
    print(f"wrote {OUT} ({len(PAGES)} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
