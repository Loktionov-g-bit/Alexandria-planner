"""Database schema.

Migrations must stay expand/contract compatible (SPEC §10): stable and beta share one DB,
so a new release may only ADD columns/tables; removal happens one release later.
"""

import enum
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    TypeDecorator,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Timestamps are always UTC-aware in Python. SQLite drops the zone, Postgres keeps it; both read back aware,
    so the API never sends a zone-less time that browsers would take for local time."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


def _enum(cls: type[enum.Enum]) -> Enum:
    # Store enum values as plain strings: easier to evolve than native PG enums under expand/contract.
    return Enum(cls, native_enum=False, length=24, values_callable=lambda e: [m.value for m in e])


class Role(str, enum.Enum):
    employee = "employee"
    manager = "manager"


class Quadrant(str, enum.Enum):
    """Eisenhower matrix."""

    do = "do"            # urgent + important
    plan = "plan"        # important, not urgent
    delegate = "delegate"  # urgent, not important
    drop = "drop"        # neither

    @classmethod
    def from_flags(cls, urgent: bool, important: bool) -> "Quadrant":
        if urgent and important:
            return cls.do
        if important:
            return cls.plan
        if urgent:
            return cls.delegate
        return cls.drop

    @property
    def urgent(self) -> bool:
        return self in (Quadrant.do, Quadrant.delegate)

    @property
    def important(self) -> bool:
        return self in (Quadrant.do, Quadrant.plan)


class Status(str, enum.Enum):
    new = "new"
    triaged = "triaged"
    in_progress = "in_progress"
    needs_info = "needs_info"
    delegated = "delegated"
    resolved = "resolved"
    closed = "closed"
    snoozed = "snoozed"
    rejected = "rejected"
    withdrawn = "withdrawn"


class Outcome(str, enum.Enum):
    approved = "approved"
    declined = "declined"
    done = "done"
    fyi = "fyi"


class Kind(str, enum.Enum):
    normal = "normal"      # to a manager or colleague
    personal = "personal"  # note to self, visible only to the author


class PlacementRole(str, enum.Enum):
    recipient = "recipient"  # handles the sticker (manager or colleague)
    delegate = "delegate"    # got it delegated by the recipient
    viewer = "viewer"        # access opened via "share"


class CommentKind(str, enum.Enum):
    comment = "comment"
    question = "question"   # "needs info" request
    answer = "answer"       # author's reply to a question
    report = "report"       # delegate's report
    resolution = "resolution"


# ---------------------------------------------------------------- org / users


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL", use_alter=True))
    update_channel: Mapped[str | None] = mapped_column(String(8))  # None = stable
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    manager: Mapped["User | None"] = relationship(foreign_keys=[manager_id], lazy="joined")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))  # "first last", kept for sorting and old clients
    first_name: Mapped[str] = mapped_column(String(60), default="", server_default="")
    last_name: Mapped[str] = mapped_column(String(60), default="", server_default="")
    email: Mapped[str | None] = mapped_column(String(254))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum(Role), default=Role.employee)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    avatar_color: Mapped[str] = mapped_column(String(16), default="#5b7cfa")

    locale: Mapped[str] = mapped_column(String(8), default="ru")
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    theme: Mapped[str] = mapped_column(String(8), default="system")  # system | light | dark
    update_channel: Mapped[str | None] = mapped_column(String(8))     # None = inherit department/default

    totp_secret: Mapped[str | None] = mapped_column(String(64))
    totp_last_step: Mapped[int | None] = mapped_column(Integer)  # last accepted 30 s step: a code works once
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # notifications (stage 3)
    notify_push: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    notify_telegram: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    digest_morning: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    digest_evening: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    digest_time: Mapped[str] = mapped_column(String(5), default="08:00", server_default="08:00")
    digest_days: Mapped[str] = mapped_column(String(7), default="12345", server_default="12345")  # ISO weekdays
    digest_skip_empty: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    digest_last_sent: Mapped[date | None] = mapped_column(Date)
    digest_evening_last_sent: Mapped[date | None] = mapped_column(Date)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    # set when an admin deleted the account but the person's stickers or comments stay in other people's history
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    telegram_username: Mapped[str | None] = mapped_column(String(64))
    telegram_link_code: Mapped[str | None] = mapped_column(String(32), unique=True)  # one-time, from the profile
    telegram_link_expires: Mapped[datetime | None] = mapped_column(UTCDateTime())

    # absence: while away (away_from..away_until, both inclusive) new stickers addressed to this person
    # also go to the deputy. away_from None = from now on.
    away_from: Mapped[date | None] = mapped_column(Date)
    away_until: Mapped[date | None] = mapped_column(Date)
    deputy_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # secret part of the personal calendar feed URL (deadlines as ICS); None = feed off
    calendar_token: Mapped[str | None] = mapped_column(String(64), unique=True)

    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    department: Mapped[Department | None] = relationship(foreign_keys=[department_id], lazy="joined")

    def is_away(self, today: date | None = None) -> bool:
        today = today or date.today()
        return (self.away_until is not None and self.away_until >= today
                and (self.away_from is None or self.away_from <= today))

    @property
    def away_now_until(self) -> date | None:
        """Last day of the current absence, None when the person is at work (shown to colleagues)."""
        return self.away_until if self.is_away() else None

    @property
    def calendar_enabled(self) -> bool:
        return self.calendar_token is not None

    @property
    def away_deputy_id(self) -> int | None:
        return self.deputy_id if self.is_away() else None

    @property
    def effective_channel(self) -> str:
        """stable | beta: the user's own choice, else the department's, else stable."""
        return self.update_channel or (self.department.update_channel if self.department else None) or "stable"

    @property
    def telegram_linked(self) -> bool:
        return self.telegram_chat_id is not None

    @property
    def needs_2fa(self) -> bool:
        """2FA is mandatory for managers and admins (SPEC §4)."""
        return self.is_admin or self.role == Role.manager


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of the cookie token
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    # False until the TOTP step is passed (or the user has no 2FA)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))

    user: Mapped[User] = relationship(lazy="joined")


