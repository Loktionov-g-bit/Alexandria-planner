from datetime import date, timedelta

import pytest

from app import db as dbmod
from app import stickers as lc

from .conftest import STRONG, new_client


@pytest.fixture
async def team(app, client, admin):
    """boss (manager of dept 1, = `client`), ivan and petr (employees of dept 1)."""
    users = {}
    for login, name in (("ivan", "Иван Петров"), ("petr", "Пётр Сидоров")):
        r = await client.post("/api/admin/users", json={"login": login, "first_name": name.split()[0], "last_name": name.split()[1], "password": STRONG, "department_id": 1})
        assert r.status_code == 201, r.text
        c = await new_client(app)
        assert (await c.post("/api/auth/login", json={"login": login, "password": STRONG})).status_code == 200
        users[login] = (r.json()["id"], c)
    return users


async def act(c, sid, action, **kw):
    return await c.post(f"/api/stickers/{sid}/actions", json={"action": action, **kw})


async def test_default_recipient_is_department_manager(client, team):
    _, ivan = team["ivan"]
    r = await ivan.post("/api/stickers", json={"title": "Отпуск", "body": "С 10 по 20", "important": True})
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["status"] == "new" and s["quadrant"] == "plan" and s["my_role"] == "author"
    assert [u["display_name"] for u in s["recipients"]] == ["Босс Главный"]
    assert set(s["actions"]) == {"withdraw", "comment"}

    board = (await client.get("/api/board")).json()
    assert [(b["id"], b["my_quadrant"]) for b in board] == [(s["id"], None)]  # in the inbox
    assert (await ivan.get("/api/board")).json() == []
    assert [x["id"] for x in (await ivan.get("/api/stickers/sent")).json()] == [s["id"]]


async def test_privacy(client, team):
    _, ivan = team["ivan"]
    _, petr = team["petr"]
    sid = (await ivan.post("/api/stickers", json={"title": "Личное", "personal": True})).json()["id"]
    assert (await petr.get(f"/api/stickers/{sid}")).status_code == 404
    assert (await client.get(f"/api/stickers/{sid}")).status_code == 404  # manager does not see personal notes
    # employee → employee is invisible to the manager by default
    pid = (await ivan.post("/api/stickers", json={"title": "Коллеге", "recipient_ids": [team["petr"][0]]})).json()["id"]
    assert (await petr.get(f"/api/stickers/{pid}")).status_code == 200
    assert (await client.get(f"/api/stickers/{pid}")).status_code == 404
    assert (await ivan.post("/api/stickers", json={"title": "Себе", "recipient_ids": [team["ivan"][0]]})).status_code == 422


async def test_full_lifecycle(client, team):
    _, ivan = team["ivan"]
    petr_id, petr = team["petr"]
    sid = (await ivan.post("/api/stickers", json={"title": "Закупка", "urgent": True})).json()["id"]

    # drag from the inbox = triage
    r = await client.put(f"/api/stickers/{sid}/place", json={"quadrant": "do"})
    assert r.json()["status"] == "triaged" and r.json()["decided_quadrant"] == "do"
    assert "withdraw" not in (await ivan.get(f"/api/stickers/{sid}")).json()["actions"]

    assert (await act(client, sid, "ask")).status_code == 422  # question needs text
    s = (await act(client, sid, "ask", text="Сколько штук?")).json()
    assert s["status"] == "needs_info"
    assert (await act(client, sid, "answer", text="10")).status_code == 409  # only the author answers
    s = (await act(ivan, sid, "answer", text="10 штук")).json()
    assert s["status"] == "in_progress" and [c["kind"] for c in s["thread"]] == ["question", "answer"]

    s = (await act(client, sid, "delegate", user_id=petr_id, text="Займись")).json()
    assert s["status"] == "delegated"
    pb = (await petr.get("/api/board")).json()
    assert [(b["id"], b["my_role"], b["my_quadrant"]) for b in pb] == [(sid, "delegate", "do")]
    # the delegate rearranges own board, the manager's decision stays
    await petr.put(f"/api/stickers/{sid}/place", json={"quadrant": "plan"})
    s = (await client.get(f"/api/stickers/{sid}")).json()
    assert s["decided_quadrant"] == "do"
    assert {p["user"]["id"]: p["quadrant"] for p in s["placements"]}[petr_id] == "plan"

    assert (await act(petr, sid, "report", text="Заказал")).status_code == 200
    assert (await act(petr, sid, "resolve", outcome="done", text="x")).status_code == 409
    s = (await act(client, sid, "resolve", outcome="done", text="Принято")).json()
    assert s["status"] == "resolved" and s["outcome"] == "done"
    assert (await petr.get("/api/board")).json() == [] and (await client.get("/api/board")).json() == []

    s = (await act(ivan, sid, "confirm")).json()
    assert s["status"] == "closed"
    assert [x["id"] for x in (await ivan.get("/api/stickers/archive", params={"q": "Закуп"})).json()] == [sid]  # SQLite folds only ASCII case
    s = (await act(ivan, sid, "reopen", text="Пришло 9")).json()
    assert s["status"] == "in_progress" and s["outcome"] is None
    actions = [h["action"] for h in s["history"]]
    assert actions[0] == "created" and "quadrant" in actions and actions.count("status") >= 7


