"""Edits a runs file the way a person would: only the lines of the run being changed are touched.

PyYAML reports where every node starts and ends in the text, so a run's value is replaced in place (in the style it
was written in, flow `{…}` or block), a new run is inserted after the last one, and a removed run takes its own
lines with it. Comments, blank lines, key order and the line endings of everything else stay byte for byte.
Every edit is parsed back and compared with what was asked; if they differ, nothing is written.
"""
from __future__ import annotations

import difflib
import hashlib
import re
from pathlib import Path

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

from .errors import Conflict, Invalid  # noqa: F401 (Conflict is re-exported)

RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,40}")


def version_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def flow(values: dict) -> str:
    return yaml.safe_dump(values, default_flow_style=True, sort_keys=False, allow_unicode=True, width=10**6).strip()


def scalar(value) -> str:
    """One value as YAML writes it inline: 100, 0.01, true, "8.4.191", [a, b] or {a: 1}."""
    return yaml.safe_dump([value], default_flow_style=True, allow_unicode=True, width=10**6).strip()[1:-1]


def _end(node) -> int:
    """Where a node's own text ends: block collections end at their last value, not at the next key."""
    if isinstance(node, (MappingNode, SequenceNode)) and not node.flow_style and node.value:
        last = node.value[-1]
        return _end(last[1] if isinstance(node, MappingNode) else last)
    return node.end_mark.index


