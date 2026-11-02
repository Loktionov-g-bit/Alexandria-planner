"""People's names and logins: "Олег Журавлёв" → login "o.zhuravlev"."""

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import User

# simple, readable transliteration (close to passport rules, no diacritics);
# covers Russian, Belarusian, Ukrainian, Kazakh and Georgian; Latin letters lose
# their diacritics (Čapek → capek), German umlauts follow German rules (Müller → mueller)
_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya", "і": "i", "ї": "yi", "є": "ye", "ґ": "g", "ў": "u",
    "ә": "a", "ғ": "g", "қ": "k", "ң": "n", "ө": "o", "ұ": "u", "ү": "u", "һ": "h",
    "ა": "a", "ბ": "b", "გ": "g", "დ": "d", "ე": "e", "ვ": "v", "ზ": "z", "თ": "t", "ი": "i", "კ": "k",
    "ლ": "l", "მ": "m", "ნ": "n", "ო": "o", "პ": "p", "ჟ": "zh", "რ": "r", "ს": "s", "ტ": "t", "უ": "u",
    "ფ": "p", "ქ": "k", "ღ": "gh", "ყ": "q", "შ": "sh", "ჩ": "ch", "ც": "ts", "ძ": "dz", "წ": "ts", "ჭ": "ch",
    "ხ": "kh", "ჯ": "j", "ჰ": "h",
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
}


def translit(text: str) -> str:
    out = "".join(_MAP.get(ch, ch) for ch in text.lower())
    out = "".join(ch for ch in unicodedata.normalize("NFKD", out) if not unicodedata.combining(ch))
    out = re.sub(r"[\s_]*-[\s_-]*", "-", out)  # keep double-barrelled names: Хрущёв-Ёжиков → khrushchev-ezhikov
    return re.sub(r"[^a-z0-9-]+", "", out).strip("-")


def full_name(first: str, last: str) -> str:
    return f"{first.strip()} {last.strip()}".strip()


def base_login(first: str, last: str) -> str:
    f, la = translit(first), translit(last)
    if f and la:
        return f"{f[0]}.{la}"[:60]
    return (la or f or "user")[:60]


async def free_login(db: AsyncSession, first: str, last: str, exclude_id: int | None = None) -> str:
    """o.zhuravlev, then o.zhuravlev2, o.zhuravlev3... whichever is not taken."""
    base = base_login(first, last)
    taken = set(await db.scalars(select(User.login).where(User.login.like(f"{base}%"))))
    if base not in taken:
        return base
    n = 2
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


def set_names(user: User, first: str | None, last: str | None) -> None:
    if first is not None:
        user.first_name = first.strip()
    if last is not None:
        user.last_name = last.strip()
    user.display_name = full_name(user.first_name, user.last_name)
