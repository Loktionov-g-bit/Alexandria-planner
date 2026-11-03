from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy import select

from ..config import get_settings
from ..deps import CHANNEL_COOKIE, COOKIE, DB, set_channel_cookie, CurrentUser, as_utc, client_ip, current_session, load_session
from ..models import AuthSession, LoginEvent, User
from ..schemas import CodeIn, LoginIn, MeOut, PasswordChangeIn, TotpSetupOut, UserOut
from .. import throttle
from ..security import (
    hash_password,
    new_token,
    new_totp_secret,
    password_problems,
    totp_uri,
    verify_password,
    use_totp,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def pending_step(s: AuthSession) -> str | None:
    if s.verified:
        return None
    return "totp" if s.user.totp_enabled else "totp_setup"


async def me_out(db, s: AuthSession) -> MeOut:
    from ..mode import get_mode

    return MeOut(
        user=UserOut.model_validate(s.user), verified=s.verified, pending=pending_step(s), channel=get_settings().channel,
        mode=await get_mode(db),
    )


def set_cookie(response: Response, token: str) -> None:
    st = get_settings()
    response.set_cookie(
        COOKIE,
        token,
        max_age=st.session_days * 86400,
        httponly=True,
        secure=st.cookie_secure,
        samesite="lax",
        path=st.root_path or "/",
    )


async def start_session(db: DB, request: Request, response: Response, user: User) -> AuthSession:
    token, sid = new_token()
    now = datetime.now(timezone.utc)
    s = AuthSession(
        id=sid,
        user_id=user.id,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(days=get_settings().session_days),
        verified=not (user.totp_enabled or user.needs_2fa),
        ip=client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:255],
    )
    s.user = user
    db.add(s)
    set_cookie(response, token)
    set_channel_cookie(request, response, user.effective_channel)
    return s


def log_event(db: DB, request: Request, login: str, user: User | None, success: bool, reason: str) -> None:
    db.add(
        LoginEvent(
            user_id=user.id if user else None,
            login=login[:64],
            ip=client_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:255],
            success=success,
            reason=reason,
        )
    )


def register_failure(user: User) -> None:
    st = get_settings()
    user.failed_logins += 1
    if user.failed_logins >= st.login_max_attempts:
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=st.login_lock_minutes)
        user.failed_logins = 0


def ensure_not_locked(user: User | None) -> None:
    if user and user.locked_until and as_utc(user.locked_until) > datetime.now(timezone.utc):
        raise HTTPException(429, "auth.locked")


@router.post("/login", response_model=MeOut)
async def login(data: LoginIn, request: Request, response: Response, db: DB) -> MeOut:
    throttle.check(client_ip(request))
    user = await db.scalar(select(User).where(User.login == data.login.strip()))
    try:
        ensure_not_locked(user)
    except HTTPException:
        log_event(db, request, data.login, user, False, "locked")
        await db.commit()
        raise
    ok = verify_password(user.password_hash if user else None, data.password)
    if not ok or not user.is_active:
        if user:
            register_failure(user)
        throttle.failed(client_ip(request))
        log_event(db, request, data.login, user, False, "bad_password" if not ok else "inactive")
        await db.commit()
        raise HTTPException(401, "auth.invalid")
    user.failed_logins = 0
    user.locked_until = None
    s = await start_session(db, request, response, user)
    log_event(db, request, data.login, user, True, "ok" if s.verified else "password_ok")
    await db.commit()
    return await me_out(db, s)


@router.post("/totp", response_model=MeOut)
async def totp_verify(data: CodeIn, request: Request, db: DB, s: Annotated[AuthSession, Depends(current_session)]) -> MeOut:
    user = s.user
    throttle.check(client_ip(request))
    ensure_not_locked(user)
    if not user.totp_enabled:
        raise HTTPException(400, "auth.totp_not_enabled")
    if not use_totp(user, data.code):
        register_failure(user)
        throttle.failed(client_ip(request))
        log_event(db, request, user.login, user, False, "bad_totp")
        await db.commit()
        raise HTTPException(401, "auth.bad_code")
    user.failed_logins = 0
    s.verified = True
    log_event(db, request, user.login, user, True, "ok")
    await db.commit()
    return await me_out(db, s)


@router.post("/totp/setup", response_model=TotpSetupOut)
async def totp_setup(db: DB, s: Annotated[AuthSession, Depends(current_session)]) -> TotpSetupOut:
    """Start (or restart) 2FA enrollment. Allowed for a fresh password-only session or a verified one."""
    user = s.user
    if user.totp_enabled:
        raise HTTPException(400, "auth.totp_already_enabled")
    user.totp_secret = new_totp_secret()
    await db.commit()
    return TotpSetupOut(secret=user.totp_secret, uri=totp_uri(user.totp_secret, user.login))


@router.post("/totp/enable", response_model=MeOut)
async def totp_enable(data: CodeIn, request: Request, db: DB, s: Annotated[AuthSession, Depends(current_session)]) -> MeOut:
    user = s.user
    if user.totp_enabled:
        raise HTTPException(400, "auth.totp_already_enabled")
    if not use_totp(user, data.code):
        raise HTTPException(401, "auth.bad_code")
    user.totp_enabled = True
    s.verified = True
    log_event(db, request, user.login, user, True, "totp_enabled")
    await db.commit()
    return await me_out(db, s)


@router.post("/totp/disable", response_model=MeOut)
async def totp_disable(data: CodeIn, db: DB, user: CurrentUser, s: Annotated[AuthSession, Depends(current_session)]) -> MeOut:
    if user.needs_2fa:
        raise HTTPException(403, "auth.totp_mandatory")
    if not use_totp(user, data.code):
        raise HTTPException(401, "auth.bad_code")
    user.totp_enabled = False
    user.totp_secret = None
    await db.commit()
    return await me_out(db, s)


@router.get("/me", response_model=MeOut)
async def me(db: DB, s: Annotated[AuthSession, Depends(current_session)]) -> MeOut:
    return await me_out(db, s)


@router.post("/logout", status_code=204)
async def logout(response: Response, db: DB, planner_session: Annotated[str | None, Cookie()] = None) -> None:
    s = await load_session(db, planner_session)
    if s:
        await db.delete(s)
        await db.commit()
    response.delete_cookie(COOKIE, path=get_settings().root_path or "/")
    response.delete_cookie(CHANNEL_COOKIE, path=get_settings().root_path or "/")


@router.post("/password", status_code=204)
async def change_password(data: PasswordChangeIn, request: Request, db: DB, user: CurrentUser,
                          s: Annotated[AuthSession, Depends(current_session)]) -> None:
    throttle.check(client_ip(request))
    if not verify_password(user.password_hash, data.old_password):
        throttle.failed(client_ip(request))
        raise HTTPException(401, "auth.invalid")
    problems = password_problems(data.new_password, login=user.login)
    if problems:
        raise HTTPException(422, problems)
    user.password_hash = hash_password(data.new_password)
    # sign out every other session
    others = await db.scalars(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.id != s.id))
    for o in others:
        await db.delete(o)
    await db.commit()
