"""HTTP API and static UI. Who may connect is decided in access.py: this computer freely, other devices only when
network access is on and after pairing; every request is checked against DNS rebinding and cross-site use."""
from __future__ import annotations

import asyncio
import atexit
import json
import math
import os
import platform
import re
import shutil
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse,
                               StreamingResponse)

from . import __version__, access, home, qr, wizard
from .backends import ACTIVE, BACKENDS
from .progress import Parser
from .project import Project
from .errors import Busy, Denied, Err, Invalid, Missing
from .proc import spawn_detached
from .runtime import Runtime
from .watch import ensure_running, note

def finite(obj):
    """NaN/inf (early epochs, empty CSV cells) are not valid JSON; they become null."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [finite(v) for v in obj]
    return obj


def dumps(obj) -> str:
    return json.dumps(finite(obj), ensure_ascii=False, separators=(",", ":"))


class SafeJSON(JSONResponse):
    def render(self, content) -> bytes:
        return dumps(content).encode("utf-8")


STATIC = Path(__file__).parent / "static"
STARTUP = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup/runboard.vbs"
rt = Runtime()
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, default_response_class=SafeJSON)
PUBLIC = {"/pair", "/api/pair", "/icon.svg", "/manifest.webmanifest"}  # reachable before a device is paired


class Guard:
    """Runs before every request (see access.py): Host check, cross-site check, then this computer or a paired device."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.inner(scope, receive, send)
        h = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        if not access.host_allowed(h.get("host", ""), home.config().get("allowed_hosts") or []):
            return await PlainTextResponse("Host not allowed (add it to allowed_hosts in ~/.runboard/config.yaml)",
                                           403)(scope, receive, send)
        if access.cross_site(scope["method"], h):
            return await PlainTextResponse("Cross-site request refused", 403)(scope, receive, send)
        local = access.is_local_client((scope.get("client") or (None,))[0])
        device = None if local else access.device_for(access.cookie_value(h))
        scope.setdefault("state", {}).update(local=local, device=device)
        if not (local or device or scope["path"] in PUBLIC):
            resp = (JSONResponse(Denied("not_paired").body(), 401) if scope["path"].startswith("/api/")
                    else RedirectResponse("/pair", 303))
            return await resp(scope, receive, send)

        async def with_headers(msg):
            if msg["type"] == "http.response.start":
                have = {k.lower() for k, _ in msg.get("headers", [])}  # a page's own policy is kept
                msg["headers"] = list(msg.get("headers", [])) + [h for h in access.SECURITY_HEADERS if h[0] not in have]
            await send(msg)

        await self.inner(scope, receive, with_headers)


app.add_middleware(Guard)


@app.exception_handler(Err)
async def coded_error(request: Request, e: Err):
    """Errors carry a code and values; the page words them in its own language (e_<code> in index.html)."""
    return SafeJSON(e.body(), status_code=e.status)


def local_only(request: Request) -> None:
    """Credentials, new projects (they bring commands to run), the folder browser and startup settings."""
    if not request.state.local:
        raise Denied("local_only")


LOCAL = [Depends(local_only)]
NO_CACHE = {"Cache-Control": "no-store"}  # a new version shows up on the next reload


def bad(e: Exception, code: int = 400):
    if isinstance(e, Err):  # already says what went wrong, with a code the page can translate
        raise e
    raise HTTPException(code, str(e))


def proj(key: str) -> Project:
    try:
        return rt.project(key)
    except KeyError:
        raise Missing("unknown_project")


# ---------------------------------------------------------------- pages

def page(name: str) -> HTMLResponse:
    html = (STATIC / name).read_text(encoding="utf-8")
    return HTMLResponse(html, headers={**NO_CACHE, "Content-Security-Policy": access.page_csp(html)})


@app.get("/", response_class=HTMLResponse)
def index():
    return page("index.html")


@app.get("/mini", response_class=HTMLResponse)
def mini():
    return page("mini.html")


@app.get("/js/{name}")
def script(name: str):
    """The page's scripts (static/js, loaded in order by index.html); the policy allows scripts from this server only."""
    f = STATIC / "js" / name
    if not re.fullmatch(r"[a-z0-9-]+\.js", name) or not f.is_file():
        raise HTTPException(404)
    return FileResponse(f, media_type="text/javascript", headers=NO_CACHE)


@app.get("/icon.svg")
def icon():
    return FileResponse(STATIC / "icon.svg", media_type="image/svg+xml")


@app.get("/manifest.webmanifest")
def webmanifest():
    return JSONResponse({"name": "runboard", "short_name": "runboard", "start_url": "/mini", "display": "standalone",
                         "background_color": "#121211", "theme_color": "#121211",
                         "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml"}]},
                        media_type="application/manifest+json")


