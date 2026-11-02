from datetime import datetime, timezone

import pytest

from app import db as dbmod
from app import digest, dispatch
from app.telegram import bot as botmod
from app.api import telegram as tgapi

from .test_stickers import team  # noqa: F401 - fixture


class FakeAPI:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.next_id = 100

    async def call(self, method, **params):
        self.calls.append((method, params))
        if method == "getMe":
            return {"id": 1, "username": "planner_test_bot"}
        self.next_id += 1
        return {"message_id": self.next_id}

    async def download(self, file_id, limit):
        return b"\x89PNG fake"

    async def close(self):
        pass

    def sent(self, chat_id=None):
        return [p for m, p in self.calls if m == "sendMessage" and (chat_id is None or p["chat_id"] == chat_id)]

    def last(self, chat_id):
        return self.sent(chat_id)[-1]


def msg(chat, text=None, *, uid=None, kind="private", **extra):
    m = {"message_id": 1, "chat": {"id": chat, "type": kind}, "from": {"id": uid or chat, "username": f"u{chat}"}}
    if text is not None:
        m["text"] = text
    m.update(extra)
    return {"message": m}


def cb(chat, data, message=None):
    return {"callback_query": {"id": "cq", "from": {"id": chat}, "data": data,
                               "message": message or {"message_id": 5, "chat": {"id": chat}, "text": "x"}}}


def buttons(markup):
    return [b.get("callback_data") for row in (markup or {}).get("inline_keyboard", []) for b in row]


