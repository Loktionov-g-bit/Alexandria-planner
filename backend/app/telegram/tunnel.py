"""Backup route to Telegram through WireGuard, for servers where api.telegram.org is blocked.

The admin uploads an ordinary WireGuard config (.conf, or a .zip with one inside). We run it with
wireproxy: WireGuard entirely in user space, no NET_ADMIN, no /dev/net/tun, nothing changes for the
rest of the container. It only exposes an HTTP proxy on 127.0.0.1, and only the Telegram client uses it.

Mode "auto" (default): talk to Telegram directly; fall back to the tunnel when the direct route fails,
and go back to direct once it works again. "always": tunnel only. "off": keep the config but never use it.
"""

from __future__ import annotations

import asyncio
import configparser
import io
import logging
import os
import re
import shutil
import socket
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from ..config import get_settings
from ..models import AppSetting, utcnow

log = logging.getLogger("planner.telegram")

KEY = "telegram_tunnel"
MODES = ("auto", "always", "off")
MAX_UPLOAD = 256 * 1024
MAX_CONF = 64 * 1024
# wg-quick hooks and routing options: they mean nothing to a user-space proxy (and hooks are shell commands)
DROP = {"preup", "postup", "predown", "postdown", "table", "saveconfig", "fwmark"}
# AmneziaWG obfuscation parameters: a different protocol that plain WireGuard cannot speak
AMNEZIA = {"jc", "jmin", "jmax", "s1", "s2", "s3", "s4", "h1", "h2", "h3", "h4", "i1", "i2", "i3", "i4", "i5"}
B64KEY = re.compile(r"^[A-Za-z0-9+/]{42,43}=?$")


class TunnelError(ValueError):
    """Bad upload; .args[0] is an i18n key (admin.tunnel.err.*)."""


@dataclass
class Parsed:
    text: str          # cleaned config written for wireproxy
    endpoint: str      # host:port of the first peer, shown to the admin
    address: str       # tunnel address, shown to the admin
    name: str          # file name inside the upload


def _clean(raw: str, name: str) -> Parsed:
    raw = raw.lstrip("﻿")
    cp = configparser.ConfigParser(strict=False, interpolation=None, delimiters=("=",))
    cp.optionxform = str  # keep key case
    try:
        # several [Peer] sections are legal in WireGuard; configparser merges duplicates, so number them first
        n = 0

        def peer(_m):
            nonlocal n
            n += 1
            return f"[Peer.{n}]"
        cp.read_string(re.sub(r"^\s*\[Peer\]\s*$", peer, raw, flags=re.M | re.I))
    except configparser.Error:
        raise TunnelError("bad_format") from None
    iface = next((cp[s] for s in cp.sections() if s.lower() == "interface"), None)
    peers = [cp[s] for s in cp.sections() if s.lower().startswith("peer.")]
    if iface is None or not peers:
        raise TunnelError("bad_format")
    for sec in cp.sections():
        for k, v in cp[sec].items():
            if any(ch in v for ch in "\r\n\x00") or not re.fullmatch(r"[A-Za-z0-9_]+", k):
                raise TunnelError("bad_format")  # a value spanning lines could add sections to wireproxy's config
    keys = {k.lower() for s in cp.sections() for k in cp[s]}
    if keys & AMNEZIA:
        raise TunnelError("amnezia")
    get = lambda sec, k: next((v.strip() for kk, v in sec.items() if kk.lower() == k), "")  # noqa: E731
    if not B64KEY.match(get(iface, "privatekey")) or not get(iface, "address"):
        raise TunnelError("bad_format")
    for p in peers:
        if not B64KEY.match(get(p, "publickey")) or ":" not in get(p, "endpoint"):
            raise TunnelError("bad_format")
    lines = ["[Interface]"] + [f"{k} = {v.strip()}" for k, v in iface.items() if k.lower() not in DROP]
    for p in peers:
        lines += ["", "[Peer]"] + [f"{k} = {v.strip()}" for k, v in p.items() if k.lower() not in DROP]
        if not get(p, "allowedips"):
            lines.append("AllowedIPs = 0.0.0.0/0, ::/0")
    return Parsed("\n".join(lines) + "\n", get(peers[0], "endpoint"), get(iface, "address").split(",")[0].strip(), name)


