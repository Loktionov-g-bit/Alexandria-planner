"""In-app notification feed, Web Push subscriptions and the live-refresh stream."""

import asyncio
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from .. import live, push
from ..db import sessionmaker
from ..deps import COOKIE, DB, CurrentUser, load_session
from ..models import Notification, PushSubscription, utcnow
from ..notify import render
from ..schemas import UserBrief

router = APIRouter(prefix="/api", tags=["notifications"])


class NotificationOut(BaseModel):
    id: int
    event: str
    sticker_id: int | None
    title: str
    body: str
    actor: UserBrief | None
    created_at: datetime
    read: bool


class Feed(BaseModel):
    unread: int
    items: list[NotificationOut]


class ReadIn(BaseModel):
    ids: list[int] | None = None  # None = all


class SubscriptionIn(BaseModel):
    endpoint: str = Field(max_length=1000, pattern=r"^https://")
    keys: dict[str, str]


@router.get("/notifications", response_model=Feed)
async def feed(db: DB, user: CurrentUser, limit: int = 30) -> Feed:
    rows = list(await db.scalars(
        select(Notification).where(Notification.user_id == user.id).order_by(Notification.id.desc()).limit(min(limit, 100))
    ))
    unread = await db.scalar(select(func.count()).where(Notification.user_id == user.id, Notification.read_at.is_(None)))
    items = []
    for n in rows:
        title, body = render(n, user.locale)
        items.append(NotificationOut(id=n.id, event=n.event, sticker_id=n.sticker_id, title=title, body=body,
                                     actor=n.actor, created_at=n.created_at, read=n.read_at is not None))
    return Feed(unread=unread or 0, items=items)


@router.post("/notifications/read", status_code=204)
async def mark_read(data: ReadIn, db: DB, user: CurrentUser) -> None:
    q = update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if data.ids is not None:
        q = q.where(Notification.id.in_(data.ids))
    await db.execute(q.values(read_at=utcnow()))
    await db.commit()


@router.get("/push/key")
async def push_key(db: DB, _: CurrentUser) -> dict:
    _, public = await push.vapid(db)
    return {"key": public}


@router.post("/push/subscribe", status_code=204)
async def subscribe(data: SubscriptionIn, request: Request, db: DB, user: CurrentUser) -> None:
    if not data.keys.get("p256dh") or not data.keys.get("auth"):
        raise HTTPException(422, "push.bad_subscription")
    sub = await db.scalar(select(PushSubscription).where(PushSubscription.endpoint == data.endpoint))
    if sub is None:
        sub = PushSubscription(endpoint=data.endpoint)
        db.add(sub)
    sub.user_id = user.id  # the device now belongs to whoever is signed in on it
    sub.p256dh = data.keys["p256dh"][:200]
    sub.auth = data.keys["auth"][:100]
    sub.user_agent = (request.headers.get("user-agent") or "")[:255]
    await db.commit()


@router.post("/push/unsubscribe", status_code=204)
async def unsubscribe(data: SubscriptionIn, db: DB, user: CurrentUser) -> None:
    sub = await db.scalar(select(PushSubscription).where(PushSubscription.endpoint == data.endpoint, PushSubscription.user_id == user.id))
    if sub is not None:
        await db.delete(sub)
        await db.commit()


@router.post("/push/test")
async def push_test(db: DB, user: CurrentUser) -> dict:
    from ..notify import TEXTS

    title = TEXTS.get(user.locale, TEXTS["ru"])["test"]
    return {"sent": await push.send(db, user.id, {"title": title, "body": "Alexandria", "url": "./", "tag": "test"})}


@router.get("/live")
async def live_stream(request: Request, planner_session: Annotated[str | None, Cookie(alias=COOKIE)] = None) -> StreamingResponse:
    # resolve the user with a short-lived DB session: a long stream must not hold a pool connection
    async with sessionmaker()() as db:
        s = await load_session(db, planner_session)
        if s is None or not s.verified:
            raise HTTPException(401, "auth.required")
        user_id = s.user_id

    async def stream():
        q = live.subscribe(user_id)
        try:
            yield "retry: 5000\n\n"
            while not await request.is_disconnected():
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=25)
                    yield f"data: {msg}\n\n"
                except TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            live.unsubscribe(user_id, q)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
