from datetime import date, timedelta

from .test_stickers import team  # noqa: F401 - fixture


async def test_away_manager_deputy_gets_new_stickers(client, team):
    ivan_id, ivan = team["ivan"]
    petr_id, petr = team["petr"]
    today = date.today()
    r = await client.patch("/api/profile", json={"away_until": (today + timedelta(days=5)).isoformat(), "deputy_id": petr_id})
    assert r.status_code == 200, r.text
    assert r.json()["deputy_id"] == petr_id

    me = next(u for u in (await ivan.get("/api/directory/users")).json() if u["display_name"] == "Босс Главный")
    assert me["away_now_until"] == (today + timedelta(days=5)).isoformat() and me["away_deputy_id"] == petr_id

    s = (await ivan.post("/api/stickers", json={"title": "Вопрос"})).json()
    assert sorted(u["display_name"] for u in s["recipients"]) == ["Босс Главный", "Пётр Сидоров"]
    assert any(h["action"] == "deputy" for h in s["history"])
    assert [b["id"] for b in (await petr.get("/api/board")).json()] == [s["id"]]
    # the deputy can handle it
    assert (await petr.post(f"/api/stickers/{s['id']}/actions", json={"action": "start"})).status_code == 200

    # the deputy's own sticker to the away manager is not sent back to the deputy
    s2 = (await petr.post("/api/stickers", json={"title": "Сам себе"})).json()
    assert [u["display_name"] for u in s2["recipients"]] == ["Босс Главный"]


async def test_absence_in_future_or_past_does_nothing(client, team):
    _, ivan = team["ivan"]
    petr_id, petr = team["petr"]
    today = date.today()
    await client.patch("/api/profile", json={"away_from": (today + timedelta(days=3)).isoformat(),
                                             "away_until": (today + timedelta(days=9)).isoformat(), "deputy_id": petr_id})
    s = (await ivan.post("/api/stickers", json={"title": "Ещё не в отпуске"})).json()
    assert len(s["recipients"]) == 1


async def test_absence_validation(client, team):
    today = date.today()
    me = (await client.get("/api/auth/me")).json()["user"]["id"]
    assert (await client.patch("/api/profile", json={"deputy_id": me})).json()["detail"] == "absence.self_deputy"
    r = await client.patch("/api/profile", json={"away_from": today.isoformat(), "away_until": (today - timedelta(days=1)).isoformat()})
    assert r.json()["detail"] == "absence.bad_dates"
    assert (await client.patch("/api/profile", json={"deputy_id": 999})).status_code == 404


async def test_calendar_feed(client, team, app):
    from .conftest import new_client

    _, ivan = team["ivan"]
    assert (await ivan.get("/api/profile/calendar")).json() == {"url": None}
    url = (await ivan.post("/api/profile/calendar")).json()["url"]
    path = url.split("testserver", 1)[1]
    deadline = date.today() + timedelta(days=4)
    s = (await ivan.post("/api/stickers", json={"title": "Отчёт, квартал; итог", "deadline": deadline.isoformat()})).json()
    await ivan.post("/api/stickers", json={"title": "Без срока"})

    anon = await new_client(app)
    r = await anon.get(path)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    body = r.text
    assert f"UID:sticker-{s['id']}@testserver" in body
    assert f"DTSTART;VALUE=DATE:{deadline:%Y%m%d}" in body
    assert "Отчёт\\, квартал\\; итог" in body
    assert "Без срока" not in body
    assert all(len(line.encode()) <= 75 for line in body.split("\r\n"))
    # the recipient's own feed has it too
    boss_url = (await client.post("/api/profile/calendar")).json()["url"]
    assert f"sticker-{s['id']}@" in (await anon.get(boss_url.split("testserver", 1)[1])).text

    # new address: the old one stops working; off: nothing works
    url2 = (await ivan.post("/api/profile/calendar")).json()["url"]
    assert (await anon.get(path)).status_code == 404
    await ivan.delete("/api/profile/calendar")
    assert (await anon.get(url2.split("testserver", 1)[1])).status_code == 404
    assert (await anon.get("/api/calendar/short.ics")).status_code == 404