# ---------------------------------------------------------------- projects

def own_remote(p: Project, run_id: str, st: dict) -> bool:
    """True only for a remote copy runboard itself created for this run. A run linked to a hand-made notebook
    (runboard attach) shares that notebook with other runs, so deleting it from here is never offered."""
    b = st.get("backend")
    if b != "kaggle" or not st.get("kernel"):
        return False
    return st["kernel"] == BACKENDS["kaggle"].slug(p, run_id)


def run_rows(p: Project, with_history: bool = False) -> list[dict]:
    saved = p.state.all()
    doc = p.doc()
    data_field = (p.m.get("data") or {}).get("field")
    rows = []
    for info in p.infos():
        st = rt.run_state(p, info, saved)
        prog = rt.progress(p, info["id"]) if st else None
        if prog and not with_history:
            hist = prog.pop("history", [])
            prog["spark"] = [h.get("map") for h in hist if h.get("map") is not None][-100:]
        rows.append({**info, **{k: st.get(k) for k in ("status", "failure", "backend", "pushed_at", "version", "url",
                                                       "collected", "check", "metrics", "kernel")}, "progress": prog,
                     "own_remote": own_remote(p, info["id"], st),
                     "changed_since_start": p.changed_since_start(info["id"], st, doc) if st.get("status") else [],
                     "data_key": p.spec(info["id"], doc).get(data_field) if data_field else None})
    return rows


def card(p: Project) -> dict:
    rows = run_rows(p)
    plan = [r for r in rows if not r["extra"]]
    active = [r for r in rows if r["status"] in ACTIVE]
    best = max((r for r in rows if (r.get("metrics") or {}).get("primary") is not None),
               key=lambda r: r["metrics"]["primary"], default=None)
    return {"key": p.key, "name": p.m.get("name", p.key), "description": p.m.get("description"),
            "color": p.m.get("color"), "logo": bool(p.m.get("logo")), "path": str(p.root),
            "runs": len(plan), "done": sum(r["status"] == "COMPLETE" for r in plan), "active": active[:1],
            "best": {"id": best["id"], "value": best["metrics"]["primary"]} if best else None,
            "primary_label": ((p.m.get("results") or {}).get("labels") or {}).get("primary", "score"),
            "backends": list((p.m.get("backends") or {}).keys())}


@app.get("/api/projects")
def api_projects():
    ps = rt.projects()
    return {"projects": [card(p) for p in ps.values()], "errors": rt.errors, "backends": rt.backend_info,
            "version": __version__, "queue": rt.queue_view()}


@app.post("/api/projects", dependencies=LOCAL)
def api_add_project(body: dict = Body(...)):
    try:
        p = rt.add_project(Path(body.get("path", "")))
    except Exception as e:
        bad(e)
    return {"key": p.key}


@app.delete("/api/projects/{key}", dependencies=LOCAL)
def api_remove_project(key: str):
    home.unregister(proj(key).root)
    return {"ok": True}


@app.get("/api/p/{key}/logo")
def api_logo(key: str):
    p = proj(key)
    f = (p.root / p.m.get("logo", "")).resolve()
    if not p.m.get("logo") or not f.is_file() or not f.is_relative_to(p.root.resolve()):  # only a file of the project
        raise HTTPException(404)
    return FileResponse(f)


@app.get("/api/p/{key}")
def api_project(key: str):
    p = proj(key)
    rows = run_rows(p)
    m = p.m
    return {"key": p.key, "name": m.get("name", p.key), "description": m.get("description"), "color": m.get("color"),
            "logo": bool(m.get("logo")), "path": str(p.root), "runs": rows,
            "busy": [r["id"] for r in rows if r["status"] in ACTIVE],
            "phases": m.get("phases") or [], "backends": [{"name": n, "label": BACKENDS[n].label, **(c or {})}
                                                          for n, c in (m.get("backends") or {}).items() if n in BACKENDS],
            "default_backend": m.get("default_backend", next(iter(m.get("backends") or {"kaggle": 0}))),
            "labels": (m.get("results") or {}).get("labels") or {}, "has_data": bool(m.get("data")), "v2": p.v2,
            "jobs": {k: {"title": v.get("title", k), "per_run": bool(v.get("per_run"))} for k, v in (m.get("jobs") or {}).items()},
            "job_views": [j.view(0) for (k, _), j in rt.jobs.items() if k == p.key],
            "backend_info": rt.backend_info}


