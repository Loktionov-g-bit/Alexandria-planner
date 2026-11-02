import httpx
import pytest

from app import proxy
from app.config import get_settings

from .test_stickers import team  # noqa: F401 - fixture


async def test_channel_assignment_and_cookie(client, team):  # noqa: F811
    ivan_id, ivan = team["ivan"]
    assert ivan.cookies.get("planner_channel") == "stable"  # set at login
    # department to beta: everybody in it follows, a personal override wins
    assert (await client.put("/api/admin/channels/departments/1", json={"channel": "beta"})).status_code == 204
    assert (await client.put(f"/api/admin/channels/users/{ivan_id}", json={"channel": "stable"})).status_code == 204
    ov = (await client.get("/api/admin/channels")).json()
    eff = {u["display_name"]: u["effective"] for u in ov["users"]}
    assert eff["Иван Петров"] == "stable" and eff["Пётр Сидоров"] == "beta" and ov["on_beta"] == 2
    petr = team["petr"][1]
    await petr.get("/api/auth/me")  # any authenticated request re-syncs the cookie
    assert petr.cookies.get("planner_channel") == "beta"
    # rollback: one button, overrides cleared
    await client.post("/api/admin/channels/all", json={"channel": "stable"})
    ov = (await client.get("/api/admin/channels")).json()
    assert ov["on_beta"] == 0 and all(u["channel"] is None for u in ov["users"])
    assert (await ivan.get("/api/admin/channels")).status_code == 403


@pytest.fixture
def with_beta(monkeypatch):
    """Stable with a beta behind it; the beta is a fake ASGI app reached through httpx."""
    async def beta_app(scope, receive, send):
        assert scope["type"] == "http"
        headers = dict(scope["headers"])
        body = f"beta:{scope['path']}:{headers.get(b'x-planner-proxied', b'').decode()}".encode()
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain"), (b"x-from", b"beta")]})
        await send({"type": "http.response.body", "body": body})

    monkeypatch.setattr(get_settings(), "beta_url", "http://beta:8000")
    monkeypatch.setattr(proxy, "_client", httpx.AsyncClient(transport=httpx.ASGITransport(app=beta_app)))


async def test_proxy_routes_beta_cookie(with_beta, tmp_path):
    from app import db as dbmod
    from app.db import Base
    from app.main import create_app

    dbmod.init_engine(f"sqlite+aiosqlite:///{tmp_path}/p.db")
    async with dbmod.get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as plain:
        assert (await plain.get("/api/setup")).json() == {"needed": True}  # no cookie: stable serves
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", cookies={"planner_channel": "beta"}) as c:
        r = await c.get("/api/setup")
        assert r.text == "beta:/api/setup:1" and r.headers["x-from"] == "beta"
        assert (await c.get("/api/health")).json()["channel"] == "stable"


async def test_proxy_falls_back_when_beta_down(monkeypatch, tmp_path):
    from app import db as dbmod
    from app.db import Base
    from app.main import create_app

    def refuse(request):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(get_settings(), "beta_url", "http://beta:8000")
    monkeypatch.setattr(proxy, "_client", httpx.AsyncClient(transport=httpx.MockTransport(refuse)))
    dbmod.init_engine(f"sqlite+aiosqlite:///{tmp_path}/p.db")
    async with dbmod.get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://t", cookies={"planner_channel": "beta"}) as c:
        assert (await c.get("/api/setup")).json() == {"needed": True}
