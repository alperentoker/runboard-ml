"""Errors the dashboard shows to people. Each has a code and values; the English text below is what the API and the
command line print, and the web page shows the same code in its own language (index.html, `e_<code>`)."""
from __future__ import annotations

MESSAGES = {
    # values of fields
    "one_of": "{field}: one of {choices}",
    "range": "{field}: between {lo} and {hi}",
    "required": "{field}: required",
    "number": "{field}: a number is expected",
    "bool": "{field}: true or false",
    "file": "{field}: a {pattern} file inside the project",
    "empty": "{field}: empty",
    "not_editable": "Not an editable field: {fields}",
    "bad_key": "Not a valid setting name: {key}",
    "bad_run_id": "Run id '{run}': letters, digits, '-', '_' or '.', up to 41 characters",
    # the plan
    "locked": "This plan is pre-registered; change it through its decisions or add an extra run "
              "(shared settings and the file itself are read-only).",
    "started": "This run has started; its settings stay as they were. Copy it to change them.",
    "started_entry": "{run} has started; its entry must stay as it ran",
    "no_extras": "This project does not allow extra runs (runs.extras in runboard.yaml)",
    "extras_direct": "A pre-registered plan only takes extra runs; they are added directly",
    "not_extra": "Only extra runs can be removed",
    "launched": "A run that was already launched cannot be removed",
    "unknown_run": "Unknown run: {run}",
    "exists": "{run} already exists",
    "block_only": "Only runs written one per line can be removed here",
    "not_section": "'{name}' is not a shared settings section",
    "run_mapping": "{run}: a run is a mapping of fields",
    "keep_runs": "The file must keep a '{section}:' mapping of runs",
    "stay_mapping": "'{section}' must stay a mapping",
    "yaml_line": "line {line}: {problem}",
    "yaml": "Not valid YAML: {problem}",
    "broken": "{problem}",
    "file_mapping": "{file} must be a mapping",
    "section_missing": "'{section}' not found in {file}",
    "would_break": "The edit would break {file}: {problem}",
    "not_as_intended": "The edit did not come out as intended in {file}; nothing was written",
    "conflict": "{file} changed since this page loaded it; reload and try again",
    # plan.yaml and runboard.yaml (manifest v2)
    "plan_key": "plan.yaml has no section '{key}'; it holds questions, hypotheses, protocol, groups, decisions and locked",
    "plan_shape": "{what} must be {shape}",
    "plan_ref": "{item} names {ref}, which does not exist",
    "plan_dup": "{id} is used twice",
    "not_v2": "This project has no plan.yaml yet; run `runboard migrate` first",
    "already_v2": "This project already uses plan.yaml",
    "in_plan": "{key} belongs in plan.yaml in this project",
    "keep_version": "The manifest version changes only through `runboard migrate`",
    "manifest_runs": "runboard.yaml needs runs.file naming an existing runs file",
    "migrate_by_hand": "{what} is written in a way the migration cannot move; move it by hand",
    # hypotheses, the lock and deviations
    "criterion": "Criterion: {problem}",
    "evidence": "{file}: {problem}",
    "already_locked": "The plan is already locked",
    "deviation_reason": "The plan is locked: say why it changes (at least 10 characters); the change is recorded as a deviation",
    "not_locked": "The plan is not locked",
    "research": "Research plan: {problem}",
    # code in the dashboard
    "bad_code_path": "{path}: not a code file of this project",
    "too_big": "{path} is over {kb} KB; open it in an editor",
    "syntax": "{file}, line {line}: {problem}",
    "use_editor": "{file} has its own editor on the Settings page",
    # SSH and SLURM
    "no_ssh": "ssh was not found on this computer (install OpenSSH)",
    "ssh_error": "{host}: {problem}",
    "remote_config": "{backend}: {problem}",
    # code templates
    "unknown_template": "No template called {name}",
    "not_template": "{file} was not written from this template; pick another path",
    "owned": "{file} has your changes, so runboard does not write it again",
    "template_param": "{field}: write it as {shape}",
    "bad_path": "{path}: give a .py file inside the project",
    # decisions
    "unknown_decision": "Unknown decision",
    "finish_first": "All candidate runs must finish first",
    "from_candidates": "The value must come from one of the candidate runs",
    "reason_short": "Write a reason (at least 10 characters)",
    "decided": "Decision already made",
    # runs, backends, jobs
    "no_manifest": "{path} not found (see examples/ and docs/manifest.md)",
    "not_ready": "{run}: {fields} not set yet",
    "unknown_backend": "Unknown backend: {backend}",
    "not_configured": "{backend} is not configured for this project",
    "busy": "{backend} is busy: {runs}",
    "unknown_job": "Unknown job",
    "no_resume": "{backend} has no resume command (backends.<name>.resume in runboard.yaml)",
    "cannot_resume": "Only a run that stopped (error or cancelled) can be resumed, on the backend it ran on",
    "resume_missing": "The previous output was not found: {path}",
    "job_running": "A job is already running: {job}",
    "not_on_kaggle": "{data} is not on Kaggle yet (Data tab)",
    "kaggle_error": "Kaggle refused: {problem}",
    "no_local_command": "backends.local.command is not set in runboard.yaml",
    "only_finished_delete": "Only finished runs can be deleted",
    "not_launched": "Not started yet: there is nothing to stop",
    "foreign_kernel": "This run is linked to a notebook runboard did not create; delete it on Kaggle",
    "unknown_project": "Unknown project",
    "not_run_yet": "Not run yet",
    "nothing_selected": "Nothing selected",
    "queue_unknown": "{run} is not in the queue",
    "queue_has": "{run} is already queued",
    "queue_quota": "Not enough Kaggle quota left for {run}: about {need} h needed, {left} h left",
    "sweep_empty": "Pick at least one value for each field you sweep",
    "sweep_too_many": "{n} runs would be created; the limit is {limit}",
    # access and connections
    "local_only": "Only from the computer runboard runs on",
    "not_paired": "This device is not paired",
    "wrong_code": "Wrong or expired code",
    "lan_off": "Turn on tablet access first",
    "unknown_device": "Unknown device",
    "bad_token": "That does not look like a Kaggle API token (Settings → API Tokens → Generate New Token)",
    "token_rejected": "Kaggle rejected the token: {why}",
    "autostart_windows": "Autostart switch is Windows-only; use your OS's service manager",
    # new-project wizard
    "not_folder": "Not a folder: {path}",
    "choose_dataset": "Choose the dataset's YAML file (it lists the classes and the train/val folders)",
    "choose_script": "Choose the training script",
    "add_run": "Add at least one run",
}


