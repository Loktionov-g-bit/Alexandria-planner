"""First-run wizard: creates the first administrator. No default passwords exist."""

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ..deps import DB
from ..models import AppSetting, Department, Role, User
from ..schemas import MeOut, SetupIn
from ..mode import set_mode
from ..names import base_login, full_name
from ..security import hash_password, password_problems
from .auth import me_out, start_session

router = APIRouter(prefix="/api/setup", tags=["setup"])


class SetupState(BaseModel):
    needed: bool


async def setup_needed(db: DB) -> bool:
    return (await db.scalar(select(func.count()).select_from(User))) == 0


@router.get("", response_model=SetupState)
async def state(db: DB) -> SetupState:
    return SetupState(needed=await setup_needed(db))


@router.post("", response_model=MeOut)
async def run_setup(data: SetupIn, request: Request, response: Response, db: DB) -> MeOut:
    if not await setup_needed(db):
        raise HTTPException(409, "setup.already_done")
    team = data.mode == "team"
    if team and not data.department.strip():
        raise HTTPException(422, "setup.team_name_required")
    login = data.login or base_login(data.first_name, data.last_name)
    problems = password_problems(data.password, login=login)
    if problems:
        raise HTTPException(422, problems)
    # Primary-key insert acts as a lock against two concurrent wizards.
    db.add(AppSetting(key="setup_done", value=True))
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(409, "setup.already_done") from None
    await set_mode(db, data.mode)
    dept = None
    if team:
        dept = Department(name=data.department.strip())
        db.add(dept)
        await db.flush()
    user = User(
        login=login,
        first_name=data.first_name.strip(),
        last_name=data.last_name.strip(),
        display_name=full_name(data.first_name, data.last_name),
        password_hash=hash_password(data.password),
        # a diary's owner is their own manager: if the diary later grows into a team, they lead it
        role=Role.manager if data.is_manager or not team else Role.employee,
        is_admin=True,
        department_id=dept.id if dept else None,
        locale=data.locale,
        timezone=data.timezone,
    )
    db.add(user)
    await db.flush()
    if dept is not None and data.is_manager:
        dept.manager_id = user.id
    s = await start_session(db, request, response, user)
    await db.commit()
    return await me_out(db, s)
