"""Notifications: who hears about which sticker event, the text in their language, and the outbox.

`emit()` only writes rows into `notifications` (inside the caller's transaction). After commit the
live broker pings open browser tabs and the dispatcher delivers to channels (Web Push, Telegram).
Nothing is lost if the process restarts: undelivered rows are picked up on the next pass.
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from .locales import texts
from .models import Kind, Notification, PlacementRole, Sticker, User

# action/event -> who is told. a = author, r = recipients, d = delegates, v = viewers, t = data["target"]
RULES: dict[str, str] = {
    "created": "r",
    "triaged": "a",
    "start": "a",
    "ask": "a",
    "answer": "r",
    "delegate": "at",
    "report": "r",
    "rework": "d",
    "resolve": "adv",
    "snooze": "a",
    "reject": "a",
    "withdraw": "rd",
    "confirm": "r",
    "reopen": "rd",
    "comment": "ardv",
    "share": "t",
    "escalated": "rd",
    "woken": "r",
    "deadline": "ardv",
}

TEXTS: dict[str, dict[str, str]] = texts("notify")


def _targets(s: Sticker, rule: str, data: dict) -> set[int]:
    out: set[int] = set()
    roles = {"r": PlacementRole.recipient, "d": PlacementRole.delegate, "v": PlacementRole.viewer}
    for ch in rule:
        if ch == "a":
            out.add(s.author_id)
        elif ch == "t" and data.get("target_id"):
            out.add(data["target_id"])
        elif ch in roles:
            out |= {p.user_id for p in s.placements if p.role == roles[ch]}
    return out


def emit(db: AsyncSession, s: Sticker, actor: User | None, ev: str, **data) -> None:
    """Queue a notification about sticker `s` for everybody the rule names, except the actor."""
    if s.kind == Kind.personal or ev not in RULES:
        return
    users = _targets(s, RULES[ev], data) - ({actor.id} if actor else set())
    for uid in users:
        db.add(Notification(user_id=uid, sticker_id=s.id, actor_id=actor.id if actor else None, event=ev, data=data))
    # everybody involved gets a "something changed" ping for live board refresh, the actor's other tabs too
    db.info.setdefault("live", set()).update(_targets(s, "ardv", data))


def render(n: Notification, locale: str) -> tuple[str, str]:
    """(title, body) in the reader's language."""
    tx = TEXTS.get(locale, TEXTS["ru"])
    d = n.data or {}
    key = "delegate_me" if n.event == "delegate" and d.get("target_id") == n.user_id else n.event
    title = tx.get(key, n.event).format(
        actor=n.actor.display_name if n.actor else "Alexandria",
        target=d.get("target", ""),
        quadrant=tx.get(f"q.{d.get('quadrant')}", ""),
        outcome=tx.get(f"o.{d.get('outcome')}", ""),
        until=d.get("until", ""),
        deadline=d.get("deadline") or tx["none"],
    )
    body = f"№{n.sticker.id} {n.sticker.title}" if n.sticker else ""
    if d.get("text"):
        body = f"{body}\n{d['text']}" if body else d["text"]
    return title, body[:400]


# ---------------------------------------------------------------- after-commit hooks

_after_commit_hooks: list = []


def on_commit(fn) -> None:
    """Register fn(user_ids: set[int]) called after a commit that emitted something."""
    _after_commit_hooks.append(fn)


@event.listens_for(Session, "after_commit")
def _fire(session: Session) -> None:
    users = session.info.pop("live", None)
    if users:
        for fn in _after_commit_hooks:
            fn(users)


@event.listens_for(Session, "after_rollback")
def _drop(session: Session) -> None:
    session.info.pop("live", None)
