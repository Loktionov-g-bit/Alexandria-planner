"""Bot texts. HTML parse mode: everything user-supplied goes through esc()."""

from html import escape

from ..locales import texts

T: dict[str, dict[str, str]] = texts("telegram")


def t(locale: str | None, key: str, **kw) -> str:
    table = T.get(locale or "ru", T["ru"])
    return table.get(key, T["ru"].get(key, key)).format(**kw)


def esc(s: str | None) -> str:
    return escape(s or "", quote=False)
