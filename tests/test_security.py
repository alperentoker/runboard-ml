import time

import pytest
import yaml
from fastapi.testclient import TestClient

from runboard import access, home


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setattr(home, "HOME", tmp_path / ".rb")
    monkeypatch.setattr(home, "CONFIG", tmp_path / ".rb" / "config.yaml")
    home.save_config({"projects": [], "port": 8000, "lan": True})
    from runboard import server
    return server


def client(server, local: bool, host: str = "127.0.0.1:8000") -> TestClient:
    ip = "127.0.0.1" if local else "192.168.1.50"
    return TestClient(server.app, base_url=f"http://{host}", client=(ip, 50000))


def pair(server) -> TestClient:
    code = client(server, True).post("/api/devices/pair").json()["code"]
    tablet = client(server, False, "192.168.1.10:8000")
    assert tablet.post("/api/pair", json={"code": code, "name": "test tablet"}).status_code == 200
    return tablet


def test_this_computer_needs_no_login(server):
    c = client(server, True)
    assert c.get("/api/me").json()["local"] is True
    assert c.get("/").status_code == 200


def test_other_devices_need_pairing(server):
    c = client(server, False, "192.168.1.10:8000")
    assert c.get("/api/projects").status_code == 401
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/pair"
    assert c.get("/pair").status_code == 200  # the pairing page itself is reachable


def test_dns_rebinding_host_refused(server):
    assert client(server, True, "evil.example.com").get("/api/projects").status_code == 403
    assert client(server, True, "localhost:8000").get("/api/me").status_code == 200


def test_cross_site_post_refused(server):
    c = client(server, True)
    r = c.post("/api/system/restart", headers={"Origin": "https://evil.example.com"})
    assert r.status_code == 403
    r = c.post("/api/devices/pair", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_pairing_with_code_then_device_works(server):
    tablet = pair(server)
    me = tablet.get("/api/me").json()
    assert me["local"] is False and me["device"]["name"] == "test tablet"
    assert tablet.get("/api/projects").status_code == 200
    stored = (home.HOME / "devices.json").read_text()
    assert tablet.cookies[access.COOKIE].split(".", 1)[1] not in stored  # only a hash is kept


def test_qr_link_pairs_once(server):
    url = client(server, True).post("/api/devices/pair").json()["url"]
    token = url.split("c=", 1)[1]
    t1 = client(server, False, "192.168.1.10:8000")
    r = t1.get(f"/pair?c={token}", follow_redirects=False)
    assert r.status_code == 303 and access.COOKIE in r.headers["set-cookie"]
    t2 = client(server, False, "192.168.1.10:8000")
    assert access.COOKIE not in (t2.get(f"/pair?c={token}", follow_redirects=False).headers.get("set-cookie") or "")


def test_wrong_codes_void_the_pairing(server):
    code = client(server, True).post("/api/devices/pair").json()["code"]
    t = client(server, False, "192.168.1.10:8000")
    for _ in range(access.PAIR_TRIES):
        assert t.post("/api/pair", json={"code": "000000" if code != "000000" else "111111"}).status_code == 400
    assert t.post("/api/pair", json={"code": code}).status_code == 400  # too many tries: the right code is void too


def test_expired_code_refused(server, monkeypatch):
    code = client(server, True).post("/api/devices/pair").json()["code"]
    real = time.time
    monkeypatch.setattr(access.time, "time", lambda: real() + access.PAIR_SECONDS + 1)
    assert client(server, False, "192.168.1.10:8000").post("/api/pair", json={"code": code}).status_code == 400


def test_tablet_cannot_touch_credentials_or_add_projects(server):
    tablet = pair(server)
    assert tablet.post("/api/connections/kaggle", json={"token": "x" * 30}).status_code == 403
    assert tablet.post("/api/projects", json={"path": "C:/"}).status_code == 403
    assert tablet.get("/api/fs").status_code == 403
    assert tablet.post("/api/devices/pair").status_code == 403
    assert tablet.post("/api/system/lan", json={"on": False}).status_code == 403


def test_removed_device_is_locked_out(server):
    tablet = pair(server)
    did = tablet.get("/api/me").json()["device"]["id"]
    assert client(server, True).delete(f"/api/devices/{did}").status_code == 200
    assert tablet.get("/api/projects").status_code == 401


def test_pairing_needs_network_access_on(server):
    cfg = home.config()
    cfg["lan"] = False
    home.save_config(cfg)
    assert client(server, True).post("/api/devices/pair").status_code == 400


def test_security_headers(server):
    r = client(server, True).get("/")
    assert r.headers["x-frame-options"] == "DENY" and "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_secrets_masked_in_logs():
    from runboard.progress import redact
    assert redact("token: KGAT_abcdef1234567") == "token: ***"
    assert "abc123456789" not in redact("export KAGGLE_API_TOKEN=abc123456789")
    assert redact("max_tokens: 4096") == "max_tokens: 4096"


def test_pages_run_only_their_own_scripts(server):
    import base64
    import hashlib
    import re
    c = client(server, True)
    for path in ("/", "/mini", "/pair"):
        r = c.get(path)
        csp = r.headers["content-security-policy"]
        assert "'unsafe-inline'" not in csp.split("script-src", 1)[1].split(";", 1)[0], path
        for script in re.findall(r"<script>(.*?)</script>", r.text, re.S):
            assert "'sha256-" + base64.b64encode(hashlib.sha256(script.encode()).digest()).decode() + "'" in csp
        assert not re.search(r"\son[a-z]+=\"", r.text), f"{path} has an inline handler"
