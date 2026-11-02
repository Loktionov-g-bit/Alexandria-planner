"""Stickers: create, board, detail, lifecycle actions, comments, attachments."""

import re
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from ..deps import DB, CurrentUser
from ..models import (
    Attachment,
    AuditEvent,
    Comment,
    CommentKind,
    Kind,
    Outcome,
    Placement,
    PlacementRole,
    Quadrant,
    Status,
    Sticker,
    User,
)
from ..schemas import ORM, UserBrief
from .. import notify
from .. import stickers as lc

router = APIRouter(prefix="/api", tags=["stickers"])

INLINE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"}


# ---------------------------------------------------------------- schemas


class StickerIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=20000)
    urgent: bool = False
    important: bool = False
    deadline: date | None = None
    personal: bool = False
    recipient_ids: list[int] = Field(default_factory=list, max_length=20)


class StickerPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, max_length=20000)
    urgent: bool | None = None
    important: bool | None = None
    deadline: date | None = None


class ActionIn(BaseModel):
    action: str = Field(max_length=16)
    text: str | None = Field(default=None, max_length=20000)
    user_id: int | None = None
    outcome: Outcome | None = None
    until: date | None = None


class MoveIn(BaseModel):
    quadrant: Quadrant


class PlacementOut(ORM):
    user: UserBrief
    role: PlacementRole
    quadrant: Quadrant | None


class AttachmentOut(ORM):
    id: int
    comment_id: int | None
    filename: str
    content_type: str
    size: int
    created_at: datetime


class CommentOut(ORM):
    id: int
    author: UserBrief
    kind: CommentKind
    body: str
    created_at: datetime


class AuditOut(ORM):
    id: int
    actor: UserBrief | None
    at: datetime
    action: str
    data: dict


class StickerOut(BaseModel):
    id: int
    kind: Kind
    title: str
    body: str
    author: UserBrief
    status: Status
    author_quadrant: Quadrant
    decided_quadrant: Quadrant | None
    quadrant: Quadrant  # effective: decided, else author's (escalation applied)
    escalated: bool
    deadline: date | None
    overdue: bool
    snoozed_until: date | None
    outcome: Outcome | None
    reject_reason: str | None
    created_at: datetime
    updated_at: datetime
    recipients: list[UserBrief]
    my_role: str  # author | recipient | delegate | viewer
    my_quadrant: Quadrant | None
    comments: int = 0
    attachments: int = 0


class StickerDetail(StickerOut):
    placements: list[PlacementOut]
    thread: list[CommentOut]
    files: list[AttachmentOut]
    history: list[AuditOut]
    actions: list[str]
    can_edit: bool
    can_edit_deadline: bool


# ---------------------------------------------------------------- helpers


def out(s: Sticker, user: User, counts: dict | None = None) -> dict:
    p = lc.placement_of(s, user)
    today = date.today()
    return dict(
        id=s.id, kind=s.kind, title=s.title, body=s.body, author=s.author, status=s.status,
        author_quadrant=lc.author_quadrant(s), decided_quadrant=s.decided_quadrant, quadrant=lc.effective_quadrant(s),
        escalated=s.escalated_at is not None, deadline=s.deadline,
        overdue=bool(s.deadline and s.deadline < today and s.status in lc.ACTIVE),
        snoozed_until=s.snoozed_until, outcome=s.outcome, reject_reason=s.reject_reason,
        created_at=s.created_at, updated_at=s.updated_at,
        recipients=[r.user for r in lc.recipients(s)],
        my_role=my_role(s, user, p),
        my_quadrant=p.quadrant if p else None,
        **(counts or {}),
    )


def my_role(s: Sticker, user: User, p: Placement | None) -> str:
    if s.author_id == user.id and (p is None or s.kind == Kind.personal):
        return "author"
    return p.role.value if p else "viewer"


async def counts_for(db: DB, ids: list[int]) -> dict[int, dict]:
    res = {i: {"comments": 0, "attachments": 0} for i in ids}
    if not ids:
        return res
    for sid, n in await db.execute(select(Comment.sticker_id, func.count()).where(Comment.sticker_id.in_(ids)).group_by(Comment.sticker_id)):
        res[sid]["comments"] = n
    for sid, n in await db.execute(select(Attachment.sticker_id, func.count()).where(Attachment.sticker_id.in_(ids)).group_by(Attachment.sticker_id)):
        res[sid]["attachments"] = n
    return res


async def listing(db: DB, user: User, stickers: list[Sticker]) -> list[dict]:
    c = await counts_for(db, [s.id for s in stickers])
    return [out(s, user, c[s.id]) for s in stickers]


