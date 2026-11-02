import os

import pyotp
import pytest
from httpx import ASGITransport, AsyncClient

os.environ["PLANNER_BASE_URL"] = "http://testserver"
os.environ["PLANNER_STATIC_DIR"] = "/nonexistent"
os.environ["PLANNER_SCHEDULER_MINUTES"] = "0"

from app import db as dbmod  # noqa: E402
from app import models  # noqa: E402,F401
from app.db import Base  # noqa: E402

STRONG = "Correct-horse-42"


@pytest.fixture
async def app(tmp_path, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    # PLANNER_TEST_DATABASE_URL=postgresql+asyncpg://... runs the suite on Postgres (schema is wiped per test)
    url = os.environ.get("PLANNER_TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{tmp_path}/t.db"
    dbmod.init_engine(url)
    async with dbmod.get_engine().begin() as conn:
        if url.startswith("postgresql"):
            await conn.exec_driver_sql("DROP SCHEMA public CASCADE")
            await conn.exec_driver_sql("CREATE SCHEMA public")
        await conn.run_sync(Base.metadata.create_all)
    from app.main import create_app

    yield create_app()
    await dbmod.get_engine().dispose()


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c


async def new_client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


@pytest.fixture
async def admin(client):
    """Run the setup wizard and finish mandatory 2FA enrollment. Returns the TOTP secret."""
    r = await client.post(
        "/api/setup",
        json={"department": "Офис", "login": "boss", "first_name": "Босс", "last_name": "Главный", "password": STRONG},
    )
    assert r.status_code == 200, r.text
    assert r.json()["pending"] == "totp_setup"
    secret = (await client.post("/api/auth/totp/setup")).json()["secret"]
    r = await client.post("/api/auth/totp/enable", json={"code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200, r.text
    return secret
