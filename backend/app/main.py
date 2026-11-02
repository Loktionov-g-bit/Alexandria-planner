import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from . import __version__
from .api import admin, auth, channels, notifications, profile, setup, stats, stickers, telegram
from .config import get_settings
from .db import get_engine, sessionmaker

log = logging.getLogger("planner")


async def scheduler() -> None:
    """Escalation by deadline, waking snoozed stickers, auto-close. Runs inside the app process."""
    from . import stickers as lc
    from .db import sessionmaker

    while True:
        try:
            async with sessionmaker()() as db:
                await lc.tick(db)
        except Exception:  # noqa: BLE001 - a failed pass must not kill the loop
            log.exception("scheduler pass failed")
        await asyncio.sleep(get_settings().scheduler_minutes * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    st = get_settings()
    from .telegram import tunnel as tun

    try:  # the WireGuard backup route to Telegram, if the admin uploaded one
        async with sessionmaker()() as db:
            await tun.tunnel.configure(await tun.load(db))
    except Exception:  # noqa: BLE001 - no tunnel must never stop the app (e.g. tables not created yet in tests)
        log.exception("could not start the Telegram tunnel")
    guard = asyncio.create_task(worker_guard()) if st.worker and st.scheduler_minutes > 0 else None
    yield
    if guard:
        guard.cancel()
    await tun.tunnel.configure(None)
    await get_engine().dispose()


def start_workers() -> list[asyncio.Task]:
    from . import digest, dispatch, live
    from .db import sessionmaker
    from .telegram import runner

    return [
        asyncio.create_task(scheduler()),
        asyncio.create_task(dispatch.loop(sessionmaker(), live.wakeup)),
        asyncio.create_task(runner.run(sessionmaker())),
        asyncio.create_task(digest.loop(sessionmaker())),
    ]


async def worker_guard() -> None:
    """Background work runs in exactly one process. On Postgres a session-level advisory lock decides
    (two stable replicas, or a beta started with PLANNER_WORKER=true by mistake, stay safe);
    whoever holds it works, the others retry every minute and take over if the holder dies."""
    from sqlalchemy import text

    engine = get_engine()
    tasks: list[asyncio.Task] = []
    if engine.dialect.name != "postgresql":
        tasks = start_workers()
        try:
            await asyncio.Event().wait()
        finally:
            for t in tasks:
                t.cancel()
    conn = None
    try:
        while True:
            try:
                if conn is None:
                    conn = await engine.connect()
                    got = (await conn.execute(text("SELECT pg_try_advisory_lock(7310421)"))).scalar()
                    if got:
                        log.info("this process runs background work")
                        tasks = start_workers()
                    else:
                        await conn.close()
                        conn = None
                else:
                    await conn.execute(text("SELECT 1"))  # keep the lock's connection alive
            except Exception:  # noqa: BLE001 - lost DB: drop the lock and the work, try again
                log.exception("worker lock check failed")
                for t in tasks:
                    t.cancel()
                tasks = []
                if conn is not None:
                    await conn.invalidate()
                    conn = None
            await asyncio.sleep(60)
    finally:
        for t in tasks:
            t.cancel()
        if conn is not None:
            await conn.close()


def create_app() -> FastAPI:
    st = get_settings()
    app = FastAPI(title="Alexandria Planner", version=__version__, lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    for r in (setup.router, auth.router, profile.router, admin.router, stickers.router, notifications.router, telegram.router, stats.router, channels.router):
        app.include_router(r)

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True, "version": __version__, "channel": st.channel}

    if st.beta_url and st.channel == "stable":
        from . import proxy

        @app.middleware("http")
        async def route_beta(request, call_next):
            # health of *this* container stays local; everything else follows the user's channel
            if request.url.path != "/api/health" and proxy.wants_beta(request):
                resp = await proxy.forward(request, st.beta_url)
                if resp is not None:
                    return resp
            return await call_next(request)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    # Built frontend is served by the same process (no extra nginx container).
    static = st.static_dir
    if static.is_dir():
        # <base href> tells the SPA where it lives, so the app works under any sub-path behind a proxy
        index_html = (static / "index.html").read_text().replace('<base href="/" />', f'<base href="{st.root_path}/" />')

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            if path.startswith("api/"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            f = (static / path).resolve()
            if path and f.is_file() and f.is_relative_to(static.resolve()):
                return FileResponse(f)
            if path.startswith("assets/") or "." in path.rsplit("/", 1)[-1]:
                # a missing file must not turn into index.html (browsers then report a confusing MIME error)
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            return HTMLResponse(index_html, headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
