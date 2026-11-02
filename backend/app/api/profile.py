from fastapi import APIRouter
from sqlalchemy import select

from ..deps import DB, CurrentUser
from ..models import Department, User
from ..names import set_names
from ..schemas import DepartmentOut, ProfileUpdateIn, UserBrief, UserOut

router = APIRouter(prefix="/api", tags=["profile"])


@router.patch("/profile", response_model=UserOut)
async def update_profile(data: ProfileUpdateIn, db: DB, user: CurrentUser) -> User:
    for k, v in data.model_dump(exclude_unset=True, exclude={"first_name", "last_name"}).items():
        setattr(user, k, v)
    set_names(user, data.first_name, data.last_name)
    await db.commit()
    return user


@router.get("/directory/users", response_model=list[UserBrief])
async def directory(db: DB, _: CurrentUser) -> list[User]:
    """Colleagues list for addressing stickers (name + avatar only)."""
    return list(await db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.display_name)))


@router.get("/directory/departments", response_model=list[DepartmentOut])
async def departments(db: DB, _: CurrentUser) -> list[Department]:
    return list(await db.scalars(select(Department).order_by(Department.name)))
