"""Rule-based daily summary: facts → small template rules → ranked sentences.

Pure and deterministic (no I/O, no randomness, no AI): the same facts always give the same
text. ``pulse.queries.day_facts`` gathers the facts from the database. Wording stays factual:
it compares you with your own baselines and goals and never diagnoses.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

Tone = Literal["good", "neutral", "attention"]
Units = Literal["metric", "imperial"]
MAX_SENTENCES = 4


# ---- facts --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Reading:
    """One daily value compared with its 28-day baseline (median/IQR, excluding the day)."""

    value: float | None
    median: float | None = None
    status: str = "none"  # in_range | mild | notable | none
    prev_status: str = "none"  # the same comparison for the day before


@dataclass(frozen=True)
class ReadinessPart:
    key: str  # hrv | rhr | sleep | strain
    score: float | None
    weight: float
    value: float | None
    reference: float | None


@dataclass(frozen=True)
class StreakFact:
    key: str  # steps | sleep | azm
    current: int
    met_now: bool  # today's (or this week's) goal already met
    goal: float


@dataclass(frozen=True)
class RecordFact:
    key: str
    label: str  # "most steps in a day"
    value: float
    unit: str
    when: date


@dataclass(frozen=True)
class DayFacts:
    date: date
    is_today: bool
    units: Units = "metric"
    goals: dict[str, int] = field(default_factory=dict)
    readiness: Reading = Reading(None)
    readiness_parts: tuple[ReadinessPart, ...] = ()
    sleep_main_min: float | None = None
    sleep_debt_min: float | None = None
    bedtime_min: float | None = None  # minutes from wake-day midnight (negative = evening)
    bedtime_usual_min: float | None = None  # 14-night median, same scale
    vitals: dict[str, Reading] = field(default_factory=dict)  # resting_hr, hrv_rmssd, …
    steps: Reading = Reading(None)  # "so far" baseline when is_today
    azm_week: float | None = None
    days_left_in_week: int = 0  # after this day
    load_ratio: float | None = None
    streaks: tuple[StreakFact, ...] = ()
    records: tuple[RecordFact, ...] = ()


# ---- output -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Sentence:
    text: str
    tone: Tone
    priority: int
    metrics: tuple[str, ...] = ()


@dataclass(frozen=True)
class Summary:
    date: date
    headline: str
    sentences: tuple[Sentence, ...]


# ---- formatting (mirrors frontend/src/lib/format.ts + units.ts) -----------------------------


def fmt_num(v: float, decimals: int = 0) -> str:
    return f"{v:,.{decimals}f}"


def fmt_duration(minutes: float) -> str:
    m = round(abs(minutes))
    h, rest = divmod(m, 60)
    if h and not rest:
        return f"{h}h"
    return f"{h}h {rest:02d}m" if h else f"{rest}m"


def fmt_clock(minutes: float) -> str:
    m = round(minutes) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def wrap_clock(minutes: float) -> float:
    """Same scale as derived.clock_wrap: -6h…18h around midnight."""
    return ((minutes + 360) % 1440) - 360


def fmt_temp_delta(c: float, units: Units) -> str:
    v = c * 1.8 if units == "imperial" else c
    return f"{abs(v):.1f} °{'F' if units == 'imperial' else 'C'}"


VITAL_META: dict[str, tuple[str, str, int, bool, float]] = {
    # key: (label, unit, decimals, higher_is_better, smallest difference worth mentioning)
    "resting_hr": ("Resting heart rate", " bpm", 0, False, 2.0),
    "hrv_rmssd": ("HRV", " ms", 1, True, 3.0),
    "spo2_avg": ("Overnight blood oxygen", "%", 1, True, 1.5),
}
PART_LABEL = {"hrv": "HRV", "rhr": "resting heart rate", "sleep": "sleep", "strain": "strain"}


def _tense(f: DayFacts, present: str, past: str) -> str:
    return present if f.is_today else past


# ---- rules --------------------------------------------------------------------------------


def rule_readiness(f: DayFacts) -> Sentence | None:
    r = f.readiness
    if r.value is None:
        return None
    is_ = _tense(f, "is", "was")
    if r.median is None:
        text = f"Readiness {is_} {fmt_num(r.value)}."
        tone: Tone = "neutral"
    else:
        diff = r.value - r.median
        where = (
            "in your usual range"
            if r.status == "in_range"
            else ("above" if diff > 0 else "below") + f" your usual {fmt_num(r.median)}"
        )
        text = f"Readiness {is_} {fmt_num(r.value)}, {where}"
        tone = (
            "neutral" if r.status in ("in_range", "none") else "good" if diff > 0 else "attention"
        )
        parts = [p for p in f.readiness_parts if p.score is not None and p.weight > 0]
        if parts and r.status != "in_range":
            # The part that moved the score most from a neutral 50, in the same direction.
            driver = max(parts, key=lambda p: (p.score - 50) * p.weight * (1 if diff > 0 else -1))  # type: ignore[operator]
            if driver.score is not None and (driver.score - 50) * diff > 0:
                text += f", mostly from {PART_LABEL[driver.key]}"
        text += "."
    return Sentence(text, tone, 90, ("readiness",))


def rule_sleep(f: DayFacts) -> Sentence | None:
    s, goal = f.sleep_main_min, f.goals.get("sleep_min")
    if s is None or not goal:
        return None
    short = goal - s
    if short > 15:
        text = (
            f"You slept {fmt_duration(s)}, {fmt_duration(short)} short of your "
            f"{fmt_duration(goal)} goal"
        )
        tone: Tone = "attention" if short >= 60 else "neutral"
        prio = 80 if short >= 60 else 55
    else:
        text = f"You slept {fmt_duration(s)}, meeting your {fmt_duration(goal)} goal"
        tone, prio = "good", 50
    if f.sleep_debt_min is not None and f.sleep_debt_min >= 60:
        text += f"; 7-night sleep debt {_tense(f, 'is', 'was')} {fmt_duration(f.sleep_debt_min)}"
    return Sentence(text + ".", tone, prio, ("sleep_main_min", "sleep_debt_min"))


def rule_bedtime(f: DayFacts) -> Sentence | None:
    if f.bedtime_min is None or f.bedtime_usual_min is None:
        return None
    shift = wrap_clock(f.bedtime_min) - f.bedtime_usual_min
    if abs(shift) < 45:
        return None
    when = "later" if shift > 0 else "earlier"
    return Sentence(
        f"Bedtime was {fmt_duration(shift)} {when} than your usual "
        f"{fmt_clock(f.bedtime_usual_min)}.",
        "attention" if shift >= 90 else "neutral",
        55,
        ("bedtime_min",),
    )


def rule_vitals(f: DayFacts) -> list[Sentence]:
    out = []
    for key, (label, unit, dec, higher_better, min_diff) in VITAL_META.items():
        r = f.vitals.get(key)
        if r is None or r.value is None or r.median is None:
            continue
        if abs(r.value - r.median) < min_diff:
            continue
        repeated_mild = r.status == "mild" and r.prev_status in ("mild", "notable")
        if r.status != "notable" and not repeated_mild:
            continue
        up = r.value > r.median
        degree = "well " if r.status == "notable" else ""
        streak = " for a second day" if repeated_mild else ""
        good = up == higher_better
        out.append(
            Sentence(
                f"{label} {_tense(f, 'is', 'was')} {fmt_num(r.value, dec)}{unit}, {degree}"
                f"{'above' if up else 'below'} your usual {fmt_num(r.median, dec)}{streak}.",
                "good" if good else "attention",
                85 if r.status == "notable" else 60,
                (key,),
            )
        )
    t = f.vitals.get("skin_temp_delta")
    if t is not None and t.value is not None and abs(t.value) >= 0.5:
        out.append(
            Sentence(
                f"Skin temperature {_tense(f, 'is', 'was')} {fmt_temp_delta(t.value, f.units)} "
                f"{'above' if t.value > 0 else 'below'} your baseline.",
                "attention" if abs(t.value) >= 1.0 else "neutral",
                70 if abs(t.value) >= 1.0 else 45,
                ("skin_temp_delta",),
            )
        )
    return out


def rule_azm_week(f: DayFacts) -> Sentence | None:
    goal = f.goals.get("azm_weekly")
    if f.azm_week is None or not goal:
        return None
    done = f.azm_week
    if done >= goal:
        return Sentence(
            f"Weekly active zone minutes: {fmt_num(done)} of {goal}, goal met ✓.",
            "good",
            45,
            ("azm",),
        )
    left = goal - done
    if f.is_today and f.days_left_in_week >= 0:
        days = f.days_left_in_week + 1  # today counts
        per_day = math.ceil(left / days)
        tail = (
            f": {fmt_num(left)} to go today"
            if days == 1
            else f": {fmt_num(left)} to go in {days} days (~{per_day} a day)"
        )
        prio = 70 if days <= 2 else 45
    else:
        tail = f" by the end of {'the week' if f.days_left_in_week == 0 else 'that day'}"
        prio = 40
    return Sentence(
        f"{fmt_num(done)} of {goal} active zone minutes this week{tail}.", "neutral", prio, ("azm",)
    )


def rule_steps(f: DayFacts) -> Sentence | None:
    s, goal = f.steps, f.goals.get("steps", 0)
    if s.value is None:
        return None
    if not f.is_today:
        met = goal and s.value >= goal
        return Sentence(
            f"You walked {fmt_num(s.value)} steps"
            + (f", above your {fmt_num(goal)} goal ✓." if met else f" (goal {fmt_num(goal)})."),
            "good" if met else "neutral",
            42,
            ("steps",),
        )
    if s.median is None or s.status in ("in_range", "none"):
        return None
    above = s.value > s.median
    return Sentence(
        f"{fmt_num(s.value)} steps so far, {'above' if above else 'below'} your usual "
        f"{fmt_num(s.median)} by this time.",
        "good" if above else "neutral",
        40,
        ("steps",),
    )


def rule_streaks(f: DayFacts) -> list[Sentence]:
    out = []
    for st in f.streaks:
        if st.key == "steps" and f.is_today and st.current >= 2 and not st.met_now:
            out.append(
                Sentence(
                    f"Step streak: {st.current} days. Reach {fmt_num(st.goal)} today to make it "
                    f"{st.current + 1}.",
                    "neutral",
                    65,
                    ("steps",),
                )
            )
        elif st.key == "sleep" and st.met_now and st.current >= 3:
            out.append(
                Sentence(
                    f"{st.current} nights in a row at your sleep goal.",
                    "good",
                    50,
                    ("sleep_main_min",),
                )
            )
        elif st.key == "azm" and st.met_now and st.current >= 2:
            out.append(
                Sentence(
                    f"{st.current} weeks in a row at your active-minutes goal.",
                    "good",
                    48,
                    ("azm",),
                )
            )
    return out


def rule_records(f: DayFacts) -> list[Sentence]:
    out = []
    for r in f.records:
        when = (
            "today"
            if r.when == f.date and f.is_today
            else ("yesterday" if (f.date - r.when).days == 1 else "on this day")
        )
        value = (
            fmt_duration(r.value)
            if r.unit == "min" and "sleep" in r.key
            else (
                f"{fmt_num(r.value, 1 if r.unit in ('ms', 'km') else 0)}"
                + ("" if r.unit in ("count", "steps", "score") else f" {r.unit}")
            )
        )
        out.append(Sentence(f"New record {when}: {r.label} ({value}).", "good", 75, (r.key,)))
    return out


def rule_load(f: DayFacts) -> Sentence | None:
    lr = f.load_ratio
    if lr is None or 0.7 <= lr <= 1.5:
        return None
    if lr > 1.5:
        return Sentence(
            f"Training load {_tense(f, 'is', 'was')} {lr:.1f}× your 4-week norm.",
            "attention",
            52,
            ("load_ratio",),
        )
    return Sentence(
        f"A lighter week than usual: load {lr:.1f}× your 4-week norm.",
        "neutral",
        35,
        ("load_ratio",),
    )


RULES: tuple[Callable[[DayFacts], Sentence | list[Sentence] | None], ...] = (
    rule_readiness,
    rule_sleep,
    rule_bedtime,
    rule_vitals,
    rule_azm_week,
    rule_steps,
    rule_streaks,
    rule_records,
    rule_load,
)


def headline(f: DayFacts) -> str:
    r = f.readiness
    if r.value is None:
        return (
            "Not enough data for a readiness score yet"
            if f.is_today
            else "No readiness score for this day"
        )
    if r.median is None or r.status == "in_range":
        return f"Readiness {fmt_num(r.value)}: a typical day for you"
    above = r.value > r.median
    if r.status == "notable":
        return f"Readiness {fmt_num(r.value)}: well {'above' if above else 'below'} your usual"
    return f"Readiness {fmt_num(r.value)}: a bit {'above' if above else 'below'} your usual"


def build_summary(f: DayFacts, limit: int = MAX_SENTENCES) -> Summary:
    found: list[Sentence] = []
    for rule in RULES:
        out = rule(f)
        if out is None:
            continue
        found.extend(out if isinstance(out, list) else [out])
    # Stable ranking: priority, then rule order (Python's sort is stable).
    ranked = sorted(found, key=lambda s: -s.priority)[:limit]
    return Summary(date=f.date, headline=headline(f), sentences=tuple(ranked))
