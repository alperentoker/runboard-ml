from __future__ import annotations

from typing import Callable

# Normalised run states shared by every backend.
ACTIVE = {"QUEUED", "STARTING", "RUNNING", "CANCELLING"}
DONE = {"COMPLETE", "ERROR", "CANCELLED"}


class Backend:
    name = "base"
    label = "Base"
    can_cancel = False
    has_data = False      # can upload training data packages
    has_quota = False

    def available(self) -> tuple[bool, str | None]:
        """(usable, reason if not)."""
        return True, None

    def info(self) -> dict:
        """Account / machine facts shown on the dashboard (quota, GPU …)."""
        return {}

    def submit(self, project, run_id: str, info: dict) -> dict:
        """Launches the run; returns fields stored in the run's state (handle, url …)."""
        raise NotImplementedError

    def status(self, project, run_id: str, st: dict) -> tuple[str, str | None]:
        """(normalised status, failure message)."""
        raise NotImplementedError

    def stream(self, project, run_id: str, st: dict, sink: list[str], alive: Callable[[], bool]) -> None:
        """Appends live log lines to sink until the run ends (blocking)."""
        raise NotImplementedError

    def final_log(self, project, run_id: str, st: dict) -> list[str]:
        return []

    def fetch(self, project, run_id: str, st: dict) -> None:
        """Brings outputs into the project's output directory (no-op when they are already local)."""

    def cancel(self, project, run_id: str, st: dict) -> None:
        raise NotImplementedError("This backend cannot cancel runs")

    def delete(self, project, run_id: str, st: dict) -> None:
        """Removes the remote copy of a finished run (optional)."""
        raise NotImplementedError