@pytest.fixture
async def tg(client, team, monkeypatch):  # noqa: F811
    async def fake_me(token):
        return {"id": 1, "username": "planner_test_bot"}

    monkeypatch.setattr(tgapi, "get_me", fake_me)
    r = await client.put("/api/admin/telegram", json={"token": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcd"})
    assert r.json() == {"configured": True, "username": "planner_test_bot", "token": "123456:…abcd"}
    api = FakeAPI()
    bot = botmod.Bot(api, dbmod.sessionmaker(), "planner_test_bot")
    monkeypatch.setitem(dispatch.channels, "telegram", bot.notify)

    async def link(c, chat):
        code = (await c.post("/api/telegram/link")).json()["code"]
        await bot.handle(msg(chat, f"/start {code}"))
    await link(client, 222)          # boss
    await link(team["ivan"][1], 111)  # ivan
    return bot, api


async def deliver():
    async with dbmod.sessionmaker()() as db:
        await dispatch.deliver(db)


async def test_link_and_create_from_dm(client, team, tg):  # noqa: F811
    bot, api = tg
    assert "Telegram привязан" in api.sent(111)[-2]["text"]
    menu = api.last(111)["reply_markup"]["keyboard"]
    assert [b["text"] for row in menu for b in row] == ["Сделать сейчас", "Запланировать", "Поручить", "Не делать", "Мои стикеры", "Написать стикер", "Обстановка"]
    me = (await team["ivan"][1].get("/api/auth/me")).json()["user"]
    assert me["telegram_linked"] and me["telegram_username"] == "u111"

    await bot.handle(msg(111, "Купить бумагу\nА4, 5 пачек"))
    reply = api.last(111)
    assert reply["text"].startswith("Стикер №") and "Босс Главный" in reply["text"]
    sid = int(reply["text"].split("№")[1].split()[0])
    assert buttons(reply["reply_markup"]) == [f"f:{sid}:u", f"f:{sid}:i"]
    await bot.handle(cb(111, f"f:{sid}:u", {"message_id": 7, "chat": {"id": 111}, "text": reply["text"], "reply_markup": reply["reply_markup"]}))
    s = (await client.get(f"/api/stickers/{sid}")).json()
    assert s["title"] == "Купить бумагу" and s["body"] == "А4, 5 пачек" and s["author_quadrant"] == "delegate"

    # the manager gets "you have a new sticker" with one View button; View turns it into the card with the 4 quadrants only
    await deliver()
    note = api.last(222)
    assert "Вам назначен новый стикер" in note["text"] and f"№{sid} Купить бумагу" in note["text"]
    assert buttons(note["reply_markup"]) == [f"s:{sid}"]
    await bot.handle(cb(222, f"s:{sid}"))
    edit = [p for m, p in api.calls if m == "editMessageText"][-1]
    assert f"№{sid} Купить бумагу" in edit["text"]
    assert buttons(edit["reply_markup"]) == [f"q:{sid}:do", f"q:{sid}:plan", f"q:{sid}:delegate", f"q:{sid}:drop"]


async def test_full_flow_from_telegram(client, team, tg):  # noqa: F811
    bot, api = tg
    await bot.handle(msg(111, "Командировка"))
    sid = (await client.get("/api/board")).json()[0]["id"]
    await bot.handle(cb(222, f"q:{sid}:plan"))
    assert (await client.get(f"/api/stickers/{sid}")).json()["status"] == "triaged"
    # ask: the bot wants the question text
    await bot.handle(cb(222, f"a:{sid}:ask"))
    assert "Что уточнить" in api.last(222)["text"]
    await bot.handle(msg(222, "Сколько дней?"))
    assert (await client.get(f"/api/stickers/{sid}")).json()["status"] == "needs_info"
    await deliver()
    q = api.last(111)
    assert "Босс Главный: вопрос" in q["text"] and "Сколько дней?" in q["text"] and f"a:{sid}:answer" in buttons(q["reply_markup"])
    # the author simply replies to the bot's message
    reply_to = {"message_id": 9, "from": {"id": 1, "is_bot": True}, "text": q["text"]}
    await bot.handle(msg(111, "Три дня", reply_to_message=reply_to))
    assert "Ответ отправлен" in api.last(111)["text"]
    assert (await client.get(f"/api/stickers/{sid}")).json()["status"] == "in_progress"
    # resolve with an outcome and a text
    await bot.handle(cb(222, f"a:{sid}:resolve"))
    await bot.handle(cb(222, f"o:{sid}:approved"))
    await bot.handle(msg(222, "Согласовано, оформляй"))
    s = (await client.get(f"/api/stickers/{sid}")).json()
    assert s["status"] == "resolved" and s["outcome"] == "approved"
    # same rights as the web: Ivan cannot resolve
    await bot.handle(cb(111, f"a:{sid}:resolve"))
    assert [p for m, p in api.calls if m == "answerCallbackQuery"][-1]["text"] == "Это действие сейчас недоступно"


async def test_group_command_photo_and_strangers(client, team, tg):  # noqa: F811
    bot, api = tg
    await bot.handle(msg(-500, "/stiker@planner_test_bot Сломался принтер", uid=111, kind="supergroup"))
    assert api.last(-500)["text"].startswith("Стикер №") and api.last(-500)["text"].endswith("создан")
    await bot.handle(msg(-500, "просто болтовня", uid=111, kind="supergroup"))
    assert len(api.sent(-500)) == 1  # the bot stays silent in the group otherwise
    await bot.handle(msg(-500, "/stiker чужой", uid=999, kind="supergroup"))
    assert "привяжите" in api.last(-500)["text"]
    await bot.handle(msg(999, "привет"))
    assert "Профиль" in api.last(999)["text"]

    await bot.handle(msg(111, None, caption="Счёт от поставщика", photo=[{"file_id": "small"}, {"file_id": "big"}]))
    sid = int(api.last(111)["text"].split("№")[1].split()[0])
    s = (await client.get(f"/api/stickers/{sid}")).json()
    assert s["title"] == "Счёт от поставщика" and s["files"][0]["content_type"] == "image/jpeg"
    await bot.handle(msg(111, None, photo=[{"file_id": "x"}]))
    assert "подпись" in api.last(111)["text"]


async def test_bot_commands(client, team, tg):  # noqa: F811
    bot, api = tg
    await bot.handle(msg(111, "Первый"))
    await bot.handle(msg(222, "/inbox"))
    assert api.sent(222)[-2]["text"].startswith("<b>Входящие</b>: 1")
    await bot.handle(msg(222, "/board"))
    assert "Первый" in api.last(222)["text"]
    await bot.handle(msg(111, "/stats"))
    assert "В работе у других: 1" in api.last(111)["text"]


async def test_morning_digest(client, team, tg, monkeypatch):  # noqa: F811
    bot, api = tg
    monkeypatch.setattr(digest.runner, "current", bot)
    await bot.handle(msg(111, "Срочное дело"))
    # Monday 2026-11-02 08:05 Moscow
    now = datetime(2026, 11, 2, 5, 5, tzinfo=timezone.utc)
    async with dbmod.sessionmaker()() as db:
        assert await digest.run_once(db, now) >= 1
        assert await digest.run_once(db, now) == 0  # once a day
    text = api.last(222)["text"]
    assert text.startswith("<b>Доброе утро, Босс</b>") and "Во входящих: 1" in text
    assert buttons(api.last(222)["reply_markup"]) == ["v:inbox", "v:do", "v:late"]
    # Saturday: not in the default days
    async with dbmod.sessionmaker()() as db:
        assert await digest.run_once(db, datetime(2026, 11, 7, 5, 5, tzinfo=timezone.utc)) == 0


async def test_unlink(client, team, tg):  # noqa: F811
    r = await team["ivan"][1].delete("/api/telegram/link")
    assert r.json()["telegram_linked"] is False
    r = await client.patch("/api/admin/users/1", json={"telegram_unlink": True})
    assert r.json()["telegram_linked"] is False


def keyboard_texts(m):
    return [b["text"] for row in m["reply_markup"]["keyboard"] for b in row]


async def test_menu_write_triage_and_close(client, team, tg):  # noqa: F811
    bot, api = tg
    boss_id = (await client.get("/api/auth/me")).json()["user"]["id"]
    ivan_id = team["ivan"][0]
    # Ivan: "Write a sticker" -> whom: my manager / another department / an employee
    await bot.handle(msg(111, "Написать стикер"))
    who = api.last(111)
    assert who["text"] == "Кому адресовать стикер?"
    assert buttons(who["reply_markup"]) == [f"w:to:{boss_id}", "w:depts", "w:emp:0", "w:x"]
    picker = {"message_id": 40, "chat": {"id": 111}, "text": who["text"]}
    await bot.handle(cb(111, "w:emp:0", picker))
    people = [p for m, p in api.calls if m == "editMessageText"][-1]
    assert f"w:to:{boss_id}" in buttons(people["reply_markup"]) and f"w:to:{ivan_id}" not in buttons(people["reply_markup"])
    await bot.handle(cb(111, f"w:to:{boss_id}", picker))
    assert "Стикер для <b>Босс Главный</b>" in [p for m, p in api.calls if m == "editMessageText"][-1]["text"]
    await bot.handle(msg(111, "Заказать картридж\nHP 85A"))
    sid = int(api.last(111)["text"].split("№")[1].split()[0])
    s = (await client.get(f"/api/stickers/{sid}")).json()
    assert s["title"] == "Заказать картридж" and [r["id"] for r in s["recipients"]] == [boss_id]

    # boss: View -> quadrant -> confirmation in place + main menu with the count
    await deliver()
    await bot.handle(cb(222, f"s:{sid}"))
    await bot.handle(cb(222, f"q:{sid}:do", {"message_id": 50, "chat": {"id": 222}, "text": "x"}))
    assert "→ <b>Сделать сейчас</b>" in [p for m, p in api.calls if m == "editMessageText"][-1]["text"]
    assert "Сделать сейчас · 1" in keyboard_texts(api.last(222))

    # the quadrant button lists its stickers; a sticker opens with Done / Not done, Delegate / Ask / Snooze, Back
    await bot.handle(msg(222, "Сделать сейчас · 1"))
    assert buttons(api.last(222)["reply_markup"]) == [f"S:{sid}"]
    await bot.handle(cb(222, f"S:{sid}"))
    assert buttons(api.last(222)["reply_markup"]) == [f"o:{sid}:done", f"o:{sid}:declined", f"a:{sid}:delegate", f"a:{sid}:ask",
                                                      f"a:{sid}:snooze", "L:do"]

    # Ivan sees it among his active stickers with who has it
    await bot.handle(msg(111, "Мои стикеры"))
    mine = api.last(111)
    assert f"№{sid} Заказать картридж" in mine["text"] and "Босс Главный · разобран" in mine["text"] and buttons(mine["reply_markup"]) == [f"S:{sid}"]

    # Done without a comment
    await bot.handle(cb(222, f"o:{sid}:done"))
    assert buttons(api.last(222)["reply_markup"]) == [f"n:{sid}"]
    await bot.handle(cb(222, f"n:{sid}", {"message_id": 60, "chat": {"id": 222}, "text": "x"}))
    s = (await client.get(f"/api/stickers/{sid}")).json()
    assert s["status"] == "resolved" and s["outcome"] == "done"
    await bot.handle(msg(111, "Мои стикеры"))
    assert "решён, ждёт вашей приёмки" in api.last(111)["text"]

    # Not done: the reason is required and goes to the author
    await bot.handle(msg(111, "Второй"))
    sid2 = int(api.last(111)["text"].split("№")[1].split()[0])
    await bot.handle(cb(222, f"q:{sid2}:plan"))
    await bot.handle(cb(222, f"o:{sid2}:declined"))
    assert "Почему №" in api.last(222)["text"]
    await bot.handle(msg(222, "Нет бюджета"))
    s = (await client.get(f"/api/stickers/{sid2}")).json()
    assert s["status"] == "resolved" and s["outcome"] == "declined"

    # Overview
    await bot.handle(msg(222, "Обстановка"))
    assert "Обстановка сейчас" in api.last(222)["text"] and "Сделать сейчас: 0" in api.last(222)["text"]
    # Ivan cannot close the boss's sticker
    await bot.handle(cb(111, f"o:{sid2}:done"))
    assert [p for m, p in api.calls if m == "answerCallbackQuery"][-1]["text"] == "Это действие сейчас недоступно"
