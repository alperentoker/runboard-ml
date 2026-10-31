"""End-to-end checks of the web page in a real headless browser (Chrome, Chromium or Edge, driven over the DevTools
protocol with the standard library only). Skipped when no such browser is installed.

They catch what the API tests cannot: a JavaScript error, a refused script under the content security policy, a page
that patches itself wrongly, charts that do not open or zoom.
"""
import base64
import csv
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import pytest
import yaml

from runboard import home

CANDIDATES = [os.environ.get("RUNBOARD_TEST_BROWSER", ""), "google-chrome", "google-chrome-stable", "chromium",
              "chromium-browser", "chrome", "msedge",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
BROWSER = next((b for b in (shutil.which(c) or (c if c and Path(c).exists() else None) for c in CANDIDATES) if b), None)
pytestmark = pytest.mark.skipif(not BROWSER, reason="no Chrome, Chromium or Edge for the browser tests")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class CDP:
    """A minimal DevTools client: one page, calls answered by id, events kept."""

    def __init__(self, ws_url: str):
        host, path = ws_url.split("//", 1)[1].split("/", 1)
        h, p = host.split(":")
        self.s = socket.create_connection((h, int(p)), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /{path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(1)
        self.n, self.events = 0, []

    def _read(self, n):
        out = b""
        while len(out) < n:
            out += self.s.recv(n - len(out))
        return out

    def _frame(self):
        msg = b""
        while True:
            h = self._read(2)
            n = h[1] & 0x7F
            n = struct.unpack(">H", self._read(2))[0] if n == 126 else struct.unpack(">Q", self._read(8))[0] if n == 127 else n
            msg += self._read(n)
            if h[0] & 0x80:
                return json.loads(msg)

    def call(self, method, **params):
        self.n += 1
        data = json.dumps({"id": self.n, "method": method, "params": params}).encode()
        mask = os.urandom(4)
        head = bytes([0x81]) + (bytes([0x80 | len(data)]) if len(data) < 126 else bytes([0x80 | 126]) + struct.pack(">H", len(data))
                                if len(data) < 65536 else bytes([0x80 | 127]) + struct.pack(">Q", len(data)))
        self.s.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
        while True:
            m = self._frame()
            if m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError(m["error"])
                return m.get("result", {})
            self.events.append(m)

    def js(self, code, wait=0.0):
        r = self.call("Runtime.evaluate", expression=code, awaitPromise=True, returnByValue=True)
        if r.get("exceptionDetails"):
            raise AssertionError(r["exceptionDetails"].get("exception", {}).get("description") or r["exceptionDetails"])
        time.sleep(wait)
        return r.get("result", {}).get("value")

    def until(self, code, timeout=10.0):
        end = time.time() + timeout
        while time.time() < end:
            if self.js(f"!!({code})"):
                return True
            time.sleep(0.2)
        raise AssertionError(f"not true within {timeout}s: {code}")


@pytest.fixture(scope="module")
def page():
    tmp = Path(tempfile.mkdtemp(prefix="rb-ui-"))
    old_home, old_config = home.HOME, home.CONFIG
    home.HOME, home.CONFIG = tmp / ".rb", tmp / ".rb" / "config.yaml"
    proj = tmp / "demo"
    (proj / "out" / "base-s0").mkdir(parents=True)
    (proj / "runs.yaml").write_text("# demo plan\ndefaults: {epochs: 20, seed: 0}\nruns:\n  base: {model: a.pt}\n  other: {model: b.pt, seed: 1}\n")
    (proj / "runboard.yaml").write_text(yaml.safe_dump({
        "version": 2, "name": "Demo", "id": "demo", "runs": {"file": "runs.yaml", "defaults": "defaults", "name": "{id}-s{seed}",
                                              "fields": ["model", "seed", "epochs"],
                                              "schema": {"model": {"choices": ["a.pt", "b.pt"]}, "seed": {"int": [0, 9]}}},
        "backends": {"local": {"command": "echo {id}", "output_dir": "out"}},
        "results": {"report": "{out}/summary.json", "metrics": {"primary": "map"}, "curves": {"file": "{out}/results.csv", "format": "ultralytics"}}}))
    (proj / "plan.yaml").write_text("questions: []\n")
    with open(proj / "out" / "base-s0" / "results.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["epoch", "metrics/mAP50-95(B)", "metrics/mAP50(B)", "train/box_loss", "val/box_loss"])
        for e in range(1, 21):
            w.writerow([e, 0.3 + 0.01 * e, 0.5 + 0.01 * e, 2 - 0.05 * e, 2.1 - 0.04 * e])
    (proj / "out" / "base-s0" / "summary.json").write_text(json.dumps({"map": 50.0}))
    home.save_config({"projects": [str(proj)], "port": 0})
    home.State("demo").set("base", {"status": "COMPLETE", "backend": "local", "collected": True})

    import uvicorn
    from runboard import server
    port = free_port()
    srv = uvicorn.Server(uvicorn.Config(server.app, log_level="warning", log_config=None))
    threading.Thread(target=srv.run, kwargs={"sockets": server.listen_sockets(port, False)}, daemon=True).start()
    base = f"http://127.0.0.1:{port}/"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "api/me", timeout=1)
            break
        except OSError:
            time.sleep(0.1)

    dbg = free_port()
    prof = tmp / "browser"
    proc = subprocess.Popen([BROWSER, "--headless=new", f"--remote-debugging-port={dbg}", f"--user-data-dir={prof}",
                             "--no-first-run", "--no-default-browser-check", "--window-size=1400,900", "--lang=en-US",
                             "--disable-gpu", "--no-sandbox", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{dbg}/json/list", timeout=1))
                if any(t["type"] == "page" for t in tabs):
                    break
            except OSError:
                time.sleep(0.2)
        cdp = CDP(next(t for t in tabs if t["type"] == "page")["webSocketDebuggerUrl"])
        cdp.call("Runtime.enable")
        cdp.call("Page.enable")
        cdp.call("Page.addScriptToEvaluateOnNewDocument", source=(
            "window.__errors = []; addEventListener('error', e => __errors.push(String(e.message)));"
            "document.addEventListener('securitypolicyviolation', e => __errors.push('CSP ' + e.violatedDirective));"))
        cdp.base = base
        yield cdp
    finally:
        proc.terminate()
        srv.should_exit = True
        home.HOME, home.CONFIG = old_home, old_config


def go(cdp, path, ready):
    cdp.call("Page.navigate", url=cdp.base + path)
    cdp.until(ready)


def test_pages_render_without_errors(page):
    go(page, "#/", "document.querySelector('.pcard[data-go]') !== null")
    assert page.js("document.querySelector('.pcard h3').textContent") == "Demo"
    for route, ready in [("#/p/demo/overview", "document.querySelector('.kpis')"),
                         ("#/p/demo/runs/base", "document.querySelector('#detail .dh h2')"),
                         ("#/p/demo/settings", "document.querySelector('[data-pcopy]')"),
                         ("#/p/demo/results", "document.querySelector('#content .card')"),
                         ("#/system", "document.querySelector('#kbox')"),
                         ("#/new", "document.querySelector('.stepper')")]:
        page.js(f"location.hash = '{route}'")
        page.until(ready)
    page.js("document.querySelector('[data-lang=tr]').click()", 0.3)
    assert page.js("document.documentElement.lang") == "tr"
    page.js("document.querySelector('[data-lang=en]').click()", 0.3)
    assert page.js("__errors") == []


def test_links_use_data_attributes_and_the_live_stream_connects(page):
    go(page, "#/", "document.querySelector('.pcard[data-go]')")
    page.js("document.querySelector('.pcard[data-go]').click()")
    page.until("location.hash === '#/p/demo/overview'")
    page.until("typeof ES !== 'undefined' && ES && ES.readyState === 1")
    assert page.js("document.querySelectorAll('[onclick]').length") == 0
    assert page.js("__errors") == []


def test_charts_open_large_and_zoom(page):
    go(page, "#/p/demo/run/base", "document.querySelector('[data-sub=charts]')")
    page.js("document.querySelector('[data-sub=charts]').click()")
    page.until("document.querySelectorAll('#content .chart .cx').length >= 2")
    page.js("document.querySelector('#content .chart .cx').click()")
    page.until("document.querySelector('#chartdlg') && document.querySelector('#chartdlg').open")
    page.js("""(() => { const cw = document.querySelector('#chartdlg .chart .cw'), r = cw.getBoundingClientRect();
        cw.dispatchEvent(new WheelEvent('wheel', {bubbles: true, cancelable: true, deltaY: -100, clientX: r.left + r.width / 2, clientY: r.top + 40})); })()""", 0.3)
    rng = page.js("BIG && BIG.range")
    assert rng and 1 < rng[0] < rng[1] < 20
    page.js("document.querySelector('#chartdlg [data-bs]').click()", 0.2)  # hide the only series: no error
    page.js("document.querySelector('#bigx').click()", 0.2)
    assert page.js("document.querySelector('#chartdlg').open") is False
    assert page.js("__errors") == []


def _box(page, sel):
    return page.js(f"(() => {{ const r = document.querySelector('{sel}').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }})()")


def _mouse_drag(page, x0, y, x1, steps=6):
    page.call("Input.dispatchMouseEvent", type="mouseMoved", x=x0, y=y)
    page.call("Input.dispatchMouseEvent", type="mousePressed", x=x0, y=y, button="left", clickCount=1)
    for i in range(1, steps + 1):
        page.call("Input.dispatchMouseEvent", type="mouseMoved", x=x0 + (x1 - x0) * i / steps, y=y, button="left", buttons=1)
    page.call("Input.dispatchMouseEvent", type="mouseReleased", x=x1, y=y, button="left", clickCount=1)
    time.sleep(0.15)


def _touch(page, kind, points):
    page.call("Input.dispatchTouchEvent", type=kind, touchPoints=[{"x": x, "y": y, "id": i} for i, (x, y) in enumerate(points)])


def test_large_chart_moves_and_zooms_by_mouse_and_touch(page):
    go(page, "#/p/demo/run/base", "document.querySelector('[data-sub=charts]')")
    page.js("document.querySelector('[data-sub=charts]').click()")
    page.until("document.querySelectorAll('#content .chart .cx').length >= 2")
    page.js("document.querySelector('#content .chart .cx').click()")
    page.until("document.querySelector('#chartdlg') && document.querySelector('#chartdlg').open && document.querySelector('#bigplot .cw')")
    rng = lambda: page.js("BIG && BIG.range")
    assert rng() is None and page.js("document.querySelector('[data-z=all]').disabled") is True

    # hovering the large chart shows the values, inside the dialog (a modal dialog covers anything outside it)
    x, y, w, h = _box(page, "#bigplot .cw")
    page.call("Input.dispatchMouseEvent", type="mouseMoved", x=x + w / 2, y=y + h / 2)
    time.sleep(0.15)
    assert page.js("!document.querySelector('#ctip').hidden && !!document.querySelector('#ctip').closest('#chartdlg')")
    assert page.js("!!document.querySelector('#cguide').closest('#chartdlg')")
    assert not page.js("document.querySelector('#bcurh').textContent").endswith("—")  # the table follows the cursor

    # buttons: zoom in around the middle, then move right
    page.js("document.querySelector('[data-z=in]').click()", 0.15)
    lo, hi = rng()
    assert abs((hi - lo) - 19 * .6) < 1e-6 and abs((lo + hi) / 2 - 10.5) < 1e-6
    page.js("document.querySelector('[data-z=left]').click()", 0.15)
    assert rng()[0] < lo
    # the x axis is the chosen range itself: moving is smooth, not from point to point
    assert page.js("CHARTS.__big__.geom.x0") == rng()[0]

    # mouse: dragging a zoomed view to the left shows later epochs
    x, y, w, h = _box(page, "#bigplot .cw")
    before = rng()
    _mouse_drag(page, x + w * .6, y + h / 2, x + w * .3)
    after = rng()
    assert after[0] > before[0] and abs((after[1] - after[0]) - (before[1] - before[0])) < 1e-6  # same width
    # dragging past the end stops there and keeps the width
    _mouse_drag(page, x + w * .9, y + h / 2, x + w * .05)
    _mouse_drag(page, x + w * .9, y + h / 2, x + w * .05)
    assert abs(rng()[1] - 20) < 1e-6 and page.js("document.querySelector('[data-z=right]').disabled") is True

    # the strip under the chart: drag the window back to the start
    ox, oy, ow, oh = _box(page, "#bigwin")
    _mouse_drag(page, ox + ow / 2, oy + oh / 2, ox + ow / 2 - 2000)
    assert abs(rng()[0] - 1) < 1e-6
    # a double click shows everything again
    page.call("Input.dispatchMouseEvent", type="mousePressed", x=x + w / 2, y=y + h / 2, button="left", clickCount=1)
    page.call("Input.dispatchMouseEvent", type="mouseReleased", x=x + w / 2, y=y + h / 2, button="left", clickCount=1)
    page.call("Input.dispatchMouseEvent", type="mousePressed", x=x + w / 2, y=y + h / 2, button="left", clickCount=2)
    page.call("Input.dispatchMouseEvent", type="mouseReleased", x=x + w / 2, y=y + h / 2, button="left", clickCount=2)
    time.sleep(0.15)
    assert rng() is None
    # at full view a mouse drag picks a range
    _mouse_drag(page, x + w * .3, y + h / 2, x + w * .6)
    lo, hi = rng()
    assert 3 < lo < hi < 15

    # touch: two fingers spreading apart zoom in; the view keeps up while they move
    page.js("document.querySelector('[data-z=all]').click()", 0.1)
    page.call("Emulation.setTouchEmulationEnabled", enabled=True, maxTouchPoints=5)
    try:
        cx, cy = x + w / 2, y + h / 2
        _touch(page, "touchStart", [(cx - 40, cy), (cx + 40, cy)])
        for d in (60, 90, 120, 160):
            _touch(page, "touchMove", [(cx - d, cy), (cx + d, cy)])
            time.sleep(0.06)
        _touch(page, "touchEnd", [])
        time.sleep(0.15)
        lo, hi = rng()
        assert hi - lo < 19 / 3 and lo < 10.5 < hi
        # one finger moves the zoomed view; the plot that is redrawn under it does not end the gesture
        _touch(page, "touchStart", [(cx + 150, cy)])
        for i in range(1, 7):
            _touch(page, "touchMove", [(cx + 150 - 50 * i, cy)])
            time.sleep(0.06)
        _touch(page, "touchEnd", [])
        time.sleep(0.15)
        assert rng()[0] > lo + 1
        # a tap shows the values above the finger and they stay
        _touch(page, "touchStart", [(cx, cy)]); _touch(page, "touchEnd", [])
        time.sleep(0.15)
        assert page.js("!document.querySelector('#ctip').hidden")
        assert page.js("document.querySelector('#ctip').getBoundingClientRect().bottom") < cy
        # a double tap on a zoomed view shows everything
        time.sleep(0.4)
        for _ in range(2):
            _touch(page, "touchStart", [(cx, cy)]); _touch(page, "touchEnd", [])
            time.sleep(0.08)
        time.sleep(0.15)
        assert rng() is None
    finally:
        page.call("Emulation.setTouchEmulationEnabled", enabled=False)
    page.js("document.querySelector('#bigx').click()", 0.2)
    assert page.js("__errors") == []


def test_plan_copy_shows_the_diff_before_saving(page):
    go(page, "#/p/demo/settings", "document.querySelector('[data-pcopy=base]')")
    page.js("document.querySelector('[data-pcopy=base]').click()")
    page.until("document.querySelector('#dlg') && document.querySelector('#dlg').open")
    page.js("""(() => { const s = document.querySelector('#dlg [data-f=seed]'); s.value = '3'; s.dispatchEvent(new Event('input'));
        document.querySelector('#fgo').click(); })()""")
    page.until("document.querySelector('#fout .diff')")
    assert "base-copy: {model: a.pt, seed: 3}" in page.js("document.querySelector('#fout').innerText")
    page.js("document.querySelector('#fx').click()", 0.2)
    assert "base-copy" not in Path(page.js("PLAN.file") and home.config()["projects"][0], "runs.yaml").read_text()
    assert page.js("__errors") == []


def test_plan_and_project_files_are_checked_as_they_are_typed(page):
    go(page, "#/p/demo/settings", "document.querySelector('#pfed') && document.querySelector('#mfed')")
    page.js("(() => { const t = document.querySelector('#pfed'); t.value = 'runs: {}'; t.dispatchEvent(new Event('input')); })()")
    page.until("document.querySelector('#pfstate').textContent.includes('runs')")
    page.js("document.querySelector('#pfreset').click()")
    page.until("document.querySelector('#pfstate').textContent === 'No changes'")
    page.js("""(() => { const t = document.querySelector('#mfed'); t.value = t.value.replace('name: Demo', 'name: Demo\\ndescription: d');
        t.dispatchEvent(new Event('input')); document.querySelector('#mfgo').click(); })()""")
    page.until("document.querySelector('#mfout .diff')")
    assert "description: d" in page.js("document.querySelector('#mfout').innerText")
    assert page.js("__errors") == []


def test_errors_are_shown_in_the_interface_language(page):
    go(page, "#/p/demo/settings", "document.querySelector('[data-pcopy=base]')")
    page.js("document.querySelector('[data-lang=tr]').click()", 0.3)
    msg = page.js("api('/api/p/demo/plan/runs/other', {method: 'PUT', json: {values: {seed: 42}, dry: true}}).then(() => 'ok', e => e.message)")
    page.js("document.querySelector('[data-lang=en]').click()", 0.3)
    assert msg == "seed: 0 ile 9 arasında olmalı"


def test_keyboard_reaches_everything_a_mouse_can(page):
    go(page, "#/", "document.querySelector('.pcard[data-go]')")
    assert page.js("document.querySelector('.pcard[data-go]').tabIndex") == 0
    page.js("""(() => { const c = document.querySelector('.pcard[data-go]'); c.focus();
        c.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); })()""")
    page.until("location.hash === '#/p/demo/overview'")
    assert page.js("[...document.querySelectorAll('[data-go]')].every(el => el.tabIndex >= 0)")
    assert page.js("__errors") == []


def test_hypotheses_page_shows_verdicts_and_the_lock(page):
    root = Path(home.config()["projects"][0])
    (root / "plan.yaml").write_text(yaml.safe_dump({
        "questions": [{"id": "S1", "text": "Is the copy better?"}],
        "hypotheses": [{"id": "H1", "question": "S1", "criterion": "base.val > other.val"},
                       {"id": "H2", "question": "S1", "criterion": "base.val >"}],
        "protocol": {"sets": ["val"]}}), encoding="utf-8")
    try:
        go(page, "#/p/demo/hypotheses", "document.querySelector('[data-h=H2]')")
        assert "waiting for evaluations" in page.js("document.querySelector('[data-h=H1]').innerText")
        assert "Criterion: cannot read it" in page.js("document.querySelector('[data-h=H2]').innerText")
        assert page.js("!!document.querySelector('#hlock')") and page.js("document.title") is not None
        assert page.js("__errors") == []
    finally:
        (root / "plan.yaml").write_text("questions: []\n", encoding="utf-8")


def test_a_script_is_written_from_a_template_after_its_diff(page):
    root = Path(home.config()["projects"][0])
    go(page, "#/p/demo/settings", "document.querySelector('#tplsel')")
    page.js("(() => { const s = document.querySelector('#tplsel'); s.value = 'check'; s.dispatchEvent(new Event('change')); })()")
    page.until("document.querySelector('#tplgo')")
    page.js("document.querySelector('#tplgo').click()")
    page.until("document.querySelector('#tplout .diff')")
    assert "runboard-template: check" in page.js("document.querySelector('#tplout').innerText")
    page.js("document.querySelector('#tplgo').click()")
    page.until("document.querySelector('[data-tedit]')")
    assert (root / "scripts" / "check.py").is_file()
    assert page.js("__errors") == []



def test_research_wizard_plans_runs_checks_hypotheses_and_creates_the_project(page):
    folder = Path(tempfile.mkdtemp(prefix="rb-study-")) / "study"
    for key in ("ground", "aerial"):
        d = folder / "data" / key
        d.mkdir(parents=True)
        (d / "train.txt").write_text("./images/a.jpg\n")
        (d / "data.yaml").write_text("train: train.txt\nval: val.txt\nnames: [person, vehicle]\n")
    go(page, "#/new", "document.querySelector('.stepper')")
    page.js(f"W.fs = {{path: {json.dumps(str(folder))}, dirs: [], roots: []}}; W.step = 1; renderWizard()", 0.3)
    page.js("document.querySelector('#wpick').click()")
    page.until("document.querySelector('[data-kind=research]')")
    page.js("document.querySelector('[data-kind=research]').click()", 0.3)
    for ready in ("[data-r='questions.0.id']", "[data-r='packages.0.key']", "[data-r='protocol.sets']", "[data-ruse]"):
        page.js("document.querySelector('#wnext').click()")
        page.until(f"document.querySelector(\"{ready}\")")
    assert page.js("document.querySelectorAll('.stp').length") == 8
    page.js("document.querySelector('[data-ruse]').click()")
    page.until("document.querySelector('[data-wh=\"0\"] .msg.ok')")
    assert "collapse(" in page.js("document.querySelector(\"[data-r='hypotheses.0.criterion']\").value")
    page.js("(() => { const c = document.querySelector(\"[data-r='hypotheses.0.criterion']\"); c.value = 'R9.ground > 0'; c.dispatchEvent(new Event('input')); })()")
    page.until("document.querySelector('[data-wh=\"0\"] .msg.bad')")  # R9 is not planned
    page.js("(() => { const c = document.querySelector(\"[data-r='hypotheses.0.criterion']\"); c.value = 'R1.ground > R2.ground'; c.dispatchEvent(new Event('input')); })()")
    page.until("document.querySelector('[data-wh=\"0\"] .msg.ok')")
    page.js("document.querySelector('#wnext').click()")
    page.until("document.querySelector('.wb')")
    page.js("document.querySelector('#wnext').click()")
    page.until("document.querySelector('#wcreate') && !document.querySelector('#wcreate').disabled")
    page.js("document.querySelector('#wcreate').click()")
    page.until("location.hash.endsWith('/hypotheses') && document.querySelector('[data-h=H1]')", 15)
    assert (folder / "plan.yaml").is_file() and (folder / "scripts" / "evaluate.py").is_file()
    assert "waiting for evaluations" in page.js("document.querySelector('[data-h=H1]').innerText")
    assert page.js("__errors") == []
