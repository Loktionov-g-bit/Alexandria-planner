import hashlib
import hmac
import re
import secrets
import time

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from .config import get_settings

_ph = PasswordHasher()
# Used to spend the same time on unknown logins as on real ones (no user enumeration by timing).
_DUMMY_HASH = _ph.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _ph.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_problems(password: str, *, login: str = "") -> list[str]:
    """Return a list of i18n keys for violated rules; empty list = password OK."""
    problems = []
    if len(password) < get_settings().password_min_length:
        problems.append("password.too_short")
    # any alphabet counts: Čáp, Müller, Әлия; Georgian has no capitals, so it counts as lowercase
    kinds = (str.islower, str.isupper, str.isdigit, lambda c: not c.isalnum() and not c.isspace())
    classes = sum(any(k(c) for c in password) for k in kinds)
    if classes < 3:
        problems.append("password.too_simple")
    if login and login.lower() in password.lower():
        problems.append("password.contains_login")
    return problems


def new_token() -> tuple[str, str]:
    """Return (cookie_value, db_id). Only the hash is stored, so a DB leak does not leak sessions."""
    token = secrets.token_urlsafe(32)
    return token, token_id(token)


def token_id(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, login: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=login, issuer_name="Alexandria Planner")


def verify_totp(secret: str | None, code: str) -> bool:
    return totp_step(secret, code) is not None


def totp_step(secret: str | None, code: str, after: int | None = None) -> int | None:
    """The 30-second step the code belongs to (current one ±1 for clock drift), or None.
    Steps not newer than `after` are refused: one code, one use."""
    if not secret:
        return None
    code = re.sub(r"\s", "", code or "")
    if not (code.isdigit() and len(code) == 6):
        return None
    totp = pyotp.TOTP(secret)
    now = int(time.time()) // totp.interval
    for step in (now, now - 1, now + 1):
        if (after is None or step > after) and hmac.compare_digest(totp.at(step * totp.interval), code):
            return step
    return None


def use_totp(user, code: str) -> bool:
    """Check a code and burn it."""
    step = totp_step(user.totp_secret, code, user.totp_last_step)
    if step is None:
        return False
    user.totp_last_step = step
    return True
