"""Structured-ish logging to a rotating file, with secrets redacted before anything is written."""

from __future__ import annotations

import json
import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Google access tokens, refresh tokens, client secrets, bearer headers, auth codes.
_PATTERNS = [
    re.compile(r"ya29\.[\w\-.]+"),
    re.compile(r"1//[\w\-]+"),
    re.compile(r"GOCSPX-[\w\-]+"),
    re.compile(r"(?i)(bearer\s+)\S+"),
    re.compile(
        r"(?i)((?:access_token|refresh_token|client_secret|code|code_verifier)[\"']?\s*[:=]\s*[\"']?)[^\s\"'&,}]+"
    ),
]
REDACTED = "[REDACTED]"


def redact(text: str, extra_secrets: tuple[str, ...] = ()) -> str:
    for secret in extra_secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    for pat in _PATTERNS:
        text = pat.sub(lambda m: (m.group(1) if m.groups() else "") + REDACTED, text)
    return text


class JsonFormatter(logging.Formatter):
    """One JSON object per line: easy to grep, jq or ship later."""

    def __init__(self, extra_secrets: tuple[str, ...] = ()) -> None:
        super().__init__()
        self.extra_secrets = extra_secrets

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = redact(self.formatException(record.exc_info), self.extra_secrets)
        return json.dumps(entry, ensure_ascii=False)


class RedactingFilter(logging.Filter):
    def __init__(self, extra_secrets: tuple[str, ...] = ()) -> None:
        super().__init__()
        self.extra_secrets = extra_secrets

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage(), self.extra_secrets)
        record.args = None
        return True


def setup_logging(
    log_dir: Path, extra_secrets: tuple[str, ...] = (), level: int = logging.INFO
) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = RotatingFileHandler(log_dir / "pulse.log", maxBytes=5_000_000, backupCount=5)
    handler.setFormatter(JsonFormatter(extra_secrets))
    handler.addFilter(RedactingFilter(extra_secrets))
    root.addHandler(handler)
    # Third-party libraries can log full URLs/headers at DEBUG; keep them quiet.
    for noisy in ("httpx", "httpcore", "urllib3", "requests_oauthlib", "oauthlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
