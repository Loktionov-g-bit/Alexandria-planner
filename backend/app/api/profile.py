import secrets

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ..config import get_settings
from ..deps import DB, CurrentUser
from ..models import Department, User
from ..names import set_names
from ..schemas import DepartmentOut, ProfileUpdateIn, UserBrief, UserOut

router = APIRouter(prefix="/api", tags=["profile"])

ABSENCE = {"away_from", "away_until", "deputy_id"}


@router.patch("/profile", response_model=UserOut)
async def update_profile(data: ProfileUpdateIn, db: DB, user: CurrentUser) -> User:
    fields = data.model_dump(exclude_unset=True, exclude={"first_name", "last_name"})
    if ABSENCE & fields.keys():
        await check_absence(db, user, {k: fields.get(k, getattr(user, k)) for k in ABSENCE})
    for k, v in fields.items():
        setattr(user, k, v)
    set_names(user, data.first_name, data.last_name)
    await db.commit()
    return user


async def check_absence(db: DB, user: User, a: dict) -> None:
    if a["away_until"] is not None and a["away_from"] is not None and a["away_from"] > a["away_until"]:
        raise HTTPException(422, "absence.bad_dates")
    dep_id = a["deputy_id"]
    if dep_id is None:
        return
    if dep_id == user.id:
        raise HTTPException(422, "absence.self_deputy")
    dep = await db.get(User, dep_id)
    if dep is None or not dep.is_active or dep.deleted_at is not None:
        raise HTTPException(404, "user.not_found")


def calendar_url(token: str) -> str:
    return f"{get_settings().base_url.rstrip('/')}/api/calendar/{token}.ics"


@router.get("/profile/calendar")
async def calendar_link(user: CurrentUser) -> dict:
    return {"url": calendar_url(user.calendar_token) if user.calendar_token else None}


@router.post("/profile/calendar")
async def calendar_new(db: DB, user: CurrentUser) -> dict:
    """Create the feed, or replace its address (the old link stops working)."""
    user.calendar_token = secrets.token_urlsafe(32)
    await db.commit()
    return {"url": calendar_url(user.calendar_token)}


@router.delete("/profile/calendar")
async def calendar_off(db: DB, user: CurrentUser) -> dict:
    user.calendar_token = None
    await db.commit()
    return {"url": None}


@router.get("/directory/users", response_model=list[UserBrief])
async def directory(db: DB, _: CurrentUser) -> list[User]:
    """Colleagues list for addressing stickers (name + avatar only)."""
    return list(await db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.display_name)))


@router.get("/directory/departments", response_model=list[DepartmentOut])
async def departments(db: DB, _: CurrentUser) -> list[Department]:
    return list(await db.scalars(select(Department).order_by(Department.name)))
