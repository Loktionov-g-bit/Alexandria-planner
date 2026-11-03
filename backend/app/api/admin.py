"""Administrator: users, departments, login journal. Admins never see sticker contents here."""

import random

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, exists, or_, select, update
from sqlalchemy.exc import IntegrityError

from ..deps import DB, AdminUser
from ..locales import texts
from ..models import (Attachment, AuditEvent, AuthSession, Comment, Department, LoginEvent, Notification, Placement,
                      PushSubscription, Role, Sticker, User, utcnow)
from ..mode import get_mode, set_mode
from ..schemas import ModeIn, DepartmentIn, DepartmentOut, LoginEventOut, UserCreateIn, UserOut, UserUpdateIn
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
    return list(await db.scalars(select(User).where(User.deleted_at.is_(None)).order_by(User.display_name)))


@router.get("/login-suggestion")
async def login_suggestion(first_name: str, last_name: str, db: DB, _: AdminUser) -> dict:
    """Free login for a new user: Олег Журавлёв → o.zhuravlev (or o.zhuravlev2 if taken)."""
    return {"login": await free_login(db, first_name[:60], last_name[:60])}


@router.post("/mode")
async def change_mode(data: ModeIn, db: DB, admin: AdminUser) -> dict:
    """Diary -> team: the admin leads the first team (named here). Team -> diary: only while nobody else is active."""
    if data.mode == await get_mode(db):
        return {"mode": data.mode}
    if data.mode == "team":
        name = (data.team or "").strip()
        if not name:
            raise HTTPException(422, "setup.team_name_required")
        if admin.department_id is None:
            dept = await db.scalar(select(Department).where(Department.name == name))
            if dept is None:
                dept = Department(name=name)
                db.add(dept)
                await db.flush()
            admin.department_id = dept.id
            admin.role = Role.manager
            if dept.manager_id is None:
                dept.manager_id = admin.id
    else:
        others = await db.scalar(select(User.id).where(User.is_active.is_(True), User.deleted_at.is_(None), User.id != admin.id).limit(1))
        if others is not None:
            raise HTTPException(409, "mode.has_people")
    await set_mode(db, data.mode)
    await db.commit()
    return {"mode": data.mode}


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(data: UserCreateIn, db: DB, admin: AdminUser) -> User:
    if await get_mode(db) == "solo":
        raise HTTPException(409, "mode.solo_no_people")
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


DELETED = texts("common")


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, db: DB, admin: AdminUser) -> dict:
    """Remove an account from the system.

    Nobody else's data depends on it -> the row is deleted for good. Otherwise (the person wrote stickers or comments
    that stay in colleagues' history) the account is erased: no login, password, 2FA, e-mail or Telegram remain,
    the name becomes "Deleted user", it disappears from every list, and the login can be given to someone new."""
    user = await db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(404, "user.not_found")
    if user.id == admin.id:
        raise HTTPException(400, "user.cannot_delete_self")
    await db.execute(update(Department).where(Department.manager_id == user.id).values(manager_id=None))
    for model in (AuthSession, PushSubscription, Notification):
        await db.execute(delete(model).where(model.user_id == user.id))
    await db.execute(update(Notification).where(Notification.actor_id == user.id).values(actor_id=None))
    await db.execute(update(LoginEvent).where(LoginEvent.user_id == user.id).values(user_id=None))
    used = await db.scalar(select(or_(
        exists().where(Sticker.author_id == user.id), exists().where(Comment.author_id == user.id),
        exists().where(Attachment.uploader_id == user.id), exists().where(AuditEvent.actor_id == user.id),
        exists().where(Placement.user_id == user.id),
    )))
    if not used:
        await db.delete(user)
        await db.commit()
        return {"deleted": True, "kept_in_history": False}
    name = DELETED.get(admin.locale, DELETED["ru"])["deleted_user"]
    user.login = f"deleted-{user.id}"
    user.first_name, user.last_name, user.display_name = name, "", name
    user.email = None
    user.password_hash = hash_password(random.randbytes(32).hex())  # nobody knows it
    user.totp_enabled, user.totp_secret, user.totp_last_step = False, None, None
    user.telegram_chat_id = user.telegram_username = user.telegram_link_code = user.telegram_link_expires = None
    user.notify_telegram = False
    user.is_active, user.is_admin, user.role = False, False, Role.employee
    user.department_id = None
    user.avatar_color = "#9aa1ab"
    user.deleted_at = utcnow()
    await db.commit()
    return {"deleted": True, "kept_in_history": True}