async def load(db: DB, sticker_id: int, user: User) -> Sticker:
    s = await db.get(Sticker, sticker_id)
    if s is None or not lc.can_view(s, user):
        raise HTTPException(404, "sticker.not_found")  # same answer for "no access": do not leak existence
    return s


async def detail(db: DB, s: Sticker, user: User) -> dict:
    await db.refresh(s, ["placements"])
    thread = list(await db.scalars(select(Comment).where(Comment.sticker_id == s.id).order_by(Comment.id).execution_options(populate_existing=True)))
    files = list(await db.scalars(select(Attachment).where(Attachment.sticker_id == s.id).order_by(Attachment.id).execution_options(populate_existing=True)))
    history = list(await db.scalars(select(AuditEvent).where(AuditEvent.sticker_id == s.id).order_by(AuditEvent.id).execution_options(populate_existing=True)))
    base = out(s, user, {"comments": len(thread), "attachments": len(files)})
    return dict(
        base,
        placements=[p for p in s.placements],
        thread=thread, files=files, history=history,
        actions=lc.allowed_actions(s, user),
        can_edit=s.author_id == user.id and (s.status == Status.new or s.kind == Kind.personal) and s.status not in lc.ARCHIVED,
        can_edit_deadline=lc.can_edit_deadline(s, user),
    )


def safe_name(name: str | None) -> str:
    name = (name or "file").replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip() or "file"
    return name[:200]


# ---------------------------------------------------------------- routes


@router.post("/stickers", response_model=StickerDetail, status_code=201)
async def create_sticker(data: StickerIn, db: DB, user: CurrentUser) -> dict:
    s = await lc.create(
        db, user, title=data.title, body=data.body, urgent=data.urgent, important=data.important,
        deadline=data.deadline, personal=data.personal, recipient_ids=data.recipient_ids,
    )
    await db.commit()
    s = await db.get(Sticker, s.id, populate_existing=True, options=[selectinload(Sticker.placements)])
    return await detail(db, s, user)


@router.get("/board", response_model=list[StickerOut])
async def board(db: DB, user: CurrentUser) -> list[dict]:
    """Everything on my board: inbox (my_quadrant = null) and the four quadrants."""
    q = (
        select(Sticker).join(Placement, Placement.sticker_id == Sticker.id)
        .where(
            Placement.user_id == user.id,
            Placement.role != PlacementRole.viewer,
            Sticker.status.in_(lc.ACTIVE),
            or_(Placement.role == PlacementRole.recipient, Sticker.status == Status.delegated),
        )
        .order_by(Sticker.deadline.is_(None), Sticker.deadline, Sticker.id.desc())
    )
    return await listing(db, user, list((await db.scalars(q)).unique()))


@router.get("/stickers/sent", response_model=list[StickerOut])
async def sent(db: DB, user: CurrentUser, include_archived: bool = False) -> list[dict]:
    q = select(Sticker).where(Sticker.author_id == user.id, Sticker.kind == Kind.normal)
    if not include_archived:
        q = q.where(Sticker.status.not_in(lc.ARCHIVED))
    return await listing(db, user, list(await db.scalars(q.order_by(Sticker.id.desc()).limit(500))))


@router.get("/stickers/shared", response_model=list[StickerOut])
async def shared(db: DB, user: CurrentUser) -> list[dict]:
    q = (
        select(Sticker).join(Placement)
        .where(Placement.user_id == user.id, Placement.role == PlacementRole.viewer, Sticker.status.not_in(lc.ARCHIVED))
        .order_by(Sticker.id.desc()).limit(500)
    )
    return await listing(db, user, list((await db.scalars(q)).unique()))


@router.get("/stickers/archive", response_model=list[StickerOut])
async def archive(db: DB, user: CurrentUser, q: str = "", limit: int = 100, before_id: int | None = None) -> list[dict]:
    mine = select(Placement.sticker_id).where(Placement.user_id == user.id)
    stmt = select(Sticker).where(
        Sticker.status.in_(lc.ARCHIVED),
        or_(Sticker.author_id == user.id, Sticker.id.in_(mine)),
    )
    if q.strip():
        term = f"%{q.strip()}%"
        cond = or_(Sticker.title.ilike(term), Sticker.body.ilike(term))  # PG ILIKE is Unicode-aware
        if q.strip().lstrip("№#").isdigit():
            cond = or_(cond, Sticker.id == int(q.strip().lstrip("№#")))
        stmt = stmt.where(cond)
    if before_id:
        stmt = stmt.where(Sticker.id < before_id)
    stmt = stmt.order_by(Sticker.id.desc()).limit(min(limit, 500))
    return await listing(db, user, list(await db.scalars(stmt)))


