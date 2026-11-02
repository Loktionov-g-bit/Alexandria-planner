from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import get_db
from .models import AuthSession, Role, User
from .security import token_id

COOKIE = "planner_session"
CHANNEL_COOKIE = "planner_channel"
DB = Annotated[AsyncSession, Depends(get_db)]


def as_utc(dt: datetime) -> datetime:
    # SQLite drops tzinfo; Postgres keeps it. Normalise.
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def load_session(db: AsyncSession, token: str | None) -> AuthSession | None:
    if not token:
        return None
    s = await db.get(AuthSession, token_id(token))
    if s is None:
        return None
    now = datetime.now(timezone.utc)
    idle = timedelta(hours=get_settings().session_idle_hours)
    if as_utc(s.expires_at) < now or as_utc(s.last_seen_at) + idle < now or not s.user.is_active:
        await db.delete(s)
        await db.commit()
        return None
    if now - as_utc(s.last_seen_at) > timedelta(minutes=5):
        s.last_seen_at = now
        await db.commit()
    return s


def set_channel_cookie(request: Request, response: Response, channel: str) -> None:
    """The stable container routes by this cookie; keep it in sync with the admin's choice."""
    if request.cookies.get(CHANNEL_COOKIE) != channel:
        st = get_settings()
        response.set_cookie(CHANNEL_COOKIE, channel, max_age=st.session_days * 86400, httponly=True,
                            secure=st.cookie_secure, samesite="lax", path=st.root_path or "/")


async def current_session(db: DB, request: Request, response: Response,
                          planner_session: Annotated[str | None, Cookie()] = None) -> AuthSession:
    s = await load_session(db, planner_session)
    if s is None:
        raise HTTPException(401, "auth.required")
    set_channel_cookie(request, response, s.user.effective_channel)
    return s


async def current_user(s: Annotated[AuthSession, Depends(current_session)]) -> User:
    if not s.verified:
        raise HTTPException(401, "auth.totp_required")
    return s.user


async def require_admin(u: Annotated[User, Depends(current_user)]) -> User:
    if not u.is_admin:
        raise HTTPException(403, "auth.admin_only")
    return u


async def require_manager(u: Annotated[User, Depends(current_user)]) -> User:
    if u.role != Role.manager:
        raise HTTPException(403, "auth.manager_only")
    return u


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


CurrentUser = Annotated[User, Depends(current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
ManagerUser = Annotated[User, Depends(require_manager)]