class LoginEvent(Base):
    __tablename__ = "login_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    login: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    success: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(String(32))  # bad_password, locked, bad_totp, ok, ...


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | str | int | bool | None] = mapped_column(JSON)


# ---------------------------------------------------------------- stickers


class Sticker(Base):
    __tablename__ = "stickers"

    id: Mapped[int] = mapped_column(primary_key=True)  # shown to users as "№N"
    kind: Mapped[Kind] = mapped_column(_enum(Kind), default=Kind.normal)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[Status] = mapped_column(_enum(Status), default=Status.new, index=True)

    # author's own assessment
    author_urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    author_important: Mapped[bool] = mapped_column(Boolean, default=False)
    # final decision of the recipient (None until triaged)
    decided_quadrant: Mapped[Quadrant | None] = mapped_column(_enum(Quadrant))
    escalated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())  # auto-urgent by deadline

    deadline: Mapped[date | None] = mapped_column(Date)
    snoozed_until: Mapped[date | None] = mapped_column(Date)
    outcome: Mapped[Outcome | None] = mapped_column(_enum(Outcome))
    reject_reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)
    triaged_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    author: Mapped[User] = relationship(lazy="joined")
    placements: Mapped[list["Placement"]] = relationship(
        back_populates="sticker", cascade="all, delete-orphan", lazy="selectin"
    )


class Placement(Base):
    """A sticker on somebody's board. Each board owner chooses the quadrant on their own board."""

    __tablename__ = "placements"
    __table_args__ = (UniqueConstraint("sticker_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sticker_id: Mapped[int] = mapped_column(ForeignKey("stickers.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[PlacementRole] = mapped_column(_enum(PlacementRole))
    quadrant: Mapped[Quadrant | None] = mapped_column(_enum(Quadrant))  # None = still in inbox
    position: Mapped[int] = mapped_column(Integer, default=0)
    seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    sticker: Mapped[Sticker] = relationship(back_populates="placements")
    user: Mapped[User] = relationship(lazy="joined")


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    sticker_id: Mapped[int] = mapped_column(ForeignKey("stickers.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[CommentKind] = mapped_column(_enum(CommentKind), default=CommentKind.comment)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    author: Mapped[User] = relationship(lazy="joined")


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    sticker_id: Mapped[int] = mapped_column(ForeignKey("stickers.id", ondelete="CASCADE"), index=True)
    comment_id: Mapped[int | None] = mapped_column(ForeignKey("comments.id", ondelete="CASCADE"))
    uploader_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(127))
    size: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(80), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class AuditEvent(Base):
    """Who changed what and when (status, quadrant, deadline, access...)."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    sticker_id: Mapped[int] = mapped_column(ForeignKey("stickers.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))  # None = system (scheduler, bot)
    at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    action: Mapped[str] = mapped_column(String(32))
    data: Mapped[dict] = mapped_column(JSON, default=dict)

    actor: Mapped[User | None] = relationship(lazy="joined")


# ---------------------------------------------------------------- notifications


class Notification(Base):
    """One event for one person. Doubles as the outbox: channels mark what they delivered."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    sticker_id: Mapped[int | None] = mapped_column(ForeignKey("stickers.id", ondelete="CASCADE"))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event: Mapped[str] = mapped_column(String(32))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # None = not handled yet; True = sent; False = skipped (channel off / not linked)
    push_done: Mapped[bool | None] = mapped_column(Boolean)
    telegram_done: Mapped[bool | None] = mapped_column(Boolean)

    actor: Mapped[User | None] = relationship(foreign_keys=[actor_id], lazy="joined")
    sticker: Mapped[Sticker | None] = relationship(lazy="joined")


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(String(1000), unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
