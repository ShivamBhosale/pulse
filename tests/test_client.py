import httpx
import pytest

from pulse.client import (
    AccountNotLinked,
    HealthClient,
    InvalidArgument,
    NotFound,
    RateLimited,
    RetryPolicy,
    ServerError,
)


def make(handler, tokens=None, sleeps=None):
    tokens = tokens if tokens is not None else []

    state = {"token": "stale"}

    def provider(force: bool) -> str:
        tokens.append(force)
        if force:
            state["token"] = "fresh"
        return state["token"]

    return HealthClient(
        provider,
        http=httpx.Client(
            base_url="https://health.example/v4/", transport=httpx.MockTransport(handler)
        ),
        min_interval=0,
        retry=RetryPolicy(max_attempts=3, base_delay=1, max_delay=10),
        sleep=(sleeps.append if sleeps is not None else (lambda _s: None)),
    )


def test_pagination_follows_next_page_token(load_fixture):
    calls: list[httpx.Request] = []

    def handler(req):
        calls.append(req)
        if "pageToken" not in req.url.params:
            return httpx.Response(200, json={"dataPoints": [{"a": 1}], "nextPageToken": "t2"})
        assert req.url.params["pageToken"] == "t2"
        assert req.url.params["filter"] == "x"
        return httpx.Response(200, json={"dataPoints": [{"a": 2}]})

    pages = list(make(handler).list_points("steps", filter="x", page_size=10))
    assert [p["dataPoints"][0]["a"] for p in pages] == [1, 2]
    assert calls[0].url.path == "/v4/users/me/dataTypes/steps/dataPoints"
    assert calls[0].headers["Authorization"] == "Bearer stale"


def test_max_pages_caps_requests():
    def handler(req):
        return httpx.Response(200, json={"dataPoints": [], "nextPageToken": "again"})

    assert len(list(make(handler).list_points("heart-rate", max_pages=3))) == 3


def test_post_pagination_puts_token_in_body():
    bodies = []

    def handler(req):
        import json

        body = json.loads(req.content)
        bodies.append(body)
        if "pageToken" in body:
            return httpx.Response(200, json={"rollupDataPoints": []})
        return httpx.Response(200, json={"rollupDataPoints": [], "nextPageToken": "n"})

    list(make(handler).daily_roll_up("steps", {"range": {}, "windowSizeDays": 1}))
    assert bodies[1]["pageToken"] == "n" and bodies[1]["windowSizeDays"] == 1
    assert "pageToken" not in bodies[0]


def test_account_not_linked_is_typed(load_fixture):
    err = load_fixture("error_not_linked.json")
    client = make(lambda req: httpx.Response(400, json=err))
    with pytest.raises(AccountNotLinked) as exc:
        client.get_identity()
    assert exc.value.code == "FAILED_PRECONDITION"


@pytest.mark.parametrize(("status", "cls"), [(400, InvalidArgument), (404, NotFound)])
def test_error_mapping(status, cls):
    client = make(
        lambda req: httpx.Response(status, json={"error": {"status": "X", "message": "m"}})
    )
    with pytest.raises(cls):
        client.get_settings()


def test_non_json_error_body():
    client = make(lambda req: httpx.Response(404, text="<html>nope</html>"))
    with pytest.raises(NotFound):
        client.get_profile()


def test_401_refreshes_token_once_then_succeeds():
    tokens: list[bool] = []

    def handler(req):
        if req.headers["Authorization"] == "Bearer stale":
            return httpx.Response(401, json={"error": {"status": "UNAUTHENTICATED"}})
        return httpx.Response(200, json={"ok": True})

    assert make(handler, tokens=tokens).get_identity() == {"ok": True}
    assert tokens == [False, True, False]


def test_retries_429_respecting_retry_after():
    sleeps: list[float] = []
    n = 0

    def handler(req):
        nonlocal n
        n += 1
        if n == 1:
            return httpx.Response(429, headers={"Retry-After": "7"}, json={"error": {}})
        return httpx.Response(200, json={"ok": 1})

    assert make(handler, sleeps=sleeps).get_identity() == {"ok": 1}
    assert sleeps == [7.0]


def test_gives_up_after_max_attempts_on_5xx():
    sleeps: list[float] = []
    client = make(lambda req: httpx.Response(503, json={"error": {}}), sleeps=sleeps)
    with pytest.raises(ServerError):
        client.get_identity()
    assert len(sleeps) == 2
    assert all(0 <= s <= 10 for s in sleeps)


def test_429_exhausted_raises_rate_limited():
    client = make(lambda req: httpx.Response(429, json={"error": {}}))
    with pytest.raises(RateLimited):
        client.get_identity()


def test_throttle_waits_min_interval():
    sleeps: list[float] = []
    now = [100.0]
    client = HealthClient(
        lambda _f: "t",
        http=httpx.Client(
            base_url="https://h/v4/",
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
        ),
        min_interval=0.5,
        sleep=sleeps.append,
        clock=lambda: now[0],
    )
    client.get_identity()
    now[0] += 0.2
    client.get_identity()
    assert sleeps == [pytest.approx(0.3)]


def test_transport_errors_are_retried_then_typed():
    from pulse.client import TransportFailure

    sleeps: list[float] = []
    n = 0

    def flaky(req):
        nonlocal n
        n += 1
        if n == 1:
            raise httpx.ReadTimeout("slow", request=req)
        return httpx.Response(200, json={"ok": 1})

    assert make(flaky, sleeps=sleeps).get_identity() == {"ok": 1}
    assert len(sleeps) == 1

    def dead(req):
        raise httpx.ConnectError("down", request=req)

    with pytest.raises(TransportFailure):
        make(dead).get_identity()
