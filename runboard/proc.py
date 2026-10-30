"""Processes: whether one still runs (Windows API through ctypes, signal 0 elsewhere) and starting one detached."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


FLAGS = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0) | \
    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
BREAKAWAY = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)


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


def stop_pid(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
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
        handle = k32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            ok = k32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok) and code.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # it exists, owned by someone else
        return True
    return True