async def test_withdraw_reject_snooze(client, team):
    _, ivan = team["ivan"]
    a = (await ivan.post("/api/stickers", json={"title": "A"})).json()["id"]
    assert (await act(ivan, a, "withdraw")).json()["status"] == "withdrawn"
    assert (await client.get("/api/board")).json() == []

    b = (await ivan.post("/api/stickers", json={"title": "B"})).json()["id"]
    assert (await act(client, b, "reject")).status_code == 422
    s = (await act(client, b, "reject", text="Не актуально")).json()
    assert s["status"] == "rejected" and s["reject_reason"] == "Не актуально"

    c = (await ivan.post("/api/stickers", json={"title": "C"})).json()["id"]
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert (await act(client, c, "snooze", until=date.today().isoformat())).status_code == 422
    assert (await act(client, c, "snooze", until=tomorrow)).json()["status"] == "snoozed"
    assert (await client.get("/api/board")).json() == []
    async with dbmod.sessionmaker()() as db:
        assert (await lc.tick(db, date.today() + timedelta(days=1)))["woken"] == 1
    board = (await client.get("/api/board")).json()
    assert [(x["id"], x["status"]) for x in board] == [(c, "triaged")]


async def test_deadline_escalation_keeps_importance(client, team):
    _, ivan = team["ivan"]
    soon = (date.today() + timedelta(days=2)).isoformat()
    later = (date.today() + timedelta(days=30)).isoformat()
    a = (await ivan.post("/api/stickers", json={"title": "Скоро", "important": True, "deadline": soon})).json()["id"]
    b = (await ivan.post("/api/stickers", json={"title": "Потом", "deadline": later})).json()["id"]
    await client.put(f"/api/stickers/{a}/place", json={"quadrant": "plan"})
    async with dbmod.sessionmaker()() as db:
        assert (await lc.tick(db))["escalated"] == 1
        assert (await lc.tick(db))["escalated"] == 0  # only once
    s = (await client.get(f"/api/stickers/{a}")).json()
    assert s["escalated"] and s["quadrant"] == "do" and s["my_quadrant"] == "do" and s["author_quadrant"] == "plan"
    assert not (await client.get(f"/api/stickers/{b}")).json()["escalated"]


async def test_autoclose(client, team):
    _, ivan = team["ivan"]
    sid = (await ivan.post("/api/stickers", json={"title": "X"})).json()["id"]
    await act(client, sid, "resolve", outcome="fyi", text="Ок")
    async with dbmod.sessionmaker()() as db:
        assert (await lc.tick(db))["closed"] == 0
        s = await db.get(lc.Sticker, sid)
        s.resolved_at = lc.utcnow() - timedelta(days=4)
        await db.commit()
        assert (await lc.tick(db))["closed"] == 1


async def test_personal_sticker(team):
    _, ivan = team["ivan"]
    s = (await ivan.post("/api/stickers", json={"title": "Позвонить", "urgent": True, "important": True, "personal": True})).json()
    assert s["status"] == "triaged" and s["my_quadrant"] == "do" and s["my_role"] == "author"
    assert set(s["actions"]) == {"resolve", "comment"}
    assert [x["id"] for x in (await ivan.get("/api/board")).json()] == [s["id"]]
    assert (await ivan.get("/api/stickers/sent")).json() == []
    s = (await ivan.patch(f"/api/stickers/{s['id']}", json={"urgent": False})).json()
    assert s["my_quadrant"] == "plan"
    s = (await act(ivan, s["id"], "resolve")).json()
    assert s["status"] == "closed"


async def test_share_and_deadline_edit(client, team):
    ivan_id, ivan = team["ivan"]
    petr_id, petr = team["petr"]
    sid = (await ivan.post("/api/stickers", json={"title": "Общее"})).json()["id"]
    assert (await act(client, sid, "share", user_id=petr_id)).status_code == 200
    s = (await petr.get(f"/api/stickers/{sid}")).json()
    assert s["my_role"] == "viewer" and s["actions"] == ["comment"]
    assert [x["id"] for x in (await petr.get("/api/stickers/shared")).json()] == [sid]
    assert (await petr.get("/api/board")).json() == []
    assert (await petr.patch(f"/api/stickers/{sid}", json={"deadline": "2030-01-01"})).status_code == 403
    r = await client.patch(f"/api/stickers/{sid}", json={"deadline": "2030-01-01"})
    assert r.json()["deadline"] == "2030-01-01"
    assert (await client.patch(f"/api/stickers/{sid}", json={"title": "Чужое"})).status_code == 403


async def test_attachments(client, team):
    _, ivan = team["ivan"]
    _, petr = team["petr"]
    sid = (await ivan.post("/api/stickers", json={"title": "Счёт"})).json()["id"]
    r = await ivan.post(f"/api/stickers/{sid}/attachments", files={"file": ("../../счёт.pdf", b"%PDF-1.4 test", "application/pdf")})
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["filename"] == "счёт.pdf" and a["size"] == 13
    r = await client.get(f"/api/attachments/{a['id']}")
    assert r.status_code == 200 and r.content == b"%PDF-1.4 test"
    assert r.headers["content-security-policy"] == "sandbox"
    assert (await petr.get(f"/api/attachments/{a['id']}")).status_code == 404
    r = await ivan.post(f"/api/stickers/{sid}/attachments", files={"file": ("x.html", b"<script>", "text/html")})
    r = await client.get(f"/api/attachments/{r.json()['id']}")
    assert r.headers["content-type"] == "application/octet-stream" and r.headers["content-disposition"].startswith("attachment")
