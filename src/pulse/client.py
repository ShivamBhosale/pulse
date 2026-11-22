"""Thin httpx client for the Google Health API v4 with retries and typed errors."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import httpx

from pulse.config import API_BASE

log = logging.getLogger(__name__)

JSON = dict[str, Any]


class HealthApiError(RuntimeError):
    def __init__(self, status: int, code: str, message: str, reason: str | None = None) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.reason = reason


class AccountNotLinked(HealthApiError):
    """User has not signed in to the Google Health app with this Google account."""


class InvalidArgument(HealthApiError):
    """Typically a bad filter for this data type."""


class Unauthorized(HealthApiError):
    pass


class PermissionDenied(HealthApiError):
    pass


class NotFound(HealthApiError):
    pass


class RateLimited(HealthApiError):
    pass


class ServerError(HealthApiError):
    pass


class TransportFailure(HealthApiError):
    """Timeouts / connection errors that persisted through every retry."""


def _parse_error(resp: httpx.Response) -> HealthApiError:
    code, message, reason = "UNKNOWN", resp.reason_phrase, None
    try:
        err = resp.json().get("error", {})
        code = err.get("status", code)
        message = err.get("message", message)
        for detail in err.get("details", []) or []:
            if isinstance(detail, dict) and detail.get("reason"):
                reason = detail["reason"]
                break
    except ValueError:
        pass
    s = resp.status_code
    cls: type[HealthApiError]
    if reason == "ACCOUNT_NOT_LINKED":
        cls = AccountNotLinked
    elif s == 400:
        cls = InvalidArgument
    elif s == 401:
        cls = Unauthorized
    elif s == 403:
        cls = PermissionDenied
    elif s == 404:
        cls = NotFound
    elif s == 429:
        cls = RateLimited
    elif s >= 500:
        cls = ServerError
    else:
        cls = HealthApiError
    return cls(s, code, message, reason)


def _retry_after_seconds(resp: httpx.Response) -> float | None:
    value = resp.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


@dataclass
class RetryPolicy:
    max_attempts: int = 5
    base_delay: float = 1.0
    max_delay: float = 60.0

    def delay(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return min(retry_after, self.max_delay)
        # Full jitter exponential backoff.
        return random.uniform(0, min(self.max_delay, self.base_delay * 2**attempt))  # noqa: S311


class HealthClient:
    def __init__(
        self,
        token_provider: Callable[[bool], str],
        *,
        base_url: str = API_BASE,
        http: httpx.Client | None = None,
        min_interval: float = 0.5,
        retry: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._token = token_provider
        self._http = http or httpx.Client(
            base_url=base_url, timeout=httpx.Timeout(120.0, connect=15.0)
        )
        self._min_interval = min_interval
        self._retry = retry or RetryPolicy()
        self._sleep = sleep
        self._clock = clock
        self._last_request: float | None = None
        self.request_count = 0

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> HealthClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- core -------------------------------------------------------------------------

    def _throttle(self) -> None:
        if self._last_request is not None:
            wait = self._min_interval - (self._clock() - self._last_request)
            if wait > 0:
                self._sleep(wait)
        self._last_request = self._clock()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: JSON | None = None,
    ) -> JSON:
        refreshed = False
        attempt = 0
        while True:
            self._throttle()
            headers = {
                "Authorization": f"Bearer {self._token(False)}",
                "Accept": "application/json",
            }
            self.request_count += 1
            try:
                resp = self._http.request(method, path, params=params, json=json, headers=headers)
            except httpx.TransportError as exc:  # timeouts, resets, DNS hiccups
                if attempt + 1 < self._retry.max_attempts:
                    delay = self._retry.delay(attempt, None)
                    log.warning(
                        "retrying %s %s after %s (%.1fs)", method, path, type(exc).__name__, delay
                    )
                    self._sleep(delay)
                    attempt += 1
                    continue
                raise TransportFailure(
                    0, type(exc).__name__, str(exc) or "transport error"
                ) from exc
            if resp.is_success:
                body: JSON = resp.json() if resp.content else {}
                return body
            err = _parse_error(resp)
            if isinstance(err, Unauthorized) and not refreshed:
                refreshed = True
                self._token(True)
                continue
            if (
                isinstance(err, RateLimited | ServerError)
                and attempt + 1 < self._retry.max_attempts
            ):
                delay = self._retry.delay(attempt, _retry_after_seconds(resp))
                log.warning(
                    "retrying %s %s after %s (%.1fs)", method, path, resp.status_code, delay
                )
                self._sleep(delay)
                attempt += 1
                continue
            log.info("api error %s %s -> %s %s", method, path, err.status, err.code)
            raise err

    def pages(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: JSON | None = None,
        max_pages: int | None = None,
    ) -> Iterator[JSON]:
        """Yield raw response pages, following ``nextPageToken``."""
        params = dict(params or {})
        body = dict(json) if json is not None else None
        n = 0
        while True:
            page = self.request(method, path, params=params or None, json=body)
            yield page
            n += 1
            token = page.get("nextPageToken")
            if not token or (max_pages is not None and n >= max_pages):
                return
            if body is not None:
                body["pageToken"] = token
            else:
                params["pageToken"] = token

    # ---- endpoints ---------------------------------------------------------------------

    def get_identity(self) -> JSON:
        return self.request("GET", "users/me/identity")

    def get_profile(self) -> JSON:
        return self.request("GET", "users/me/profile")

    def get_settings(self) -> JSON:
        return self.request("GET", "users/me/settings")

    def list_points(
        self,
        data_type: str,
        *,
        filter: str | None = None,
        page_size: int | None = None,
        max_pages: int | None = None,
        reconcile: bool = False,
    ) -> Iterator[JSON]:
        suffix = ":reconcile" if reconcile else ""
        params: dict[str, Any] = {}
        if filter:
            params["filter"] = filter
        if page_size:
            params["pageSize"] = page_size
        yield from self.pages(
            "GET",
            f"users/me/dataTypes/{data_type}/dataPoints{suffix}",
            params=params,
            max_pages=max_pages,
        )

    def daily_roll_up(self, data_type: str, body: JSON) -> Iterator[JSON]:
        yield from self.pages(
            "POST", f"users/me/dataTypes/{data_type}/dataPoints:dailyRollUp", json=body
        )
