"""runboard command line.

  runboard serve                       start the dashboard (http://localhost:8000) and its watchdog
  runboard stop                        stop the dashboard and its watchdog
  runboard --version
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

from . import __version__, home


def main(argv: list[str] | None = None) -> int:
    if sys.stdout is not None:
        sys.stdout.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="runboard", description="Self-hosted dashboard for ML training runs.")
    ap.add_argument("--version", action="version", version=f"runboard {__version__}")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("stop")
    sub.add_parser("watch")
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
    sub.add_parser("migrate", help="move decisions and the lock into plan.yaml (manifest v2)").add_argument(
        "path", type=Path, nargs="?", default=Path("."))
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
    if args.cmd == "watch":
        from .watch import main as watch

        return watch()
    if args.cmd == "stop":
        from .proc import pid_alive, stop_pid

        from .watch import note

        home.HOME.mkdir(parents=True, exist_ok=True)
        (home.HOME / "stopped").write_text("runboard stop")  # the watchdog leaves it stopped
        note("stopped with runboard stop")
        f = home.HOME / "server.pid"
        pid = int(f.read_text().strip()) if f.exists() and f.read_text().strip().isdigit() else None
        if pid and pid_alive(pid):
            stop_pid(pid)
            print(f"stopped the dashboard (pid {pid})")
        else:
            print("the dashboard was not running")
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
    if args.cmd == "migrate":
        from .errors import Err
        from .planfile import migrate
        from .project import Project

        try:
            out = migrate(args.path, Project(args.path).state.dir / "backup")
        except Err as e:
            print(e)
            return 1
        print(f"wrote {out['plan']} (moved: {', '.join(out['moved']) or 'nothing'}); runboard.yaml is version 2")
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
