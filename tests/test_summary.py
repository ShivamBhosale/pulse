"""Rule-based daily summary: each rule, ranking, formatting, tense, and the API."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from pulse import summary as M
from tests.test_api import TODAY, app_env, client  # noqa: F401 - pytest fixtures

D = date(2026, 11, 22)  # Sunday
GOALS = {"sleep_min": 480, "steps": 10_000, "azm_weekly": 150}


def facts(**kw) -> M.DayFacts:
    base = M.DayFacts(date=D, is_today=True, goals=GOALS)
    return replace(base, **kw)


def texts(f: M.DayFacts) -> list[str]:
    return [s.text for s in M.build_summary(f).sentences]


# ---- formatting ----------------------------------------------------------------------------


def test_formatting_helpers() -> None:
    assert M.fmt_duration(301) == "5h 01m"
    assert M.fmt_duration(480) == "8h"
    assert M.fmt_duration(45) == "45m"
    assert M.fmt_clock(-20) == "23:40"
    assert M.fmt_clock(1500) == "01:00"
    assert M.fmt_temp_delta(0.6, "metric") == "0.6 °C"
    assert M.fmt_temp_delta(-0.6, "imperial") == "1.1 °F"
    assert M.wrap_clock(23 * 60) == -60


# ---- rules -----------------------------------------------------------------------------------


def test_empty_facts_say_nothing_and_never_none() -> None:
    s = M.build_summary(facts())
    assert s.sentences == ()
    assert "None" not in s.headline and "readiness" in s.headline.lower()


def test_readiness_with_driver() -> None:
    f = facts(
        readiness=M.Reading(66, median=58, status="mild"),
        readiness_parts=(
            M.ReadinessPart("hrv", 95, 0.35, 54, 42),
            M.ReadinessPart("sleep", 63, 0.25, 301, 480),
            M.ReadinessPart("rhr", 50, 0.25, 71, 71),
        ),
    )
    s = M.build_summary(f)
    assert s.headline == "Readiness 66: a bit above your usual"
    assert s.sentences[0].text == "Readiness is 66, above your usual 58, mostly from HRV."
    assert s.sentences[0].tone == "good"


def test_readiness_in_range_has_no_driver() -> None:
    f = facts(readiness=M.Reading(60, median=58, status="in_range"))
    assert texts(f) == ["Readiness is 60, in your usual range."]
    assert M.build_summary(f).headline == "Readiness 60: a typical day for you"


def test_sleep_short_and_met() -> None:
    short = facts(sleep_main_min=301, sleep_debt_min=772)
    s = M.build_summary(short).sentences[0]
    assert (
        s.text == "You slept 5h 01m, 2h 59m short of your 8h goal; 7-night sleep debt is 12h 52m."
    )
    assert s.tone == "attention"
    met = M.build_summary(facts(sleep_main_min=490, sleep_debt_min=20)).sentences[0]
    assert met.text == "You slept 8h 10m, meeting your 8h goal." and met.tone == "good"


def test_bedtime_shift_across_midnight() -> None:
    # Usual 23:40 (-20); last night 01:00 (+60) → 1h 20m later.
    f = facts(bedtime_min=60, bedtime_usual_min=-20)
    assert texts(f) == ["Bedtime was 1h 20m later than your usual 23:40."]
    # An evening bedtime recorded as +1410 (same day 23:30) is wrapped, not "23h later".
    assert texts(facts(bedtime_min=1410, bedtime_usual_min=-20)) == []


def test_vitals_notable_or_repeated_mild_only() -> None:
    notable = facts(vitals={"resting_hr": M.Reading(77, median=71, status="notable")})
    assert texts(notable) == ["Resting heart rate is 77 bpm, well above your usual 71."]
    assert M.build_summary(notable).sentences[0].tone == "attention"
    one_mild = facts(vitals={"resting_hr": M.Reading(74, 71, "mild", "in_range")})
    assert texts(one_mild) == []
    two_mild = facts(vitals={"hrv_rmssd": M.Reading(52.6, 42.2, "mild", "mild")})
    assert texts(two_mild) == ["HRV is 52.6 ms, above your usual 42.2 for a second day."]
    assert M.build_summary(two_mild).sentences[0].tone == "good"
    tiny = facts(vitals={"spo2_avg": M.Reading(96.0, 97.0, "notable")})
    assert texts(tiny) == []  # below the 1.5-point floor


def test_skin_temperature_in_units() -> None:
    f = facts(units="imperial", vitals={"skin_temp_delta": M.Reading(1.2)})
    assert texts(f) == ["Skin temperature is 2.2 °F above your baseline."]
    assert texts(facts(vitals={"skin_temp_delta": M.Reading(0.2)})) == []


def test_weekly_azm() -> None:
    sunday = facts(azm_week=99, days_left_in_week=0)
    assert texts(sunday) == ["99 of 150 active zone minutes this week: 51 to go today."]
    friday = facts(azm_week=99, days_left_in_week=2)
    assert texts(friday) == [
        "99 of 150 active zone minutes this week: 51 to go in 3 days (~17 a day)."
    ]
    done = facts(azm_week=160, days_left_in_week=3)
    assert texts(done) == ["Weekly active zone minutes: 160 of 150, goal met ✓."]


def test_steps_today_and_past() -> None:
    low = facts(steps=M.Reading(573, median=3900, status="notable"))
    assert texts(low) == ["573 steps so far, below your usual 3,900 by this time."]
    assert texts(facts(steps=M.Reading(4000, 3900, "in_range"))) == []
    past = facts(is_today=False, steps=M.Reading(27902))
    assert texts(past) == ["You walked 27,902 steps, above your 10,000 goal ✓."]


def test_streak_at_stake_only_today_and_unmet() -> None:
    st = (M.StreakFact("steps", 4, False, 10_000),)
    assert texts(facts(streaks=st)) == ["Step streak: 4 days. Reach 10,000 today to make it 5."]
    assert texts(facts(streaks=(M.StreakFact("steps", 4, True, 10_000),))) == []
    assert texts(facts(is_today=False, streaks=st)) == []
    sleep = (M.StreakFact("sleep", 3, True, 480),)
    assert texts(facts(streaks=sleep)) == ["3 nights in a row at your sleep goal."]


def test_records() -> None:
    rec = (M.RecordFact("steps", "most steps in a day", 31737, "count", D - timedelta(days=1)),)
    assert texts(facts(records=rec)) == ["New record yesterday: most steps in a day (31,737)."]
    sleep = (M.RecordFact("sleep_main_min", "longest main sleep", 635, "min", D),)
    assert texts(facts(records=sleep)) == ["New record today: longest main sleep (10h 35m)."]


def test_load_ratio() -> None:
    assert texts(facts(load_ratio=1.6)) == ["Training load is 1.6× your 4-week norm."]
    assert texts(facts(load_ratio=1.1)) == []
    assert texts(facts(load_ratio=0.5)) == [
        "A lighter week than usual: load 0.5× your 4-week norm."
    ]


def test_past_tense() -> None:
    f = facts(
        is_today=False,
        readiness=M.Reading(74, 58, "mild"),
        vitals={"resting_hr": M.Reading(80, 71, "notable")},
        sleep_main_min=400,
        sleep_debt_min=300,
    )
    joined = " ".join(texts(f))
    assert "Readiness was 74" in joined and "Resting heart rate was 80" in joined
    assert "sleep debt was" in joined and " is " not in joined


def test_ranking_caps_and_orders() -> None:
    f = facts(
        readiness=M.Reading(40, 58, "notable"),
        sleep_main_min=300,
        vitals={"resting_hr": M.Reading(80, 71, "notable")},
        azm_week=20,
        days_left_in_week=4,
        load_ratio=1.8,
        streaks=(M.StreakFact("steps", 5, False, 10_000),),
        records=(M.RecordFact("hrv_rmssd", "highest HRV", 60, "ms", D),),
    )
    s = M.build_summary(f).sentences
    assert len(s) == M.MAX_SENTENCES
    assert [x.priority for x in s] == sorted((x.priority for x in s), reverse=True)
    assert s[0].metrics == ("readiness",)


def test_deterministic() -> None:
    f = facts(readiness=M.Reading(66, 58, "mild"), sleep_main_min=301, azm_week=99)
    assert M.build_summary(f) == M.build_summary(f)


# ---- API -------------------------------------------------------------------------------------


def test_summary_api(client):  # noqa: F811
    body = client.get("/api/v1/summary").json()
    assert body["date"] == TODAY.isoformat()
    assert isinstance(body["headline"], str) and body["headline"]
    for s in body["sentences"]:
        assert s["tone"] in {"good", "neutral", "attention"}
        assert "None" not in s["text"] and "nan" not in s["text"].lower()
    past = client.get(f"/api/v1/summary?date={TODAY - timedelta(days=1)}").json()
    assert past["date"] == (TODAY - timedelta(days=1)).isoformat()
    assert client.get(f"/api/v1/summary?date={TODAY + timedelta(days=1)}").status_code == 422
    today = client.get("/api/v1/today").json()
    assert today["summary"]["headline"] == body["headline"]


@pytest.mark.parametrize("units", ["metric", "imperial"])
def test_summary_api_units(client, units):  # noqa: F811
    client.put("/api/v1/settings", json={"units": units})
    assert client.get("/api/v1/summary").status_code == 200
