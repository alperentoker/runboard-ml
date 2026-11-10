"""The README's pictures, made from the real dashboard: the demo study in a throwaway runboard home, the dashboard
on a free port, a headless Chrome or Edge driven over the DevTools protocol (standard library only), Pillow to put
the animation together.

    python tools/capture_docs.py            # writes docs/images/demo.gif and docs/images/overview.png, results.png

Nothing of yours is touched or shown: the runboard home, the demo project, the browser profile and the user folder the
dashboard sees are temporary folders, and the Kaggle variables are removed, so no account of yours (a Kaggle token,
its quota) can appear in a picture.
Needs: runboard installed (pip install -e .), numpy (the demo), Pillow, and Chrome, Chromium or Edge.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = [os.environ.get("RUNBOARD_TEST_BROWSER", ""), "google-chrome", "google-chrome-stable", "chromium",
              "chromium-browser", "chrome", "msedge",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
W, H = 1360, 1240  # the window (tall enough for the queue and the live curve); the animation is scaled down


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class CDP:
    """A minimal DevTools client (the same as tests/test_ui.py): one page, calls answered by id."""

    def __init__(self, ws_url: str):
        host, path = ws_url.split("//", 1)[1].split("/", 1)
        h, p = host.split(":")
        self.s = socket.create_connection((h, int(p)), timeout=60)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /{path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(1)
        self.n = 0

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

    def js(self, code):
        r = self.call("Runtime.evaluate", expression=code, awaitPromise=True, returnByValue=True)
        return r.get("result", {}).get("value")

    def until(self, code, timeout=30.0):
        end = time.time() + timeout
        while time.time() < end:
            if self.js(f"!!({code})"):
                return
            time.sleep(0.2)
        raise SystemExit(f"the page did not get there within {timeout:.0f} s: {code}")

    def shot(self):
        from PIL import Image
        data = base64.b64decode(self.call("Page.captureScreenshot", format="png")["data"])
        return Image.open(io.BytesIO(data)).convert("RGB")


def api(base: str, path: str, body: dict | None = None):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "images")
    ap.add_argument("--frames", type=int, default=28, help="frames of the animation (one every --every seconds)")
    ap.add_argument("--every", type=float, default=0.4)
    args = ap.parse_args()
    browser = next((b for b in (shutil.which(c) or (c if c and Path(c).exists() else None) for c in CANDIDATES) if b), None)
    if not browser:
        raise SystemExit("no Chrome, Chromium or Edge found (set RUNBOARD_TEST_BROWSER)")

    tmp = Path(tempfile.mkdtemp(prefix="rb-docs-"))
    port = free_port()
    (tmp / "user").mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("KAGGLE_")}
    env.update({"RUNBOARD_HOME": str(tmp / "home"), "RUNBOARD_NO_WATCHDOG": "1", "HOME": str(tmp / "user"),
                "USERPROFILE": str(tmp / "user"), "KAGGLE_CONFIG_DIR": str(tmp / "user" / ".kaggle")})
    (tmp / "home").mkdir()
    (tmp / "home" / "config.yaml").write_text(json.dumps({"projects": [], "port": port, "lang": "en", "watchdog": False}))
    subprocess.run([sys.executable, "-m", "runboard", "demo", str(tmp / "demo")], env=env, check=True, capture_output=True)
    server = subprocess.Popen([sys.executable, "-m", "runboard", "serve"], env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}/"
    proc = None
    try:
        for _ in range(150):
            try:
                urllib.request.urlopen(base + "api/me", timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        listing = api(base, "api/projects")
        key = listing["projects"][0]["key"]
        if (listing.get("backends") or {}).get("kaggle", {}).get("ok"):
            raise SystemExit("a Kaggle account is visible to the dashboard: it would show in the pictures")
        dbg = free_port()
        proc = subprocess.Popen([browser, "--headless=new", f"--remote-debugging-port={dbg}", f"--user-data-dir={tmp / 'browser'}",
                                 "--no-first-run", "--no-default-browser-check", f"--window-size={W},{H}", "--lang=en-US",
                                 "--hide-scrollbars", "--force-device-scale-factor=1", "--disable-gpu", "--no-sandbox",
                                 "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        tabs, end = [], time.time() + 60
        while not any(t.get("type") == "page" for t in tabs):
            if time.time() > end:
                raise SystemExit("the browser did not open its debugging port")
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{dbg}/json/list", timeout=2))
            except (OSError, ValueError):
                pass
            time.sleep(0.2)
        cdp = CDP(next(t for t in tabs if t["type"] == "page")["webSocketDebuggerUrl"])
        cdp.call("Page.enable")
        cdp.call("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1, mobile=False)

        # the study as the tutorial does it: lock the plan, then (with the page open) queue the six runs here
        api(base, f"api/p/{key}/lock", {})
        cdp.call("Page.navigate", url=base + f"#/p/{key}/overview")
        cdp.until("document.querySelector('.kpi')", 60)
        runs = [r["id"] for r in api(base, f"api/p/{key}")["runs"]]
        api(base, "api/queue", {"project": key, "runs": runs, "backend": "local"})
        epoch = r"(+((document.body.innerText.match(/epoch (\d+)\/40/) || [0, -1])[1]))"
        cdp.until(f"{epoch} >= 2", 60)  # the first run is training: its curve is already a line
        frames, epochs = [], []
        for _ in range(args.frames):
            epochs.append(cdp.js(epoch))
            frames.append(cdp.shot())
            time.sleep(args.every)
        args.out.mkdir(parents=True, exist_ok=True)
        frames[max(range(len(frames)), key=lambda i: epochs[i])].save(args.out / "overview.png", optimize=True)

        small = [f.resize((W * 3 // 4, H * 3 // 4)) for f in frames]
        pal = small[len(small) // 2].quantize(colors=128, method=2)  # one palette for every frame: no flicker
        gif = [f.quantize(palette=pal, dither=0) for f in small]
        gif[0].save(args.out / "demo.gif", save_all=True, append_images=gif[1:], duration=int(args.every * 1000),
                    loop=0, optimize=True)

        # once every run is done: the results
        end = time.time() + 240
        while time.time() < end:
            st = {r["id"]: r.get("status") for r in api(base, f"api/p/{key}")["runs"]}
            if all(v == "COMPLETE" for v in st.values()):
                break
            time.sleep(1)
        cdp.call("Page.navigate", url=base + f"#/p/{key}/results")
        cdp.until("document.querySelectorAll('table').length > 0", 60)
        time.sleep(2)
        cdp.shot().save(args.out / "results.png", optimize=True)
        for f in ("demo.gif", "overview.png", "results.png"):
            print(f"{args.out / f}  {(args.out / f).stat().st_size // 1024} KB")
        return 0
    finally:
        if proc:
            proc.terminate()
        subprocess.run([sys.executable, "-m", "runboard", "stop"], env=env, capture_output=True)
        server.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
