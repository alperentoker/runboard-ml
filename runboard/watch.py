"""Watchdog: keeps the dashboard running. `runboard serve` starts it once (one per machine).

Every 10 s it checks that something answers on the dashboard port. After 20 s without an answer it starts the
dashboard again and notes it in ~/.runboard/server.log. `runboard stop` stops both and leaves a flag, so a dashboard
that was stopped on purpose stays stopped until the next `runboard serve`.
"""
from __future__ import annotations

import os
import socket
import sys
import time
from datetime import datetime

from . import home
from .proc import pid_alive, spawn_detached

EVERY = 10
DOWN_CHECKS = 2


def note(msg: str) -> None:
    """A line with a timestamp in ~/.runboard/server.log, whatever process writes it."""
    home.HOME.mkdir(parents=True, exist_ok=True)
    with open(home.HOME / "server.log", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")


def port_busy(p: int) -> bool:
    with socket.socket() as s:
        s.settimeout(2)
        return s.connect_ex(("127.0.0.1", p)) == 0


def stopped_on_purpose() -> bool:
    return (home.HOME / "stopped").exists()


def check(state: dict, busy: bool) -> bool:
    """One look. True when the dashboard has to be started again."""
    state["down"] = 0 if busy else state.get("down", 0) + 1
    if state["down"] >= DOWN_CHECKS:
        state["down"] = -3  # give the new process time to come up before looking again
        return True
    return False


def ensure_running() -> None:
    """Starts the watchdog unless one is already alive (its pid is in ~/.runboard/watch.pid)."""
    f = home.HOME / "watch.pid"
    try:
        if f.exists() and pid_alive(int(f.read_text().strip() or 0)):
            return
    except ValueError:
        pass
    spawn_detached(["-m", "runboard", "watch"])


def main() -> int:
    f = home.HOME / "watch.pid"
    home.HOME.mkdir(parents=True, exist_ok=True)
    try:
        if f.exists() and int(f.read_text().strip() or 0) != os.getpid() and pid_alive(int(f.read_text().strip())):
            return 0  # another watchdog is on duty
    except ValueError:
        pass
    f.write_text(str(os.getpid()))
    note(f"watchdog started (pid {os.getpid()})")
    state: dict = {}
    try:
        while not stopped_on_purpose():
            if check(state, port_busy(int(home.config().get("port", 8000)))):
                note("watchdog: the dashboard was not answering; starting it again")
                spawn_detached(["-m", "runboard", "serve", "--wait-port"])
            time.sleep(EVERY)
        note("watchdog: stopped on purpose (runboard stop)")
    finally:
        if f.exists() and f.read_text().strip() == str(os.getpid()):
            f.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
