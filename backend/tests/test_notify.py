from app import db as dbmod
from app import dispatch, push

from .test_stickers import act, team  # noqa: F401 - fixture


async def feed(c):
    return (await c.get("/api/notifications")).json()


async def test_who_hears_what(client, team):  # noqa: F811
    ivan_id, ivan = team["ivan"]
    petr_id, petr = team["petr"]
    sid = (await ivan.post("/api/stickers", json={"title": "Закупка", "body": "Нужно 10 стульев"})).json()["id"]
    f = await feed(client)
    assert f["unread"] == 1
    n = f["items"][0]
    assert n["title"] == "Иван Петров: новый стикер" and n["body"].startswith(f"№{sid} Закупка")
    assert n["created_at"].endswith(("Z", "+00:00"))  # never zone-less: browsers would read it as local time
    assert (await feed(ivan))["unread"] == 0  # the actor is never notified

    await client.put(f"/api/stickers/{sid}/place", json={"quadrant": "plan"})
    assert (await feed(ivan))["items"][0]["title"] == "Стикер разобран: важно, не срочно"
    await act(client, sid, "ask", text="Каких стульев?")
    n = (await feed(ivan))["items"][0]
    assert n["title"] == "Босс Главный: вопрос" and n["body"].endswith("Каких стульев?")
    await act(ivan, sid, "answer", text="Офисных")
    assert (await feed(client))["items"][0]["title"] == "Иван Петров: ответ"
    assert (await act(client, sid, "delegate", user_id=petr_id)).status_code == 200
    assert (await feed(petr))["items"][0]["title"] == "Вам поручен стикер"
    assert (await feed(ivan))["items"][0]["title"] == "Стикер передан: Пётр Сидоров"
    await act(client, sid, "resolve", outcome="approved", text="Ок")
    for c in (ivan, petr):
        assert (await feed(c))["items"][0]["title"] == "Решение: согласовано"


async def test_personal_is_silent_and_read_marks(client, team):  # noqa: F811
    _, ivan = team["ivan"]
    await ivan.post("/api/stickers", json={"title": "Себе", "personal": True})
    assert (await feed(client))["unread"] == 0
    await ivan.post("/api/stickers", json={"title": "A"})
    await ivan.post("/api/stickers", json={"title": "B"})
    f = await feed(client)
    assert f["unread"] == 2
    await client.post("/api/notifications/read", json={"ids": [f["items"][0]["id"]]})
    assert (await feed(client))["unread"] == 1
    await client.post("/api/notifications/read", json={})
    assert (await feed(client))["unread"] == 0


async def test_dispatch_push(client, team, monkeypatch):  # noqa: F811
    _, ivan = team["ivan"]
    sent = []

    async def fake_send(db, user_id, payload):
        sent.append((user_id, payload))
        return True

    monkeypatch.setattr(push, "send", fake_send)
    sub = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}}
    assert (await client.post("/api/push/subscribe", json=sub)).status_code == 204
    sid = (await ivan.post("/api/stickers", json={"title": "Push me"})).json()["id"]
    async with dbmod.sessionmaker()() as db:
        assert await dispatch.deliver(db) == 1
        assert await dispatch.deliver(db) == 0  # nothing twice
    (uid, payload), = sent
    assert payload["title"].endswith("новый стикер") and payload["url"] == f"./?s={sid}"

    # switched off in the profile: delivery is skipped
    await client.patch("/api/profile", json={"notify_push": False})
    await ivan.post("/api/stickers", json={"title": "Silent"})
    async with dbmod.sessionmaker()() as db:
        await dispatch.deliver(db)
    assert len(sent) == 1


async def test_push_key_is_stable(client, admin):
    k1 = (await client.get("/api/push/key")).json()["key"]
    k2 = (await client.get("/api/push/key")).json()["key"]
    assert k1 == k2 and len(k1) > 80
