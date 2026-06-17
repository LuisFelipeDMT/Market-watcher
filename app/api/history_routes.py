"""History endpoints: raw series + 'cheaper than its norm' comparison."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query, Request

from app.history import (
    BacktestResult,
    MetricPoint,
    NormStat,
    backtest_mean_reversion,
    cheapness_vs_norm,
)

router = APIRouter(prefix="/history", tags=["history"])


@router.get("/series", response_model=list[MetricPoint])
async def series(
    request: Request,
    metric: str = Query(..., description="e.g. bond.net_ytm, equity.price"),
    key: str | None = Query(None, description="offer id / ticker"),
    since_hours: float = Query(720.0, ge=0.0),
) -> list[MetricPoint]:
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    return request.app.state.history.query(metric, key, since)


@router.get("/norm", response_model=NormStat)
async def norm(
    request: Request,
    metric: str = Query(...),
    key: str = Query(...),
    window_days: float | None = Query(None, ge=0.0),
) -> NormStat:
    """Where the latest value sits vs its recent distribution."""
    days = window_days if window_days is not None else request.app.state.settings.history_window_days
    since = datetime.now(timezone.utc) - timedelta(days=days)
    points = request.app.state.history.query(metric, key, since)
    return cheapness_vs_norm(metric, key, points)


@router.get("/backtest", response_model=BacktestResult)
async def backtest(
    request: Request,
    metric: str = Query(...),
    key: str = Query(...),
    horizon: int = Query(5, ge=1),
    entry_z: float = Query(1.0, gt=0.0),
    direction: str = Query("below"),
) -> BacktestResult:
    """Mean-reversion sanity check on the cheapness signal over recorded history."""
    points = request.app.state.history.query(metric, key)
    return backtest_mean_reversion(metric, key, points, horizon, entry_z, direction)