@app.get("/api/p/{key}/run/{run_id}")
def api_run(key: str, run_id: str):
    p = proj(key)
    if run_id not in p.run_ids():
        raise Missing("unknown_run", run=run_id)
    info = p.info(run_id)
    st = rt.run_state(p, info)
    return {**info, **st, "progress": rt.progress(p, run_id), "curves": p.curves(run_id, info),
            "final": p.final(run_id, info), "output": str(p.output_dir(run_id, info) or "")}


@app.get("/api/p/{key}/log/{run_id}")
def api_log(key: str, run_id: str, all: bool = False):
    p = proj(key)
    return {"lines": Parser(p.m.get("progress")).human(rt.log(p, run_id), all)}


@app.post("/api/p/{key}/start/{run_id}")
def api_start(key: str, run_id: str, body: dict = Body(default={})):
    p = proj(key)
    try:
        return rt.start(p, run_id, body.get("backend") or p.m.get("default_backend", "kaggle"), bool(body.get("resume")))
    except Exception as e:
        bad(e)


@app.post("/api/p/{key}/collect/{run_id}")
def api_collect(key: str, run_id: str):
    try:
        rt.collect(proj(key), run_id)
    except Exception as e:
        bad(e, 500)
    return {"ok": True}


@app.post("/api/p/{key}/cancel/{run_id}")
def api_cancel(key: str, run_id: str):
    p = proj(key)
    st = p.state.get(run_id)
    if not st or st.get("status") not in ACTIVE:
        raise Invalid("not_launched", run=run_id)
    try:
        BACKENDS[st.get("backend") or p.m.get("default_backend", "kaggle")].cancel(p, run_id, st)
    except Exception as e:
        bad(e)
    p.state.update(run_id, status="CANCELLING")
    return {"ok": True}


@app.post("/api/p/{key}/delete/{run_id}")
def api_delete(key: str, run_id: str):
    p = proj(key)
    st = p.state.get(run_id)
    if not st or st.get("status") in ACTIVE:
        raise Invalid("only_finished_delete")
    if st.get("backend") == "kaggle" and not own_remote(p, run_id, st):
        raise Invalid("foreign_kernel")
    try:
        BACKENDS[st.get("backend", "kaggle")].delete(p, run_id, st)
    except NotImplementedError:
        pass
    except Exception as e:
        bad(e, 500)
    p.state.remove(run_id)
    return {"ok": True}


@app.get("/api/p/{key}/config")
def api_config(key: str):
    p = proj(key)
    doc = p.doc()
    r = p.m.get("runs", {})
    return {"runs": p.infos(), "fields": r.get("fields", []), "locked": p.locked,
            "shared": {s: doc.get(s) for s in r.get("show", [])}, "extras": p.extras or None,
            "extra_choices": {k: (sorted({p.spec(i, doc).get(k) for i in doc.get(p.section) or {}} - {None})
                                  if v.get("choices") == "$existing" else v.get("choices"))
                              for k, v in (p.extras.get("fields") or {}).items()},
            "decisions": p.decisions(), "raw": p.runs_file.read_text(encoding="utf-8"),
            "runs_file": p.runs_file.relative_to(p.root).as_posix(),
            "decision_log": next(((p.root / d.get("log", "decisions.md")).read_text(encoding="utf-8")
                                  for d in p.decision_specs() if (p.root / d.get("log", "decisions.md")).exists()), None)}


@app.post("/api/p/{key}/runs")
def api_add_run(key: str, body: dict = Body(...)):
    try:
        return {"id": proj(key).add_extra(body.get("values") or {}, body.get("note", ""))}
    except Exception as e:
        bad(e)


@app.delete("/api/p/{key}/runs/{run_id}")
def api_remove_run(key: str, run_id: str):
    try:
        proj(key).remove_extra(run_id)
    except Exception as e:
        bad(e)
    return {"ok": True}


@app.post("/api/p/{key}/decide/{decision}")
def api_decide(key: str, decision: str, body: dict = Body(...)):
    try:
        proj(key).decide(decision, body.get("value", ""), body.get("reason", ""))
    except Exception as e:
        bad(e)
    return {"ok": True}


# ---------------------------------------------------------------- the plan: editing the runs file

def who(request: Request) -> str:
    d = request.state.device
    return f"device {d['name']}" if d else "this computer"


def plan_call(fn):
    try:
        return fn()
    except Err:
        raise
    except (ValueError, KeyError) as e:
        bad(e)


@app.get("/api/p/{key}/plan")
def api_plan(key: str):
    return plan_call(proj(key).plan)


@app.post("/api/p/{key}/plan/runs")
def api_plan_add(key: str, request: Request, body: dict = Body(...)):
    p = proj(key)
    return plan_call(lambda: p.add_run(body.get("id"), body.get("values") or {}, body.get("version"),
                                       body.get("copy_from"), body.get("note", ""), bool(body.get("dry")), who(request)))


