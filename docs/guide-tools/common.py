"""Shared bits of the guide screenshot scripts: work dir, language, demo content, UI strings."""
import json
import sys
import time
from pathlib import Path

import pyotp

ROOT = Path(__file__).resolve().parents[2]
WORK, LANG = Path(sys.argv[1]), sys.argv[2]
U = "http://localhost:8001"
PW = "Demo-planner-2026"
C = json.loads((Path(__file__).parent / "content" / f"{LANG}.json").read_text(encoding="utf-8"))
UI = json.loads((ROOT / "frontend" / "src" / "locales" / f"{LANG}.json").read_text(encoding="utf-8"))
OUT = WORK / "shots"


def ui(path: str) -> str:
    v = UI
    for k in path.split("."):
        v = v[k]
    return v


def logins() -> dict:
    return json.loads((WORK / "logins.json").read_text())


def fresh_code() -> str:
    """A TOTP code not used before (the server rejects replays)."""
    totp = pyotp.TOTP((WORK / "totp.txt").read_text().strip())
    last = WORK / "lastcode.txt"
    while last.exists() and totp.now() == last.read_text().strip():
        time.sleep(2)
    code = totp.now()
    last.write_text(code)
    return code
