"""FastAPI application factory: API, passcode gate, scheduler, and the built PWA."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Engine

from pulse import __version__, prefs, security
from pulse.api.routes import router, session_valid
from pulse.client import HealthClient
from pulse.config import Settings, get_settings
from pulse.db import make_engine, make_session_factory, migrate
from pulse.runtime import make_client
from pulse.scheduler import SyncService

OPEN_PATHS = {"/api/v1/health", "/api/v1/session"}
NO_CACHE = {"index.html", "sw.js", "manifest.webmanifest", "registerSW.js"}


class ImmutableStatic(StaticFiles):
    """Hashed build assets never change: cache them for a year."""

    async def get_response(self, path: str, scope: dict) -> Response:  # type: ignore[override,type-arg]
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def _operation_id(route: APIRoute) -> str:
    return route.name


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    start_scheduler: bool | None = None,
    client_factory: Callable[[], HealthClient] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> FastAPI:
    settings = settings or get_settings()
    engine = engine or make_engine(settings.db_path)
    sessions = make_session_factory(engine)
    run_scheduler = settings.scheduler_enabled if start_scheduler is None else start_scheduler

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        migrate(engine)
        service = None
        if run_scheduler:
            service = SyncService(
                sessions,
                client_factory or (lambda: make_client(settings)),
                settings.zone,
                settings.lock_path,
                settings.sync_interval_min,
            )
            service.start()
        app.state.sync_service = service
        yield
        if service:
            service.shutdown()

    app = FastAPI(
        title="Pulse",
        version=__version__,
        description="Self-hosted Google Health dashboard API.",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
        lifespan=lifespan,
        generate_unique_id_function=_operation_id,
    )
    app.state.settings = settings
    app.state.sessions = sessions
    app.state.zone = settings.zone
    app.state.now = now
    app.state.sync_service = None
    app.state.signer = security.SessionSigner(security.load_secret(settings.secret_key_path))
    app.state.limiter = security.AttemptLimiter()

    @app.middleware("http")
    async def passcode_gate(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if (
            path.startswith("/api/")
            and path not in OPEN_PATHS
            and not path.startswith("/api/v1/docs")
            and path != "/api/v1/openapi.json"
        ):
            with sessions() as db:
                stored = prefs.get(db, "passcode_hash")
            if isinstance(stored, str) and not session_valid(request, stored):
                return JSONResponse({"detail": "passcode required"}, status_code=401)
        return await call_next(request)

    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.include_router(router)
    _mount_frontend(app, settings.static_dir)
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    index = dist / "index.html"
    if not index.exists():
        return
    if (dist / "assets").is_dir():
        app.mount("/assets", ImmutableStatic(directory=dist / "assets"), name="assets")
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404)
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            headers = {"Cache-Control": "no-cache"} if candidate.name in NO_CACHE else None
            return FileResponse(candidate, headers=headers)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
