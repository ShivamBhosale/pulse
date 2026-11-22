"""Pure derived-metric maths: baselines, status, medians. No I/O."""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

Status = Literal["in_range", "mild", "notable", "none"]
BASELINE_DAYS = 28
MIN_BASELINE_POINTS = 7


@dataclass(frozen=True)
class Baseline:
    median: float
    q1: float
    q3: float
    n: int

    @property
    def iqr(self) -> float:
        return self.q3 - self.q1


def baseline(
    values: Sequence[float | None], min_points: int = MIN_BASELINE_POINTS
) -> Baseline | None:
    """Median and quartiles of the window (caller excludes the current day)."""
    vals = sorted(v for v in values if v is not None)
    if len(vals) < min_points:
        return None
    q1, med, q3 = statistics.quantiles(vals, n=4, method="inclusive")
    return Baseline(median=med, q1=q1, q3=q3, n=len(vals))


def status(value: float | None, b: Baseline | None) -> Status:
    """in_range inside the IQR; notable beyond 1.5 x IQR from the median; mild otherwise."""
    if value is None or b is None:
        return "none"
    if b.q1 <= value <= b.q3:
        return "in_range"
    if abs(value - b.median) > 1.5 * b.iqr:
        return "notable"
    return "mild"


def delta(value: float | None, b: Baseline | None) -> float | None:
    if value is None or b is None:
        return None
    return value - b.median


def cumulative(slots: Sequence[float]) -> list[float]:
    out: list[float] = []
    total = 0.0
    for v in slots:
        total += v
        out.append(total)
    return out


def median_curve(curves: Sequence[Sequence[float]]) -> list[float]:
    """Point-wise median of equal-length curves (e.g. cumulative steps per 15-min slot)."""
    if not curves:
        return []
    width = len(curves[0])
    return [statistics.median(c[i] for c in curves) for i in range(width)]


def stdev(values: Sequence[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return statistics.pstdev(vals) if len(vals) >= 2 else None
