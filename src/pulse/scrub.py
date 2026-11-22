"""Deterministic scrubbing of identifiers in API responses before they become fixtures.

IDs are replaced with ``scrubbed-<hmac8>`` using a per-install random salt, so the same ID maps
to the same placeholder across files (joins still work) but short IDs can't be brute-forced
back from the fixture. Health values and timestamps are kept.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from pathlib import Path
from typing import Any

from pulse.fileio import write_private

# Keys whose string values are always identifiers.
ID_KEYS = {
    "legacyUserId",
    "healthUserId",
    "webClientId",
    "googleWebClientId",
    "packageName",
    "serialNumber",
    "deviceId",
    "uid",
}
# Resource names: users/{user}/dataTypes/{type}/dataPoints/{id} etc.
NAME_KEYS = {"name", "dataPointName", "parent"}
_ID_SEGMENT = re.compile(
    r"(?P<coll>users|dataPoints|pairedDevices|subscribers|subscriptions)/(?P<id>[^/]+)"
)


class Scrubber:
    def __init__(self, salt: bytes) -> None:
        self._salt = salt

    @classmethod
    def from_salt_file(cls, path: Path) -> Scrubber:
        if not path.exists():
            write_private(path, secrets.token_hex(32))
        return cls(bytes.fromhex(path.read_text().strip()))

    def token(self, value: str) -> str:
        digest = hmac.new(self._salt, value.encode(), hashlib.sha256).hexdigest()[:8]
        return f"scrubbed-{digest}"

    def _scrub_name(self, value: str) -> str:
        def repl(m: re.Match[str]) -> str:
            ident = m.group("id")
            if m.group("coll") == "users" and ident == "me":
                return m.group(0)
            return f"{m.group('coll')}/{self.token(ident)}"

        return _ID_SEGMENT.sub(repl, value)

    def scrub(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for k, v in obj.items():
                if isinstance(v, str) and (k in ID_KEYS or k.lower().endswith("serial")):
                    out[k] = self.token(v)
                elif isinstance(v, str) and k in NAME_KEYS:
                    out[k] = self._scrub_name(v)
                else:
                    out[k] = self.scrub(v)
            return out
        if isinstance(obj, list):
            return [self.scrub(v) for v in obj]
        return obj
