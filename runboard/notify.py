"""A Windows notification when a run ends, failed or was cancelled: shown even when no dashboard page is open.

The dashboard's own loop (runtime.poll_once) sees every run of every backend end, so the notice comes from there.
It is a toast through PowerShell and the Windows notification API (no extra package), shown as Windows PowerShell's;
a click opens the run in the browser. Switched with `notify` in ~/.runboard/config.yaml (on by default), worded in
the language the dashboard was last used in (`lang`).
"""
from __future__ import annotations

import base64
import os
import subprocess
from xml.sax.saxutils import escape

from . import home

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
APP = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
WORDS = {
    "en": {"COMPLETE": "{run} finished", "ERROR": "{run} failed", "CANCELLED": "{run} was stopped", "test": "runboard notifications are on",
           "test_body": "You will see this when a run finishes or fails."},
    "tr": {"COMPLETE": "{run} bitti", "ERROR": "{run} hata verdi", "CANCELLED": "{run} durduruldu", "test": "runboard bildirimleri açık",
           "test_body": "Bir koşu bitince ya da hata verince bunu göreceksin."},
}


def available() -> bool:
    return os.name == "nt"


def enabled() -> bool:
    return available() and bool(home.config().get("notify", True))


def words() -> dict:
    return WORDS.get(home.config().get("lang") or "en", WORDS["en"])


def run_ended(project, run_id: str, status: str, failure: str | None = None) -> None:
    """The notice for one run that reached COMPLETE, ERROR or CANCELLED (called once, by the runtime)."""
    if not enabled() or status not in ("COMPLETE", "ERROR", "CANCELLED"):
        return
    st = project.state.get(run_id) or {}
    mark = f"{status}@{st.get('pushed_at') or st.get('job') or st.get('pid') or ''}"  # once per start of the run
    if st.get("notified") == mark:  # e.g. a collection that failed and is tried again
        return
    project.state.update(run_id, notified=mark)
    try:
        m = project.metrics(run_id) or {}  # read from the run's report, which collection has just brought home
    except Exception:
        m = {}
    label = (((project.m.get("results") or {}).get("labels") or {}).get("primary"))
    label = label.get(home.config().get("lang") or "en") or label.get("en") if isinstance(label, dict) else label
    name = project.m.get("name", project.key)
    if status == "COMPLETE":
        body = f"{name}" + (f" · {label or 'score'} {m['primary']:.2f}" if isinstance(m.get("primary"), (int, float)) else "")
    else:
        body = f"{name}" + (f" · {failure}" if failure else "")
    port = int(home.config().get("port", 8000))
    show(words()[status].format(run=run_id), body[:200], f"http://localhost:{port}/#/p/{project.key}/run/{run_id}")


def show(title: str, body: str, url: str | None = None) -> subprocess.Popen | None:
    """Shows one toast without waiting for it; None where there is no Windows."""
    if not available():
        return None
    launch = f' activationType="protocol" launch="{escape(url, {chr(34): "&quot;"})}"' if url else ""
    xml = (f"<toast{launch}><visual><binding template=\"ToastGeneric\"><text>{escape(title)}</text>"
           f"<text>{escape(body)}</text></binding></visual></toast>")
    script = ("[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null\n"
              "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null\n"
              "$x = New-Object Windows.Data.Xml.Dom.XmlDocument\n"
              f"$x.LoadXml('{xml.replace(chr(39), chr(39) * 2)}')\n"
              f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{APP}').Show("
              "[Windows.UI.Notifications.ToastNotification]::new($x))\n")
    # -EncodedCommand: the script reaches PowerShell as it is, whatever quotes a project name holds
    enc = base64.b64encode(script.encode("utf-16-le")).decode()
    try:
        return subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc],
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=NO_WINDOW)
    except OSError:
        return None
