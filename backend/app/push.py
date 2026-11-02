"""Web Push (VAPID). Keys are generated on first use and kept in app_settings."""

import asyncio
import base64
import json
import logging
from urllib.parse import urlparse

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01
from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .models import AppSetting, PushSubscription

log = logging.getLogger("planner.push")


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


async def vapid(db: AsyncSession) -> tuple[Vapid01, str]:
    """(signing key, public key for the browser's applicationServerKey)."""
    row = await db.get(AppSetting, "vapid")
    if row is None:
        v = Vapid01()
        v.generate_keys()
        row = AppSetting(key="vapid", value={"pem": v.private_pem().decode()})
        db.add(row)
        await db.commit()
    v = Vapid01.from_pem(row.value["pem"].encode())
    public = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return v, _b64(public)


def _claims() -> dict:
    base = get_settings().base_url
    host = urlparse(base).hostname or "localhost"
    # Apple rejects mailto: with a non-public host less often than a bare URL; both are allowed by the spec
    return {"sub": base if base.startswith("https://") else f"mailto:planner@{host}"}


async def send(db: AsyncSession, user_id: int, payload: dict) -> bool:
    """Send to every device of the user. Dead subscriptions are removed. True if any device accepted."""
    subs = list(await db.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id)))
    if not subs:
        return False
    key, _ = await vapid(db)
    data = json.dumps(payload, ensure_ascii=False)
    ok = False
    dead: list[int] = []
    for s in subs:
        info = {"endpoint": s.endpoint, "keys": {"p256dh": s.p256dh, "auth": s.auth}}
        try:
            await asyncio.to_thread(webpush, info, data, vapid_private_key=key, vapid_claims=_claims(), ttl=86400, timeout=10)
            ok = True
        except WebPushException as e:
            status = e.response.status_code if e.response is not None else None
            if status in (404, 410):
                dead.append(s.id)
            else:
                log.warning("push to user %s failed: %s", user_id, e)
        except Exception as e:  # noqa: BLE001 - network trouble must not stop the dispatcher
            log.warning("push to user %s failed: %s", user_id, e)
    if dead:
        await db.execute(delete(PushSubscription).where(PushSubscription.id.in_(dead)))
        await db.commit()
    return ok
