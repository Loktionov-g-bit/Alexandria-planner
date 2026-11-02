"""Long polling loop. Picks up a new/changed/removed token from the admin panel without a restart.
A token may be polled by one process only (Telegram returns 409 otherwise): run the worker on one container."""

import asyncio
import logging

from .. import dispatch
from ..models import AppSetting
from .api import TelegramAPI, TelegramError
from .bot import Bot

log = logging.getLogger("planner.telegram")

current: Bot | None = None  # the live bot, for other modules (digest)


async def load_config(db) -> dict | None:
    row = await db.get(AppSetting, "telegram")
    return row.value if row is not None and row.value and row.value.get("token") else None


async def run(sm) -> None:
    global current
    token = None
    api: TelegramAPI | None = None
    offset = None
    while True:
        try:
            async with sm() as db:
                cfg = await load_config(db)
            new_token = cfg["token"] if cfg else None
            if new_token != token:
                if api is not None:
                    await api.close()
                dispatch.channels.pop("telegram", None)
                current, api, offset, token = None, None, None, new_token
                if token:
                    api = TelegramAPI(token)
                    await api.call("deleteWebhook")
                    current = Bot(api, sm, cfg.get("username", ""))
                    dispatch.channels["telegram"] = current.notify
                    log.info("telegram bot @%s is polling", cfg.get("username"))
            if current is None:
                await asyncio.sleep(15)
                continue
            updates = await api.call("getUpdates", offset=offset, timeout=25, allowed_updates=["message", "callback_query"])
            for u in updates:
                offset = u["update_id"] + 1
                try:
                    await current.handle(u)
                except Exception:  # noqa: BLE001 - one bad update must not stop the bot
                    log.exception("update %s failed", u.get("update_id"))
        except asyncio.CancelledError:
            if api is not None:
                await api.close()
            raise
        except TelegramError as e:
            if e.code == 409:
                log.warning("another process polls this bot token; retrying in 30 s")
                await asyncio.sleep(30)
            elif e.code == 401:
                log.warning("telegram token rejected; fix it in the admin panel")
                await asyncio.sleep(60)
            else:
                log.warning("telegram: %s", e)
                await asyncio.sleep(5)
        except Exception:  # noqa: BLE001
            log.exception("telegram loop failed")
            await asyncio.sleep(5)
