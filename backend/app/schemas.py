from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .locales import LOCALE_PATTERN
from .models import Role


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserBrief(ORM):
    id: int
    display_name: str
    avatar_color: str
    role: Role
    department_id: int | None
    away_now_until: date | None = None  # set only while the person is away
    away_deputy_id: int | None = None


class DepartmentOut(ORM):
    id: int
    name: str
    manager_id: int | None


class UserOut(ORM):
    id: int
    login: str
    display_name: str
    first_name: str
    last_name: str
    email: str | None
    role: Role
    is_admin: bool
    is_active: bool
    department_id: int | None
    avatar_color: str
    locale: str
    timezone: str
    theme: str
    totp_enabled: bool
    needs_2fa: bool
    notify_push: bool
    notify_telegram: bool
    digest_morning: bool
    digest_evening: bool
    digest_time: str
    digest_days: str
    digest_skip_empty: bool
    telegram_username: str | None
    telegram_linked: bool
    away_from: date | None
    away_until: date | None
    deputy_id: int | None
    calendar_enabled: bool


class MeOut(BaseModel):
    user: UserOut
    verified: bool
    # what the client must do before using the app: None | "totp" | "totp_setup"
    pending: str | None
    channel: str
    mode: Literal["team", "solo"] = "team"


class SetupIn(BaseModel):
    mode: Literal["team", "solo"] = "team"
    department: str = Field(default="", max_length=120)  # the team's name; required for a team
    login: str | None = Field(default=None, min_length=2, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")  # None = generate
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(min_length=1, max_length=60)
    password: str = Field(max_length=256)
    is_manager: bool = True  # small company: admin is also the department manager
    locale: str = Field(default="ru", pattern=LOCALE_PATTERN)
    timezone: str = "Europe/Moscow"


class LoginIn(BaseModel):
    login: str = Field(max_length=64)
    password: str = Field(max_length=256)


class CodeIn(BaseModel):
    code: str = Field(max_length=16)


class TotpSetupOut(BaseModel):
    secret: str
    uri: str


class PasswordChangeIn(BaseModel):
    old_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class LoginEventOut(ORM):
    id: int
    user_id: int | None
    login: str
    at: datetime
    ip: str | None
    user_agent: str | None
    success: bool
    reason: str | None


class UserCreateIn(BaseModel):
    login: str | None = Field(default=None, min_length=2, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")  # None = generate
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(min_length=1, max_length=60)
    email: str | None = Field(default=None, max_length=254)
    password: str = Field(max_length=256)
    role: Role = Role.employee
    is_admin: bool = False
    department_id: int | None = None
    avatar_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class UserUpdateIn(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=60)
    last_name: str | None = Field(default=None, min_length=1, max_length=60)
    email: str | None = Field(default=None, max_length=254)
    role: Role | None = None
    is_admin: bool | None = None
    is_active: bool | None = None
    department_id: int | None = None
    avatar_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    password: str | None = Field(default=None, max_length=256)  # admin reset
    reset_2fa: bool = False
    telegram_unlink: bool = False


class ProfileUpdateIn(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=60)
    last_name: str | None = Field(default=None, min_length=1, max_length=60)
    email: str | None = Field(default=None, max_length=254)
    locale: str | None = Field(default=None, pattern=LOCALE_PATTERN)
    timezone: str | None = Field(default=None, max_length=64)
    theme: str | None = Field(default=None, pattern=r"^(system|light|dark)$")
    notify_push: bool | None = None
    notify_telegram: bool | None = None
    digest_morning: bool | None = None
    digest_evening: bool | None = None
    digest_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    digest_days: str | None = Field(default=None, pattern=r"^[1-7]{0,7}$")
    digest_skip_empty: bool | None = None
    away_from: date | None = None
    away_until: date | None = None
    deputy_id: int | None = None


class ModeIn(BaseModel):
    mode: Literal["team", "solo"]
    team: str | None = Field(default=None, max_length=120)  # name of the first team when a diary grows into a team


class DepartmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    manager_id: int | None = None


__all__ = ["date"]
