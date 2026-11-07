"""Processes: whether one still runs (Windows API through ctypes, signal 0 elsewhere) and starting one detached."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


FLAGS = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0) | \
    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
BREAKAWAY = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)


LOCALRUN = Path(__file__).with_name("localrun.py")


def localrun_argv(*args: str) -> list[str]:
    """The detached runner of local runs and jobs, started by its file in isolated mode (-I): it needs only the
    standard library, so it works whether or not runboard is installed where the run starts (a run starts in its
    project folder), and nothing of runboard's own is put on the path of the user's command."""
    return [sys.executable, "-I", str(LOCALRUN), *args]


def popen_detached(args: list[str], **kw) -> subprocess.Popen:
    """A process that outlives this one. On Windows a terminal or app (an editor, an AI assistant) may hold its
    children in a job that ends them all when it closes, so the child leaves that job; a job that forbids leaving
    refuses the start, and then the child stays in it."""
    kw = dict(start_new_session=os.name != "nt", stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
              stderr=subprocess.DEVNULL, **kw)
    if BREAKAWAY:
        try:
            return subprocess.Popen(args, creationflags=FLAGS | BREAKAWAY, **kw)
        except PermissionError:
            pass
    return subprocess.Popen(args, creationflags=FLAGS, **kw)


def spawn_detached(args: list[str]) -> int:
    """Starts this Python (pythonw on Windows, so no console window) detached from the current process."""
    exe = Path(sys.executable).with_name("pythonw.exe")
    exe = exe if exe.exists() else Path(sys.executable)
    return popen_detached([str(exe), *args]).pid


def hold_lock(path: Path):
    """An exclusive lock on `path` for as long as this process lives (the system lets go when it ends, even by a
    crash, so no lock is ever left behind). Returns the open file to keep, or None when another process holds it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a+")  # never inherited by children (PEP 446): runs started from the dashboard do not keep it
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def stop_pid(pid: int, tree: bool = True) -> None:
    """Ends a process; on Windows with its children unless tree=False. The dashboard is stopped alone: local runs and
    jobs are its children there, but are meant to go on without it (its watchdog ends by itself, see watch.py)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), *(["/T"] if tree else []), "/F"], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        import signal
        os.kill(pid, signal.SIGTERM)


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        handle = k32.OpenProcess(0x1000 | 0x100000, False, int(pid))  # QUERY_LIMITED_INFORMATION | SYNCHRONIZE
        if not handle:
            return False
        try:
            # WAIT_TIMEOUT (258): still running. The exit code alone cannot tell: a process may exit with 259,
            # the value that also means STILL_ACTIVE.
            return k32.WaitForSingleObject(wintypes.HANDLE(handle), 0) == 258
        finally:
            k32.CloseHandle(wintypes.HANDLE(handle))
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # it exists, owned by someone else
        return True
    return True
