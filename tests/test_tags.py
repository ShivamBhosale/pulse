"""Tags & notes: migration defaults, CRUD, journal, tag effects (maths + API), summary rule."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from pulse import derived as D
from pulse import journal
from pulse import summary as M
from pulse.models import DailyMetric
from tests.test_api import TODAY, app_env, client  # noqa: F401 - pytest fixtures

API = "/api/v1"


# ---- maths -----------------------------------------------------------------------------------


def test_default_lag() -> None:
    assert D.default_lag("hrv_rmssd", "evening") == 1
    assert D.default_lag("steps", "evening") == 0
    assert D.default_lag("hrv_rmssd", "day") == 0


def test_split_by_tag_with_lag_and_exclusions() -> None:
    sun, mon, tue = date(2026, 11, 22), date(2026, 11, 23), date(2026, 11, 24)
    values = {sun: 40.0, mon: 30.0, tue: 45.0, tue + timedelta(1): 41.0}
    tagged, untagged = D.split_by_tag(values, {sun}, lag=1, exclude_days={tue})
    assert tagged == {mon: 30.0}  # Sunday-evening tag → Monday's overnight value
    assert untagged == {sun: 40.0, tue: 45.0}  # Wed excluded (sick on Tue, lag 1)


def test_permutation_is_deterministic_and_sane() -> None:
    a = [30.0, 31, 29, 32, 30, 28]
    b = [42.0, 41, 43, 40, 44, 42, 41, 43, 40, 42]
    p1, p2 = D.permutation_p(a, b), D.permutation_p(a, b)
    assert p1 == p2 and p1 is not None and p1 < 0.01
    same = D.permutation_p([1.0, 2, 3, 4, 5], [1.0, 2, 3, 4, 5])
    assert same is not None and same > 0.5
    assert D.permutation_p([1.0], [1.0, 2.0]) is None


def test_tag_effect_verdicts() -> None:
    clear = D.tag_effect([30.0, 31, 29, 32, 30, 28], [42.0, 41, 43, 40, 44, 42, 41, 43])
    assert clear.verdict == "clear"
    assert clear.diff == pytest.approx(30 - 42)
    assert clear.diff_in_iqr is not None and clear.diff_in_iqr < -1
    none = D.tag_effect([40.0, 42, 41, 43, 39], [41.0, 40, 42, 43, 39, 41, 42])
    assert none.verdict == "none"
    few = D.tag_effect([30.0, 31], [42.0, 41, 43, 40])
    assert few.verdict == "too_few" and few.p is None and few.diff == pytest.approx(-11)


def test_slugify() -> None:
    assert journal.slugify("Late Caffeine!") == "late-caffeine"
    assert journal.slugify("Café au lait") == "cafe-au-lait"
    assert journal.slugify("  ") == ""


# ---- API -------------------------------------------------------------------------------------


def test_migration_seeds_default_tags(client):  # noqa: F811
    tags = client.get(f"{API}/tags").json()
    keys = [t["key"] for t in tags]
    assert keys[:4] == ["alcohol", "late-meal", "late-caffeine", "screen-late"]
    assert {"sick", "travel", "stress", "rest-day"} <= set(keys)
    assert all(t["uses"] == 0 and not t["archived"] for t in tags)
    assert next(t for t in tags if t["key"] == "alcohol")["kind"] == "evening"


def test_tag_crud(client):  # noqa: F811
    r = client.post(f"{API}/tags", json={"label": "Sauna", "kind": "evening"})
    assert r.status_code == 201 and r.json()["key"] == "sauna"
    assert client.post(f"{API}/tags", json={"label": "sauna"}).status_code == 409
    assert client.post(f"{API}/tags", json={"label": "!!!"}).status_code == 422
    assert client.post(f"{API}/tags", json={"label": "x", "kind": "noon"}).status_code == 422
    r = client.patch(f"{API}/tags/sauna", json={"label": "Sauna session", "kind": "day"})
    assert r.json()["label"] == "Sauna session" and r.json()["kind"] == "day"
    assert client.patch(f"{API}/tags/sauna", json={"archived": True}).json()["archived"]
    assert client.patch(f"{API}/tags/nope", json={"archived": True}).status_code == 404


def test_journal_round_trip(client):  # noqa: F811
    day = (TODAY - timedelta(days=1)).isoformat()
    assert client.get(f"{API}/journal/{day}").json() == {"date": day, "tags": [], "note": ""}
    r = client.put(
        f"{API}/journal/{day}", json={"tags": ["stress", "alcohol", "alcohol"], "note": " Wedding "}
    )
    assert r.status_code == 200
    assert r.json() == {"date": day, "tags": ["alcohol", "stress"], "note": "Wedding"}  # sorted
    r = client.put(f"{API}/journal/{day}", json={"tags": ["travel"], "note": ""})
    assert r.json() == {"date": day, "tags": ["travel"], "note": ""}  # replaced, note removed
    tags = {t["key"]: t for t in client.get(f"{API}/tags").json()}
    assert tags["travel"]["uses"] == 1 and tags["travel"]["last_used"] == day
    assert tags["alcohol"]["uses"] == 0


def test_journal_validation(client):  # noqa: F811
    today = TODAY.isoformat()
    tomorrow = (TODAY + timedelta(days=1)).isoformat()
    assert client.put(f"{API}/journal/{tomorrow}", json={"tags": []}).status_code == 422
    assert client.put(f"{API}/journal/{today}", json={"tags": ["nope"]}).status_code == 422
    assert client.put(f"{API}/journal/{today}", json={"note": "x" * 2000}).status_code == 200
    assert client.put(f"{API}/journal/{today}", json={"note": "x" * 2001}).status_code == 422


def test_archived_tag_rules(client):  # noqa: F811
    day = TODAY.isoformat()
    client.put(f"{API}/journal/{day}", json={"tags": ["stress"]})
    client.patch(f"{API}/tags/stress", json={"archived": True})
    # Keeping an already-applied archived tag is fine; adding one to another day is not.
    assert client.put(f"{API}/journal/{day}", json={"tags": ["stress"]}).status_code == 200
    other = (TODAY - timedelta(days=2)).isoformat()
    assert client.put(f"{API}/journal/{other}", json={"tags": ["stress"]}).status_code == 422
    assert client.get(f"{API}/journal/{day}").json()["tags"] == ["stress"]  # history kept


def test_journal_range(client):  # noqa: F811
    a, b = TODAY - timedelta(days=3), TODAY - timedelta(days=1)
    client.put(f"{API}/journal/{a}", json={"tags": ["sick"]})
    client.put(f"{API}/journal/{b}", json={"note": "Long flight"})
    body = client.get(f"{API}/journal?from={a - timedelta(days=5)}&to={TODAY}").json()
    assert [d["date"] for d in body["days"]] == [a.isoformat(), b.isoformat()]
    assert body["days"][1]["note"] == "Long flight"


def test_journal_needs_passcode(app_env, client):  # noqa: F811
    client.put(f"{API}/settings/passcode", json={"new": "4321"})
    client.cookies.clear()
    assert client.get(f"{API}/tags").status_code == 401
    assert client.put(f"{API}/journal/{TODAY}", json={"tags": []}).status_code == 401


def test_tag_effect_api(app_env, client):  # noqa: F811
    _, sessions, _ = app_env
    with sessions() as s:
        for i in range(60):
            d = TODAY - timedelta(days=i)
            s.merge(DailyMetric(civil_date=d, metric="hrv_rmssd", value=42.0 + i % 3, unit="ms"))
        s.commit()
    # Alcohol on 6 evenings → the following mornings get a low HRV.
    for i in (10, 17, 24, 31, 38, 45):
        tagged = TODAY - timedelta(days=i)
        client.put(f"{API}/journal/{tagged}", json={"tags": ["alcohol"]})
    with sessions() as s:
        for i in (10, 17, 24, 31, 38, 45):
            s.merge(
                DailyMetric(
                    civil_date=TODAY - timedelta(days=i - 1),
                    metric="hrv_rmssd",
                    value=30.0,
                    unit="ms",
                )
            )
        s.commit()
    frm = (TODAY - timedelta(days=59)).isoformat()
    e = client.get(f"{API}/explore/tag-effect?tag=alcohol&metric=hrv_rmssd&from={frm}").json()
    assert e["lag"] == 1 and e["n_tagged"] == 6
    assert e["median_tagged"] == 30 and e["verdict"] == "clear"
    assert e["verdict_text"] == "Clear difference" and len(e["tagged"]) == 6
    same_day = client.get(
        f"{API}/explore/tag-effect?tag=alcohol&metric=hrv_rmssd&from={frm}&lag=0"
    ).json()
    assert same_day["lag"] == 0 and same_day["verdict"] != "clear"
    overview = client.get(f"{API}/explore/tag-effects?metric=hrv_rmssd&from={frm}").json()
    assert overview["effects"][0]["tag"] == "alcohol"
    assert overview["effects"][0]["tagged"] == []  # overview omits points
    assert client.get(f"{API}/explore/tag-effect?tag=nope&metric=hrv_rmssd").status_code == 404
    assert client.get(f"{API}/explore/tag-effect?tag=alcohol&metric=x").status_code == 404
    assert client.get(f"{API}/explore/tag-effect?tag=alcohol&metric=steps&lag=2").status_code == 422


def test_summary_mentions_last_nights_tags(client):  # noqa: F811
    client.put(f"{API}/journal/{TODAY - timedelta(days=1)}", json={"tags": ["alcohol", "stress"]})
    texts = [s["text"] for s in client.get(f"{API}/summary").json()["sentences"]]
    assert "Tagged last night: Alcohol." in texts  # day tags (Stress) aren't "last night"


def test_rule_tags_wording() -> None:
    f = M.DayFacts(date=TODAY, is_today=False, evening_tags_before=("Alcohol", "Late meal"))
    assert [s.text for s in M.build_summary(f).sentences] == [
        "Tagged the evening before: Alcohol, Late meal."
    ]


def test_put_journal_unit(app_env):  # noqa: F811
    _, sessions, _ = app_env
    now = datetime(2026, 11, 21, 12, tzinfo=UTC)
    with sessions() as s:
        out = journal.put_journal(s, TODAY, ["rest-day"], "easy", now)
        s.commit()
        assert out.tags == ["rest-day"] and out.note == "easy"
        with pytest.raises(journal.JournalError):
            journal.put_journal(s, TODAY, [], "x" * 2001, now)
