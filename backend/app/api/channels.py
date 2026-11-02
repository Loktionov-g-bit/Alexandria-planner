"""Admin: who runs the beta version. Rollout = everybody to beta; rollback = everybody to stable."""

from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update

from .. import __version__
from ..config import get_settings
from ..deps import DB, AdminUser
from ..models import Department, User

router = APIRouter(prefix="/api/admin/channels", tags=["admin"])

Channel = Literal["stable", "beta"]


class ChannelIn(BaseModel):
    channel: Channel | None  # None = inherit (user: from department; department: stable)


async def beta_health() -> dict | None:
    st = get_settings()
    if not st.beta_url:
        return None
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(st.beta_url.rstrip("/") + "/api/health")
            return r.json() if r.status_code == 200 else {"ok": False}
    except (httpx.HTTPError, ValueError):
        return {"ok": False}


@router.get("")
async def overview(db: DB, _: AdminUser) -> dict:
    st = get_settings()
    users = list(await db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.display_name)))
    depts = list(await db.scalars(select(Department).order_by(Department.name)))
    health = await beta_health()
    return {
        "this": {"channel": st.channel, "version": __version__},
        "beta": {"configured": st.beta_url is not None, "reachable": bool(health and health.get("ok")),
                 "version": health.get("version") if health else None},
        "departments": [{"id": d.id, "name": d.name, "channel": d.update_channel} for d in depts],
        "users": [{"id": u.id, "display_name": u.display_name, "avatar_color": u.avatar_color, "department_id": u.department_id,
                   "channel": u.update_channel, "effective": u.effective_channel} for u in users],
        "on_beta": sum(1 for u in users if u.effective_channel == "beta"),
    }


@router.put("/users/{user_id}", status_code=204)
async def set_user(user_id: int, data: ChannelIn, db: DB, _: AdminUser) -> None:
    u = await db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "user.not_found")
    u.update_channel = data.channel
    await db.commit()


@router.put("/departments/{dept_id}", status_code=204)
async def set_department(dept_id: int, data: ChannelIn, db: DB, _: AdminUser) -> None:
    d = await db.get(Department, dept_id)
    if d is None:
        raise HTTPException(404, "department.not_found")
    d.update_channel = data.channel
    await db.commit()


@router.post("/all", status_code=204)
async def set_all(data: ChannelIn, db: DB, _: AdminUser) -> None:
    """One button: rollout (all to beta) or rollback (all to stable). Personal overrides are cleared."""
    if data.channel is None:
        raise HTTPException(422, "channel.required")
    await db.execute(update(Department).values(update_channel=data.channel))
    await db.execute(update(User).values(update_channel=None if data.channel == "stable" else data.channel))
    await db.commit()
