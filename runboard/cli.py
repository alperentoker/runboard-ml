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


def demo(target: Path) -> int:
    """Copies the demo study (runboard/demo) and rb.py into an empty folder and adds it to the dashboard."""
    import shutil

    from .runtime import Runtime
    src = Path(__file__).parent / "demo"
    target = target.expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        print(f"{target} is not empty; give another folder: runboard demo <folder>")
        return 1
    target.mkdir(parents=True, exist_ok=True)
    for f in src.iterdir():
        if f.is_file() and f.suffix in (".py", ".yaml", ".md"):
            shutil.copy2(f, target / f.name)
    shutil.copy2(Path(__file__).parent / "rb.py", target / "rb.py")
    try:
        import numpy  # noqa: F401
    except ImportError:
        print("the demo needs numpy: pip install numpy")
    p = Runtime.add_project(target)
    print(f"the demo is in {target} and on the dashboard as \"{p.m.get('name')}\".\n"
          "Open http://localhost:8000 (runboard serve, if it is not running) and follow docs/tutorial.md:\n"
          "  1. Hypotheses: lock the plan   2. Runs: queue all six   3. Overview: Evaluate the finished runs   4. Hypotheses: read the verdicts")
    return 0


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
    sub.add_parser("lock", help="lock the plan (plan.lock.json)").add_argument("path", type=Path, nargs="?", default=Path("."))
    sub.add_parser("export", help="paper files into paper/: tables, methods, deviations, checklist, report, archive").add_argument(
        "path", type=Path, nargs="?", default=Path("."))
    sub.add_parser("verdicts", help="the hypotheses' verdicts").add_argument("path", type=Path, nargs="?",
                                                                          default=Path("."))
    dm = sub.add_parser("demo", help="set up the five-minute demo study (numpy, any CPU) and add it to the dashboard")
    dm.add_argument("path", type=Path, nargs="?", default=Path.home() / "runboard-demo")
    tp = sub.add_parser("template", help="write a script from a template (split, check, subsets, evaluate)")
    tp.add_argument("name")
    tp.add_argument("path", type=Path, nargs="?", default=Path("."), help="the project folder")
    tp.add_argument("--to", help="where in the project (default: scripts/<name>.py)")
    tp.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="a parameter")
    tp.add_argument("--reason", default="", help="under a lock: why (recorded as a deviation)")
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
    if args.cmd == "demo":
        return demo(args.path)
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
    if args.cmd == "template":
        from . import templating
        from .errors import Err

        try:
            out = templating.write(p, args.name, dict(kv.split("=", 1) for kv in args.set), args.to,
                                   who="command line", reason=args.reason)
        except Err as e:
            print(e)
            return 1
        print(f"wrote {out['path']}" if out["diff"] else f"{out['path']} is up to date")
        return 0
    if args.cmd == "export":
        from .export import export

        out = export(p)
        print(f"wrote {out['dir']}/: {', '.join(out['files'])} ({out['archived']} files in the archive)")
        return 0
    if args.cmd in ("lock", "verdicts"):
        from . import prereg
        from .errors import Err

        try:
            if args.cmd == "lock":
                rec = prereg.lock(p, "command line")
                git = rec.get("git") or {}
                print(f"locked at {rec['locked_at']}" + (f", commit {git['commit'][:10]}" if git else "")
                      + (" (uncommitted changes: commit the plan so the lock can be traced)" if git.get("dirty") else ""))
                return 0
            for h in prereg.hypotheses(p)["hypotheses"]:
                print(f"{h['id']:<8} {h['verdict']:<18} {h.get('criterion') or ''}")
                for part in h.get("parts") or []:
                    ci = part["ci"]
                    print(f"         {part['text']}: margin {part['margin']}" + (f" [{ci[0]}, {ci[1]}]" if ci else "")
                          + f" -> {part['verdict']}")
                if h.get("missing"):
                    print(f"         waiting for: {', '.join(h['missing'])}")
                if h.get("error"):
                    print(f"         {h['error']['detail']}")
            return 0
        except Err as e:
            print(e)
            return 1
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