class Err(Exception):
    """An error with a code. `run` names the run it is about: used in the text, or else shown in front of it."""
    status = 400

    def __init__(self, code: str, run: str | None = None, **params):
        self.code, self.run = code, run
        self.params = {k: _plain(v) for k, v in params.items()} | ({"run": run} if run else {})
        tpl = MESSAGES.get(code, code)  # a code without a text still reaches the page as an error, not a crash
        text = tpl.format(**self.params)
        super().__init__(f"{run}: {text}" if run and "{run}" not in tpl else text)

    def at(self, run: str) -> "Err":
        """The same error, now said about a run."""
        return type(self)(self.code, run, **{k: v for k, v in self.params.items() if k != "run"})

    def body(self) -> dict:
        return {"detail": str(self), "code": self.code, "params": self.params, "run": self.run}


class Invalid(Err, ValueError):
    status = 400


class Denied(Err, PermissionError):
    status = 403


class Missing(Err, KeyError):
    status = 404

    def __str__(self):  # KeyError would quote the text
        return Exception.__str__(self)


class Conflict(Err):
    status = 409


class Busy(Err, ValueError):
    status = 409


def _plain(v):
    if isinstance(v, (list, tuple, set)):
        return ", ".join(map(str, v))
    return v if isinstance(v, (int, float)) else str(v)
