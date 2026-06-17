"""Tests for the time-series history store + norm comparison."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.history import (
    HistoryStore,
    MetricPoint,
    NullHistoryStore,
    build_history_store,
    cheapness_vs_norm,
    metrics_from_equities,
)


def test_store_record_and_query_roundtrip(tmp_path):
    store = HistoryStore(str(tmp_path / "h.jsonl"))
    now = datetime.now(timezone.utc)
    store.record_many([
        MetricPoint(metric="bond.net_ytm", key="x", value=12.0, ts=now - timedelta(days=2)),
        MetricPoint(metric="bond.net_ytm", key="x", value=13.0, ts=now),
        MetricPoint(metric="bond.net_ytm", key="y", value=9.0, ts=now),
    ])
    all_x = store.query("bond.net_ytm", "x")
    assert [p.value for p in all_x] == [12.0, 13.0]
    # since filter
    recent = store.query("bond.net_ytm", "x", since=now - timedelta(days=1))
    assert [p.value for p in recent] == [13.0]
    # key filter
    assert len(store.query("bond.net_ytm")) == 3


def test_null_store_is_noop():
    store = NullHistoryStore()
    store.record_many([MetricPoint(metric="m", key="k", value=1.0)])
    assert store.query("m", "k") == []
    assert isinstance(build_history_store(Settings(history_path="")), NullHistoryStore)


def test_cheapness_vs_norm_stats():
    pts = [MetricPoint(metric="bond.net_ytm", key="x", value=v) for v in (10, 10, 10, 13)]
    stat = cheapness_vs_norm("bond.net_ytm", "x", pts)
    assert stat.samples == 4
    assert stat.latest == 13.0
    assert stat.mean == 10.75
    assert stat.maximum == 13.0
    assert stat.pct_vs_mean is not None and stat.pct_vs_mean > 0  # above its norm
    assert stat.zscore is not None and stat.zscore > 0


def test_cheapness_handles_empty():
    stat = cheapness_vs_norm("m", "k", [])
    assert stat.samples == 0 and stat.latest is None


def test_metrics_from_equities_shape():
    from app.equities.analysis import evaluate_universe
    from app.equities.sources.fixtures import FixturesEquitySource
    from app.market.fixtures import fixtures_context
    import asyncio

    settings = Settings()
    snaps = asyncio.run(FixturesEquitySource().fetch_universe())
    ops = evaluate_universe(snaps, fixtures_context(settings), settings,
                            FixturesEquitySource().sector_multiples())
    points = metrics_from_equities(ops)
    metrics = {p.metric for p in points}
    assert "equity.price" in metrics and "equity.score" in metrics
