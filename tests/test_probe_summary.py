from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import httpx

from pulse.client import HealthClient
from pulse.datatypes import REGISTRY, CivilWindow
from pulse.probe import Status, describe_value, point_time, probe_type, summarize


def test_interval_summary_first_last_and_nanoseconds(load_fixture):
    cov = summarize(REGISTRY["steps"], [load_fixture("steps_list.json")])
    assert cov.status is Status.OK
    assert cov.points == 2
    assert cov.first == datetime(2026, 11, 15, 22, 30, 0, 123456, tzinfo=UTC)
    assert cov.last == datetime(2026, 11, 20, 14, 5, tzinfo=UTC)
    assert cov.samples[0] == "count=112"


def test_daily_summary_uses_civil_dates(load_fixture):
    cov = summarize(REGISTRY["daily-resting-heart-rate"], [load_fixture("daily_rhr_list.json")])
    assert (cov.first, cov.last) == (date(2026, 11, 14), date(2026, 11, 20))
    assert cov.samples == ["beatsPerMinute=54", "beatsPerMinute=57"]


def test_sleep_reconcile_summary(load_fixture):
    cov = summarize(REGISTRY["sleep"], [load_fixture("sleep_reconcile.json")])
    assert cov.points == 1
    assert "summary.minutesAsleep=418" in cov.samples[0] or cov.samples[0].endswith("…")
    assert "stages" not in cov.samples[0].split("=")[0]


def test_empty_and_missing_pages():
    assert summarize(REGISTRY["weight"], []).status is Status.EMPTY
    assert summarize(REGISTRY["weight"], [{}]).status is Status.EMPTY
    assert summarize(REGISTRY["weight"], [{"dataPoints": []}]).status is Status.EMPTY


def test_point_time_variants():
    assert point_time({"sampleTime": {"physicalTime": "2026-01-01T00:00:00Z"}}) == datetime(
        2026, 1, 1, tzinfo=UTC
    )
    assert point_time({"date": {"year": 2026, "month": 2, "day": 3}}) == date(2026, 2, 3)
    assert point_time({"value": 1}) is None


def test_describe_value_truncates():
    text = describe_value({"a": "x" * 100})
    assert len(text) == 60 and text.endswith("…")


def _client(handler):
    return HealthClient(
        lambda _force: "tok",
        http=httpx.Client(
            base_url="https://health.example/v4/", transport=httpx.MockTransport(handler)
        ),
        min_interval=0,
        sleep=lambda _s: None,
    )


def test_probe_falls_back_when_filter_rejected(load_fixture):
    seen: list[str] = []
    rhr = load_fixture("daily_rhr_list.json")

    def handler(req: httpx.Request) -> httpx.Response:
        flt = req.url.params["filter"]
        seen.append(flt)
        if flt.startswith("daily_resting_heart_rate."):
            return httpx.Response(
                400, json={"error": {"status": "INVALID_ARGUMENT", "message": "bad"}}
            )
        return httpx.Response(200, json=rhr)

    window = CivilWindow(date(2026, 11, 15), date(2026, 11, 22), ZoneInfo("America/Toronto"))
    cov, record = probe_type(_client(handler), REGISTRY["daily-resting-heart-rate"], window, 1)
    assert cov.status is Status.OK
    assert cov.filter_used is not None and cov.filter_used.startswith("dailyRestingHeartRate.date")
    assert len(seen) == 2
    assert record["method"] == "list"


def test_probe_reports_permission_error_without_fallback():
    calls = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED", "message": "no"}})

    window = CivilWindow(date(2026, 11, 15), date(2026, 11, 22), ZoneInfo("America/Toronto"))
    cov, _ = probe_type(_client(handler), REGISTRY["weight"], window, 1)
    assert cov.status is Status.ERROR
    assert cov.error == "403 PERMISSION_DENIED"
    assert calls == 1


def test_probe_uses_reconcile_for_sleep_and_flags_truncation(load_fixture):
    paths: list[str] = []
    page = {**load_fixture("sleep_reconcile.json"), "nextPageToken": "more"}

    def handler(req: httpx.Request) -> httpx.Response:
        paths.append(req.url.path)
        assert req.url.params["pageSize"] == "25"
        return httpx.Response(200, json=page)

    window = CivilWindow(date(2026, 11, 15), date(2026, 11, 22), ZoneInfo("America/Toronto"))
    cov, _ = probe_type(_client(handler), REGISTRY["sleep"], window, max_pages=2)
    assert paths == ["/v4/users/me/dataTypes/sleep/dataPoints:reconcile"] * 2
    assert cov.truncated and cov.points == 2


def test_run_probe_writes_private_raw_and_scrubbed_fixtures(tmp_path, load_fixture):
    import json

    from pulse.probe import FixtureWriter, run_probe
    from pulse.scrub import Scrubber

    ident = load_fixture("identity.json")
    rhr = load_fixture("daily_rhr_list.json")

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path.endswith("/identity"):
            return httpx.Response(200, json=ident)
        if path.endswith("/profile"):
            return httpx.Response(200, json={"name": "users/me/profile", "age": 33})
        if path.endswith("/settings"):
            return httpx.Response(200, json={"timeZone": "America/Toronto"})
        if "daily-resting-heart-rate" in path:
            return httpx.Response(200, json=rhr)
        return httpx.Response(200, json={})

    writer = FixtureWriter(tmp_path / "fx", Scrubber(b"salt"))
    types = [REGISTRY["daily-resting-heart-rate"], REGISTRY["weight"]]
    account, results = run_probe(_client(handler), types, ZoneInfo("America/Toronto"), 7, 1, writer)
    assert account["identity"]["healthUserId"] == "111111256096816351"
    assert [r.status for r in results] == [Status.OK, Status.EMPTY]

    scrubbed = "".join(p.read_text() for p in (tmp_path / "fx" / "scrubbed").iterdir())
    for secret in ("111111256096816351", "A1B2C3", "4417", "abc123"):
        assert secret not in scrubbed
    raw_files = list((tmp_path / "fx" / "raw").iterdir())
    assert {p.name for p in raw_files} >= {"identity.json", "coverage.json"}
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in raw_files)
    coverage = json.loads((tmp_path / "fx" / "scrubbed" / "coverage.json").read_text())
    assert coverage["results"][0]["filter"].startswith("daily_resting_heart_rate.date")
