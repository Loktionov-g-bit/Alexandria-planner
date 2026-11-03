"""Phase 1: first launch through the real UI, admin 2FA enrollment. Fictional people only."""
import os
import json
import re

from playwright.sync_api import sync_playwright

from common import C, OUT, PW, U, WORK, fresh_code

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True, args=[f"--lang={C['browser']}"], env={**os.environ, "LANGUAGE": C["browser"].replace("-", "_"), "LANG": C["browser"].replace("-", "_") + ".UTF-8"})
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale=C["browser"], timezone_id=C["tz"], color_scheme="light")
    pg = ctx.new_page()
    pg.goto(U); pg.wait_for_timeout(1000)
    pg.screenshot(path=f"{OUT}/00-mode.png")
    pg.locator(".modecard.m-team").click(); pg.wait_for_timeout(400)
    ins = pg.locator("input")
    ins.nth(0).fill(C["dept"]); ins.nth(1).fill(C["boss"][0]); ins.nth(2).fill(C["boss"][1])
    pg.wait_for_timeout(400)
    ins.nth(4).fill(PW); ins.nth(5).fill(PW)
    pg.screenshot(path=f"{OUT}/01-setup.png")
    (WORK / "logins.json").write_text(json.dumps({"boss": ins.nth(3).input_value()}))
    pg.click("button.primary"); pg.wait_for_timeout(1500)
    pg.screenshot(path=f"{OUT}/02-totp-setup.png")
    (WORK / "totp.txt").write_text(re.sub(r"\s", "", pg.locator(".secret").first.text_content()))
    pg.locator("input").last.fill(fresh_code())
    pg.keyboard.press("Enter"); pg.wait_for_timeout(1500)
    pg.screenshot(path=f"{OUT}/03-empty-board.png")
    print("setup done", pg.url)
    b.close()
