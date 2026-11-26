"""Dump API responses from the *synthetic* test dataset as Android unit-test fixtures.

Uses the same seeded in-memory database as tests/test_api.py (no real health data), so the
Android tests always decode responses in the server's current shape. Re-run after API changes:

    uv run python scripts/android_fixtures.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from pulse.api.app import create_app  # noqa: E402
from pulse.config import Settings  # noqa: E402
from pulse.db import make_engine, make_session_factory, migrate  # noqa: E402
from tests.test_api import NOW, TODAY, _seed  # noqa: E402

OUT = ROOT / "android/app/src/test/resources/fixtures"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(
            data_dir=Path(tmp) / "data",
            static_dir=Path(tmp) / "dist",
            scheduler_enabled=False,
            _env_file=None,
        )  # type: ignore[call-arg]
        engine = make_engine(None)
        migrate(engine)
        _seed(make_session_factory(engine))
        app = create_app(settings, engine=engine, start_scheduler=False, now=lambda: NOW)
        with TestClient(app) as c:
            yesterday = (TODAY - timedelta(days=1)).isoformat()
            c.put(
                f"/api/v1/journal/{yesterday}",
                json={"tags": ["alcohol"], "note": "Synthetic note"},
            )
            dumps = {
                "today.json": "/api/v1/today",
                "sleep.json": "/api/v1/sleep",
                "widget.json": "/api/v1/widget",
                "tags.json": "/api/v1/tags",
                "journal.json": f"/api/v1/journal/{yesterday}",
                "status.json": "/api/v1/status",
                "session.json": "/api/v1/session",
                "health.json": "/api/v1/health",
            }
            for name, path in dumps.items():
                r = c.get(path)
                r.raise_for_status()
                (OUT / name).write_text(json.dumps(r.json(), indent=1) + "\n")
                print(f"{name:14} {len(r.content):>7} bytes")


if __name__ == "__main__":
    main()
