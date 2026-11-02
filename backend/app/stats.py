"""Statistics (SPEC §7). A manager sees the stickers addressed to them; an employee sees what they sent.
Employee-to-employee stickers inside a department reach the manager only as anonymous numbers."""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import stickers as lc
from .models import Kind, Placement, PlacementRole, Quadrant, Role, Status, Sticker, User

DONE = {Status.resolved, Status.closed}


@dataclass
class Period:
    start: date
    end: date  # inclusive

    def bounds(self, tz: str) -> tuple[datetime, datetime]:
        try:
            z = ZoneInfo(tz)
        except Exception:  # noqa: BLE001
            z = timezone.utc
        a = datetime.combine(self.start, time(0), tzinfo=z).astimezone(timezone.utc)
        b = datetime.combine(self.end + timedelta(days=1), time(0), tzinfo=z).astimezone(timezone.utc)
        return a, b


def period_of(kind: str, today: date, start: date | None = None, end: date | None = None) -> Period:
    if kind == "custom" and start and end:
        return Period(min(start, end), max(start, end))
    if kind == "day":
        return Period(today, today)
    if kind == "month":
        return Period(today - timedelta(days=29), today)
    if kind == "quarter":
        return Period(today - timedelta(days=89), today)
    return Period(today - timedelta(days=6), today)  # week


def hours(a: datetime | None, b: datetime | None) -> float | None:
    return (b - a).total_seconds() / 3600 if a and b else None


def avg(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


@dataclass
class Report:
    scope: str  # received | sent
    period: Period
    stickers: list[Sticker]
    board: dict[str, int]
    by_person: list[dict] = field(default_factory=list)
    e2e: dict | None = None

    @property
    def totals(self) -> dict:
        today = date.today()
        return {
            "total": len(self.stickers),
            "resolved": sum(1 for s in self.stickers if s.status in DONE),
            "active": sum(1 for s in self.stickers if s.status in lc.ACTIVE),
            "overdue": sum(1 for s in self.stickers if s.status in lc.ACTIVE and s.deadline and s.deadline < today),
        }

    @property
    def times(self) -> dict:
        return {
            "to_triage": avg([hours(s.created_at, s.triaged_at) for s in self.stickers]),
            "to_resolve": avg([hours(s.triaged_at or s.created_at, s.resolved_at) for s in self.stickers]),
            "to_close": avg([hours(s.resolved_at, s.closed_at) for s in self.stickers]),
            "total": avg([hours(s.created_at, s.resolved_at) for s in self.stickers]),
        }

    @property
    def divergence(self) -> dict:
        judged = [s for s in self.stickers if s.decided_quadrant is not None]
        diff = [s for s in judged if s.decided_quadrant != lc.author_quadrant(s)]
        return {"judged": len(judged), "diverged": len(diff)}


def counterpart(s: Sticker, scope: str) -> User:
    if scope == "sent":
        r = lc.recipients(s)
        return r[0].user if r else s.author
    return s.author


def executor(s: Sticker) -> str:
    d = [p.user.display_name for p in s.placements if p.role == PlacementRole.delegate]
    r = [p.user.display_name for p in lc.recipients(s)]
    return ", ".join(d or r)


async def build(db: AsyncSession, user: User, period: Period) -> Report:
    a, b = period.bounds(user.timezone)
    scope = "received" if user.role == Role.manager else "sent"
    if scope == "received":
        mine = select(Placement.sticker_id).where(Placement.user_id == user.id, Placement.role == PlacementRole.recipient)
        q = select(Sticker).where(Sticker.id.in_(mine))
    else:
        q = select(Sticker).where(Sticker.author_id == user.id)
    q = q.where(Sticker.kind == Kind.normal, Sticker.created_at >= a, Sticker.created_at < b).order_by(Sticker.id)
    items = list(await db.scalars(q))

    # current board (not limited by period): how much hangs in each quadrant right now
    rows = (await db.execute(
        select(Sticker, Placement).join(Placement, Placement.sticker_id == Sticker.id)
        .where(Placement.user_id == user.id, Placement.role != PlacementRole.viewer, Sticker.status.in_(lc.ACTIVE))
    )).unique().all()
    board = {"inbox": 0, **{q.value: 0 for q in Quadrant}}
    for s, p in rows:
        if p.role == PlacementRole.recipient or s.status == Status.delegated:
            board[p.quadrant.value if p.quadrant else "inbox"] += 1

    rep = Report(scope, period, items, board)
    people: dict[int, dict] = {}
    for s in items:
        u = counterpart(s, scope)
        row = people.setdefault(u.id, {"user": u, "sent": 0, "resolved": 0, "_t": [], "diverged": 0, "judged": 0})
        row["sent"] += 1
        row["resolved"] += s.status in DONE
        row["_t"].append(hours(s.created_at, s.triaged_at))
        if s.decided_quadrant is not None:
            row["judged"] += 1
            row["diverged"] += s.decided_quadrant != lc.author_quadrant(s)
    for row in people.values():
        row["avg_response_hours"] = avg(row.pop("_t"))
    rep.by_person = sorted(people.values(), key=lambda r: (-r["sent"], r["user"].display_name))

    if scope == "received" and user.department_id:
        # employee -> employee inside the department: numbers only, no titles or names
        dept = select(User.id).where(User.department_id == user.department_id, User.id != user.id)
        e2e = list(await db.scalars(
            select(Sticker).join(Placement, Placement.sticker_id == Sticker.id)
            .where(Sticker.author_id.in_(dept), Placement.role == PlacementRole.recipient, Placement.user_id.in_(dept),
                   Sticker.kind == Kind.normal, Sticker.created_at >= a, Sticker.created_at < b)
        ))
        e2e = list({s.id: s for s in e2e}.values())
        rep.e2e = {"count": len(e2e), "avg_response_hours": avg([hours(s.created_at, s.triaged_at) for s in e2e])}
    return rep