@app.put("/api/p/{key}/plan/runs/{run_id}")
def api_plan_edit(key: str, run_id: str, request: Request, body: dict = Body(...)):
    p = proj(key)
    return plan_call(lambda: p.edit_run(run_id, body.get("values") or {}, body.get("version"), bool(body.get("dry")),
                                        who(request)))


@app.delete("/api/p/{key}/plan/runs/{run_id}")
def api_plan_remove(key: str, run_id: str, request: Request, version: str = "", dry: bool = False):
    p = proj(key)
    res = plan_call(lambda: p.remove_run(run_id, version or None, dry, who(request)))
    if not dry:
        rt.forget(p.key, run_id)
    return res


@app.post("/api/p/{key}/plan/sweep")
def api_plan_sweep(key: str, request: Request, body: dict = Body(...)):
    p = proj(key)
    return plan_call(lambda: p.add_sweep(body.get("grid") or {}, body.get("base"), str(body.get("prefix") or ""),
                                         body.get("version"), body.get("note", ""), bool(body.get("dry")), who(request)))


# ---------------------------------------------------------------- queue (one per backend, across projects)

@app.get("/api/queue")
def api_queue():
    return {"entries": rt.queue_view()}


@app.post("/api/queue")
def api_enqueue(request: Request, body: dict = Body(...)):
    p = proj(str(body.get("project", "")))
    backend = body.get("backend") or p.m.get("default_backend", "kaggle")
    if body.get("runs"):  # a sweep: checked as a whole, runs already queued are left as they are
        added = rt.enqueue_many(p, [str(r) for r in body["runs"] if r], backend, who(request))
    else:
        added = [rt.enqueue(p, str(body.get("run", "")), backend, who(request))]
    threading.Thread(target=rt.run_queue, daemon=True).start()  # a free backend starts at once
    return {"added": added}


@app.delete("/api/queue/{entry_id}")
def api_dequeue(entry_id: str):
    rt.dequeue(entry_id)
    return {"ok": True}


@app.post("/api/queue/{entry_id}/move")
def api_queue_move(entry_id: str, body: dict = Body(...)):
    rt.move(entry_id, -1 if int(body.get("by", 0)) < 0 else 1)
    return {"ok": True}


@app.put("/api/p/{key}/plan/section/{name}")
def api_plan_section(key: str, name: str, request: Request, body: dict = Body(...)):
    p = proj(key)
    return plan_call(lambda: p.edit_section(name, body.get("values") or {}, body.get("version"), bool(body.get("dry")),
                                            who(request)))


@app.put("/api/p/{key}/plan/raw")
def api_plan_raw(key: str, request: Request, body: dict = Body(...)):
    p = proj(key)
    return plan_call(lambda: p.edit_raw(str(body.get("text", "")), body.get("version"), bool(body.get("dry")),
                                        who(request), str(body.get("reason") or "")))


@app.get("/api/p/{key}/files")
def api_files(key: str, request: Request):
    return {**plan_call(proj(key).files), "can_edit_manifest": bool(request.state.local)}


@app.put("/api/p/{key}/files/plan")
def api_file_plan(key: str, request: Request, body: dict = Body(...)):
    p = proj(key)
    return plan_call(lambda: p.edit_file("plan", str(body.get("text", "")), body.get("version"), bool(body.get("dry")),
                                         who(request), str(body.get("reason") or "")))


@app.get("/api/p/{key}/hypotheses")
def api_hypotheses(key: str):
    """Questions, hypotheses and their verdicts, the lock and its deviations (a v2 project)."""
    from . import prereg
    p = proj(key)
    return plan_call(lambda: prereg.hypotheses(p)) if p.v2 else {"status": {"v2": False}}


@app.post("/api/p/{key}/deviation")
def api_deviation(key: str, request: Request, body: dict = Body(...)):
    """Records a change made outside runboard (a script edited by hand) as a deviation, with its reason."""
    from . import prereg
    p = proj(key)
    plan_call(lambda: prereg.record_deviation(p, str(body.get("reason") or ""), who(request)))
    return {"ok": True}


@app.get("/api/p/{key}/templates")
def api_templates(key: str, request: Request):
    from . import templating
    p = proj(key)
    return {"catalog": [{"name": n, **{k: t[k] for k in ("version", "target", "title", "desc", "params")}}
                        for n, t in templating.TEMPLATES.items()],
            "files": templating.files(p), "can_write": bool(request.state.local), "locked": p.v2 and p.locked}


