"""runboard command line.

  runboard serve                       start the dashboard (http://localhost:8000)
  runboard add PATH                    register a project folder (must contain runboard.yaml)
  runboard remove PATH                 unregister it (files are untouched)
  runboard list                        registered projects
  runboard attach PATH RUN KERNEL VER  link a Kaggle run started outside runboard
  runboard upload PATH KEY…            upload data packages to Kaggle (used by the dashboard)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import home


def main(argv: list[str] | None = None) -> int:
    if sys.stdout is not None:
        sys.stdout.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="runboard", description="Self-hosted dashboard for ML training runs.")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("serve")
    s.add_argument("--wait-port", action="store_true")
    s.add_argument("--port", type=int)
    sub.add_parser("add").add_argument("path", type=Path)
    sub.add_parser("remove").add_argument("path", type=Path)
    sub.add_parser("list")
    a = sub.add_parser("attach")
    for n in ("path", "run", "kernel"):
        a.add_argument(n)
    a.add_argument("version", type=int)
    u = sub.add_parser("upload")
    u.add_argument("path", type=Path)
    u.add_argument("keys", nargs="+")
    args = ap.parse_args(argv)

    if args.cmd in (None, "serve"):
        from .server import serve

        if getattr(args, "port", None):
            cfg = home.config()
            cfg["port"] = args.port
            home.save_config(cfg)
        serve(getattr(args, "wait_port", False))
        return 0
    if args.cmd == "add":
        from .runtime import Runtime

        p = Runtime.add_project(args.path)
        print(f"added {p.m.get('name', p.key)} ({p.key}) — {p.root}")
        return 0
    if args.cmd == "remove":
        home.unregister(args.path)
        print("removed")
        return 0
    if args.cmd == "list":
        for p in home.project_paths():
            print(p)
        return 0
    from .project import Project

    p = Project(args.path)
    if args.cmd == "attach":
        from .backends.kaggle import api, user

        if args.run not in p.run_ids():
            print(f"unknown run {args.run}")
            return 1
        p.state.update(args.run, backend="kaggle", kernel=args.kernel, version=args.version, status="RUNNING",
                       url=f"https://www.kaggle.com/code/{user(api())}/{args.kernel}", collected=False)
        print(f"{args.run} -> {args.kernel} v{args.version}")
        return 0
    if args.cmd == "upload":
        from .backends.kaggle import KaggleBackend

        return KaggleBackend().upload(p, args.keys)
    return 1