def parse_upload(filename: str, data: bytes) -> Parsed:
    """A WireGuard .conf, or a .zip with exactly one .conf (VPN providers often ship them zipped)."""
    if len(data) > MAX_UPLOAD:
        raise TunnelError("too_big")
    if data[:4] == b"PK\x03\x04" or filename.lower().endswith(".zip"):
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise TunnelError("bad_zip") from None
        confs = [i for i in z.infolist() if not i.is_dir() and i.filename.lower().endswith(".conf") and "__MACOSX" not in i.filename]
        if not confs:
            raise TunnelError("no_conf")
        if len(confs) > 1:
            raise TunnelError("many_conf")
        if confs[0].file_size > MAX_CONF:
            raise TunnelError("too_big")
        with z.open(confs[0]) as f:
            raw = f.read(MAX_CONF + 1)
        filename = os.path.basename(confs[0].filename)
    else:
        raw = data
    if len(raw) > MAX_CONF:
        raise TunnelError("too_big")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise TunnelError("bad_format") from None
    return _clean(text, filename)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class Tunnel:
    """The wireproxy process and the route state, one per worker process."""

    mode: str = "off"
    conf: str | None = None
    port: int | None = None
    proc: asyncio.subprocess.Process | None = None
    route: str = "direct"          # what the last successful call used: direct | tunnel
    last_ok: float | None = None
    last_error: str | None = None
    tunnel_since: float | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    RETRY_DIRECT = 600  # while on the tunnel, try the direct route again every 10 minutes

    @property
    def available(self) -> bool:
        return self.conf is not None and self.mode != "off" and shutil.which(binary()) is not None

    @property
    def proxy(self) -> str | None:
        return f"http://127.0.0.1:{self.port}" if self.port else None

    def routes(self) -> list[str]:
        """Order to try: the tunnel first only in "always" mode or while direct is known to be down."""
        if not self.available:
            return ["direct"]
        if self.mode == "always":
            return ["tunnel"]
        if self.route == "tunnel" and self.tunnel_since and time.monotonic() - self.tunnel_since < self.RETRY_DIRECT:
            return ["tunnel", "direct"]
        return ["direct", "tunnel"]

    def mark(self, route: str, ok: bool, error: str | None = None) -> None:
        if ok:
            if route == "tunnel" and self.route != "tunnel":
                log.warning("Telegram via the WireGuard tunnel" + ("" if self.mode == "always" else " (direct route failed)"))
                self.tunnel_since = time.monotonic()
            elif route == "direct" and self.route == "tunnel":
                log.info("Telegram reachable directly again; tunnel on standby")
            self.route, self.last_ok, self.last_error = route, time.time(), None
        else:
            self.last_error = error

    async def configure(self, value: dict | None) -> None:
        """Apply the stored setting: (re)start or stop wireproxy."""
        async with self.lock:
            await self._stop()
            self.mode = (value or {}).get("mode", "auto") if value and value.get("conf") else "off"
            self.conf = (value or {}).get("conf") or None
            self.route, self.tunnel_since = "direct", None
            if self.conf and self.mode != "off":
                await self._start()

    async def ensure(self) -> bool:
        """wireproxy running and listening (restart it if it died)."""
        if not self.available:
            return False
        async with self.lock:
            if self.proc is None or self.proc.returncode is not None:
                await self._start()
            return self.proc is not None and self.proc.returncode is None

    async def _start(self) -> None:
        folder = get_settings().data_dir / "wireguard"
        folder.mkdir(parents=True, exist_ok=True)
        os.chmod(folder, 0o700)
        wg, cfg = folder / "wg.conf", folder / "wireproxy.conf"
        self.port = _free_port()
        for path, text in ((wg, self.conf or ""), (cfg, f"WGConfig = {wg}\n\n[http]\nBindAddress = 127.0.0.1:{self.port}\n")):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(text)
        exe = shutil.which(binary())
        if exe is None:
            self.last_error = "wireproxy_missing"
            self.proc = None
            return
        self.proc = await asyncio.create_subprocess_exec(exe, "-c", str(cfg), stdout=asyncio.subprocess.DEVNULL,
                                                         stderr=asyncio.subprocess.PIPE)
        for _ in range(50):  # up to 5 s for the proxy port to open
            if self.proc.returncode is not None:
                err = (await self.proc.stderr.read()).decode(errors="replace") if self.proc.stderr else ""
                self.last_error = "wireproxy: " + (err.strip().splitlines() or ["exited"])[-1][:200]
                log.warning("wireproxy exited: %s", self.last_error)
                self.proc = None
                return
            try:
                _, w = await asyncio.open_connection("127.0.0.1", self.port)
                w.close()
                log.info("WireGuard tunnel for Telegram is up (proxy 127.0.0.1:%s)", self.port)
                return
            except OSError:
                await asyncio.sleep(0.1)

    async def _stop(self) -> None:
        if self.proc is not None and self.proc.returncode is None:
            self.proc.terminate()
            try:
                await asyncio.wait_for(self.proc.wait(), 5)
            except TimeoutError:
                self.proc.kill()
        self.proc, self.port = None, None

    def status(self) -> dict:
        return {"running": self.proc is not None and self.proc.returncode is None, "route": self.route,
                "last_ok": self.last_ok, "last_error": self.last_error, "binary": shutil.which(binary()) is not None}


def binary() -> str:
    return os.environ.get("PLANNER_WIREPROXY", "wireproxy")


tunnel = Tunnel()


async def load(db) -> dict | None:
    row = await db.get(AppSetting, KEY)
    return row.value if row is not None and row.value else None


async def save(db, value: dict | None) -> None:
    row = await db.get(AppSetting, KEY)
    if value is None:
        if row is not None:
            await db.delete(row)
    elif row is None:
        db.add(AppSetting(key=KEY, value=value))
    else:
        row.value = value
    await db.commit()
    await tunnel.configure(value)


def public(value: dict | None) -> dict:
    """What the admin page may see: never the keys."""
    if not value or not value.get("conf"):
        return {"configured": False, "mode": "auto", **tunnel.status()}
    return {"configured": True, "mode": value.get("mode", "auto"), "endpoint": value.get("endpoint"),
            "address": value.get("address"), "name": value.get("name"), "uploaded_at": value.get("uploaded_at"), **tunnel.status()}


def stored(p: Parsed, mode: str) -> dict:
    return {"conf": p.text, "endpoint": p.endpoint, "address": p.address, "name": p.name, "mode": mode,
            "uploaded_at": utcnow().isoformat()}


__all__ = ["MODES", "Path", "TunnelError", "load", "parse_upload", "public", "save", "stored", "tunnel"]