@app.post("/api/p/{key}/templates/{name}", dependencies=LOCAL)
def api_template_write(key: str, name: str, request: Request, body: dict = Body(...)):
    """From this computer only: it writes code that runs here."""
    from . import templating
    p = proj(key)
    return plan_call(lambda: templating.write(p, name, body.get("params") or {}, body.get("path") or None,
                                              bool(body.get("dry")), who(request), str(body.get("reason") or "")))


@app.post("/api/p/{key}/lock", dependencies=LOCAL)
def api_lock(key: str, request: Request):
    from . import prereg
    p = proj(key)
    return plan_call(lambda: prereg.lock(p, who(request)))


@app.put("/api/p/{key}/files/manifest", dependencies=LOCAL)
def api_file_manifest(key: str, request: Request, body: dict = Body(...)):
    """From this computer only: the manifest holds the commands runboard runs."""
    p = proj(key)
    return plan_call(lambda: p.edit_file("manifest", str(body.get("text", "")), body.get("version"),
                                         bool(body.get("dry")), who(request)))


@app.get("/api/p/{key}/data")
def api_data(key: str):
    p = proj(key)
    data = p.m.get("data") or {}
    rows = p.catalog()
    for r in rows:
        r["_on_disk"] = Path(r["_zip"]).exists()
    try:
        remote, err = BACKENDS["kaggle"].datasets(p), None
    except Exception as e:
        remote, err = [], str(e)
    cols = data.get("columns") or ({"folder": "folder", "size_mb": "size_mb"} if data.get("packages") else {})
    for r in rows:
        r["_on_disk"] = Path(r["_dir"]).is_dir() if r.get("_dir") else r["_on_disk"]
    return {"rows": rows, "columns": cols, "field": data.get("field"), "remote": remote,
            "error": err, "build": data.get("build_job") if data.get("build_job") in (p.m.get("jobs") or {}) else None}


@app.post("/api/p/{key}/data/upload")
def api_upload(key: str, body: dict = Body(...)):
    p = proj(key)
    keys = [k for k in body.get("keys", []) if re.fullmatch(r"[\w.-]+", k)]
    if not keys:
        raise Invalid("nothing_selected")
    try:
        return rt.upload_job(p, keys).view()
    except Exception as e:
        bad(e)


@app.post("/api/p/{key}/job/{kind}")
def api_job(key: str, kind: str, body: dict = Body(default={})):
    try:
        return rt.start_job(proj(key), kind, body.get("run")).view()
    except Exception as e:
        bad(e)


@app.get("/api/p/{key}/job/{kind}")
def api_job_view(key: str, kind: str):
    j = rt.jobs.get((key, kind))
    if not j:
        raise Missing("not_run_yet")
    return j.view()


@app.get("/api/p/{key}/results")
def api_results(key: str):
    p = proj(key)
    res = p.m.get("results") or {}
    pc = res.get("per_class") or {}
    rows = {}
    for info in p.infos():
        met = p.metrics(info["id"], info)
        fin = p.final(info["id"], info) if met else None
        classes = {}
        if fin and pc:
            node = fin
            for k in pc.get("path", "per_class").split("."):
                node = (node or {}).get(k)
            classes = {c: round(pc.get("scale", 1) * v.get(pc.get("metric", "map")), 2) for c, v in (node or {}).items()}
        rows[info["id"]] = {**info, "metrics": {k: v for k, v in (met or {}).items() if k != "_raw"} or None,
                            "classes": classes}
    return {"rows": rows, "tables": p.m.get("tables") or [], "labels": res.get("labels") or {},
            "note": res.get("note"), "classes": pc.get("names", []), "column": res.get("column")}


# ---------------------------------------------------------------- live updates (server-sent events)

class Snapshots:
    """Views computed at most once per `ttl` seconds and shared by every open page, so ten tabs cost what one does."""

    def __init__(self, ttl: float):
        self.ttl, self.lock, self.data = ttl, threading.Lock(), {}

    def get(self, key, fn) -> str:
        with self.lock:
            hit = self.data.get(key)
        if hit and time.time() - hit[0] < self.ttl:
            return hit[1]
        body = dumps(fn())
        with self.lock:
            self.data[key] = (time.time(), body)
        return body


SNAP = Snapshots(2.5)
TICK = 1.0


def delta(sent: list[str] | None, cur: list[str]) -> list[str] | None:
    """The lines of `cur` that follow what was already sent, or None when `cur` no longer continues it
    (a new attempt replaced the log, or the filter changed) and the page has to start over."""
    if sent is None:
        return None
    if not sent:  # nothing shown yet: every line is new
        return list(cur)
    m = min(len(sent), 8)
    tail = sent[-m:]
    for j in range(len(cur) - m, -1, -1):
        if cur[j:j + m] == tail:
            return cur[j + m:]
    return None


