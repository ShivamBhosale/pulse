"""User preferences persisted in the ``settings`` table (JSON values with defaults)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from pulse.models import Setting

DEFAULTS: dict[str, Any] = {
    "goals": {"sleep_min": 480, "steps": 10_000, "azm_weekly": 150},
    "units": "metric",
    "theme": "dark",
    "passcode_hash": None,
}


def get(session: Session, key: str) -> Any:
    row = session.get(Setting, key)
    if row is None:
        return DEFAULTS.get(key)
    return json.loads(row.value_json)


def put(session: Session, key: str, value: Any) -> None:
    row = session.get(Setting, key)
    payload = json.dumps(value)
    if row is None:
        session.add(Setting(key=key, value_json=payload))
    else:
        row.value_json = payload


def goals(session: Session) -> dict[str, int]:
    merged = dict(DEFAULTS["goals"])
    merged.update(get(session, "goals") or {})
    return merged
