"""Canary routing (SPEC §10). The stable container is the entry point; requests of users whose
channel is beta are forwarded to the beta container. If beta is down, stable answers itself: nobody
is locked out, they just see the stable version until beta is back."""

import logging

import httpx
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from .deps import CHANNEL_COOKIE

log = logging.getLogger("planner.proxy")

HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding",
       "upgrade", "host", "content-length"}
MARK = "x-planner-proxied"

_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(60, connect=3), follow_redirects=False)
    return _client


def wants_beta(request: Request) -> bool:
    return request.cookies.get(CHANNEL_COOKIE) == "beta" and MARK not in request.headers


async def forward(request: Request, beta_url: str) -> Response | None:
    """Forward to beta; None means "beta unreachable, serve locally"."""
    url = beta_url.rstrip("/") + request.url.path + (f"?{request.url.query}" if request.url.query else "")
    headers = [(k, v) for k, v in request.headers.items() if k.lower() not in HOP]
    peer = request.client.host if request.client else ""
    xff = request.headers.get("x-forwarded-for")
    headers += [(MARK, "1"), ("x-forwarded-for", f"{xff}, {peer}" if xff else peer),
                ("x-forwarded-proto", request.headers.get("x-forwarded-proto", request.url.scheme)),
                ("x-forwarded-host", request.headers.get("x-forwarded-host", request.headers.get("host", "")))]
    body = await request.body()
    req = client().build_request(request.method, url, headers=headers, content=body)
    try:
        upstream = await client().send(req, stream=True)
    except httpx.HTTPError as e:
        log.warning("beta unreachable (%s), serving from stable", type(e).__name__)
        return None
    out_headers = [(k, v) for k, v in upstream.headers.multi_items() if k.lower() not in HOP]

    async def body_iter():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()

    resp = StreamingResponse(body_iter(), status_code=upstream.status_code)
    resp.raw_headers = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in out_headers]
    return resp