def events_once(S: dict, key: str, run_id: str, log: bool, everything: bool, jobs: str) -> list[tuple[str, str]]:
    """One round of changes for one page. S remembers what this page already has."""
    out = []

    def send(name, snap_key, fn):
        try:
            body = SNAP.get(snap_key, fn)
        except Err as e:
            body = dumps({"error": str(e), **e.body()})
        except HTTPException as e:
            body = dumps({"error": e.detail})
        if S.get(name) != body:
            S[name] = body
            out.append((name, body))

    send("projects", ("projects",), api_projects)
    if key:
        send("project", ("p", key), lambda: api_project(key))
        if run_id:
            send("run", ("run", key, run_id), lambda: api_run(key, run_id))
            if log:
                try:
                    p = proj(key)
                    lines = Parser(p.m.get("progress")).human(rt.log(p, run_id), everything)
                except (Err, HTTPException):
                    lines = []
                new = delta(S.get("log"), lines) if "log" in S else None
                if new is None and S.get("log") != lines or "log" not in S:
                    out.append(("log", dumps({"run": run_id, "reset": True, "lines": lines})))
                elif new:
                    out.append(("log", dumps({"run": run_id, "reset": False, "lines": new})))
                S["log"] = lines
    wanted = set(jobs.split(",")) if jobs else set()
    for (k, kind), j in list(rt.jobs.items()):
        if "*" not in wanted and k not in wanted:
            continue
        v = j.view(2000)
        meta = (id(j), v["status"], v["seconds"], v["code"])
        prev = S.get(("job", k, kind))
        new = delta(prev[1], v["lines"]) if prev and prev[0][0] == id(j) else None
        if prev and prev[0] == meta and new == []:
            continue
        reset = new is None and (not prev or prev[1] != v["lines"] or prev[0][0] != id(j))
        out.append(("job", dumps({"project": k, "kind": kind, "title": v["title"], "status": v["status"],
                                  "seconds": v["seconds"], "code": v["code"], "reset": reset,
                                  "lines": v["lines"][-400:] if reset else (new or [])})))
        S[("job", k, kind)] = (meta, v["lines"])
    return out


@app.get("/api/events")
async def api_events(request: Request, p: str = "", run: str = "", log: bool = False, all: bool = False, jobs: str = ""):
    """Server-sent events for one page: `projects`, `project` and `run` whenever they change, `log` and `job` as
    appended lines. The page patches what it shows instead of fetching and redrawing everything on a timer."""
    async def stream():
        S, quiet = {}, time.time()
        yield "retry: 3000\n\n"
        while not await request.is_disconnected():
            for name, body in await run_in_threadpool(events_once, S, p, run, log, all, jobs):
                yield f"event: {name}\ndata: {body}\n\n"
                quiet = time.time()
            if time.time() - quiet > 15:
                yield ": ping\n\n"  # keeps proxies and sleeping tablets from dropping the connection
                quiet = time.time()
            await asyncio.sleep(TICK)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- new-project wizard

@app.get("/api/fs", dependencies=LOCAL)
def api_fs(path: str = ""):
    try:
        return {"roots": wizard.roots(), **(wizard.listdir(path) if path else {"path": "", "dirs": [], "parent": None})}
    except Exception as e:
        bad(e)


@app.post("/api/wizard/scan", dependencies=LOCAL)
def api_scan(body: dict = Body(...)):
    try:
        return wizard.scan(body.get("path", ""))
    except Exception as e:
        bad(e)


@app.post("/api/wizard/preview", dependencies=LOCAL)
def api_preview(body: dict = Body(...)):
    try:
        files, research = wizard.build_all(body)
        return {"files": files, "research": research}
    except Exception as e:
        bad(e)


@app.post("/api/wizard/create", dependencies=LOCAL)
def api_create(body: dict = Body(...)):
    try:
        root = wizard.create(body, overwrite=bool(body.get("overwrite")))
        p = rt.add_project(root)
    except FileExistsError as e:
        bad(e, 409)
    except Exception as e:
        bad(e)
    return {"key": p.key}


# ---------------------------------------------------------------- connections (credentials)

KAGGLE_DIR = Path(os.environ.get("KAGGLE_CONFIG_DIR", Path.home() / ".kaggle"))


