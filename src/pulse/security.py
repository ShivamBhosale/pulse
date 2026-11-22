"""Optional passcode: scrypt hash in settings, HMAC-signed session cookie, attempt limiter."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from pathlib import Path

from pulse.fileio import write_private

COOKIE_NAME = "pulse_session"
SESSION_MAX_AGE_S = 30 * 24 * 3600
_N, _R, _P = 2**14, 8, 1


def hash_passcode(passcode: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(passcode.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_passcode(passcode: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    digest = hashlib.scrypt(
        passcode.encode(), salt=bytes.fromhex(salt_hex), n=int(n), r=int(r), p=int(p), dklen=32
    )
    return hmac.compare_digest(digest.hex(), digest_hex)


def fingerprint(stored_hash: str) -> str:
    """Binds sessions to the current passcode: changing it logs every device out."""
    return hashlib.sha256(stored_hash.encode()).hexdigest()[:16]


def load_secret(path: Path) -> bytes:
    if not path.exists():
        write_private(path, secrets.token_hex(32))
    return bytes.fromhex(path.read_text().strip())


class SessionSigner:
    def __init__(self, secret: bytes, now: Callable[[], float] = time.time) -> None:
        self._secret = secret
        self._now = now

    def _sig(self, issued: str, fp: str) -> str:
        return hmac.new(self._secret, f"{issued}.{fp}".encode(), hashlib.sha256).hexdigest()

    def issue(self, fp: str) -> str:
        issued = str(int(self._now()))
        return f"{issued}.{self._sig(issued, fp)}"

    def verify(self, token: str | None, fp: str, max_age: int = SESSION_MAX_AGE_S) -> bool:
        if not token or "." not in token:
            return False
        issued, sig = token.split(".", 1)
        if not issued.isdigit() or not hmac.compare_digest(sig, self._sig(issued, fp)):
            return False
        return 0 <= self._now() - int(issued) <= max_age


class AttemptLimiter:
    """At most ``limit`` failed attempts per ``window_s`` per client key."""

    def __init__(self, limit: int = 5, window_s: float = 60.0) -> None:
        self.limit, self.window_s = limit, window_s
        self._fails: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _trim(self, key: str, now: float) -> deque[float]:
        q = self._fails[key]
        while q and now - q[0] > self.window_s:
            q.popleft()
        return q

    def allowed(self, key: str, now: float | None = None) -> bool:
        t = time.monotonic() if now is None else now
        with self._lock:
            return len(self._trim(key, t)) < self.limit

    def fail(self, key: str, now: float | None = None) -> None:
        t = time.monotonic() if now is None else now
        with self._lock:
            self._trim(key, t).append(t)

    def reset(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)
