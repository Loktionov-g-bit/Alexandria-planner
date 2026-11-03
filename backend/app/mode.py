"""How the installation is used, chosen in the first-run wizard and changeable in the admin area.

team: stickers travel between people, a team lead sorts the inbox (the original Planner).
solo: one person's diary on the Eisenhower matrix; every sticker is a personal one.
"""

from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from .models import AppSetting

Mode = Literal["team", "solo"]


async def get_mode(db: AsyncSession) -> Mode:
    row = await db.get(AppSetting, "mode")
    return "solo" if row is not None and row.value == "solo" else "team"  # installs older than the setting are teams


async def set_mode(db: AsyncSession, mode: Mode) -> None:
    row = await db.get(AppSetting, "mode")
    if row is None:
        db.add(AppSetting(key="mode", value=mode))
    else:
        row.value = mode
