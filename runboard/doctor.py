"""`runboard doctor`: one report to paste into an issue. What it is (versions, system), how it is set up (the
settings, the dashboard and its watchdog, the projects, the backends, the GPU, notifications) and the end of the
dashboard's log.

Nothing personal leaves in it: keys and tokens are masked (as in every log runboard shows), and the user folder,
the user name, e-mail addresses and network addresses are replaced. It only reads; it changes nothing.
"""
from __future__ import annotations

import getpass
import os
import platform
import re
import shutil
import sys
from pathlib import Path

from . import __version__, home

LOG_LINES = 30
SETTINGS = ("port", "lan", "lang", "notify", "watchdog")  # the settings worth knowing; nothing else of config.yaml


def scrub(text: str) -> str:
    """Keys and tokens masked; the user folder, the user's name, e-mail and network addresses replaced."""
    from .progress import redact
    text = redact(text)
    for folder in {str(Path.home()), str(Path.home()).replace("\\", "/")}:
        if folder and len(folder) > 3:
            text = re.sub(re.escape(folder), "~", text, flags=re.I)
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001 — no user name to know
        user = ""
    if len(user) >= 3:
        text = re.sub(rf"(?i)(?<![\w]){re.escape(user)}(?![\w])", "<user>", text)
    text = re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "<e-mail>", text)
    text = re.sub(r"\b(?!127\.0\.0\.1\b)(?:\d{1,3}\.){3}\d{1,3}\b", "<ip>", text)
    return text


def _installed() -> str:
    here = Path(__file__).resolve().parent
    if (here.parent / "pyproject.toml").exists():
        return "installed from a source folder (editable)"
    return "installed in site-packages"


def _dashboard() -> str:
    from .proc import pid_alive
    from .server import port_busy

    def pid(name):
        f = home.HOME / name
        t = f.read_text().strip() if f.exists() else ""
        return int(t) if t.isdigit() else None

    port = int(home.config().get("port", 8000))
    srv, watch = pid("server.pid"), pid("watch.pid")
    state = "answering" if port_busy(port) else "not answering"
    return (f"port {port} {state}; dashboard {'running' if pid_alive(srv) else 'not running'}; "
            f"watchdog {'running' if pid_alive(watch) else 'not running'}"
            + ("; stopped on purpose (runboard stop)" if (home.HOME / "stopped").exists() else ""))


def _projects() -> list[str]:
    from .project import Project
    out = []
    for path in home.project_paths():
        try:
            p = Project(path)
            plan = "plan.yaml" if (Path(path) / "plan.yaml").exists() else "no plan.yaml"
            runs = len(p.run_ids())
            out.append(f"{p.key}: manifest v{p.m.get('version', 1)}, {plan}, {runs} runs, backends "
                       f"{', '.join((p.m.get('backends') or {}).keys()) or 'none'}")
        except Exception as e:  # noqa: BLE001 — a broken project is what the report is for
            out.append(f"{Path(path).name}: cannot be read: {type(e).__name__}: {str(e).splitlines()[0][:200]}")
    return out


def _backends() -> list[str]:
    from .backends import BACKENDS
    from .runtime import Runtime
    rt, out = Runtime(), []
    rt.CALL_SECONDS = 15
    for name, b in BACKENDS.items():
        try:
            ok, why = rt._call(("doctor", name), b.available)
        except Exception as e:  # noqa: BLE001
            ok, why = False, f"{type(e).__name__}: {e}"
        out.append(f"{name}: {'available' if ok else 'not available'}" + (f" ({why})" if why else ""))
    return out


def _gpu() -> str:
    from .backends.local import LocalBackend
    try:
        g = LocalBackend().info()
    except Exception as e:  # noqa: BLE001
        return f"cannot be read: {e}"
    if not g.get("gpu"):
        return "none seen (nvidia-smi or torch)"
    return f"{g['gpu']}, {g.get('total_gb')} GB" + (f", load {g['load_pct']} %" if g.get("load_pct") is not None else "")


def report() -> str:
    from . import autostart, notify
    import importlib.metadata as md

    def version(pkg):
        try:
            return md.version(pkg)
        except md.PackageNotFoundError:
            return "not installed"

    cfg = home.config()
    lines = [
        "### runboard doctor", "",
        f"- runboard {__version__}, {_installed()}; Python {platform.python_version()} ({sys.executable})",
        f"- system: {platform.platform()}",
        f"- packages: fastapi {version('fastapi')}, uvicorn {version('uvicorn')}, pyyaml {version('pyyaml')}, "
        f"kaggle {version('kaggle')}",
        f"- tools: " + ", ".join(f"{t} {'yes' if shutil.which(t) else 'no'}" for t in ("git", "ssh", "nvidia-smi")),
        f"- runboard home: {home.HOME}" + (" (RUNBOARD_HOME)" if os.environ.get("RUNBOARD_HOME") else ""),
        "- settings: " + ", ".join(f"{k} {cfg[k]}" for k in SETTINGS if k in cfg),
        f"- dashboard: {_dashboard()}",
        f"- notifications: {notify.system() or 'none on this system'}; start with the computer: "
        f"{ {True: 'on', False: 'off', None: 'not supported here'}[autostart.enabled()] }",
        f"- GPU: {_gpu()}",
        "", "**Backends**", "", *[f"- {b}" for b in _backends()],
        "", "**Projects**", "", *([f"- {p}" for p in _projects()] or ["- none"]),
    ]
    log = home.HOME / "server.log"
    tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-LOG_LINES:] if log.exists() else []
    lines += ["", f"**The last {len(tail)} lines of server.log**", "", "```", *tail, "```"]
    return scrub("\n".join(lines))


def main() -> int:
    print("Paste this into the issue. Keys, your user folder and name, e-mail and network addresses are removed;"
          " read it once before you send it.\n")
    print(report())
    return 0
