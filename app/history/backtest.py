"""A small mean-reversion backtest over recorded history.

Answers "if I had bought whenever this was cheap vs its norm, how would it have
gone?" — a sanity check on the cheapness signal, not a trading system. Uses only
data strictly *before* each decision point (no look-ahead).
"""

from __future__ import annotations

import statistics

from pydantic import BaseModel

from app.history.store import MetricPoint

_MIN_PRIOR = 5


class BacktestResult(BaseModel):
    metric: str
    key: str
    horizon: int
    entry_z: float
    trades: int = 0
    wins: int = 0
    avg_return: float | None = None
    win_rate: float | None = None


def backtest_mean_reversion(
    metric: str,
    key: str,
    points: list[MetricPoint],
    horizon: int = 5,
    entry_z: float = 1.0,
    direction: str = "below",
) -> BacktestResult:
    """Buy when the value is ``entry_z`` std from its prior mean; hold ``horizon``.

    ``direction="below"`` enters when the value is cheap (below its norm) and
    measures the forward return — the natural setup for a price metric.
    """
    values = [p.value for p in sorted(points, key=lambda p: p.ts)]
    returns: list[float] = []
    for i in range(len(values)):
        prior = values[:i]
        if len(prior) < _MIN_PRIOR or i + horizon >= len(values):
            continue
        mean = statistics.fmean(prior)
        std = statistics.pstdev(prior)
        if std == 0:
            continue
        z = (values[i] - mean) / std
        entered = z <= -entry_z if direction == "below" else z >= entry_z
        if not entered or values[i] == 0:
            continue
        returns.append((values[i + horizon] - values[i]) / values[i])

    if not returns:
        return BacktestResult(metric=metric, key=key, horizon=horizon, entry_z=entry_z)
    wins = sum(1 for r in returns if r > 0)
    return BacktestResult(
        metric=metric,
        key=key,
        horizon=horizon,
        entry_z=entry_z,
        trades=len(returns),
        wins=wins,
        avg_return=round(statistics.fmean(returns), 6),
        win_rate=round(wins / len(returns), 4),
    )
