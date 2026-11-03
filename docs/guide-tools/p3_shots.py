"""Phase 3: real screenshots for the user guide."""
import os
import datetime as dt
import sys

from playwright.sync_api import sync_playwright

from common import C, OUT, PW, U, fresh_code, logins, ui

only = set(sys.argv[3:])
NOW = dt.datetime.combine(dt.date.today(), dt.time(10, 40))
L = logins()


def new(b, theme="light", w=1440, h=900):
    ctx = b.new_context(viewport={"width": w, "height": h}, locale=C["browser"], timezone_id=C["tz"], color_scheme=theme, device_scale_factor=2 if w < 500 else 1)
    ctx.clock.install(time=NOW)
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: print("pageerror", e))
    return ctx, pg


def login(pg, user, shots=False):
    pg.goto(U); pg.wait_for_timeout(900)
    pg.locator("input").nth(0).fill(L[user]); pg.locator("input[type=password]").fill(PW)
    if shots: pg.screenshot(path=f"{OUT}/04-login.png")
    pg.keyboard.press("Enter"); pg.wait_for_timeout(1000)
    if user == "boss":
        pg.locator("input").first.fill(fresh_code())
        if shots: pg.screenshot(path=f"{OUT}/05-totp.png")
        pg.keyboard.press("Enter")
    pg.wait_for_selector(".matrix", timeout=8000); pg.wait_for_timeout(900)


def shot(pg, name, full=False):
    pg.wait_for_timeout(700); pg.screenshot(path=f"{OUT}/{name}.png", full_page=full); print("shot", name)


def go(pg, path):
    pg.goto(U + path); pg.wait_for_timeout(1200)


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True, args=[f"--lang={C['browser']}"], env={**os.environ, "LANGUAGE": C["browser"].replace("-", "_"), "LANG": C["browser"].replace("-", "_") + ".UTF-8"})
    if not only or "boss" in only:
        ctx, pg = new(b)
        login(pg, "boss", shots=True)
        shot(pg, "10-board")
        pg.click("button.tr-start"); pg.wait_for_selector(".triage"); shot(pg, "17-triage")
        pg.keyboard.press("Escape"); pg.wait_for_timeout(400)
        pg.get_by_text(C["main"]).first.click(); pg.wait_for_selector(".sheet .panel"); shot(pg, "12-sheet")
        pg.locator(".sheet").get_by_role("button", name=ui("action.resolve"), exact=True).first.click(); pg.wait_for_timeout(300)
        pg.locator(".sheet").get_by_role("button", name=ui("outcome.approved"), exact=True).first.click()
        pg.locator(".sheet textarea").last.fill(C["resolve"])
        pg.locator(".sheet .panel").evaluate("e => e.scrollTop = e.scrollHeight"); shot(pg, "13-resolve")
        pg.keyboard.press("Escape"); pg.wait_for_timeout(400); pg.keyboard.press("Escape")
        go(pg, "/"); pg.get_by_text(C["trip"]).first.click(); pg.wait_for_selector(".sheet .panel"); shot(pg, "14-sheet-question")
        go(pg, "/"); pg.click("button.create"); pg.wait_for_timeout(500)
        sel = pg.locator("select").first
        sel.select_option(label=[o for o in sel.locator("option").all_inner_texts() if C["iv"][0] in o][0])
        pg.get_by_placeholder(ui("compose.titlePh")).fill(C["ct"])
        pg.get_by_placeholder(ui("compose.bodyPh")).fill(C["cb"])
        pg.get_by_role("button", name=ui("compose.important"), exact=True).last.click()
        shot(pg, "15-compose")
        go(pg, "/"); pg.locator("header button, .brand button, button[aria-label]").first.click(); shot(pg, "16-feed")
        go(pg, "/archive"); shot(pg, "20-archive")
        go(pg, "/stats"); shot(pg, "21-stats")
        pg.set_viewport_size({"width": 1440, "height": 1010}); go(pg, "/profile"); shot(pg, "22-profile"); pg.set_viewport_size({"width": 1440, "height": 900})
        pg.locator("#p-away").scroll_into_view_if_needed(); pg.evaluate("window.scrollBy(0, -40)"); shot(pg, "23-profile-away")
        for path, n in [("/admin", "30-admin-users"), ("/admin/departments", "31-admin-departments"), ("/admin/logins", "32-admin-logins"), ("/admin/telegram", "33-admin-telegram"), ("/admin/updates", "34-admin-updates"), ("/admin/mode", "35-admin-mode")]:
            go(pg, path); shot(pg, n)
        ctx.close()
    if not only or "dark" in only:
        ctx, pg = new(b, "dark"); login(pg, "boss"); shot(pg, "11-board-dark"); ctx.close()
    if not only or "ma" in only:
        ctx, pg = new(b); login(pg, "ma"); shot(pg, "40-employee-board")
        go(pg, "/sent"); shot(pg, "41-sent")
        pg.locator("textarea").first.fill(C["tripa"]); shot(pg, "43-answer")
        go(pg, "/"); pg.click("button.create"); pg.wait_for_timeout(500); pg.locator("select").first.click(); shot(pg, "42-compose-employee")
        ctx.close()
    if not only or "mobile" in only:
        ctx, pg = new(b, "light", 390, 844); login(pg, "boss"); shot(pg, "50-mobile-board")
        pg.get_by_text(C["main"]).first.click(); pg.wait_for_timeout(600); shot(pg, "51-mobile-sheet")
        ctx.close()
        ctx, pg = new(b, "light", 390, 844); login(pg, "ma"); go(pg, "/sent"); shot(pg, "52-mobile-sent"); ctx.close()
    b.close()
