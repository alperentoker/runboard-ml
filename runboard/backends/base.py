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

    def resume_info(self, project, run_id: str, st: dict, info: dict) -> dict:
        """What a resumed attempt needs ({resume} for the command template), or an error why it cannot resume."""
        from ..errors import Invalid
        cfg = (project.m.get("backends") or {}).get(self.name) or {}
        if not cfg.get("resume"):
            raise Invalid("no_resume", backend=self.label)
        if st.get("status") not in ("ERROR", "CANCELLED") or st.get("backend") != self.name:
            raise Invalid("cannot_resume", run=run_id)
        return self._resume_info(project, run_id, st, info)

    def _resume_info(self, project, run_id: str, st: dict, info: dict) -> dict:
        raise NotImplementedError

    def may_still_run(self, project, run_id: str, st: dict) -> bool:
        """True when a run already marked as finished could in fact still be going (it is then checked again)."""
        return False

    def delete(self, project, run_id: str, st: dict) -> None:
        """Removes the remote copy of a finished run (optional)."""
        raise NotImplementedError
