"""Morning and evening digests (SPEC §4): in the user's time zone, on chosen weekdays,
to Telegram (with quick buttons) and Web Push."""

import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import exists, select

from . import push
from . import stickers as lc
from .models import Comment, CommentKind, Kind, Placement, PlacementRole, Quadrant, Status, Sticker, User
from .telegram import runner
from .telegram.texts import esc, t

log = logging.getLogger("planner.digest")

EVENING = time(18, 0)
LATE_WINDOW = timedelta(hours=3)  # after downtime: send a missed digest only if still within 3 h of its time


def local_now(user: User, now: datetime) -> datetime:
    try:
        return now.astimezone(ZoneInfo(user.timezone))
    except Exception:  # noqa: BLE001 - unknown zone name
        return now.astimezone(ZoneInfo("Europe/Moscow"))


def due(user: User, kind: str, now: datetime) -> date | None:
    """The local date to send for, or None if it is not time (or already sent)."""
    loc = local_now(user, now)
    if str(loc.isoweekday()) not in (user.digest_days or ""):
        return None
    if kind == "morning":
        if not user.digest_morning or user.digest_last_sent == loc.date():
            return None
        hh, mm = (int(x) for x in (user.digest_time or "08:00").split(":"))
        at = time(hh, mm)
    else:
        if not user.digest_evening or user.digest_evening_last_sent == loc.date():
            return None
        at = EVENING
    start = loc.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    return loc.date() if start <= loc < start + LATE_WINDOW else None


async def numbers(db, user: User, kind: str, today: date) -> dict[str, int]:
    rows = (await db.execute(
        select(Sticker, Placement).join(Placement, Placement.sticker_id == Sticker.id)
        .where(Placement.user_id == user.id, Placement.role != PlacementRole.viewer, Sticker.status.in_(lc.ACTIVE))
    )).unique().all()
    board = [(s, p) for s, p in rows if p.role == PlacementRole.recipient or s.status == Status.delegated]
    n_asks = len(list(await db.scalars(select(Sticker.id).where(Sticker.author_id == user.id, Sticker.status == Status.needs_info))))
    late = sum(1 for s, _ in board if s.deadline and s.deadline < today)
    inbox = sum(1 for _, p in board if p.quadrant is None)
    if kind == "morning":
        reported = exists().where(Comment.sticker_id == Sticker.id, Comment.kind == CommentKind.report)
        reports = len(list(await db.scalars(
            select(Sticker.id).join(Placement).where(
                Placement.user_id == user.id, Placement.role == PlacementRole.recipient,
                Sticker.status == Status.delegated, reported)
        )))
        return {
            "inbox": inbox,
            "do": sum(1 for _, p in board if p.quadrant == Quadrant.do),
            "late": late,
            "due": sum(1 for s, _ in board if s.deadline and today <= s.deadline <= today + timedelta(days=1)),
            "reports": reports,
            "asks": n_asks,
        }
    day_start = datetime.combine(today, time(0), tzinfo=local_now(user, datetime.now(timezone.utc)).tzinfo).astimezone(timezone.utc)
    mine = select(Placement.sticker_id).where(Placement.user_id == user.id, Placement.role == PlacementRole.recipient)
    resolved = len(list(await db.scalars(select(Sticker.id).where(Sticker.id.in_(mine), Sticker.resolved_at >= day_start))))
    new = len(list(await db.scalars(select(Sticker.id).where(Sticker.id.in_(mine), Sticker.created_at >= day_start, Sticker.kind == Kind.normal))))
    return {"resolved": resolved, "new": new, "inbox": inbox, "late": late}


def render(user: User, kind: str, nums: dict[str, int]) -> tuple[str, list[str]]:
    loc = user.locale
    head = t(loc, f"digest.{kind}", name=esc(user.first_name or user.display_name))
    lines = [t(loc, f"d.{k}", n=v) for k, v in nums.items() if v]
    return head, lines


async def send(db, user: User, kind: str, today: date) -> bool:
    nums = await numbers(db, user, kind, today)
    empty = not any(v for k, v in nums.items() if k not in ("resolved", "new"))
    if empty and user.digest_skip_empty and kind == "morning":
        return False
    head, lines = render(user, kind, nums)
    if kind == "morning" and empty:
        lines = [t(user.locale, "digest.clear")]
    sent = False
    bot = runner.current
    if bot is not None and user.telegram_chat_id and user.notify_telegram:
        kb = None
        if kind == "morning" and not empty:
            kb = {"inline_keyboard": [[{"text": t(user.locale, f"v.{v}"), "callback_data": f"v:{v}"} for v in ("inbox", "do", "late")]]}
        try:
            await bot.say(user.telegram_chat_id, head + "\n" + "\n".join(lines), reply_markup=kb)
            sent = True
        except Exception as e:  # noqa: BLE001
            log.warning("digest to telegram failed for user %s: %s", user.id, e)
    if user.notify_push:
        plain = head.replace("<b>", "").replace("</b>", "")
        sent = await push.send(db, user.id, {"title": plain, "body": "\n".join(lines), "url": "./", "tag": f"digest-{kind}"}) or sent
    return sent


async def run_once(db, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    users = list(await db.scalars(select(User).where(User.is_active.is_(True))))
    count = 0
    for user in users:
        for kind in ("morning", "evening"):
            day = due(user, kind, now)
            if day is None:
                continue
            # mark first: a crash mid-send must not repeat the digest every minute
            if kind == "morning":
                user.digest_last_sent = day
            else:
                user.digest_evening_last_sent = day
            await db.commit()
            try:
                if await send(db, user, kind, day):
                    count += 1
            except Exception:  # noqa: BLE001
                log.exception("digest for user %s failed", user.id)
    return count


async def loop(sm) -> None:
    while True:
        try:
            async with sm() as db:
                await run_once(db)
        except Exception:  # noqa: BLE001
            log.exception("digest pass failed")
        await asyncio.sleep(60)
