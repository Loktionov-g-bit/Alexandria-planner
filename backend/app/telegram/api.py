"""Minimal Bot API client over httpx (no framework: fewer dependencies, easy to fake in tests)."""

import asyncio
import json
from typing import Any

import httpx

from .tunnel import tunnel

BASE = "https://api.telegram.org"


class TelegramError(Exception):
    def __init__(self, description: str, code: int | None = None):
        super().__init__(description)
        self.code = code


class TelegramAPI:
    """Bot API over the direct route, or over the WireGuard tunnel when the direct one fails (see tunnel.py)."""

    def __init__(self, token: str, client: httpx.AsyncClient | None = None):
        self.token = token
        self.fixed = client  # tests pass a client: no routing then
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(40, connect=8))
        self._via: tuple[str, httpx.AsyncClient] | None = None  # (proxy url, client)

    def _proxied(self) -> httpx.AsyncClient:
        url = tunnel.proxy
        if self._via is None or self._via[0] != url:
            if self._via is not None:
                old = self._via[1]
                asyncio.get_running_loop().create_task(old.aclose())
            self._via = (url, httpx.AsyncClient(proxy=url, timeout=httpx.Timeout(40, connect=15)))
        return self._via[1]

    async def _send(self, method: str, url: str, **kw) -> httpx.Response:
        if self.fixed is not None:
            return await self.fixed.request(method, url, **kw)
        last: Exception | None = None
        for route in tunnel.routes():
            if route == "tunnel":
                if not await tunnel.ensure():
                    continue
                client = self._proxied()
            else:
                client = self.client
            try:
                r = await client.request(method, url, **kw)
            except httpx.TransportError as e:  # blocked, reset, timed out: try the other route
                tunnel.mark(route, False, f"{route}: {type(e).__name__}")
                last = e
                continue
            tunnel.mark(route, True)
            return r
        raise last or httpx.ConnectError("no route")

    async def call(self, method: str, **params: Any) -> Any:
        data = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                for k, v in params.items() if v is not None}
        try:
            r = await self._send("POST", f"{BASE}/bot{self.token}/{method}", data=data)
            body = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise TelegramError(f"network: {type(e).__name__}") from None  # never echo the URL: it holds the token
        if not body.get("ok"):
            raise TelegramError(body.get("description", "error"), body.get("error_code"))
        return body["result"]

    async def download(self, file_id: str, limit: int) -> bytes:
        info = await self.call("getFile", file_id=file_id)
        if info.get("file_size", 0) > limit:
            raise TelegramError("file too large")
        try:
            r = await self._send("GET", f"{BASE}/file/bot{self.token}/{info['file_path']}")
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise TelegramError(f"network: {type(e).__name__}") from None
        return r.content

    async def close(self) -> None:
        await self.client.aclose()
        if self._via is not None:
            await self._via[1].aclose()
