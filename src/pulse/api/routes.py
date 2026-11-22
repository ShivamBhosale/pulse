"""/api/v1 routes."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from pulse import __version__, prefs, queries, security
from pulse.api import schemas as S
from pulse.metrics import CATALOG
from pulse.sync.engine import AUTH_ROW, BACKFILL_ROW

router = APIRouter(prefix="/api/v1")


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.sessions() as session:
        yield session


DB = Annotated[Session, Depends(get_session)]


def _now(request: Request) -> datetime:
    now: datetime = request.app.state.now()
    return now


def _today(request: Request) -> date:
    return _now(request).astimezone(request.app.state.zone).date()


@router.get("/health", response_model=S.Health, name="get_health", tags=["meta"])
def health() -> S.Health:
    return S.Health(status="ok", version=__version__)


@router.get("/status", response_model=S.Status, name="get_status", tags=["meta"])
def get_status(request: Request, db: DB) -> S.Status:
    states = queries.sync_states(db)
    auth_row = states.pop(AUTH_ROW, None)
    backfill_row = states.pop(BACKFILL_ROW, None)
    token_present = request.app.state.settings.token_path.exists()
    auth = S.AuthStatus(
        ok=token_present and (auth_row is None or auth_row.last_error is None),
        error=None if token_present else "Not authorized: run `pulse auth`.",
        checked_at=None,
    )
    if auth_row is not None:
        auth.error = auth.error or auth_row.last_error
        auth.checked_at = auth_row.last_error_at if auth_row.last_error else auth_row.last_success
    streams = [
        S.StreamStatus(
            stream=s.stream,
            high_water_mark=s.high_water_mark,
            last_success=s.last_success,
            last_error=s.last_error,
            last_error_at=s.last_error_at,
        )
        for s in sorted(states.values(), key=lambda x: x.stream)
    ]
    successes = [s.last_success for s in states.values() if s.last_success]
    service = request.app.state.sync_service
    return S.Status(
        auth=auth,
        last_sync=max(successes) if successes else None,
        next_run=service.next_run if service else None,
        syncing=bool(service and service.running),
        streams=streams,
        backfill=S.BackfillStatus(
            floor=backfill_row.backfill_floor if backfill_row else None,
            cursor=backfill_row.backfill_cursor if backfill_row else None,
            last_success=backfill_row.last_success if backfill_row else None,
            last_error=backfill_row.last_error if backfill_row else None,
        ),
        metrics=queries.metrics_available(db),
    )


@router.get("/today", response_model=S.Today, name="get_today", tags=["dashboard"])
def get_today(request: Request, db: DB) -> S.Today:
    zone = request.app.state.zone
    now = _now(request)
    d = now.astimezone(zone).date()
    goals = prefs.goals(db)
    tiles = [
        queries.readiness_placeholder(d),
        queries.daily_tile(
            db,
            "sleep_main_min",
            d,
            fallback_days=1,
            label="Last night's sleep",
            goal=goals["sleep_min"],
        ),
        queries.daily_tile(db, "resting_hr", d, fallback_days=2),
        queries.daily_tile(db, "hrv_rmssd", d, fallback_days=2, label="HRV"),
        queries.steps_so_far_tile(db, d, now, zone, goals["steps"]),
        queries.azm_so_far_tile(db, d, now, zone, goals["azm_weekly"]),
    ]
    states = queries.sync_states(db)
    successes = [
        s.last_success for k, s in states.items() if s.last_success and not k.startswith("_")
    ]
    return S.Today(
        date=d,
        generated_at=now,
        last_synced=max(successes) if successes else None,
        goals=S.Goals(**goals),
        tiles=tiles,
        heart_rate=queries.intraday_heart_rate(db, d, zone),
        steps_curve=queries.steps_curve(db, d, now, zone),
    )


@router.get("/metrics/{metric}", response_model=S.MetricSeries, name="get_metric", tags=["data"])
def get_metric(
    request: Request,
    db: DB,
    metric: str,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    granularity: S.Granularity = "day",
) -> S.MetricSeries:
    m = CATALOG.get(metric)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown metric {metric!r}")
    end = to or _today(request)
    start = from_ or end - timedelta(days=29)
    if start > end:
        raise HTTPException(422, "from must be <= to")
    return queries.metric_series(db, m, start, end, granularity)


@router.get(
    "/intraday/heart-rate",
    response_model=S.IntradayHeartRate,
    name="get_intraday_heart_rate",
    tags=["data"],
)
def get_intraday_heart_rate(
    request: Request, db: DB, date: date | None = None
) -> S.IntradayHeartRate:
    return queries.intraday_heart_rate(db, date or _today(request), request.app.state.zone)


@router.get("/sleep", response_model=S.SleepNight, name="get_sleep", tags=["sleep"])
def get_sleep(request: Request, db: DB, date: date | None = None) -> S.SleepNight:
    d = date or queries.latest_sleep_date(db) or _today(request)
    return queries.sleep_night(db, d)


@router.get("/sleep/trend", response_model=S.SleepTrend, name="get_sleep_trend", tags=["sleep"])
def get_sleep_trend(
    request: Request,
    db: DB,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
) -> S.SleepTrend:
    end = to or _today(request)
    start = from_ or end - timedelta(days=29)
    if start > end:
        raise HTTPException(422, "from must be <= to")
    return queries.sleep_trend(db, start, end)


@router.post(
    "/sync",
    response_model=S.SyncAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    name="trigger_sync",
    tags=["meta"],
)
def trigger_sync(request: Request) -> S.SyncAccepted:
    service = request.app.state.sync_service
    if service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "scheduler disabled")
    return S.SyncAccepted(status="started" if service.trigger() else "already_running")


# ---- passcode session ----------------------------------------------------------------------


def _passcode_hash(db: Session) -> str | None:
    value = prefs.get(db, "passcode_hash")
    return value if isinstance(value, str) else None


def session_valid(request: Request, stored: str) -> bool:
    signer: security.SessionSigner = request.app.state.signer
    return signer.verify(request.cookies.get(security.COOKIE_NAME), security.fingerprint(stored))


@router.get("/session", response_model=S.SessionState, name="get_session_state", tags=["session"])
def get_session_state(request: Request, db: DB) -> S.SessionState:
    stored = _passcode_hash(db)
    return S.SessionState(
        passcode_required=stored is not None,
        authenticated=stored is None or session_valid(request, stored),
    )


@router.post(
    "/session",
    status_code=status.HTTP_204_NO_CONTENT,
    name="unlock",
    tags=["session"],
    responses={401: {"description": "Wrong passcode"}, 429: {"description": "Too many attempts"}},
)
def unlock(request: Request, response: Response, body: S.PasscodeIn, db: DB) -> Response:
    stored = _passcode_hash(db)
    if stored is None:
        response.status_code = status.HTTP_204_NO_CONTENT
        return response
    limiter: security.AttemptLimiter = request.app.state.limiter
    key = request.client.host if request.client else "unknown"
    if not limiter.allowed(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many attempts; wait a minute")
    if not security.verify_passcode(body.passcode, stored):
        limiter.fail(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong passcode")
    limiter.reset(key)
    token = request.app.state.signer.issue(security.fingerprint(stored))
    response.set_cookie(
        security.COOKIE_NAME,
        token,
        max_age=security.SESSION_MAX_AGE_S,
        httponly=True,
        samesite="strict",
        path="/",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT, name="lock", tags=["session"])
def lock(response: Response) -> Response:
    response.delete_cookie(security.COOKIE_NAME, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