def kaggle_connection() -> dict:
    token_file = KAGGLE_DIR / "access_token"
    legacy = KAGGLE_DIR / "kaggle.json"
    src = "env" if os.environ.get("KAGGLE_API_TOKEN") else "file" if token_file.exists() else "legacy" if legacy.exists() else None
    ok, why = BACKENDS["kaggle"].available()
    info = rt.backend_info.get("kaggle", {})
    return {"source": src, "file": str(token_file), "ok": ok, "error": None if ok else why, "user": info.get("user"),
            "quota": info.get("quota"), "installed": why != "pip install kaggle"}


@app.get("/api/connections")
def api_connections():
    return {"kaggle": kaggle_connection(), "local": rt.backend_info.get("local", {}),
            "colab": {"planned": True}}


@app.post("/api/connections/kaggle", dependencies=LOCAL)
def api_kaggle_token(body: dict = Body(...)):
    """Saves a Kaggle API token typed into the dashboard to ~/.kaggle/access_token (this machine only) and tests it.
    The token is never returned by any endpoint."""
    token = str(body.get("token", "")).strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-]{20,200}", token):
        raise Invalid("bad_token")
    KAGGLE_DIR.mkdir(parents=True, exist_ok=True)
    f = KAGGLE_DIR / "access_token"
    old = f.read_bytes() if f.exists() else None
    f.write_text(token, encoding="utf-8")
    try:
        os.chmod(f, 0o600)
    except OSError:
        pass
    ok, why = BACKENDS["kaggle"].available()
    if not ok:
        if old is not None:
            f.write_bytes(old)
        else:
            f.unlink()
        raise Invalid("token_rejected", why=why)
    rt.backend_info["kaggle"] = {**rt.backend_info.get("kaggle", {}), "ok": True, "error": None, **BACKENDS["kaggle"].info()}
    return kaggle_connection()


@app.delete("/api/connections/kaggle", dependencies=LOCAL)
def api_kaggle_disconnect():
    f = KAGGLE_DIR / "access_token"
    if f.exists():
        f.unlink()
    return kaggle_connection()


# ---------------------------------------------------------------- devices (tablet access)

@app.get("/pair", response_class=HTMLResponse)
def pair_page(request: Request, c: str = ""):
    """Opened from the QR code: a valid one-time link pairs this browser at once; otherwise the code form."""
    if c and access.redeem(token=c):
        r = RedirectResponse("/mini" if "Mobile" in request.headers.get("user-agent", "") else "/", 303)
        r.headers["set-cookie"] = access.set_cookie_header(access.add_device(access.device_name(request.headers.get("user-agent", ""))))
        return r
    return page("pair.html")


@app.post("/api/pair")
def api_pair(request: Request, body: dict = Body(...)):
    if not access.redeem(code=str(body.get("code", ""))):
        raise Invalid("wrong_code")
    name = str(body.get("name") or access.device_name(request.headers.get("user-agent", "")))
    r = JSONResponse({"ok": True})
    r.headers["set-cookie"] = access.set_cookie_header(access.add_device(name))
    return r


@app.get("/api/me")
def api_me(request: Request):
    d = request.state.device
    return {"local": request.state.local, "device": d and {"id": d["id"], "name": d["name"]}}


@app.get("/api/devices")
def api_devices():
    return {"devices": [{k: v for k, v in d.items() if k != "hash"} for d in access.devices()],
            "pairing": access.pairing_state(), "lan": bool(home.config().get("lan"))}


@app.post("/api/devices/pair", dependencies=LOCAL)
def api_pair_start():
    if not home.config().get("lan"):
        raise Invalid("lan_off")
    p = access.start_pairing()
    url = f"http://{local_ip()}:{port()}/pair?c={p['token']}"
    return {"code": p["code"], "url": url, "base": f"http://{local_ip()}:{port()}/pair", "qr": qr.svg(url),
            "seconds": access.PAIR_SECONDS}


@app.delete("/api/devices/{did}", dependencies=LOCAL)
def api_device_remove(did: str):
    if not access.remove_device(did):
        raise Missing("unknown_device")
    return {"ok": True}


@app.post("/api/system/lan", dependencies=LOCAL)
def api_lan(body: dict = Body(...)):
    """Network access changes the address the server listens on, so it restarts."""
    cfg = home.config()
    cfg["lan"] = bool(body.get("on"))
    home.save_config(cfg)
    api_restart()
    return {"lan": cfg["lan"], "restarting": True}


# ---------------------------------------------------------------- system

def os_name() -> str:
    if platform.system() == "Windows":
        build = int(platform.version().split(".")[-1])
        return f"Windows {11 if build >= 22000 else 10} (build {build})"
    return f"{platform.system()} {platform.release()}"


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no packet is sent; picks the LAN interface
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


