import pyotp

from .conftest import STRONG


async def solo_setup(client):
    r = await client.post("/api/setup", json={"mode": "solo", "first_name": "Олег", "last_name": "Журавлёв", "password": STRONG})
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "solo"
    secret = (await client.post("/api/auth/totp/setup")).json()["secret"]
    assert (await client.post("/api/auth/totp/enable", json={"code": pyotp.TOTP(secret).now()})).status_code == 200


async def test_team_setup_needs_a_name(client):
    r = await client.post("/api/setup", json={"mode": "team", "first_name": "А", "last_name": "Б", "password": STRONG})
    assert r.json()["detail"] == "setup.team_name_required"


async def test_existing_team_install_reports_team(client, admin):
    assert (await client.get("/api/auth/me")).json()["mode"] == "team"


async def test_solo_diary(client):
    await solo_setup(client)
    me = (await client.get("/api/auth/me")).json()
    assert me["user"]["department_id"] is None
    # every sticker is personal and lands straight in its quadrant
    s = (await client.post("/api/stickers", json={"title": "Купить молоко", "urgent": True, "important": True})).json()
    assert s["kind"] == "personal" and s["my_quadrant"] == "do"
    assert [b["id"] for b in (await client.get("/api/board")).json()] == [s["id"]]
    # no colleagues in a diary
    r = await client.post("/api/admin/users", json={"login": "x1", "first_name": "Х", "last_name": "Ю", "password": STRONG})
    assert r.status_code == 409 and r.json()["detail"] == "mode.solo_no_people"


async def test_diary_grows_into_team_and_back(client):
    await solo_setup(client)
    assert (await client.post("/api/admin/mode", json={"mode": "team"})).json()["detail"] == "setup.team_name_required"
    assert (await client.post("/api/admin/mode", json={"mode": "team", "team": "Офис"})).json() == {"mode": "team"}
    me = (await client.get("/api/auth/me")).json()
    assert me["mode"] == "team" and me["user"]["department_id"] is not None and me["user"]["role"] == "manager"
    r = await client.post("/api/admin/users", json={"login": "ivan", "first_name": "Иван", "last_name": "Петров", "password": STRONG,
                                                    "department_id": me["user"]["department_id"]})
    assert r.status_code == 201
    # with a colleague the install cannot become a diary again
    assert (await client.post("/api/admin/mode", json={"mode": "solo"})).json()["detail"] == "mode.has_people"
    await client.patch(f"/api/admin/users/{r.json()['id']}", json={"is_active": False})
    assert (await client.post("/api/admin/mode", json={"mode": "solo"})).json() == {"mode": "solo"}
