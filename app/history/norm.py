"""Compare the latest observation to its recent norm.

Powers "cheaper than its 30-day norm": for a yield metric a *higher* latest value
than the mean is cheap; for a price metric a *lower* latest value is cheap. The
caller decides direction; this returns the raw stats + a z-score.
"""

from __future__ import annotations

import statistics

from pydantic import BaseModel

from app.history.store import MetricPoint


class NormStat(BaseModel):
    metric: str
    key: str
    samples: int
    latest: float | None = None
    mean: float | None = None
    stdev: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    pct_vs_mean: float | None = None  # (latest-mean)/mean
    zscore: float | None = None


def cheapness_vs_norm(metric: str, key: str, points: list[MetricPoint]) -> NormStat:
    """Summarise a metric's recent distribution and where the latest sits."""
    values = [p.value for p in sorted(points, key=lambda p: p.ts)]
    if not values:
        return NormStat(metric=metric, key=key, samples=0)
    latest = values[-1]
    mean = statistics.fmean(values)
    stdev = statistics.pstdev(values) if len(values) > 1 else 0.0
    pct = (latest - mean) / mean if mean else None
    z = (latest - mean) / stdev if stdev else None
    return NormStat(
        metric=metric,
        key=key,
        samples=len(values),
        latest=round(latest, 6),
        mean=round(mean, 6),
        stdev=round(stdev, 6),
        minimum=round(min(values), 6),
        maximum=round(max(values), 6),
        pct_vs_mean=round(pct, 6) if pct is not None else None,
        zscore=round(z, 4) if z is not None else None,
    )
