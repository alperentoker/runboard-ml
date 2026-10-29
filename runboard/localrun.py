"""Detached runner for the local backend: python -m runboard.localrun LOG CODE ALIVE PYTHON "COMMAND".

Runs COMMAND through the shell (with PYTHON first on PATH), tees output to LOG, touches ALIVE every 10 s and
writes the exit code to CODE when done.
"""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path


def main() -> int:
    log, code, alive, python, cmd = sys.argv[1:6]
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8",
           "PATH": str(Path(python).parent) + os.pathsep + os.environ.get("PATH", "")}
    stop = threading.Event()

    def heartbeat():
        while not stop.is_set():
            Path(alive).touch()
            stop.wait(10)

    threading.Thread(target=heartbeat, daemon=True).start()
    with open(log, "ab", buffering=0) as out:
        proc = subprocess.Popen(cmd, shell=True, stdout=out, stderr=subprocess.STDOUT, env=env)
        rc = proc.wait()
    stop.set()
    if not Path(code).exists():  # "cancelled" is written by the dashboard
        Path(code).write_text(str(rc))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