class RunsFile:
    def __init__(self, path: Path, section: str = "runs"):
        self.path, self.section = Path(path), section
        raw = self.path.read_bytes()
        self.version = version_of(raw)
        self.nl = "\r\n" if b"\r\n" in raw else "\n"
        self.text = raw.decode("utf-8").replace("\r\n", "\n")

    # ------------------------------------------------------------ reading

    def _entries(self, text: str | None = None) -> tuple[MappingNode | None, list]:
        root = yaml.compose(self.text if text is None else text)
        if not isinstance(root, MappingNode):
            raise Invalid("file_mapping", file=self.path.name)
        for k, v in root.value:
            if k.value == self.section:
                return v, (v.value if isinstance(v, MappingNode) else [])
        raise Invalid("section_missing", section=self.section, file=self.path.name)

    def _find(self, run_id: str):
        _, entries = self._entries()
        return next(((k, v) for k, v in entries if k.value == run_id), None)

    def runs(self) -> dict:
        return (yaml.safe_load(self.text) or {}).get(self.section) or {}

    # ------------------------------------------------------------ editing (returns the new text; save() writes it)

    def set_run(self, run_id: str, values: dict) -> str:
        found = self._find(run_id)
        if not found:
            raise Invalid("unknown_run", run=run_id)
        _, v = found
        start, end = v.start_mark.index, _end(v)
        if isinstance(v, MappingNode) and not v.flow_style and values:
            indent = " " * v.start_mark.column
            block = yaml.safe_dump(values, default_flow_style=False, sort_keys=False, allow_unicode=True, width=10**6)
            new = block.rstrip("\n").replace("\n", "\n" + indent)
        else:
            new = flow(values)
            if isinstance(v, ScalarNode) and v.value == "" and start == end:  # `R4:` with nothing after it
                new = " " + new
        return self.text[:start] + new + self.text[end:]

    def add_run(self, run_id: str, values: dict, comment: str = "") -> str:
        if not RUN_ID.fullmatch(run_id):
            raise Invalid("bad_run_id", run=run_id)
        mapping, entries = self._entries()
        if any(k.value == run_id for k, _ in entries):
            raise Invalid("exists", run=run_id)
        comment = re.sub(r"[\r\n#]", " ", comment).strip()
        line = f"{run_id}: {flow(values)}" + (f"  # {comment}" if comment else "")
        if not entries:  # `runs:`, `runs: {}` or `runs: null`
            s, e = mapping.start_mark.index, mapping.end_mark.index
            return self.text[:s].rstrip(" ") + "\n  " + line + self.text[e:]
        k_last, v_last = entries[-1]
        eol = self.text.find("\n", _end(v_last))
        eol = len(self.text) if eol < 0 else eol
        return self.text[:eol] + "\n" + " " * k_last.start_mark.column + line + self.text[eol:]

    def remove_run(self, run_id: str) -> str:
        found = self._find(run_id)
        if not found:
            raise Invalid("unknown_run", run=run_id)
        k, v = found
        if k.start_mark.column == 0 or self.text[self.text.rfind("\n", 0, k.start_mark.index) + 1:k.start_mark.index].strip():
            raise Invalid("block_only")
        start = self.text.rfind("\n", 0, k.start_mark.index) + 1
        eol = self.text.find("\n", _end(v))
        end = len(self.text) if eol < 0 else eol + 1
        return self.text[:start] + self.text[end:]

    def set_section(self, name: str, changes: dict) -> str:
        """Shared settings (a top-level mapping): each key's value is replaced in place, None removes the key, new
        keys go after the last one. In a block section every other line, comments included, stays as it is."""
        root = yaml.compose(self.text)
        node = next((v for k, v in root.value if k.value == name), None)
        if not isinstance(node, MappingNode):
            raise Invalid("not_section", name=name)
        current = (yaml.safe_load(self.text) or {})[name] or {}
        if node.flow_style:  # `{a: 1, b: 2}` holds no comments inside: write it again
            merged = {k: v for k, v in {**current, **changes}.items() if not (k in changes and changes[k] is None)}
            return self.text[:node.start_mark.index] + flow(merged) + self.text[_end(node):]
        edits = []  # (start, end, replacement), applied from the end of the file backwards
        keys = {k.value: (k, v) for k, v in node.value}
        for key, value in changes.items():
            if key in keys:
                k, v = keys[key]
                if value is None:
                    start = self.text.rfind("\n", 0, k.start_mark.index) + 1
                    eol = self.text.find("\n", _end(v))
                    edits.append((start, len(self.text) if eol < 0 else eol + 1, ""))
                else:
                    start, end, rep = v.start_mark.index, _end(v), scalar(value)
                    gap = re.match(r" +(?=#)", self.text[end:])  # keep a trailing comment in its column
                    if gap:
                        end += gap.end()
                        rep += " " * max(1, gap.end() + (_end(v) - start) - len(rep))
                    edits.append((start, end, rep))
        new = [(k, v) for k, v in changes.items() if k not in keys and v is not None]
        if new:
            k_last, v_last = node.value[-1]
            eol = self.text.find("\n", _end(v_last))
            eol = len(self.text) if eol < 0 else eol
            pad = " " * k_last.start_mark.column
            edits.append((eol, eol, "".join(f"\n{pad}{scalar(k)}: {scalar(v)}" for k, v in new)))
        text = self.text
        for start, end, rep in sorted(edits, key=lambda e: e[0], reverse=True):
            text = text[:start] + rep + text[end:]
        return text

    # ------------------------------------------------------------ checking and writing

    def diff(self, new: str) -> str:
        return "".join(difflib.unified_diff(self.text.splitlines(True), new.splitlines(True), self.path.name,
                                            self.path.name, n=1))

    def verify(self, new: str, expect: dict[str, dict | None]) -> None:
        """The edited text must parse, leave every other section and run as it was and hold exactly the asked
        values (None = the run is gone)."""
        try:
            doc = yaml.safe_load(new) or {}
        except yaml.YAMLError as e:
            raise Invalid("would_break", file=self.path.name, problem=e)
        old = yaml.safe_load(self.text) or {}
        want = dict(old.get(self.section) or {})
        for rid, vals in expect.items():
            if vals is None:
                want.pop(rid, None)
            else:
                want[rid] = vals
        same = lambda d: {k: (v or {}) for k, v in d.items()}
        others = lambda d: {k: v for k, v in d.items() if k != self.section}
        if same(doc.get(self.section) or {}) != same(want) or others(doc) != others(old):
            raise Invalid("not_as_intended", file=self.path.name)

    def save(self, new: str, expected_version: str | None) -> str:
        if expected_version and version_of(self.path.read_bytes()) != expected_version:
            raise Conflict("conflict", file=self.path.name)
        self.path.write_bytes(new.replace("\n", self.nl).encode("utf-8"))
        return version_of(self.path.read_bytes())
