import io

from openpyxl import load_workbook

from .test_stickers import act, team  # noqa: F401 - fixture


async def test_manager_stats_and_excel(client, team):  # noqa: F811
    ivan_id, ivan = team["ivan"]
    petr_id, petr = team["petr"]
    a = (await ivan.post("/api/stickers", json={"title": "Срочное", "urgent": True, "important": True})).json()["id"]
    b = (await ivan.post("/api/stickers", json={"title": "Расхождение", "urgent": True})).json()["id"]
    await petr.post("/api/stickers", json={"title": "Входящий"})
    await client.put(f"/api/stickers/{a}/place", json={"quadrant": "do"})
    await client.put(f"/api/stickers/{b}/place", json={"quadrant": "drop"})  # author said "urgent", manager says "drop"
    await act(client, a, "resolve", outcome="done", text="Ок")
    # employee -> employee: the manager only gets numbers
    await ivan.post("/api/stickers", json={"title": "Тайна коллеге", "recipient_ids": [petr_id]})

    st = (await client.get("/api/stats", params={"period": "week"})).json()
    assert st["scope"] == "received"
    assert st["totals"] == {"total": 3, "resolved": 1, "active": 2, "overdue": 0}
    assert st["divergence"] == {"judged": 2, "diverged": 1}
    assert st["by_quadrant"] == {"do": 1, "plan": 0, "delegate": 0, "drop": 1}
    assert st["board"]["inbox"] == 1 and st["board"]["drop"] == 1
    people = {p["user"]["display_name"]: p for p in st["people"]}
    assert people["Иван Петров"]["sent"] == 2 and people["Иван Петров"]["diverged"] == 1
    assert st["e2e"]["count"] == 1
    assert "Тайна" not in str(st)

    r = await client.get("/api/stats/report.xlsx", params={"period": "month"})
    assert r.status_code == 200 and r.headers["content-disposition"].startswith("attachment")
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Сводка", "Стикеры", "По сотрудникам"]
    assert wb["Сводка"]["B2"].value == "ALEXANDRIA · ПЛАНЕР" and wb["Сводка"]["B8"].value == 3
    titles = [wb["Стикеры"].cell(row=r, column=3).value for r in range(8, 11)]
    assert set(titles) == {"Срочное", "Расхождение", "Входящий"}
    assert wb["По сотрудникам"]["B8"].value == "Иван Петров"


async def test_employee_sees_own_sent(client, team):  # noqa: F811
    _, ivan = team["ivan"]
    await ivan.post("/api/stickers", json={"title": "Моё"})
    st = (await ivan.get("/api/stats", params={"period": "day"})).json()
    assert st["scope"] == "sent" and st["totals"]["total"] == 1
    assert st["people"][0]["user"]["display_name"] == "Босс Главный" and st["e2e"] is None
