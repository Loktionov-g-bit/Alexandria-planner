"""Sticker lifecycle (SPEC §3): who may do what in which status, and what each action changes.

`allowed_actions()` is the single source of truth: the API refuses anything not listed there and the
UI shows exactly these buttons.
"""

from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException

from . import notify
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .models import (
    AppSetting,
    Attachment,
    Department,
    AuditEvent,
    Comment,
    CommentKind,
    Kind,
    Outcome,
    Placement,
    PlacementRole,
    Quadrant,
    Role,
    Status,
    Sticker,
    User,
)

# statuses in which a sticker still lives on its recipient's board
ACTIVE = {Status.new, Status.triaged, Status.in_progress, Status.needs_info, Status.delegated}
ARCHIVED = {Status.closed, Status.rejected, Status.withdrawn}

# recipient (the person handling the sticker): action -> statuses it is allowed from
RECIPIENT = {
    "start": {Status.new, Status.triaged, Status.needs_info},
    "ask": {Status.new, Status.triaged, Status.in_progress},
    "delegate": {Status.new, Status.triaged, Status.in_progress},
    "rework": {Status.delegated},
    "resolve": {Status.new, Status.triaged, Status.in_progress, Status.needs_info, Status.delegated},
    "snooze": {Status.new, Status.triaged, Status.in_progress},
    "wake": {Status.snoozed},
    "reject": {Status.new, Status.triaged, Status.in_progress, Status.needs_info},
}
AUTHOR = {
    "answer": {Status.needs_info},
    "withdraw": {Status.new},
    "confirm": {Status.resolved},
    "reopen": {Status.resolved, Status.closed},
}
DELEGATE = {"report": {Status.delegated}}
PERSONAL = {
    "resolve": {Status.triaged, Status.in_progress},
    "reopen": {Status.closed},
}

MAX_UPLOAD = 25 * 1024 * 1024

DEFAULTS = {"escalate_days": 2, "autoclose_days": 3}


async def get_setting(db: AsyncSession, key: str) -> int:
    row = await db.get(AppSetting, key)
    return row.value if row is not None else DEFAULTS[key]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def author_quadrant(s: Sticker) -> Quadrant:
    return Quadrant.from_flags(s.author_urgent, s.author_important)


def effective_quadrant(s: Sticker) -> Quadrant:
    if s.decided_quadrant is not None:
        return s.decided_quadrant
    q = author_quadrant(s)
    return make_urgent(q) if s.escalated_at else q


def make_urgent(q: Quadrant) -> Quadrant:
    return Quadrant.from_flags(True, q.important)


def placement_of(s: Sticker, user: User) -> Placement | None:
    return next((p for p in s.placements if p.user_id == user.id), None)


def recipients(s: Sticker) -> list[Placement]:
    return [p for p in s.placements if p.role == PlacementRole.recipient]


def can_view(s: Sticker, user: User) -> bool:
    return s.author_id == user.id or placement_of(s, user) is not None


def allowed_actions(s: Sticker, user: User) -> list[str]:
    acts: list[str] = []
    p = placement_of(s, user)
    if s.kind == Kind.personal:
        if s.author_id == user.id:
            acts = [a for a, st in PERSONAL.items() if s.status in st] + ["comment"]
        return acts
    if p is not None and p.role == PlacementRole.recipient:
        acts += [a for a, st in RECIPIENT.items() if s.status in st]
        if user.role == Role.manager and s.status != Status.withdrawn:
            acts.append("share")
    if s.author_id == user.id:
        acts += [a for a, st in AUTHOR.items() if s.status in st]
    if p is not None and p.role == PlacementRole.delegate:
        acts += [a for a, st in DELEGATE.items() if s.status in st]
    if can_view(s, user) and s.status != Status.withdrawn:
        acts.append("comment")
    return acts


def can_edit_deadline(s: Sticker, user: User) -> bool:
    if s.status in ARCHIVED or s.status == Status.resolved:
        return False
    p = placement_of(s, user)
    return s.author_id == user.id or (p is not None and p.role == PlacementRole.recipient)


def audit(db: AsyncSession, s: Sticker, actor: User | None, action: str, **data) -> None:
    db.add(AuditEvent(sticker_id=s.id, actor_id=actor.id if actor else None, action=action, data=data))


def comment(db: AsyncSession, s: Sticker, user: User, text: str, kind: CommentKind = CommentKind.comment) -> Comment:
    c = Comment(sticker_id=s.id, author_id=user.id, kind=kind, body=text.strip())
    db.add(c)
    return c


def set_status(db: AsyncSession, s: Sticker, actor: User | None, status: Status, **extra) -> None:
    old = s.status
    s.status = status
    now = utcnow()
    if status == Status.resolved:
        s.resolved_at = now
    if status == Status.closed:
        s.closed_at = now
    audit(db, s, actor, "status", old=old.value, new=status.value, **extra)