@app.get("/api/system")
def api_system():
    disk = shutil.disk_usage(home.HOME.parent)
    return {"version": __version__, "python": platform.python_version(), "os": os_name(), "home": str(home.HOME),
            "lan": f"http://{local_ip()}:{port()}", "lan_on": bool(home.config().get("lan")), "port": port(),
            "backends": rt.backend_info,
            "disk": {"free_gb": round(disk.free / 2**30, 1), "total_gb": round(disk.total / 2**30, 1)},
            "autostart": STARTUP.exists() if os.name == "nt" else None, "pid": os.getpid()}


def port() -> int:
    return int(home.config().get("port", 8000))


@app.post("/api/system/autostart", dependencies=LOCAL)
def api_autostart(body: dict = Body(...)):
    if os.name != "nt":
        raise Invalid("autostart_windows")
    if body.get("on"):
        pyw = Path(sys.executable).with_name("pythonw.exe")
        STARTUP.parent.mkdir(parents=True, exist_ok=True)
        STARTUP.write_text('Set sh = CreateObject("WScript.Shell")\r\n'
                           f'sh.Run """{pyw if pyw.exists() else sys.executable}"" -m runboard serve", 0, False\r\n',
                           encoding="utf-8")
    elif STARTUP.exists():
        STARTUP.unlink()
    return {"autostart": STARTUP.exists()}


@app.post("/api/system/restart")
def api_restart():
    note("restart requested from the dashboard")
    spawn_detached(["-m", "runboard", "serve", "--wait-port"])
    threading.Timer(1.0, lambda: os._exit(0)).start()
    return {"ok": True}


def listen_sockets(p: int, lan: bool) -> list[socket.socket]:
    """IPv4 and IPv6 both: browsers try `localhost` as ::1 first, and an IPv4-only server makes every request wait
    for that attempt to fail. Without IPv6 on the machine the IPv4 socket is enough."""
    out = []
    for family, host in ((socket.AF_INET, "0.0.0.0" if lan else "127.0.0.1"), (socket.AF_INET6, "::" if lan else "::1")):
        s = socket.socket(family, socket.SOCK_STREAM)
        try:
            if family == socket.AF_INET6:
                s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            elif os.name != "nt":
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, p))
            s.listen(2048)
            s.setblocking(False)
            out.append(s)
        except OSError:
            s.close()
            if family == socket.AF_INET:
                raise
    return out


def port_busy(p: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", p)) == 0


def serve(wait_port: bool = False) -> None:
    import uvicorn

    home.HOME.mkdir(parents=True, exist_ok=True)  # a fresh machine has none yet
    if sys.stdout is None:  # pythonw: log to a file
        sys.stdout = sys.stderr = open(home.HOME / "server.log", "a", encoding="utf-8", buffering=1)
    p = port()
    if wait_port:
        for _ in range(30):
            if not port_busy(p):
                break
            time.sleep(0.5)
    if port_busy(p):
        print(f"runboard is already running: http://localhost:{p}")
        return
    # Anything that ends this process is written down, so a dashboard that disappeared says why; the watchdog
    # (watch.py) starts it again unless it was stopped on purpose.
    (home.HOME / "stopped").unlink(missing_ok=True)
    (home.HOME / "server.pid").write_text(str(os.getpid()))
    sys.excepthook = lambda *exc: note("unexpected error:\n" + "".join(traceback.format_exception(*exc)))
    threading.excepthook = lambda a: note(f"unexpected error in thread {a.thread.name}:\n"
                                          + "".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback)))
    atexit.register(lambda: note(f"dashboard stopped (pid {os.getpid()})"))
    if home.config().get("watchdog", True):
        ensure_running()
    old = home.HOME / "password.txt"
    if old.exists():  # earlier versions used a password; access is now by machine and paired device
        old.unlink()
    lan = bool(home.config().get("lan"))
    threading.Thread(target=rt.loop, daemon=True).start()
    print(f"\nrunboard {__version__}\n  this machine : http://localhost:{p}" +
          (f"\n  tablet       : http://{local_ip()}:{p}  (pair it once: System → Tablet access)" if lan else
           "\n  tablet access is off (System → Tablet access)") + "\n", flush=True)
    note(f"dashboard started (pid {os.getpid()}, port {p}, {'tablet access on' if lan else 'this computer only'})")
    try:
        config = uvicorn.Config(app, port=p, log_level="warning", log_config=None,
                                timeout_graceful_shutdown=3)  # open event streams never end by themselves
        uvicorn.Server(config).run(sockets=listen_sockets(p, lan))
    except BaseException as e:  # noqa: BLE001 — written down, then let it end the process as before
        note(f"dashboard ended by {type(e).__name__}:\n" + traceback.format_exc())
        raise
