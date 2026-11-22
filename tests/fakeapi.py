"""A tiny stateful stand-in for the Google Health API, served through httpx.MockTransport.

It honours the same windowing the real API does (civil-date ranges in dailyRollUp bodies,
AIP-160 filters on list/reconcile, RFC 3339 ranges on rollUp) so sync windows are exercised."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import httpx

from pulse.client import HealthClient, RetryPolicy

_RANGE = re.compile(r'>= "([^"]+)" AND .* < "([^"]+)"')


def _d(c: dict) -> date:
    return date(c["date"]["year"], c["date"]["month"], c["date"]["day"])


def _civil(d: date) -> dict:
    return {"date": {"year": d.year, "month": d.month, "day": d.day}}


def _ts(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class FakeApi:
    steps: dict[date, int] = field(default_factory=dict)
    resting_hr: dict[date, int] = field(default_factory=dict)
    hr: dict[datetime, float] = field(default_factory=dict)  # minute start (UTC) → bpm
    sleep: dict[str, tuple[datetime, datetime]] = field(default_factory=dict)  # id → (start, end)
    fail_types: set[str] = field(default_factory=set)
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    def handler(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        m = re.search(r"dataTypes/([^/]+)/dataPoints(:\w+)?$", path)
        if not m:
            return httpx.Response(404, json={"error": {"status": "NOT_FOUND", "message": path}})
        dtype, action = m.group(1), (m.group(2) or "")[1:] or "list"
        detail = req.url.params.get("filter", "") or req.content.decode()
        self.calls.append((dtype, action, detail))
        if dtype in self.fail_types:
            return httpx.Response(
                400, json={"error": {"status": "INVALID_ARGUMENT", "message": "nope"}}
            )
        if action == "dailyRollUp":
            body = json.loads(req.content)
            lo, hi = _d(body["range"]["start"]), _d(body["range"]["end"])
            pts = []
            if dtype == "steps":
                pts = [
                    {"civilStartTime": _civil(d), "steps": {"countSum": str(v)}}
                    for d, v in sorted(self.steps.items())
                    if lo <= d < hi
                ]
            return httpx.Response(200, json={"rollupDataPoints": pts})
        if action == "rollUp":
            body = json.loads(req.content)
            lo = datetime.fromisoformat(body["range"]["startTime"].replace("Z", "+00:00"))
            hi = datetime.fromisoformat(body["range"]["endTime"].replace("Z", "+00:00"))
            pts = []
            if dtype == "heart-rate":
                pts = [
                    {
                        "startTime": _ts(t),
                        "endTime": _ts(t + timedelta(minutes=1)),
                        "heartRate": {
                            "beatsPerMinuteAvg": v,
                            "beatsPerMinuteMin": int(v) - 1,
                            "beatsPerMinuteMax": int(v) + 1,
                        },
                    }
                    for t, v in sorted(self.hr.items())
                    if lo <= t < hi
                ]
            return httpx.Response(200, json={"rollupDataPoints": pts})
        # list / reconcile
        rng = _RANGE.search(req.url.params.get("filter", ""))
        lo_s, hi_s = rng.groups() if rng else ("0000-01-01", "9999-12-31")
        lo_d, hi_d = date.fromisoformat(lo_s[:10]), date.fromisoformat(hi_s[:10])
        points: list[dict] = []
        if dtype == "daily-resting-heart-rate":
            points = [
                {"dailyRestingHeartRate": {"date": _civil(d)["date"], "beatsPerMinute": str(v)}}
                for d, v in sorted(self.resting_hr.items())
                if lo_d <= d < hi_d
            ]
        elif dtype == "sleep" and action == "reconcile":
            for sid, (start, end) in sorted(self.sleep.items()):
                wake = (end - timedelta(hours=5)).date()
                if lo_d <= wake < hi_d:
                    points.append(_sleep_point(sid, start, end))
        return httpx.Response(200, json={"dataPoints": points})

    def client(self, token=lambda _force: "tok") -> HealthClient:
        return HealthClient(
            token,
            http=httpx.Client(
                base_url="https://health.example/v4/", transport=httpx.MockTransport(self.handler)
            ),
            min_interval=0,
            retry=RetryPolicy(max_attempts=1),
            sleep=lambda _s: None,
        )


def _sleep_point(sid: str, start: datetime, end: datetime) -> dict:
    mid = start + (end - start) / 2
    minutes = int((end - start).total_seconds() // 60)
    iv = {
        "startTime": _ts(start),
        "startUtcOffset": "-18000s",
        "endTime": _ts(end),
        "endUtcOffset": "-18000s",
    }
    return {
        "dataPointName": f"users/u/dataTypes/sleep/dataPoints/{sid}",
        "sleep": {
            "interval": iv,
            "type": "STAGES",
            "metadata": {"mainSleep": True},
            "stages": [
                {"startTime": _ts(start), "endTime": _ts(mid), "type": "LIGHT"},
                {"startTime": _ts(mid), "endTime": _ts(end), "type": "DEEP"},
            ],
            "summary": {
                "minutesInSleepPeriod": str(minutes),
                "minutesAsleep": str(minutes - 10),
                "minutesAwake": "10",
                "stagesSummary": [
                    {"type": "LIGHT", "minutes": str(minutes // 2)},
                    {"type": "DEEP", "minutes": str(minutes // 2 - 10)},
                ],
            },
        },
    }