def ensure_triaged(db: AsyncSession, s: Sticker, user: User) -> None:
    """Any recipient action on a new sticker means it has been looked at: put it on the board."""
    if s.triaged_at is None:
        s.triaged_at = utcnow()
    p = placement_of(s, user)
    if s.decided_quadrant is None:
        s.decided_quadrant = (p and p.quadrant) or effective_quadrant(s)
        audit(db, s, user, "quadrant", new=s.decided_quadrant.value)
    if p is not None and p.quadrant is None:
        p.quadrant = s.decided_quadrant


def snippet(text: str | None, n: int = 300) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


def need(text: str | None) -> str:
    if not text or not text.strip():
        raise HTTPException(422, "sticker.text_required")
    return text


async def apply_action(db: AsyncSession, s: Sticker, user: User, action: str, data: dict) -> None:
    if action not in allowed_actions(s, user):
        raise HTTPException(409, "sticker.action_not_allowed")
    text: str | None = data.get("text")

    if action == "comment":
        comment(db, s, user, need(text))
        notify.emit(db, s, user, "comment", text=snippet(text))
        return
    if action == "share":
        other = await active_user(db, data.get("user_id"))
        if placement_of(s, other) is None:
            s.placements.append(Placement(user_id=other.id, role=PlacementRole.viewer))
            audit(db, s, user, "share", user_id=other.id)
            notify.emit(db, s, user, "share", target_id=other.id)
        return

    if s.kind == Kind.personal:
        if action == "resolve":
            s.outcome = Outcome.done
            s.resolved_at = utcnow()
            set_status(db, s, user, Status.closed, outcome="done")
        elif action == "reopen":
            set_status(db, s, user, Status.in_progress)
        if text and text.strip():
            comment(db, s, user, text)
        return

    if action in RECIPIENT and action != "wake":
        ensure_triaged(db, s, user)

    if action == "start":
        set_status(db, s, user, Status.in_progress)
    elif action == "ask":
        comment(db, s, user, need(text), CommentKind.question)
        set_status(db, s, user, Status.needs_info)
    elif action == "answer":
        comment(db, s, user, need(text), CommentKind.answer)
        set_status(db, s, user, Status.in_progress)
    elif action == "delegate":
        other = await active_user(db, data.get("user_id"))
        extra = {"target_id": other.id, "target": other.display_name}
        if other.id == user.id or other.id == s.author_id:
            raise HTTPException(422, "sticker.bad_delegate")
        p = placement_of(s, other)
        if p is None:
            s.placements.append(Placement(user_id=other.id, role=PlacementRole.delegate, quadrant=effective_quadrant(s)))
        else:
            p.role = PlacementRole.delegate
            p.quadrant = p.quadrant or effective_quadrant(s)
        if text and text.strip():
            comment(db, s, user, text)
        set_status(db, s, user, Status.delegated, delegate_id=other.id)
    elif action == "report":
        comment(db, s, user, need(text), CommentKind.report)
        audit(db, s, user, "report")
    elif action == "rework":
        comment(db, s, user, need(text))
        audit(db, s, user, "rework")
    elif action == "resolve":
        try:
            outcome = Outcome(data.get("outcome"))
        except ValueError:
            raise HTTPException(422, "sticker.outcome_required") from None
        s.outcome = outcome
        comment(db, s, user, need(text), CommentKind.resolution)
        set_status(db, s, user, Status.resolved, outcome=outcome.value)
    elif action == "snooze":
        until = parse_date(data.get("until"))
        if until is None or until <= date.today():
            raise HTTPException(422, "sticker.snooze_date")
        s.snoozed_until = until
        set_status(db, s, user, Status.snoozed, until=until.isoformat())
    elif action == "wake":
        s.snoozed_until = None
        set_status(db, s, user, Status.triaged)
    elif action == "reject":
        s.reject_reason = need(text).strip()
        set_status(db, s, user, Status.rejected)
    elif action == "withdraw":
        set_status(db, s, user, Status.withdrawn)
    elif action == "confirm":
        set_status(db, s, user, Status.closed)
    elif action == "reopen":
        comment(db, s, user, need(text))
        s.outcome = None
        s.resolved_at = None
        s.closed_at = None
        set_status(db, s, user, Status.in_progress, reopened=True)

    payload = {"text": snippet(text)} if text and text.strip() and action != "delegate" else {}
    if action == "delegate":
        payload = extra
    elif action == "resolve":
        payload["outcome"] = s.outcome.value
    elif action == "snooze":
        payload["until"] = s.snoozed_until.isoformat()
    notify.emit(db, s, user, action, **payload)


def parse_date(v) -> date | None:
    if v is None or isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except ValueError:
        raise HTTPException(422, "sticker.bad_date") from None


async def active_user(db: AsyncSession, user_id) -> User:
    u = await db.get(User, user_id) if isinstance(user_id, int) else None
    if u is None or not u.is_active:
        raise HTTPException(404, "user.not_found")
    return u


