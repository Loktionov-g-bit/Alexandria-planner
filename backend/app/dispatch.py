"""Delivers queued notifications to channels. One pass = everything pending, oldest first."""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import push
from .models import Notification, User, utcnow
from .notify import render

log = logging.getLogger("planner.dispatch")

STALE = timedelta(hours=12)  # after a long outage do not flood phones with old news
channels: dict[str, object] = {}  # name -> async fn(db, user, notification, title, body) -> bool; Telegram registers here


async def deliver(db: AsyncSession) -> int:
    q = (
        select(Notification)
        .where(or_(Notification.push_done.is_(None), Notification.telegram_done.is_(None)))
        .order_by(Notification.id)
        .limit(200)
    )
    rows = list(await db.scalars(q))
    now = utcnow()
    for n in rows:
        user = await db.get(User, n.user_id)
        created = n.created_at if n.created_at.tzinfo else n.created_at.replace(tzinfo=now.tzinfo)
        fresh = user is not None and user.is_active and now - created < STALE
        title, body = render(n, user.locale if user else "ru")
        if n.push_done is None:
            n.push_done = False
            if fresh and user.notify_push:
                url = f"./?s={n.sticker_id}" if n.sticker_id else "./"
                n.push_done = await push.send(db, user.id, {"title": title, "body": body, "url": url, "tag": f"s{n.sticker_id}"})
        if n.telegram_done is None:
            n.telegram_done = False
            tg = channels.get("telegram")
            if fresh and tg and user.notify_telegram and user.telegram_chat_id:
                try:
                    n.telegram_done = await tg(db, user, n, title, body)
                except Exception:  # noqa: BLE001
                    log.exception("telegram delivery failed")
        await db.commit()
    return len(rows)


async def loop(sessionmaker, wakeup: asyncio.Event, idle_seconds: float = 30) -> None:
    while True:
        try:
            async with sessionmaker() as db:
                while await deliver(db) == 200:
                    pass
        except Exception:  # noqa: BLE001
            log.exception("dispatch pass failed")
        try:
            await asyncio.wait_for(wakeup.wait(), timeout=idle_seconds)
        except TimeoutError:
            pass
        wakeup.clear()
        await asyncio.sleep(0.3)  # let a burst of commits settle into one pass