@router.get("/stickers/{sticker_id}", response_model=StickerDetail)
async def get_sticker(sticker_id: int, db: DB, user: CurrentUser) -> dict:
    s = await load(db, sticker_id, user)
    p = lc.placement_of(s, user)
    if p is not None and p.seen_at is None:
        p.seen_at = lc.utcnow()
        await db.commit()
    return await detail(db, s, user)


@router.patch("/stickers/{sticker_id}", response_model=StickerDetail)
async def edit_sticker(sticker_id: int, data: StickerPatch, db: DB, user: CurrentUser) -> dict:
    s = await load(db, sticker_id, user)
    d = await detail(db, s, user)
    fields = data.model_dump(exclude_unset=True)
    if "deadline" in fields:
        if not d["can_edit_deadline"]:
            raise HTTPException(403, "sticker.action_not_allowed")
        if s.deadline != fields["deadline"]:
            lc.audit(db, s, user, "deadline", old=s.deadline.isoformat() if s.deadline else None,
                     new=fields["deadline"].isoformat() if fields["deadline"] else None)
            s.deadline = fields["deadline"]
            s.escalated_at = None  # a new deadline gets a new escalation
            notify.emit(db, s, user, "deadline", deadline=s.deadline.isoformat() if s.deadline else None)
    content = {k: v for k, v in fields.items() if k != "deadline"}
    if content:
        if not d["can_edit"]:
            raise HTTPException(403, "sticker.action_not_allowed")
        for k, v in content.items():
            if v is None:
                continue
            setattr(s, {"urgent": "author_urgent", "important": "author_important"}.get(k, k), v.strip() if isinstance(v, str) else v)
        if s.kind == Kind.personal:
            s.decided_quadrant = lc.author_quadrant(s)
            for p in s.placements:
                p.quadrant = s.decided_quadrant
        lc.audit(db, s, user, "edited", fields=sorted(content))
    await db.commit()
    return await detail(db, s, user)


@router.post("/stickers/{sticker_id}/actions", response_model=StickerDetail)
async def act(sticker_id: int, data: ActionIn, db: DB, user: CurrentUser) -> dict:
    s = await load(db, sticker_id, user)
    await lc.apply_action(db, s, user, data.action, data.model_dump(exclude={"action"}, mode="python"))
    await db.commit()
    return await detail(db, s, user)


@router.put("/stickers/{sticker_id}/place", response_model=StickerOut)
async def place(sticker_id: int, data: MoveIn, db: DB, user: CurrentUser) -> dict:
    s = await load(db, sticker_id, user)
    await lc.move(db, s, user, data.quadrant)
    await db.commit()
    return (await listing(db, user, [s]))[0]


@router.post("/stickers/{sticker_id}/attachments", response_model=AttachmentOut, status_code=201)
async def upload(sticker_id: int, file: UploadFile, db: DB, user: CurrentUser,
                 comment_id: Annotated[int | None, Form()] = None) -> Attachment:
    s = await load(db, sticker_id, user)
    if "comment" not in lc.allowed_actions(s, user):
        raise HTTPException(409, "sticker.action_not_allowed")
    if comment_id is not None:
        c = await db.get(Comment, comment_id)
        if c is None or c.sticker_id != s.id or c.author_id != user.id:
            raise HTTPException(404, "comment.not_found")
    chunks = []
    size = 0
    while chunk := await file.read(1024 * 1024):
        size += len(chunk)
        if size > lc.MAX_UPLOAD:
            raise HTTPException(413, "attachment.too_large")
        chunks.append(chunk)
    a = lc.store_attachment(db, s, user, safe_name(file.filename), file.content_type, b"".join(chunks), comment_id)
    await db.commit()
    return a


@router.get("/attachments/{attachment_id}")
async def download(attachment_id: int, db: DB, user: CurrentUser) -> FileResponse:
    a = await db.get(Attachment, attachment_id)
    if a is None:
        raise HTTPException(404, "attachment.not_found")
    await load(db, a.sticker_id, user)
    path = lc.storage_dir() / a.storage_key
    if not path.is_file():
        raise HTTPException(404, "attachment.not_found")
    inline = a.content_type in INLINE_TYPES
    return FileResponse(
        path, media_type=a.content_type if inline else "application/octet-stream", filename=a.filename,
        content_disposition_type="inline" if inline else "attachment",
        headers={"Content-Security-Policy": "sandbox", "Cache-Control": "private, max-age=3600"},
    )
