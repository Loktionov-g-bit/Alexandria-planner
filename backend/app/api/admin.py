"""Administrator: users, departments, login journal. Admins never see sticker contents here."""

import random

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from ..deps import DB, AdminUser
from ..models import AuthSession, Department, LoginEvent, Role, User
from ..schemas import DepartmentIn, DepartmentOut, LoginEventOut, UserCreateIn, UserOut, UserUpdateIn
from ..names import free_login, set_names
from ..security import hash_password, password_problems

router = APIRouter(prefix="/api/admin", tags=["admin"])

AVATAR_COLORS = ["#5b7cfa", "#e8730c", "#2f9e6f", "#c2410c", "#7c5cd6", "#0e8fb8", "#d6457a", "#4d7c0f"]


def check_password(password: str, login: str) -> None:
    problems = password_problems(password, login=login)
    if problems:
        raise HTTPException(422, problems)


async def check_department(db: DB, dept_id: int | None) -> None:
    if dept_id is not None and await db.get(Department, dept_id) is None:
        raise HTTPException(404, "department.not_found")


@router.get("/users", response_model=list[UserOut])
async def list_users(db: DB, _: AdminUser) -> list[User]:
    return list(await db.scalars(select(User).order_by(User.display_name)))


@router.get("/login-suggestion")
async def login_suggestion(first_name: str, last_name: str, db: DB, _: AdminUser) -> dict:
    """Free login for a new user: Олег Журавлёв → o.zhuravlev (or o.zhuravlev2 if taken)."""
    return {"login": await free_login(db, first_name[:60], last_name[:60])}


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(data: UserCreateIn, db: DB, admin: AdminUser) -> User:
    login = data.login or await free_login(db, data.first_name, data.last_name)
    check_password(data.password, login)
    await check_department(db, data.department_id)
    user = User(
        **data.model_dump(exclude={"password", "avatar_color", "login", "first_name", "last_name"}),
        login=login,
        password_hash=hash_password(data.password),
        avatar_color=data.avatar_color or random.choice(AVATAR_COLORS),
        # same company, most likely the same language and clock; each person can change it in the profile
        locale=admin.locale,
        timezone=admin.timezone,
    )
    set_names(user, data.first_name, data.last_name)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        raise HTTPException(409, "user.login_taken") from None
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: int, data: UserUpdateIn, db: DB, admin: AdminUser) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "user.not_found")
    fields = data.model_dump(exclude_unset=True, exclude={"password", "reset_2fa", "telegram_unlink", "first_name", "last_name"})
    set_names(user, data.first_name, data.last_name)
    if user.id == admin.id and (fields.get("is_admin") is False or fields.get("is_active") is False):
        raise HTTPException(400, "user.cannot_demote_self")
    if "department_id" in fields:
        await check_department(db, fields["department_id"])
    for k, v in fields.items():
        setattr(user, k, v)
    kill_sessions = data.is_active is False
    if data.password:
        check_password(data.password, user.login)
        user.password_hash = hash_password(data.password)
        user.failed_logins = 0
        user.locked_until = None
        kill_sessions = True
    if data.telegram_unlink:  # e.g. a lost phone
        user.telegram_chat_id = None
        user.telegram_username = None
    if data.reset_2fa:
        user.totp_enabled = False
        user.totp_secret = None
        kill_sessions = True
    if kill_sessions:
        await db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    await db.commit()
    return user


@router.get("/departments", response_model=list[DepartmentOut])
async def list_departments(db: DB, _: AdminUser) -> list[Department]:
    return list(await db.scalars(select(Department).order_by(Department.name)))


async def save_department(db: DB, dept: Department, data: DepartmentIn) -> Department:
    if data.manager_id is not None:
        mgr = await db.get(User, data.manager_id)
        if mgr is None or mgr.role != Role.manager:
            raise HTTPException(422, "department.manager_must_be_manager")
    dept.name = data.name.strip()
    dept.manager_id = data.manager_id
    try:
        await db.commit()
    except IntegrityError:
        raise HTTPException(409, "department.name_taken") from None
    return dept


@router.post("/departments", response_model=DepartmentOut, status_code=201)
async def create_department(data: DepartmentIn, db: DB, _: AdminUser) -> Department:
    dept = Department(name=data.name)
    db.add(dept)
    return await save_department(db, dept, data)


@router.patch("/departments/{dept_id}", response_model=DepartmentOut)
async def update_department(dept_id: int, data: DepartmentIn, db: DB, _: AdminUser) -> Department:
    dept = await db.get(Department, dept_id)
    if dept is None:
        raise HTTPException(404, "department.not_found")
    return await save_department(db, dept, data)


@router.get("/logins", response_model=list[LoginEventOut])
async def login_journal(db: DB, _: AdminUser, limit: int = 200, before_id: int | None = None) -> list[LoginEvent]:
    q = select(LoginEvent).order_by(LoginEvent.id.desc()).limit(min(limit, 1000))
    if before_id:
        q = q.where(LoginEvent.id < before_id)
    return list(await db.scalars(q))
