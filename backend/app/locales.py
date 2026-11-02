"""Interface languages. Russian is the source text; every other table falls back to it key by key."""

import json
from functools import cache
from pathlib import Path

_DIR = Path(__file__).parent / "i18n"

LOCALES = ("ru", "en", "be", "kk", "ka", "cs", "de")
LOCALE_PATTERN = "^(" + "|".join(LOCALES) + ")$"


def from_client(code: str | None, default: str = "ru") -> str:
    """Telegram/browser language code ("de-AT", "kk") → one of LOCALES."""
    short = (code or "").lower()[:2]
    return short if short in LOCALES else default


def decimal(locale: str, value: str) -> str:
    """English writes 1.5; every other supported language writes 1,5."""
    return value if locale == "en" else value.replace(".", ",")


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


@cache
def texts(section: str) -> dict[str, dict]:
    """{locale: table} for one section of app/i18n/<locale>.json; missing keys fall back to Russian."""
    ru = json.loads((_DIR / "ru.json").read_text(encoding="utf-8"))[section]
    out = {"ru": ru}
    for loc in LOCALES[1:]:
        f = _DIR / f"{loc}.json"
        if f.exists():
            out[loc] = _merge(ru, json.loads(f.read_text(encoding="utf-8")).get(section, {}))
    return out
