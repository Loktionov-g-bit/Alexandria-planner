"""What the bot does with incoming updates. Every action goes through the same lifecycle code as the web,
so a linked Telegram account has exactly the rights of its Planner user."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select

from .. import stickers as lc
from ..locales import from_client
from ..config import get_settings
from ..models import Comment, CommentKind, Department, Kind, Notification, Outcome, Placement, PlacementRole, Quadrant, Status, Sticker, User
from .api import TelegramAPI, TelegramError
from .texts import esc, t

log = logging.getLogger("planner.telegram")

ORDER = ["start", "resolve", "ask", "delegate", "snooze", "reject", "rework", "wake", "answer", "report", "confirm", "reopen", "withdraw"]
TEXT_ACTIONS = {"ask", "answer", "report", "rework", "reject", "reopen"}
INSTANT = {"start", "confirm", "withdraw", "wake"}
STICKER_NO = re.compile(r"№(\d+)")
MAX_FILE = 20 * 1024 * 1024  # Bot API download limit
PAGE = 12  # people per page in the "write to an employee" picker
COUNT = re.compile(r"\s+·\s+\d+$")  # menu buttons carry a live count: "Сделать сейчас · 3"


def _today_local(user: User) -> date:
    from zoneinfo import ZoneInfo

    try:
        return datetime.now(ZoneInfo(user.timezone)).date()
    except Exception:  # noqa: BLE001
        return date.today()


def parse_date(text: str, today: date) -> date | None:
    m = re.fullmatch(r"\s*(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?\s*", text)
    if not m:
        return None
    d, mo, y = int(m[1]), int(m[2]), m[3]
    year = (int(y) + 2000 if len(y) == 2 else int(y)) if y else today.year
    try:
        res = date(year, mo, d)
    except ValueError:
        return None
    if not y and res <= today:
        res = date(year + 1, mo, d)
    return res


def split_text(text: str) -> tuple[str, str]:
    lines = text.strip().split("\n", 1)
    title = lines[0].strip()
    body = lines[1].strip() if len(lines) > 1 else ""
    if len(title) > 200:  # one long line: keep it whole as the body
        title, body = title[:197].rstrip() + "…", text.strip()
    return title, body


class Bot:
    def __init__(self, api: TelegramAPI, sessionmaker, username: str = ""):
        self.api = api
        self.sm = sessionmaker
        self.username = username.lower()
        self.pending: dict[int, dict] = {}  # chat id -> waiting for text: {"action", "sid", "outcome"?}

    # ------------------------------------------------------------ rendering

    def card(self, s: Sticker, user: User, header: str | None = None) -> str:
        loc = user.locale
        parts = []
        if header:
            parts.append(f"<b>{esc(header)}</b>")
        q = s.decided_quadrant or lc.effective_quadrant(s)
        meta = [t(loc, "from", name=esc(s.author.display_name)), t(loc, f"qs.{q.value}"), t(loc, f"s.{s.status.value}")]
        parts.append(f"<b>№{s.id} {esc(s.title)}</b>\n" + " · ".join(meta))
        if s.deadline:
            due = t(loc, "due", date=s.deadline.strftime("%d.%m.%Y"))
            if s.deadline < date.today() and s.status in lc.ACTIVE:
                due += f" · <b>{t(loc, 'late')}</b>"
            parts.append(due)
        if s.body:
            body = s.body if len(s.body) <= 700 else s.body[:699] + "…"
            parts.append(esc(body))
        return "\n\n".join(parts)

    def keyboard(self, s: Sticker, user: User) -> dict | None:
        """Buttons under a sticker card.
        Recipient, new sticker: only the four quadrants (triage).
        Recipient, triaged: Done / Not done, then Delegate / Ask / Snooze, then Back to the list.
        Author or delegate: their own actions (answer, confirm, report...)."""
        loc = user.locale
        acts = lc.allowed_actions(s, user)
        rows: list[list[dict]] = []
        p = lc.placement_of(s, user)
        btn = lambda key, data: {"text": t(loc, key), "callback_data": data}
        if p is not None and p.role == PlacementRole.recipient:
            if s.status == Status.new:
                qs = [btn(f"q.{q}", f"q:{s.id}:{q}") for q in ("do", "plan", "delegate", "drop")]
                return {"inline_keyboard": [qs[:2], qs[2:]]}
            if "resolve" in acts:
                rows.append([btn("btn.done", f"o:{s.id}:done"), btn("btn.fail", f"o:{s.id}:declined")])
            rows.append([btn(f"a.{a}", f"a:{s.id}:{a}") for a in ("delegate", "ask", "snooze") if a in acts])
            rows.append([btn(f"a.{a}", f"a:{s.id}:{a}") for a in ("wake", "rework") if a in acts])
            back = p.quadrant.value if p.quadrant else "inbox"
        else:
            btns = [btn(f"a.{a}", f"a:{s.id}:{a}") for a in ORDER if a in acts]
            rows += [btns[i:i + 3] for i in range(0, len(btns), 3)]
            back = "mine" if s.author_id == user.id else None
        base = get_settings().base_url.rstrip("/")
        if base.startswith("https://"):
            rows.append([{"text": t(loc, "open"), "url": f"{base}/?s={s.id}"}])
        if back:
            rows.append([btn("btn.back", f"L:{back}")])
        rows = [r for r in rows if r]
        return {"inline_keyboard": rows} if rows else None

    # ------------------------------------------------------------ helpers

    async def linked(self, db, tg_id: int | None) -> User | None:
        if tg_id is None:
            return None
        u = await db.scalar(select(User).where(User.telegram_chat_id == tg_id))
        return u if u is not None and u.is_active else None

    async def say(self, chat_id: int, text: str, **kw):
        return await self.api.call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                                   disable_web_page_preview=True, **kw)

    async def send_card(self, chat_id: int, s: Sticker, user: User, header: str | None = None):
        return await self.say(chat_id, self.card(s, user, header), reply_markup=self.keyboard(s, user))

    @staticmethod
    def reason(e: HTTPException, loc: str) -> str:
        key = {"sticker.action_not_allowed": "not_allowed", "sticker.no_recipient": "no_recipient"}.get(str(e.detail))
        return t(loc, key) if key else t(loc, "error", reason=esc(str(e.detail)))

    # ------------------------------------------------------------ entry point

    async def handle(self, update: dict) -> None:
        try:
            if "callback_query" in update:
                await self.on_callback(update["callback_query"])
            elif "message" in update:
                await self.on_message(update["message"])
        except TelegramError as e:
            log.warning("telegram call failed: %s", e)

    # ------------------------------------------------------------ messages

    async def on_message(self, m: dict) -> None:
        chat = m["chat"]
        sender = m.get("from") or {}
        text = (m.get("text") or m.get("caption") or "").strip()
        cmd, _, rest = text.partition(" ") if text.startswith("/") else ("", "", "")
        cmd, _, target = cmd.lower().partition("@")
        if target and self.username and target != self.username:
            return  # a command for another bot in the same group
        if chat["type"] in ("group", "supergroup"):
            if cmd in ("/stiker", "/sticker"):
                await self.group_sticker(m, rest.strip())
            return
        if chat["type"] != "private":
            return

        async with self.sm() as db:
            if cmd == "/start" and rest.strip():
                await self.link(db, m, rest.strip())
                return
            user = await self.linked(db, sender.get("id"))
            if user is None:
                lang = from_client(sender.get("language_code"))
                await self.say(chat["id"], t(lang, "start_unlinked"))
                return
            loc = user.locale
            if cmd in ("/start", "/menu"):
                await self.menu(db, chat["id"], user)
                return
            if cmd == "/help":
                await self.say(chat["id"], t(loc, "help"))
                return
            button = self.menu_button(loc, text) if not cmd and not (m.get("reply_to_message")) else None
            if button:
                self.pending.pop(chat["id"], None)
                if button == "write":
                    await self.write_start(db, chat["id"], user)
                elif button == "stats":
                    await self.stats(db, chat["id"], user)
                else:
                    await self.list_view(db, chat["id"], user, button)
                return
            if cmd == "/cancel":
                self.pending.pop(chat["id"], None)
                await self.say(chat["id"], t(loc, "cancelled"))
                return
            if cmd == "/inbox":
                await self.show(db, chat["id"], user, "inbox")
                return
            if cmd == "/board":
                await self.board(db, chat["id"], user)
                return
            if cmd == "/stats":
                await self.stats(db, chat["id"], user)
                return
            if cmd:
                await self.say(chat["id"], t(loc, "help"))
                return

            pend = self.pending.pop(chat["id"], None)
            if pend and pend["action"] == "compose" and (text or self.file_of(m)):
                if not text:
                    self.pending[chat["id"]] = pend
                    await self.say(chat["id"], t(loc, "file_needs_caption"))
                    return
                await self.new_sticker(db, chat["id"], user, text, self.file_of(m), reply_to=None, recipient_ids=pend["to"])
                return
            if pend and text:
                await self.finish_pending(db, chat["id"], user, pend, text)
                return

            file = self.file_of(m)
            reply = m.get("reply_to_message") or {}
            ref = STICKER_NO.search(reply.get("text") or reply.get("caption") or "") if (reply.get("from") or {}).get("is_bot") else None
            if ref:
                await self.on_reply(db, chat["id"], user, int(ref[1]), text, file)
                return
            if file and not text:
                await self.say(chat["id"], t(loc, "file_needs_caption"))
                return
            if not text:
                await self.say(chat["id"], t(loc, "need_title"))
                return
            await self.new_sticker(db, chat["id"], user, text, file, reply_to=None)

    @staticmethod
    def file_of(m: dict) -> tuple[str, str, str] | None:
        """(file_id, filename, content type) of a photo or document."""
        if m.get("photo"):
            ph = m["photo"][-1]  # biggest size
            return ph["file_id"], f"photo_{m.get('message_id', 0)}.jpg", "image/jpeg"
        if m.get("document"):
            d = m["document"]
            return d["file_id"], d.get("file_name") or "file", d.get("mime_type") or "application/octet-stream"
        return None

    async def attach(self, db, s: Sticker, user: User, file, comment_id: int | None = None) -> None:
        file_id, name, ctype = file
        data = await self.api.download(file_id, MAX_FILE)
        lc.store_attachment(db, s, user, name, ctype, data, comment_id)

    async def new_sticker(self, db, chat_id: int, user: User, text: str, file, reply_to: int | None, group: bool = False,
                         recipient_ids: list[int] | None = None):
        title, body = split_text(text)
        personal = False
        try:
            s = await lc.create(db, user, title=title, body=body, recipient_ids=recipient_ids)
        except HTTPException as e:
            if e.detail != "sticker.no_recipient" or group or recipient_ids:
                await self.say(chat_id, self.reason(e, user.locale), reply_to_message_id=reply_to)
                return
            s = await lc.create(db, user, title=title, body=body, personal=True)  # a manager without a manager: note to self
            personal = True
        if file:
            try:
                await self.attach(db, s, user, file)
            except TelegramError as e:
                log.warning("attachment download failed: %s", e)
        await db.commit()
        s = await db.get(Sticker, s.id, populate_existing=True)
        loc = user.locale
        if group:
            await self.say(chat_id, t(loc, "created_group", id=s.id), reply_to_message_id=reply_to)
            return
        to = ", ".join(p.user.display_name for p in lc.recipients(s) if p.user_id != user.id)
        msg = t(loc, "created_personal", id=s.id) if personal else t(loc, "created", id=s.id, to=esc(to))
        flags = [[{"text": t(loc, "btn.urgent"), "callback_data": f"f:{s.id}:u"},
                  {"text": t(loc, "btn.important"), "callback_data": f"f:{s.id}:i"}]]
        await self.say(chat_id, msg, reply_markup={"inline_keyboard": flags})

    async def group_sticker(self, m: dict, text: str) -> None:
        chat_id = m["chat"]["id"]
        async with self.sm() as db:
            user = await self.linked(db, (m.get("from") or {}).get("id"))
            if user is None:
                await self.say(chat_id, t("ru", "not_linked"), reply_to_message_id=m.get("message_id"))
                return
            if not text:
                await self.say(chat_id, t(user.locale, "need_title"), reply_to_message_id=m.get("message_id"))
                return
            await self.new_sticker(db, chat_id, user, text, self.file_of(m), reply_to=m.get("message_id"), group=True)

    async def on_reply(self, db, chat_id: int, user: User, sid: int, text: str, file) -> None:
        loc = user.locale
        s = await db.get(Sticker, sid)
        if s is None or not lc.can_view(s, user):
            await self.say(chat_id, t(loc, "not_allowed"))
            return
        try:
            if text:
                action = "answer" if "answer" in lc.allowed_actions(s, user) else "comment"
                await lc.apply_action(db, s, user, action, {"text": text})
                await db.flush()
                if file:
                    c = await db.scalar(select(Comment).where(Comment.sticker_id == s.id).order_by(Comment.id.desc()))
                    await self.attach(db, s, user, file, c.id if c else None)
                await db.commit()
                await self.say(chat_id, t(loc, "answered" if action == "answer" else "commented", id=s.id))
            elif file:
                if "comment" not in lc.allowed_actions(s, user):
                    raise HTTPException(409, "sticker.action_not_allowed")
                await self.attach(db, s, user, file)
                await db.commit()
                await self.say(chat_id, t(loc, "attached", id=s.id))
        except HTTPException as e:
            await db.rollback()
            await self.say(chat_id, self.reason(e, loc))

    async def link(self, db, m: dict, code: str) -> None:
        chat_id = m["chat"]["id"]
        sender = m.get("from") or {}
        u = await db.scalar(select(User).where(User.telegram_link_code == code[:32]))
        now = datetime.now(timezone.utc)
        if u is None or not u.is_active or u.telegram_link_expires is None or u.telegram_link_expires < now:
            await self.say(chat_id, t("ru", "link_bad"))
            return
        other = await db.scalar(select(User).where(User.telegram_chat_id == sender["id"]))
        if other is not None and other.id != u.id:
            await self.say(chat_id, t(u.locale, "link_taken"))
            return
        u.telegram_chat_id = sender["id"]
        u.telegram_username = (sender.get("username") or sender.get("first_name") or "")[:64] or None
        u.telegram_link_code = None
        u.telegram_link_expires = None
        await db.commit()
        await self.say(chat_id, t(u.locale, "linked", name=esc(u.first_name or u.display_name)))
        await self.menu(db, chat_id, u)

    # ------------------------------------------------------------ buttons

    async def on_callback(self, cq: dict) -> None:
        data = cq.get("data") or ""
        msg = cq.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        async with self.sm() as db:
            user = await self.linked(db, (cq.get("from") or {}).get("id"))
            if user is None:
                await self.api.call("answerCallbackQuery", callback_query_id=cq["id"], text=t("ru", "not_linked"), show_alert=True)
                return
            loc = user.locale
            kind, _, rest = data.partition(":")
            if kind == "v":
                await self.api.call("answerCallbackQuery", callback_query_id=cq["id"])
                await self.show(db, chat_id, user, rest)
                return
            if kind == "L":
                await self.api.call("answerCallbackQuery", callback_query_id=cq["id"])
                await self.list_view(db, chat_id, user, rest)
                return
            if kind == "w":
                await self.api.call("answerCallbackQuery", callback_query_id=cq["id"])
                await self.write_step(db, msg, user, rest)
                return
            sid_s, _, arg = rest.partition(":")
            s = await db.get(Sticker, int(sid_s)) if sid_s.isdigit() else None
            if s is None or not lc.can_view(s, user):
                await self.api.call("answerCallbackQuery", callback_query_id=cq["id"], text=t(loc, "not_allowed"))
                return
            if kind in ("s", "S"):
                await self.api.call("answerCallbackQuery", callback_query_id=cq["id"])
                await db.refresh(s, ["placements"])
                if kind == "s" and msg:
                    try:
                        await self.api.call("editMessageText", chat_id=chat_id, message_id=msg["message_id"], text=self.card(s, user),
                                            parse_mode="HTML", disable_web_page_preview=True,
                                            reply_markup=self.keyboard(s, user) or {"inline_keyboard": []})
                        return
                    except TelegramError:
                        pass
                await self.send_card(chat_id, s, user)
                return
            if kind == "n":  # "Done" without a comment
                self.pending.pop(chat_id, None)
                kind, arg = "a", "resolve"
            toast = t(loc, "done")
            try:
                if kind == "a" and arg == "resolve" and data.startswith("n:"):
                    await lc.apply_action(db, s, user, "resolve", {"text": t(loc, "o.done"), "outcome": "done"})
                elif kind == "q":
                    await lc.move(db, s, user, Quadrant(arg))
                elif kind == "f":
                    await self.toggle_flag(db, s, user, arg)
                elif kind == "x":
                    self.pending.pop(chat_id, None)
                    toast = t(loc, "cancelled")
                elif kind == "a":
                    if arg not in lc.allowed_actions(s, user):
                        raise HTTPException(409, "sticker.action_not_allowed")
                    if arg in INSTANT:
                        await lc.apply_action(db, s, user, arg, {})
                    else:
                        await self.api.call("answerCallbackQuery", callback_query_id=cq["id"])
                        await self.ask_more(db, chat_id, user, s, arg)
                        return
                elif kind == "o":
                    await self.api.call("answerCallbackQuery", callback_query_id=cq["id"])
                    if "resolve" not in lc.allowed_actions(s, user):
                        raise HTTPException(409, "sticker.action_not_allowed")
                    self.pending[chat_id] = {"action": "resolve", "sid": s.id, "outcome": arg}
                    if arg == "done":
                        await self.say(chat_id, t(loc, "prompt.done", id=s.id),
                                       reply_markup={"inline_keyboard": [[{"text": t(loc, "btn.nocomment"), "callback_data": f"n:{s.id}"}]]})
                    elif arg == "declined":
                        await self.say(chat_id, t(loc, "prompt.fail", id=s.id), reply_markup={"force_reply": True})
                    else:
                        await self.say(chat_id, t(loc, "prompt.resolve", id=s.id, outcome=t(loc, f"o.{arg}")),
                                       reply_markup={"force_reply": True})
                    return
                elif kind == "d":
                    await lc.apply_action(db, s, user, "delegate", {"user_id": int(arg)})
                elif kind == "z":
                    if arg == "d":
                        await self.api.call("answerCallbackQuery", callback_query_id=cq["id"])
                        self.pending[chat_id] = {"action": "snooze_date", "sid": s.id}
                        await self.say(chat_id, t(loc, "prompt.snooze_date", id=s.id), reply_markup={"force_reply": True})
                        return
                    until = _today_local(user) + timedelta(days=int(arg))
                    await lc.apply_action(db, s, user, "snooze", {"until": until})
                await db.commit()
            except HTTPException as e:
                await db.rollback()
                await self.api.call("answerCallbackQuery", callback_query_id=cq["id"], text=self.reason(e, loc))
                return
            await self.api.call("answerCallbackQuery", callback_query_id=cq["id"], text=toast)
            if kind == "q":
                if msg:
                    try:
                        await self.api.call("editMessageText", chat_id=chat_id, message_id=msg["message_id"], parse_mode="HTML",
                                            text=t(loc, "triaged", id=s.id, title=esc(s.title), q=t(loc, f"q.{arg}")))
                    except TelegramError as e:
                        log.info("could not edit triaged card: %s", e)
                await self.menu(db, chat_id, user)
                return
            if kind == "n" or data.startswith("n:"):
                if msg:
                    try:
                        await self.api.call("editMessageText", chat_id=chat_id, message_id=msg["message_id"], text=t(loc, "resolved", id=s.id))
                    except TelegramError:
                        pass
                await self.menu(db, chat_id, user)
                return
            await self.refresh_message(db, msg, s.id, user, kind)

    async def refresh_message(self, db, msg: dict, sid: int, user: User, kind: str) -> None:
        """Update the message whose button was pressed, so stale buttons disappear."""
        if not msg:
            return
        s = await db.get(Sticker, sid, populate_existing=True)
        await db.refresh(s, ["placements"])
        chat, mid = msg["chat"]["id"], msg["message_id"]
        text = msg.get("text") or ""
        try:
            if "f:" in str(msg.get("reply_markup")):  # "sticker created" message with urgent/important toggles
                await self.api.call("editMessageReplyMarkup", chat_id=chat, message_id=mid, reply_markup=self.flags_kb(s, user))
            elif kind == "x":  # cancelled a picker
                await self.api.call("editMessageText", chat_id=chat, message_id=mid, text=t(user.locale, "cancelled"))
            else:
                # a picker becomes the result card; a card keeps its first line (the notification title) as header
                if kind in ("d", "z"):
                    header = t(user.locale, "done")
                else:
                    first = text.split("\n", 1)[0]
                    header = None if first.startswith(f"№{s.id}") else first
                await self.api.call("editMessageText", chat_id=chat, message_id=mid, text=self.card(s, user, header),
                                    parse_mode="HTML", disable_web_page_preview=True,
                                    reply_markup=self.keyboard(s, user) or {"inline_keyboard": []})
        except TelegramError as e:
            if "not modified" not in str(e):
                log.info("could not refresh message: %s", e)

    def flags_kb(self, s: Sticker, user: User) -> dict:
        loc = user.locale
        if s.status != Status.new:
            return {"inline_keyboard": []}
        mark = lambda on, k: ("✓ " if on else "") + t(loc, k)  # noqa: E731
        return {"inline_keyboard": [[{"text": mark(s.author_urgent, "btn.urgent"), "callback_data": f"f:{s.id}:u"},
                                     {"text": mark(s.author_important, "btn.important"), "callback_data": f"f:{s.id}:i"}]]}

    async def toggle_flag(self, db, s: Sticker, user: User, which: str) -> None:
        if s.author_id != user.id or s.status != Status.new:
            raise HTTPException(409, "sticker.action_not_allowed")
        if which == "u":
            s.author_urgent = not s.author_urgent
        elif which == "i":
            s.author_important = not s.author_important
        lc.audit(db, s, user, "edited", fields=["urgent" if which == "u" else "important"])

    async def ask_more(self, db, chat_id: int, user: User, s: Sticker, action: str) -> None:
        loc = user.locale
        cancel = [{"text": t(loc, "btn.cancel"), "callback_data": f"x:{s.id}"}]
        if action in TEXT_ACTIONS:
            self.pending[chat_id] = {"action": action, "sid": s.id}
            await self.say(chat_id, t(loc, f"prompt.{action}", id=s.id), reply_markup={"force_reply": True})
        elif action == "resolve":
            os = [{"text": t(loc, f"o.{o.value}"), "callback_data": f"o:{s.id}:{o.value}"} for o in Outcome]
            await self.say(chat_id, t(loc, "pick_outcome", id=s.id), reply_markup={"inline_keyboard": [os[:2], os[2:], cancel]})
        elif action == "delegate":
            busy = {p.user_id for p in s.placements} | {s.author_id, user.id}
            people = list(await db.scalars(select(User).where(User.is_active.is_(True), User.id.not_in(busy)).order_by(User.display_name).limit(30)))
            btns = [{"text": u.display_name, "callback_data": f"d:{s.id}:{u.id}"} for u in people]
            rows = [btns[i:i + 2] for i in range(0, len(btns), 2)] + [cancel]
            await self.say(chat_id, t(loc, "pick_delegate", id=s.id), reply_markup={"inline_keyboard": rows})
        elif action == "snooze":
            rows = [[{"text": t(loc, "btn.tomorrow"), "callback_data": f"z:{s.id}:1"},
                     {"text": t(loc, "btn.week"), "callback_data": f"z:{s.id}:7"},
                     {"text": t(loc, "btn.date"), "callback_data": f"z:{s.id}:d"}], cancel]
            await self.say(chat_id, t(loc, "pick_snooze", id=s.id), reply_markup={"inline_keyboard": rows})

    async def finish_pending(self, db, chat_id: int, user: User, pend: dict, text: str) -> None:
        loc = user.locale
        s = await db.get(Sticker, pend["sid"])
        if s is None or not lc.can_view(s, user):
            await self.say(chat_id, t(loc, "not_allowed"))
            return
        try:
            if pend["action"] == "snooze_date":
                until = parse_date(text, _today_local(user))
                if until is None:
                    self.pending[chat_id] = pend  # let them try again
                    await self.say(chat_id, t(loc, "bad_date"), reply_markup={"force_reply": True})
                    return
                await lc.apply_action(db, s, user, "snooze", {"until": until})
            else:
                await lc.apply_action(db, s, user, pend["action"], {"text": text, "outcome": pend.get("outcome")})
            await db.commit()
        except HTTPException as e:
            await db.rollback()
            await self.say(chat_id, self.reason(e, loc))
            return
        s = await db.get(Sticker, s.id, populate_existing=True)
        await db.refresh(s, ["placements"])
        if pend["action"] == "resolve":
            await self.say(chat_id, t(loc, "resolved", id=s.id))
            await self.menu(db, chat_id, user)
            return
        await self.send_card(chat_id, s, user, t(loc, "done"))

    # ------------------------------------------------------------ views

    async def my_board(self, db, user: User) -> list[tuple[Sticker, Placement]]:
        q = (
            select(Sticker, Placement).join(Placement, Placement.sticker_id == Sticker.id)
            .where(Placement.user_id == user.id, Placement.role != PlacementRole.viewer, Sticker.status.in_(lc.ACTIVE))
            .order_by(Sticker.deadline.is_(None), Sticker.deadline, Sticker.id.desc())
        )
        rows = (await db.execute(q)).unique().all()
        return [(s, p) for s, p in rows if p.role == PlacementRole.recipient or s.status == Status.delegated]

    async def show(self, db, chat_id: int, user: User, view: str) -> None:
        rows = await self.my_board(db, user)
        today = date.today()
        if view == "inbox":
            items = [s for s, p in rows if p.quadrant is None]
        elif view == "do":
            items = [s for s, p in rows if p.quadrant == Quadrant.do]
        else:
            items = [s for s, _ in rows if s.deadline and s.deadline < today]
        loc = user.locale
        if not items:
            await self.say(chat_id, t(loc, "inbox_empty") if view == "inbox" else t(loc, "board_empty"))
            return
        await self.say(chat_id, f"<b>{t(loc, 'v.' + view)}</b>: {len(items)}")
        for s in items[:10]:
            await self.send_card(chat_id, s, user)

    async def board(self, db, chat_id: int, user: User) -> None:
        rows = await self.my_board(db, user)
        loc = user.locale
        if not rows:
            await self.say(chat_id, t(loc, "board_empty"))
            return
        parts = [t(loc, "board_head")]
        inbox = [s for s, p in rows if p.quadrant is None]
        if inbox:
            parts.append(f"<b>{t(loc, 'v.inbox')}</b> ({len(inbox)})\n" + "\n".join(f"№{s.id} {esc(s.title)}" for s in inbox[:5]))
        for q in Quadrant:
            items = [s for s, p in rows if p.quadrant == q]
            if items:
                parts.append(f"<b>{t(loc, 'q.' + q.value)}</b> ({len(items)})\n" + "\n".join(f"№{s.id} {esc(s.title)}" for s in items[:5]))
        await self.say(chat_id, "\n\n".join(parts))

    async def stats(self, db, chat_id: int, user: User) -> None:
        """The situation right now: my board by quadrant, overdue, and how my own stickers are doing."""
        rows = await self.my_board(db, user)
        today = _today_local(user)
        sent = list(await db.scalars(select(Sticker).where(Sticker.author_id == user.id, Sticker.kind == Kind.normal,
                                                          Sticker.status.in_(lc.ACTIVE | {Status.resolved}))))
        n = {q.value: sum(1 for _, p in rows if p.quadrant == q) for q in Quadrant}
        await self.say(chat_id, t(
            user.locale, "stats", inbox=sum(1 for _, p in rows if p.quadrant is None), late=sum(1 for s, _ in rows if s.deadline and s.deadline < today),
            mine=sum(1 for s in sent if s.status in lc.ACTIVE), asks=sum(1 for s in sent if s.status == Status.needs_info),
            confirm=sum(1 for s in sent if s.status == Status.resolved), **n,
        ))

    # ------------------------------------------------------------ main menu

    MENU_ROWS = (("do", "plan"), ("delegate", "drop"), ("mine", "write"), ("stats",))

    @staticmethod
    def menu_label(loc: str, key: str) -> str:
        return t(loc, f"q.{key}") if key in ("do", "plan", "delegate", "drop") else t(loc, f"menu.{key}")

    def menu_button(self, loc: str, text: str) -> str | None:
        """Which menu button a plain text message is (the reply keyboard sends its label)."""
        label = COUNT.sub("", text.strip())
        for key in ("inbox", "do", "plan", "delegate", "drop", "mine", "write", "stats"):
            if label == self.menu_label(loc, key):
                return key
        return None

    async def menu(self, db, chat_id: int, user: User, text: str | None = None) -> None:
        """The main screen: a persistent keyboard with the quadrants (with counts), my stickers, write, stats."""
        loc = user.locale
        rows = await self.my_board(db, user)
        n = {q.value: sum(1 for _, p in rows if p.quadrant == q) for q in Quadrant}
        inbox = sum(1 for _, p in rows if p.quadrant is None)
        label = lambda key: self.menu_label(loc, key) + (f" · {n[key]}" if n.get(key) else "")
        kb = ([[{"text": f"{self.menu_label(loc, 'inbox')} · {inbox}"}]] if inbox else []) + [
            [{"text": label(k)} for k in row] for row in self.MENU_ROWS]
        await self.say(chat_id, text or t(loc, "menu.title"),
                       reply_markup={"keyboard": kb, "resize_keyboard": True, "is_persistent": True})

    async def list_view(self, db, chat_id: int, user: User, view: str) -> None:
        """One quadrant (or the inbox, or my own stickers) as a list of buttons; a button opens the card."""
        loc = user.locale
        if view == "mine":
            await self.mine(db, chat_id, user)
            return
        rows = await self.my_board(db, user)
        items = [s for s, p in rows if (p.quadrant is None if view == "inbox" else p.quadrant and p.quadrant.value == view)]
        name = self.menu_label(loc, view)
        if not items:
            await self.say(chat_id, f"<b>{esc(name)}</b>\n{t(loc, 'list.empty')}")
            return
        today = _today_local(user)

        def label(s: Sticker) -> str:
            due = ""
            if s.deadline:
                due = f" · {s.deadline.strftime('%d.%m')}" + (" !" if s.deadline < today else "")
            title = s.title if len(s.title) <= 40 else s.title[:39] + "…"
            return f"№{s.id} {title}{due}"
        kb = [[{"text": label(s), "callback_data": f"S:{s.id}"}] for s in items[:30]]
        await self.say(chat_id, t(loc, "list.head", name=esc(name), n=len(items)), reply_markup={"inline_keyboard": kb})

    async def mine(self, db, chat_id: int, user: User) -> None:
        """Stickers I wrote that are still going: who has each one and at which stage."""
        loc = user.locale
        q = (select(Sticker).where(Sticker.author_id == user.id, Sticker.kind == Kind.normal,
                                   Sticker.status.in_(lc.ACTIVE | {Status.snoozed, Status.resolved}))
             .order_by(Sticker.id.desc()).limit(30))
        items = list(await db.scalars(q))
        if not items:
            await self.say(chat_id, t(loc, "mine.empty"))
            return
        lines, kb = [], []
        for s in items:
            await db.refresh(s, ["placements"])
            who = ", ".join(p.user.display_name for p in lc.recipients(s)) or "—"
            stage = t(loc, "stage.your_answer") if s.status == Status.needs_info else (
                t(loc, "stage.your_confirm") if s.status == Status.resolved else t(loc, f"s.{s.status.value}"))
            if s.status == Status.delegated:
                d = next((p.user.display_name for p in s.placements if p.role == PlacementRole.delegate), "")
                stage += f" → {d}" if d else ""
            mark = "<b>" if s.status in (Status.needs_info, Status.resolved) else ""
            lines.append(f"{mark}№{s.id} {esc(s.title)}{'</b>' if mark else ''}\n{esc(who)} · {stage}")
            title = s.title if len(s.title) <= 40 else s.title[:39] + "…"
            kb.append([{"text": f"№{s.id} {title}", "callback_data": f"S:{s.id}"}])
        await self.say(chat_id, t(loc, "mine.head", n=len(items)) + "\n\n" + "\n\n".join(lines), reply_markup={"inline_keyboard": kb})

    # ------------------------------------------------------------ write a sticker: whom, then the text

    async def write_start(self, db, chat_id: int, user: User) -> None:
        loc = user.locale
        rows = []
        mgr = await self.my_manager(db, user)
        if mgr is not None:
            rows.append([{"text": t(loc, "write.manager", name=mgr.display_name), "callback_data": f"w:to:{mgr.id}"}])
        rows.append([{"text": t(loc, "write.dept"), "callback_data": "w:depts"}, {"text": t(loc, "write.emp"), "callback_data": "w:emp:0"}])
        rows.append([{"text": t(loc, "btn.cancel"), "callback_data": "w:x"}])
        await self.say(chat_id, t(loc, "write.who"), reply_markup={"inline_keyboard": rows})

    @staticmethod
    async def my_manager(db, user: User) -> User | None:
        dept = await db.get(Department, user.department_id) if user.department_id else None
        if dept is None or dept.manager_id is None or dept.manager_id == user.id:
            return None
        mgr = await db.get(User, dept.manager_id)
        return mgr if mgr is not None and mgr.is_active else None

    async def write_step(self, db, msg: dict, user: User, step: str) -> None:
        """Edits the "whom?" message through the steps: departments / people (paged) / chosen -> ask for the text."""
        loc = user.locale
        chat_id, mid = msg["chat"]["id"], msg["message_id"]
        cancel = [{"text": t(loc, "btn.cancel"), "callback_data": "w:x"}]
        back = [{"text": t(loc, "btn.back"), "callback_data": "w:back"}]

        async def edit(text: str, rows: list | None = None):
            try:
                await self.api.call("editMessageText", chat_id=chat_id, message_id=mid, text=text, parse_mode="HTML",
                                    reply_markup={"inline_keyboard": rows or []})
            except TelegramError as e:
                if "not modified" not in str(e):
                    raise

        what, _, arg = step.partition(":")
        if what == "x":
            self.pending.pop(chat_id, None)
            await edit(t(loc, "cancelled"))
        elif what == "back":
            mgr = await self.my_manager(db, user)
            rows = ([[{"text": t(loc, "write.manager", name=mgr.display_name), "callback_data": f"w:to:{mgr.id}"}]] if mgr else []) + [
                [{"text": t(loc, "write.dept"), "callback_data": "w:depts"}, {"text": t(loc, "write.emp"), "callback_data": "w:emp:0"}], cancel]
            await edit(t(loc, "write.who"), rows)
        elif what == "depts":
            depts = list(await db.scalars(select(Department).where(Department.manager_id.is_not(None), Department.manager_id != user.id)
                                          .order_by(Department.name)))
            depts = [d for d in depts if d.id != user.department_id]
            if not depts:
                await edit(t(loc, "write.no_depts"), [back])
                return
            btns = [{"text": d.name, "callback_data": f"w:to:{d.manager_id}"} for d in depts[:30]]
            await edit(t(loc, "write.pick_dept"), [btns[i:i + 2] for i in range(0, len(btns), 2)] + [back])
        elif what == "emp":
            page = int(arg or 0)
            people = list(await db.scalars(select(User).where(User.is_active.is_(True), User.id != user.id).order_by(User.display_name)))
            chunk = people[page * PAGE:(page + 1) * PAGE]
            btns = [{"text": u.display_name, "callback_data": f"w:to:{u.id}"} for u in chunk]
            rows = [btns[i:i + 2] for i in range(0, len(btns), 2)]
            nav = ([{"text": "‹", "callback_data": f"w:emp:{page - 1}"}] if page else []) + (
                [{"text": "›", "callback_data": f"w:emp:{page + 1}"}] if (page + 1) * PAGE < len(people) else [])
            await edit(t(loc, "write.pick_emp"), rows + ([nav] if nav else []) + [back])
        elif what == "to":
            to = await db.get(User, int(arg)) if arg.isdigit() else None
            if to is None or not to.is_active or to.id == user.id:
                await edit(t(loc, "not_allowed"))
                return
            self.pending[chat_id] = {"action": "compose", "to": [to.id]}
            await edit(t(loc, "write.prompt", to=esc(to.display_name)), [cancel])

    # ------------------------------------------------------------ outgoing notifications

    async def notify(self, db, user: User, n: Notification, title: str, body: str) -> bool:
        """Channel for the dispatcher: the notification as a sticker card with action buttons."""
        if n.sticker_id is None:
            await self.say(user.telegram_chat_id, f"<b>{esc(title)}</b>\n{esc(body)}")
            return True
        s = await db.get(Sticker, n.sticker_id)
        if s is None:
            return False
        await db.refresh(s, ["placements"])
        loc = user.locale
        assigned = {"created": "new.assigned", "delegate": "new.delegated"}.get(n.event)
        p = lc.placement_of(s, user)
        if assigned and p is not None and p.role in (PlacementRole.recipient, PlacementRole.delegate):
            text = t(loc, assigned) + f"\n\n<b>№{s.id} {esc(s.title)}</b>\n" + t(loc, "from", name=esc(s.author.display_name))
            kb = {"inline_keyboard": [[{"text": t(loc, "btn.view"), "callback_data": f"s:{s.id}"}]]}
            try:
                await self.say(user.telegram_chat_id, text, reply_markup=kb)
            except TelegramError as e:
                if e.code == 403:
                    user.notify_telegram = False
                raise
            return True
        text = self.card(s, user, title)
        extra = (n.data or {}).get("text")
        if extra and n.event not in ("created",):
            text += f"\n\n<i>{esc(extra)}</i>"
        try:
            await self.say(user.telegram_chat_id, text, reply_markup=self.keyboard(s, user))
        except TelegramError as e:
            if e.code == 403:  # the user blocked the bot: stop trying
                user.notify_telegram = False
            raise
        return True


__all__ = ["Bot", "CommentKind"]
