"""Telegram settings (admin) and account linking (profile). The token never leaves the server unmasked."""

import secrets
from datetime import timedelta

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..deps import DB, AdminUser, CurrentUser
from ..models import AppSetting, utcnow
from ..schemas import UserOut
from ..telegram.api import TelegramAPI, TelegramError
from ..telegram import tunnel as tun
from ..telegram.runner import load_config

router = APIRouter(prefix="/api", tags=["telegram"])


class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=100, pattern=r"^\d+:[A-Za-z0-9_-]+$")


def mask(token: str) -> str:
    bot_id, _, secret = token.partition(":")
    return f"{bot_id}:…{secret[-4:]}"


async def get_me(token: str) -> dict:
    api = TelegramAPI(token)
    try:
        return await api.call("getMe")
    except TelegramError as e:
        raise HTTPException(422, "telegram.bad_token" if e.code in (401, 404) else "telegram.unreachable") from None
    finally:
        await api.close()


@router.get("/telegram/status")
async def status(db: DB, _: CurrentUser) -> dict:
    cfg = await load_config(db)
    return {"configured": cfg is not None, "username": cfg.get("username") if cfg else None}


@router.get("/admin/telegram")
async def admin_status(db: DB, _: AdminUser) -> dict:
    cfg = await load_config(db)
    if cfg is None:
        return {"configured": False, "username": None, "token": None}
    return {"configured": True, "username": cfg.get("username"), "token": mask(cfg["token"])}


@router.put("/admin/telegram")
async def set_token(data: TokenIn, db: DB, _: AdminUser) -> dict:
    me = await get_me(data.token)
    row = await db.get(AppSetting, "telegram")
    value = {"token": data.token, "username": me.get("username", ""), "bot_id": me.get("id")}
    if row is None:
        db.add(AppSetting(key="telegram", value=value))
    else:
        row.value = value
    await db.commit()
    return {"configured": True, "username": value["username"], "token": mask(data.token)}


@router.post("/admin/telegram/check")
async def check(db: DB, _: AdminUser) -> dict:
    cfg = await load_config(db)
    if cfg is None:
        raise HTTPException(409, "telegram.not_configured")
    me = await get_me(cfg["token"])
    return {"ok": True, "username": me.get("username")}


@router.delete("/admin/telegram", status_code=204)
async def remove(db: DB, _: AdminUser) -> None:
    row = await db.get(AppSetting, "telegram")
    if row is not None:
        await db.delete(row)
        await db.commit()


@router.post("/telegram/link")
async def link(db: DB, user: CurrentUser) -> dict:
    """One-time code (15 min). The user opens t.me/<bot>?start=<code>; the bot ties the chat to this account."""
    cfg = await load_config(db)
    if cfg is None:
        raise HTTPException(409, "telegram.not_configured")
    user.telegram_link_code = secrets.token_urlsafe(12)
    user.telegram_link_expires = utcnow() + timedelta(minutes=15)
    await db.commit()
    return {"url": f"https://t.me/{cfg['username']}?start={user.telegram_link_code}", "code": user.telegram_link_code,
            "username": cfg["username"]}


@router.delete("/telegram/link", response_model=UserOut)
async def unlink(db: DB, user: CurrentUser):
    user.telegram_chat_id = None
    user.telegram_username = None
    user.telegram_link_code = None
    await db.commit()
    return user


# ------------------------------------------------------------ backup route: WireGuard tunnel to Telegram

class TunnelMode(BaseModel):
    mode: str = Field(pattern="^(auto|always|off)$")


@router.get("/admin/telegram/tunnel")
async def tunnel_status(db: DB, _: AdminUser) -> dict:
    return tun.public(await tun.load(db))


@router.put("/admin/telegram/tunnel")
async def tunnel_upload(db: DB, _: AdminUser, file: UploadFile = File(...)) -> dict:
    """A WireGuard .conf or a .zip with one. Keys stay on the server; the page sees only endpoint and address."""
    data = await file.read(tun.MAX_UPLOAD + 1)
    try:
        parsed = tun.parse_upload(file.filename or "", data)
    except tun.TunnelError as e:
        raise HTTPException(422, f"tunnel.{e.args[0]}") from None
    old = await tun.load(db)
    await tun.save(db, tun.stored(parsed, (old or {}).get("mode", "auto")))
    return tun.public(await tun.load(db))


@router.patch("/admin/telegram/tunnel")
async def tunnel_mode(data: TunnelMode, db: DB, _: AdminUser) -> dict:
    value = await tun.load(db)
    if value is None:
        raise HTTPException(409, "tunnel.not_configured")
    await tun.save(db, {**value, "mode": data.mode})
    return tun.public(await tun.load(db))


@router.delete("/admin/telegram/tunnel", status_code=204)
async def tunnel_remove(db: DB, _: AdminUser) -> None:
    await tun.save(db, None)


@router.post("/admin/telegram/tunnel/check")
async def tunnel_check(db: DB, _: AdminUser) -> dict:
    """Try both routes separately: is Telegram reachable directly, and through the tunnel?"""
    import httpx

    async def probe(proxy: str | None) -> dict:
        try:
            async with httpx.AsyncClient(proxy=proxy, timeout=httpx.Timeout(15, connect=10)) as c:
                r = await c.get("https://api.telegram.org/")
            return {"ok": True, "status": r.status_code}
        except httpx.HTTPError as e:
            return {"ok": False, "error": type(e).__name__}

    direct = await probe(None)
    via = {"ok": False, "error": "not_configured"}
    if await tun.tunnel.ensure():
        via = await probe(tun.tunnel.proxy)
    return {"direct": direct, "tunnel": via, **tun.public(await tun.load(db))}
