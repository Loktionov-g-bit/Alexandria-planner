"""WireGuard backup route to Telegram: config upload, route choice and fallback."""
import base64
import io
import os
import zipfile

import httpx
import pytest

from app.telegram import api as tgapi
from app.telegram import tunnel as tun

PRIV = base64.b64encode(os.urandom(32)).decode()
PUB = base64.b64encode(os.urandom(32)).decode()
CONF = f"""[Interface]
PrivateKey = {PRIV}
Address = 10.66.0.2/32, fd00::2/128
DNS = 1.1.1.1
PostUp = iptables -A FORWARD -j ACCEPT
Table = off

[Peer]
PublicKey = {PUB}
Endpoint = vpn.example.org:51820
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
"""


def zipped(files: dict[str, str]) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return b.getvalue()


def test_parse_conf_strips_hooks_and_keeps_peers():
    two = CONF + f"\n[Peer]\nPublicKey = {PUB}\nEndpoint = 203.0.113.7:443\n"
    p = tun.parse_upload("home.conf", two.encode())
    assert p.endpoint == "vpn.example.org:51820" and p.address == "10.66.0.2/32" and p.name == "home.conf"
    assert "PostUp" not in p.text and "Table" not in p.text and "iptables" not in p.text
    assert p.text.count("[Peer]") == 2 and "Endpoint = 203.0.113.7:443" in p.text
    assert "AllowedIPs = 0.0.0.0/0, ::/0" in p.text  # second peer had none
    assert f"PrivateKey = {PRIV}" in p.text


def test_parse_zip_variants():
    p = tun.parse_upload("provider.zip", zipped({"__MACOSX/._x.conf": "junk", "configs/nl-ams.conf": CONF, "README.txt": "hi"}))
    assert p.name == "nl-ams.conf"
    for files, err in (({"a.conf": CONF, "b.conf": CONF}, "many_conf"), ({"readme.txt": "x"}, "no_conf")):
        with pytest.raises(tun.TunnelError) as e:
            tun.parse_upload("x.zip", zipped(files))
        assert e.value.args[0] == err
    with pytest.raises(tun.TunnelError) as e:
        tun.parse_upload("x.zip", b"PK\x03\x04 broken")
    assert e.value.args[0] == "bad_zip"


@pytest.mark.parametrize("text,err", [
    ("hello", "bad_format"),
    ("[Interface]\nAddress = 10.0.0.2/32\n[Peer]\nPublicKey = x\nEndpoint = h:1\n", "bad_format"),
    (CONF.replace("[Peer]", "Jc = 4\nJmin = 40\n[Peer]"), "amnezia"),
    (CONF.replace("Endpoint = vpn.example.org:51820\n", ""), "bad_format"),
])
def test_parse_rejects(text, err):
    with pytest.raises(tun.TunnelError) as e:
        tun.parse_upload("x.conf", text.encode())
    assert e.value.args[0] == err


def test_route_order(monkeypatch):
    t = tun.Tunnel()
    assert t.routes() == ["direct"]  # nothing uploaded
    monkeypatch.setattr(tun, "binary", lambda: "sh")
    t.conf, t.mode = "x", "auto"
    assert t.routes() == ["direct", "tunnel"]
    t.mark("tunnel", True)
    assert t.route == "tunnel" and t.routes() == ["tunnel", "direct"]  # direct is down: tunnel first for a while
    t.tunnel_since -= t.RETRY_DIRECT + 1
    assert t.routes() == ["direct", "tunnel"]  # ...then give direct another chance
    t.mark("direct", True)
    assert t.route == "direct"
    t.mode = "always"
    assert t.routes() == ["tunnel"]
    t.mode = "off"
    assert t.routes() == ["direct"]


async def test_api_falls_back_to_tunnel_and_back(monkeypatch):
    blocked = {"on": True}

    def direct(req):
        if blocked["on"]:
            raise httpx.ConnectTimeout("blocked", request=req)
        return httpx.Response(200, json={"ok": True, "result": {"via": "direct"}})

    def via(req):
        return httpx.Response(200, json={"ok": True, "result": {"via": "tunnel"}})

    t = tun.Tunnel(conf="x", mode="auto", port=1)
    monkeypatch.setattr(tgapi, "tunnel", t)
    monkeypatch.setattr(tun, "binary", lambda: "sh")

    async def ensure():
        return True
    monkeypatch.setattr(t, "ensure", ensure)
    a = tgapi.TelegramAPI("1:x", None)
    a.client = httpx.AsyncClient(transport=httpx.MockTransport(direct))
    a._proxied = lambda: httpx.AsyncClient(transport=httpx.MockTransport(via))
    assert await a.call("getMe") == {"via": "tunnel"} and t.route == "tunnel"
    blocked["on"] = False
    assert await a.call("getMe") == {"via": "tunnel"}  # stays on the tunnel for a while
    t.tunnel_since -= t.RETRY_DIRECT + 1
    assert await a.call("getMe") == {"via": "direct"} and t.route == "direct"
    # no tunnel and no direct route: a network error, without the token in it
    t.mode = "off"
    blocked["on"] = True
    with pytest.raises(tgapi.TelegramError) as e:
        await a.call("getMe")
    assert str(e.value) == "network: ConnectTimeout"


async def test_admin_upload_mode_and_delete(client, admin):
    r = await client.put("/api/admin/telegram/tunnel", files={"file": ("vpn.zip", zipped({"wg0.conf": CONF}), "application/zip")})
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["configured"] and st["endpoint"] == "vpn.example.org:51820" and st["mode"] == "auto" and st["name"] == "wg0.conf"
    assert PRIV not in r.text and "conf" not in st
    assert PRIV not in (await client.get("/api/admin/telegram/tunnel")).text
    assert (await client.patch("/api/admin/telegram/tunnel", json={"mode": "always"})).json()["mode"] == "always"
    assert (await client.patch("/api/admin/telegram/tunnel", json={"mode": "sometimes"})).status_code == 422
    bad = await client.put("/api/admin/telegram/tunnel", files={"file": ("x.conf", CONF.replace("[Peer]", "H1 = 1\n[Peer]").encode())})
    assert bad.status_code == 422 and bad.json()["detail"] == "tunnel.amnezia"
    assert (await client.delete("/api/admin/telegram/tunnel")).status_code == 204
    assert (await client.get("/api/admin/telegram/tunnel")).json()["configured"] is False
    await tun.tunnel.configure(None)
