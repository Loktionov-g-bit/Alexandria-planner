"""Personal calendar feed (RFC 5545): sticker deadlines as all-day events.

Phones and mail clients subscribe to /api/calendar/<token>.ics and re-read it on their own schedule.
The token in the address is the only key, so the feed shows titles only (no bodies, no comments).
"""

from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy import or_, select

from . import stickers as lc
from .config import get_settings
from .deps import DB
from .models import Placement, PlacementRole, Status, Sticker, User

router = APIRouter(prefix="/api", tags=["calendar"])

SHOWN = lc.ACTIVE | {Status.snoozed}


def esc(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", ""))


def fold(line: str) -> str:
    """Lines longer than 75 octets continue on the next line after a space (RFC 5545 §3.1)."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode()
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode())
            cur = b""
        cur += b
    out.append(cur.decode())
    return "\r\n ".join(out)


def build(user: User, stickers: list[Sticker], now: datetime | None = None) -> str:
    st = get_settings()
    base = st.base_url.rstrip("/")
    host = urlparse(base).hostname or "planner"
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Alexandria//Planner//EN", "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH", f"X-WR-CALNAME:{esc('Alexandria Planner · ' + user.display_name)}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H",
    ]
    for s in stickers:
        d: date = s.deadline
        url = f"{base}/?s={s.id}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:sticker-{s.id}@{host}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{d:%Y%m%d}",
            f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{esc(f'№{s.id} {s.title}')}",
            f"URL:{url}",
            f"DESCRIPTION:{esc(url)}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(x) for x in lines) + "\r\n"


async def deadlines(db: DB, user: User) -> list[Sticker]:
    """Stickers on my board or sent by me that still have a deadline ahead of them (or overdue)."""
    mine = select(Placement.sticker_id).where(Placement.user_id == user.id, Placement.role != PlacementRole.viewer)
    q = (select(Sticker)
         .where(Sticker.deadline.is_not(None), Sticker.status.in_(SHOWN),
                or_(Sticker.author_id == user.id, Sticker.id.in_(mine)))
         .order_by(Sticker.deadline, Sticker.id).limit(1000))
    return list(await db.scalars(q))


@router.get("/calendar/{name}", include_in_schema=False)
async def feed(name: str, db: DB) -> Response:
    token = name.removesuffix(".ics")
    user = None
    if 20 <= len(token) <= 64:
        user = await db.scalar(select(User).where(User.calendar_token == token))
    if user is None or not user.is_active or user.deleted_at is not None:
        raise HTTPException(404, "calendar.not_found")
    body = build(user, await deadlines(db, user))
    return Response(body, media_type="text/calendar; charset=utf-8", headers={
        "Cache-Control": "private, max-age=300", "Content-Disposition": 'inline; filename="planner.ics"',
        "X-Robots-Tag": "noindex",
    })
