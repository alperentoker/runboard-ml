"""Who may use the dashboard.

- This computer (a loopback connection) needs nothing: no password, no login screen.
- Other devices (a tablet on the same Wi-Fi) only when network access is switched on, and only after pairing once:
  this computer shows a QR code / 6-digit code, the device gets a long random key in a cookie, and only a hash of that
  key is stored (~/.runboard/devices.json). Paired devices can be removed at any time.
- Every request is also checked against DNS rebinding (Host header) and cross-site requests (Origin), so a web page
  open in a browser cannot drive the dashboard.
"""
from __future__ import annotations

import hashlib
import ipaddress
import secrets
import socket
import threading
import time
from http.cookies import SimpleCookie

from . import home

COOKIE = "rb_device"
PAIR_SECONDS = 120
PAIR_TRIES = 5
_lock = threading.Lock()
_pairing: dict | None = None


# ---------------------------------------------------------------- devices

def _devices_file():
    return home.HOME / "devices.json"


def devices() -> list[dict]:
    return home.read_json(_devices_file(), [])


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def add_device(name: str) -> str:
    """Creates a device and returns its cookie value (the key itself is never stored)."""
    did, key = secrets.token_hex(4), secrets.token_urlsafe(32)
    with _lock:
        ds = devices()
        ds.append({"id": did, "name": name[:60] or "device", "hash": _hash(key),
                   "created": time.strftime("%Y-%m-%d %H:%M"), "last_seen": None})
        home.write_json(_devices_file(), ds)
    return f"{did}.{key}"


def remove_device(did: str) -> bool:
    with _lock:
        ds = devices()
        keep = [d for d in ds if d["id"] != did]
        home.write_json(_devices_file(), keep)
    return len(keep) != len(ds)


def device_for(cookie_value: str | None) -> dict | None:
    if not cookie_value or "." not in cookie_value:
        return None
    did, key = cookie_value.split(".", 1)
    h = _hash(key)
    for d in devices():
        if d["id"] == did and secrets.compare_digest(d["hash"], h):
            if not d.get("last_seen") or d["last_seen"][:16] != time.strftime("%Y-%m-%d %H:%M"):
                with _lock:
                    ds = devices()
                    for x in ds:
                        if x["id"] == did:
                            x["last_seen"] = time.strftime("%Y-%m-%d %H:%M")
                    home.write_json(_devices_file(), ds)
            return d
    return None


def device_name(user_agent: str) -> str:
    ua = user_agent or ""
    for key, name in (("iPad", "iPad"), ("iPhone", "iPhone"), ("Android", "Android"), ("Macintosh", "Mac"),
                      ("Windows", "Windows"), ("Linux", "Linux")):
        if key in ua:
            return name + (" tablet" if key == "Android" and "Mobile" not in ua else "")
    return "device"


# ---------------------------------------------------------------- pairing

def start_pairing() -> dict:
    """A new one-time pairing: a token for the QR link and a 6-digit code to type by hand. The previous one ends."""
    global _pairing
    with _lock:
        _pairing = {"token": secrets.token_urlsafe(16), "code": f"{secrets.randbelow(10**6):06d}",
                    "expires": time.time() + PAIR_SECONDS, "tries": 0}
        return dict(_pairing)


def redeem(token: str | None = None, code: str | None = None) -> bool:
    """True once for the current pairing's token or code; wrong codes count, and after PAIR_TRIES it is void."""
    global _pairing
    with _lock:
        p = _pairing
        if not p or time.time() > p["expires"]:
            _pairing = None
            return False
        ok = (token is not None and secrets.compare_digest(token, p["token"])) or \
             (code is not None and secrets.compare_digest(str(code).strip(), p["code"]))
        if ok:
            _pairing = None
            return True
        p["tries"] += 1
        if p["tries"] >= PAIR_TRIES:
            _pairing = None
        return False


def pairing_state() -> dict | None:
    p = _pairing
    return {"seconds": max(0, round(p["expires"] - time.time()))} if p and time.time() < p["expires"] else None


# ---------------------------------------------------------------- request checks

def _local_addresses() -> set[str]:
    out = {"127.0.0.1", "::1"}
    try:
        out.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    return out


LOCAL_ADDRESSES = _local_addresses()


def is_local_client(host: str | None) -> bool:
    if not host:
        return False
    host = host.removeprefix("::ffff:")
    return host in LOCAL_ADDRESSES or host.startswith("127.")


def host_allowed(host_header: str, extra: list[str]) -> bool:
    """DNS rebinding guard: a request must name this machine by IP, as localhost, by its own name or by a name listed
    in config.yaml (allowed_hosts, e.g. a Tailscale name). A web page's own domain is never accepted."""
    host = host_header.strip().lower()
    if host.startswith("["):
        host = host[1:host.find("]")]
    elif host.count(":") == 1:
        host = host.split(":")[0]
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    names = {"localhost", socket.gethostname().lower()} | {h.lower() for h in extra}
    return host in names or host.endswith(".localhost")


def cross_site(method: str, headers: dict[str, str]) -> bool:
    """CSRF guard for anything that changes state: another site's page may not send it."""
    if method in ("GET", "HEAD", "OPTIONS"):
        return False
    if headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
        return True
    origin = headers.get("origin")
    if origin and origin != "null":
        return origin.split("://", 1)[-1].lower() != headers.get("host", "").lower()
    return origin == "null"


def cookie_value(headers: dict[str, str]) -> str | None:
    c = SimpleCookie()
    try:
        c.load(headers.get("cookie", ""))
    except Exception:
        return None
    return c[COOKIE].value if COOKIE in c else None


def set_cookie_header(value: str) -> str:
    return f"{COOKIE}={value}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Strict"


CSP = ("default-src 'self'; script-src 'self'{scripts}; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
SECURITY_HEADERS = [
    (b"x-frame-options", b"DENY"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"content-security-policy", CSP.format(scripts="").encode()),
]


def page_csp(html: str) -> str:
    """The policy for one page: only the page's own scripts run, named by their SHA-256. A script that got into the page
    any other way (an injected tag or an onclick attribute) is refused by the browser."""
    import base64
    import re
    hashes = [base64.b64encode(hashlib.sha256(m.encode("utf-8")).digest()).decode()
              for m in re.findall(r"<script>(.*?)</script>", html, re.S)]
    return CSP.format(scripts="".join(f" 'sha256-{h}'" for h in hashes))

