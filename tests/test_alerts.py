"""Tests for the shared alerting layer (service, sinks, builders, wiring)."""

from __future__ import annotations

import pytest

from app.alerts import AlertKind, AlertService, equity_alert
from app.alerts.models import Alert, AlertSeverity
from app.alerts.sinks import MemorySink
from app.config import Settings
from app.equities.analysis import evaluate_universe
from app.equities.models import WatchState
from app.equities.sources.fixtures import FixturesEquitySource
from app.equities.tracker import EquityTracker
from app.equities.watchlist import Watchlist
from app.market import build_market_provider
from app.market.fixtures import fixtures_context


def _alert(n: int = 0, score: float = 80.0) -> Alert:
    return Alert(
        id=f"EQUITY_TRIGGERED:T{n}",
        kind=AlertKind.EQUITY_TRIGGERED,
        severity=AlertSeverity.ACTIONABLE,
        title=f"Buy zone: T{n}",
        message="test",
        symbol=f"T{n}",
        score=score,
    )


@pytest.mark.asyncio
async def test_memory_sink_keeps_recent_newest_first():
    sink = MemorySink(capacity=3)
    for i in range(5):
        await sink.send(_alert(i))
    recent = sink.recent()
    assert [a.symbol for a in recent] == ["T4", "T3", "T2"]  # ring buffer, newest first


@pytest.mark.asyncio
async def test_service_dispatch_and_recent():
    svc = AlertService(Settings(alerts_enabled=True))
    await svc.dispatch([_alert(1), _alert(2)])
    recent = svc.recent()
    assert {a.symbol for a in recent} == {"T1", "T2"}
    assert "memory" in svc.sink_names and "log" in svc.sink_names


@pytest.mark.asyncio
async def test_service_disabled_sends_nothing():
    svc = AlertService(Settings(alerts_enabled=False))
    await svc.dispatch([_alert(1)])
    assert svc.recent() == []


@pytest.mark.asyncio
async def test_min_score_filters_low_scores():
    svc = AlertService(Settings(alert_min_score=70))
    await svc.dispatch([_alert(1, score=50), _alert(2, score=90)])
    assert [a.symbol for a in svc.recent()] == ["T2"]


def test_equity_alert_builder():
    settings = Settings()
    ctx = fixtures_context(settings)
    src = FixturesEquitySource()
    import asyncio

    snaps = asyncio.run(src.fetch_universe())
    ops = evaluate_universe(snaps, ctx, settings, src.sector_multiples())
    triggered = next(o for o in ops if o.state is WatchState.TRIGGERED)
    alert = equity_alert(triggered)
    assert alert.kind is AlertKind.EQUITY_TRIGGERED
    assert alert.symbol == triggered.ticker
    assert alert.id == f"EQUITY_TRIGGERED:{triggered.ticker}"
    assert triggered.ticker in alert.title


@pytest.mark.asyncio
async def test_tracker_emits_alert_on_first_trigger(tmp_path):
    settings = Settings(equity_source="fixtures", market_source="fixtures")
    svc = AlertService(settings)
    tracker = EquityTracker(
        FixturesEquitySource(),
        settings,
        build_market_provider(settings),
        Watchlist(tmp_path / "wl.json"),
        svc,
    )
    await tracker._refresh_market(force=True)
    await tracker.refresh_once()
    triggered_alerts = [a for a in svc.recent() if a.kind is AlertKind.EQUITY_TRIGGERED]
    assert len(triggered_alerts) >= 1
    # Second cycle: nothing newly triggered, so no new alerts are added.
    before = len(svc.recent())
    await tracker.refresh_once()
    assert len(svc.recent()) == before


def test_alerts_api_smoke(monkeypatch, tmp_path):
    monkeypatch.setenv("MARKET_SOURCE", "fixtures")
    monkeypatch.setenv("OFFER_SOURCE", "mock")
    monkeypatch.setenv("EQUITY_SOURCE", "fixtures")
    monkeypatch.setenv("EQUITY_WATCHLIST_PATH", str(tmp_path / "wl.json"))
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()
    try:
        with TestClient(app) as client:
            assert client.get("/alerts/health").json()["status"] == "ok"
            alerts = client.get("/alerts").json()
            assert isinstance(alerts, list)
            # Equity tracker triggers at least one name on startup.
            assert any(a["kind"] == "EQUITY_TRIGGERED" for a in alerts)
    finally:
        get_settings.cache_clear()
