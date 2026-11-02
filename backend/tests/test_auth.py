import pyotp

from .conftest import STRONG, new_client


async def test_setup_only_once(client, admin):
    assert (await client.get("/api/setup")).json() == {"needed": False}
    r = await client.post(
        "/api/setup", json={"department": "X", "login": "evil", "first_name": "E", "last_name": "V", "password": STRONG}
    )
    assert r.status_code == 409


async def test_setup_rejects_weak_password(client):
    r = await client.post("/api/setup", json={"department": "X", "login": "a1", "first_name": "A", "last_name": "B", "password": "123"})
    assert r.status_code == 422
    assert "password.too_short" in r.json()["detail"]


async def test_admin_cannot_use_app_before_2fa(client):
    await client.post("/api/setup", json={"department": "Офис", "login": "boss", "first_name": "Б", "last_name": "Г", "password": STRONG})
    assert (await client.get("/api/admin/users")).status_code == 401


async def test_login_with_totp(app, admin):
    c = await new_client(app)
    r = await c.post("/api/auth/login", json={"login": "boss", "password": STRONG})
    assert r.json()["pending"] == "totp"
    assert (await c.get("/api/admin/users")).status_code == 401
    assert (await c.post("/api/auth/totp", json={"code": "000000"})).status_code == 401
    r = await c.post("/api/auth/totp", json={"code": pyotp.TOTP(admin).now()})
    assert r.json()["verified"] is True
    assert (await c.get("/api/admin/users")).status_code == 200


async def test_lockout_and_journal(app, client, admin):
    c = await new_client(app)
    for _ in range(5):
        assert (await c.post("/api/auth/login", json={"login": "boss", "password": "wrong"})).status_code == 401
    r = await c.post("/api/auth/login", json={"login": "boss", "password": STRONG})
    assert r.status_code == 429
    events = (await client.get("/api/admin/logins")).json()
    assert events[0]["reason"] == "locked"
    assert sum(e["reason"] == "bad_password" for e in events) == 5


async def test_employee_without_2fa_and_permissions(app, client, admin):
    r = await client.post(
        "/api/admin/users",
        json={"login": "ivan", "first_name": "Иван", "last_name": "Петров", "password": STRONG, "department_id": 1},
    )
    assert r.status_code == 201, r.text
    c = await new_client(app)
    r = await c.post("/api/auth/login", json={"login": "ivan", "password": STRONG})
    assert r.json()["verified"] is True
    assert (await c.get("/api/admin/users")).status_code == 403
    assert (await c.patch("/api/profile", json={"theme": "dark"})).json()["theme"] == "dark"
    # deactivation kills the session
    await client.patch("/api/admin/users/2", json={"is_active": False})
    assert (await c.get("/api/auth/me")).status_code == 401


async def test_password_change_and_logout(client, admin):
    r = await client.post("/api/auth/password", json={"old_password": STRONG, "new_password": "New-password-77"})
    assert r.status_code == 204
    await client.post("/api/auth/logout")
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_login_generated_from_name(client, admin):
    r = await client.get("/api/admin/login-suggestion", params={"first_name": "Олег", "last_name": "Журавлёв"})
    assert r.json() == {"login": "o.zhuravlev"}
    body = {"first_name": "Олег", "last_name": "Журавлёв", "password": STRONG, "department_id": 1}
    u = (await client.post("/api/admin/users", json=body)).json()
    assert (u["login"], u["first_name"], u["last_name"], u["display_name"]) == ("o.zhuravlev", "Олег", "Журавлёв", "Олег Журавлёв")
    # namesake gets the next free login
    assert (await client.post("/api/admin/users", json=body)).json()["login"] == "o.zhuravlev2"
    r = await client.get("/api/admin/login-suggestion", params={"first_name": "Щука", "last_name": "Хрущёв-Ёжиков"})
    assert r.json() == {"login": "s.khrushchev-ezhikov"}
    # renaming keeps display_name in sync
    r = await client.patch(f"/api/admin/users/{u['id']}", json={"last_name": "Иванов"})
    assert r.json()["display_name"] == "Олег Иванов"


def test_logins_and_passwords_in_every_alphabet():
    from app.names import base_login
    from app.security import password_problems

    assert base_login("Олег", "Журавлёв") == "o.zhuravlev"
    assert base_login("Аліна", "Ўладава") == "a.uladava"
    assert base_login("Айгүл", "Әбдіқадырова") == "a.abdikadyrova"
    assert base_login("გიორგი", "ბერიძე") == "g.beridze"
    assert base_login("Jiří", "Čapek") == "j.capek"
    assert base_login("Jürgen", "Müller-Weiß") == "j.mueller-weiss"
    assert "password.too_simple" not in password_problems("ČáPéKövá2026")
    assert "password.too_simple" not in password_problems("გიორგი-2026-ok")


def test_every_locale_has_complete_server_texts():
    """Raw files, not the merged tables: a missing key would silently show Russian."""
    import json
    import re
    from pathlib import Path

    from app.locales import LOCALES, texts

    def flat(d, p=""):
        return {k2: v2 for k, v in d.items() for k2, v2 in (flat(v, f"{p}{k}.").items() if isinstance(v, dict) else [(p + k, v)])}

    def slots(v):
        return sorted(re.findall(r"\{\w*\}", json.dumps(v, ensure_ascii=False))), len(v) if isinstance(v, list) else 0

    folder = Path(__file__).parents[1] / "app" / "i18n"
    ru = flat(json.loads((folder / "ru.json").read_text(encoding="utf-8")))
    for loc in LOCALES:
        other = flat(json.loads((folder / f"{loc}.json").read_text(encoding="utf-8")))
        assert other.keys() == ru.keys(), (loc, other.keys() ^ ru.keys())
        for k, v in ru.items():
            assert slots(other[k]) == slots(v), (loc, k)
    for section in ("notify", "report", "telegram"):
        assert set(texts(section)) == set(LOCALES)
