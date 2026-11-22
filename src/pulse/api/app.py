"""FastAPI application. Phase 0 exposes only a liveness endpoint."""

from __future__ import annotations

from fastapi import FastAPI

from pulse import __version__

app = FastAPI(title="Pulse", version=__version__, openapi_url="/api/v1/openapi.json")


@app.get("/api/v1/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