async def move(db: AsyncSession, s: Sticker, user: User, quadrant: Quadrant) -> None:
    """Drag on one's own board. The recipient's choice is the decision; a delegate only rearranges own board."""
    p = placement_of(s, user)
    if p is None or p.role == PlacementRole.viewer:
        raise HTTPException(403, "sticker.not_on_board")
    if s.status not in ACTIVE:
        raise HTTPException(409, "sticker.action_not_allowed")
    if p.role == PlacementRole.delegate and s.status != Status.delegated:
        raise HTTPException(409, "sticker.action_not_allowed")
    old = p.quadrant
    p.quadrant = quadrant
    if p.role == PlacementRole.recipient:
        if s.status == Status.new:
            s.triaged_at = utcnow()
            set_status(db, s, user, Status.triaged)
            notify.emit(db, s, user, "triaged", quadrant=quadrant.value)
        if s.decided_quadrant != quadrant:
            s.decided_quadrant = quadrant
            audit(db, s, user, "quadrant", old=old.value if old else None, new=quadrant.value)
    else:
        audit(db, s, user, "delegate_quadrant", new=quadrant.value)


async def tick(db: AsyncSession, today: date | None = None) -> dict:
    """Scheduler pass: deadline escalation, waking snoozed stickers, auto-closing resolved ones."""
    today = today or date.today()
    escalate_days = await get_setting(db, "escalate_days")
    autoclose_days = await get_setting(db, "autoclose_days")
    stats = {"escalated": 0, "woken": 0, "closed": 0}

    q = select(Sticker).where(
        Sticker.status.in_(ACTIVE),
        Sticker.deadline.is_not(None),
        Sticker.deadline <= today + timedelta(days=escalate_days),
        Sticker.escalated_at.is_(None),
        Sticker.kind == Kind.normal,
    )
    for s in await db.scalars(q):
        # importance never changes automatically, only urgency (SPEC §2)
        s.escalated_at = utcnow()
        if s.decided_quadrant is not None:
            s.decided_quadrant = make_urgent(s.decided_quadrant)
        for p in s.placements:
            if p.quadrant is not None and p.role != PlacementRole.viewer:
                p.quadrant = make_urgent(p.quadrant)
        audit(db, s, None, "escalated", deadline=s.deadline.isoformat())
        notify.emit(db, s, None, "escalated", deadline=s.deadline.isoformat())
        stats["escalated"] += 1

    q = select(Sticker).where(Sticker.status == Status.snoozed, Sticker.snoozed_until <= today)
    for s in await db.scalars(q):
        s.snoozed_until = None
        set_status(db, s, None, Status.triaged, woken=True)
        notify.emit(db, s, None, "woken")
        stats["woken"] += 1

    limit = utcnow() - timedelta(days=autoclose_days)
    q = select(Sticker).where(Sticker.status == Status.resolved, Sticker.resolved_at <= limit)
    for s in await db.scalars(q):
        set_status(db, s, None, Status.closed, auto=True)
        stats["closed"] += 1

    await db.commit()
    return stats


async def create(db: AsyncSession, user: User, *, title: str, body: str = "", urgent: bool = False, important: bool = False,
                 deadline: date | None = None, personal: bool = False, recipient_ids: list[int] | None = None) -> Sticker:
    """New sticker from the web or the bot. Without recipients it goes to the author's department manager."""
    s = Sticker(
        kind=Kind.personal if personal else Kind.normal,
        title=title.strip()[:200], body=body.strip(), author_id=user.id,
        author_urgent=urgent, author_important=important, deadline=deadline,
    )
    if personal:
        q = Quadrant.from_flags(urgent, important)
        s.status = Status.triaged
        s.decided_quadrant = q
        s.placements = [Placement(user_id=user.id, role=PlacementRole.recipient, quadrant=q)]
    else:
        ids = list(dict.fromkeys(recipient_ids or []))
        if not ids:
            dept = await db.get(Department, user.department_id) if user.department_id else None
            if dept is None or dept.manager_id is None or dept.manager_id == user.id:
                raise HTTPException(422, "sticker.no_recipient")
            ids = [dept.manager_id]
        if user.id in ids:
            raise HTTPException(422, "sticker.self_recipient")
        for uid in ids:
            await active_user(db, uid)
        s.placements = [Placement(user_id=uid, role=PlacementRole.recipient) for uid in ids]
    db.add(s)
    await db.flush()
    audit(db, s, user, "created", recipients=[p.user_id for p in s.placements])
    notify.emit(db, s, user, "created", text=snippet(s.body))
    return s


def storage_dir():
    d = get_settings().data_dir / "attachments"
    d.mkdir(parents=True, exist_ok=True)
    return d


def store_attachment(db: AsyncSession, s: Sticker, user: User, filename: str, content_type: str | None,
                     data: bytes, comment_id: int | None = None) -> Attachment:
    import secrets

    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "attachment.too_large")
    key = secrets.token_hex(20)
    (storage_dir() / key).write_bytes(data)
    a = Attachment(
        sticker_id=s.id, comment_id=comment_id, uploader_id=user.id, filename=filename[:200] or "file",
        content_type=(content_type or "application/octet-stream")[:127], size=len(data), storage_key=key,
    )
    db.add(a)
    audit(db, s, user, "attachment", filename=a.filename)
    return a
