"""Tests for the equities (stocks + FIIs) two-stage watcher."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.equities.analysis import (
    compute_technical,
    evaluate_universe,
    stock_quality,
    value_asset,
)
from app.equities.models import AssetKind, Fundamentals, WatchState
from app.equities.sources.fixtures import FixturesEquitySource
from app.equities.tracker import EquityTracker
from app.equities.watchlist import Watchlist
from app.market import build_market_provider
from app.market.fixtures import fixtures_context


@pytest.fixture
def equity_settings() -> Settings:
    return Settings(equity_source="fixtures", market_source="fixtures")


def _evaluate(settings: Settings):
    import asyncio

    ctx = fixtures_context(settings)
    src = FixturesEquitySource()
    snaps = asyncio.run(src.fetch_universe())
    ops = evaluate_universe(snaps, ctx, settings, src.sector_multiples())
    return {o.ticker: o for o in ops}


def test_universe_has_stocks_and_fiis():
    import asyncio

    snaps = asyncio.run(FixturesEquitySource().fetch_universe())
    kinds = {s.stock.asset_kind for s in snaps}
    assert AssetKind.STOCK in kinds and AssetKind.FII in kinds
    assert all(len(s.stock.price_history) > 200 for s in snaps)


def test_cheap_quality_names_trigger(equity_settings):
    ops = _evaluate(equity_settings)
    # Deeply discounted high-quality names with oversold timing fire.
    assert ops["PETR4"].state is WatchState.TRIGGERED
    assert ops["BBAS3"].state is WatchState.TRIGGERED
    assert ops["PETR4"].is_opportunity is True


def test_good_company_not_cheap_waits(equity_settings):
    ops = _evaluate(equity_settings)
    # High quality but insufficient margin of safety -> WATCH, not triggered.
    assert ops["ITUB4"].state is WatchState.WATCH
    assert ops["ITUB4"].is_opportunity is False


def test_cheap_but_extended_is_armed_not_triggered(equity_settings):
    ops = _evaluate(equity_settings)
    cmig = ops["CMIG4"]
    # Valuation buy condition met, but the timing signal is weak.
    assert cmig.state is WatchState.ARMED
    assert cmig.valuation.margin_of_safety >= cmig.valuation.required_margin_of_safety
    assert cmig.technical.entry_score < equity_settings.equity_entry_min


def test_negative_earnings_rejected(equity_settings):
    ops = _evaluate(equity_settings)
    assert ops["MGLU3"].state is WatchState.REJECTED
    assert ops["MGLU3"].opportunity_score == 0.0
    assert any("Red flag" in r or "Negative" in r for r in ops["MGLU3"].reasons)


def test_fii_can_trigger(equity_settings):
    ops = _evaluate(equity_settings)
    assert ops["KNRI11"].stock.asset_kind is AssetKind.FII
    assert ops["KNRI11"].state is WatchState.TRIGGERED


def test_valuation_ensemble_and_mos_sign(equity_settings):
    ctx = fixtures_context(equity_settings)
    f = Fundamentals(
        eps=9.0, bvps=30.0, dps=5.5, fcf_per_share=11.0, roe=28,
        earnings_cagr_5y=5, payout=0.6,
    )
    val = value_asset(
        AssetKind.STOCK, price=38.0, sector="Petróleo", context=ctx,
        settings=equity_settings, peer_multiples={"Petróleo": 6.0},
        fundamentals=f,
    )
    # Several independent methods agree on a range above the price.
    assert len(val.method_breakdown) >= 3
    assert val.fair_value_low <= val.fair_value_mid <= val.fair_value_high
    assert val.margin_of_safety > 0  # trading below fair value
    assert val.buy_zone_price < val.fair_value_mid


def test_required_mos_tightens_with_selic(equity_settings):
    low = fixtures_context(equity_settings)
    low.selic_annual = 8.0
    high = fixtures_context(equity_settings)
    high.selic_annual = 14.0
    f = Fundamentals(eps=5.0, bvps=20.0, dps=2.0, fcf_per_share=4.0, payout=0.4)
    v_low = value_asset(
        AssetKind.STOCK, 30.0, "Bancos", low, equity_settings, {"Bancos": 8.0}, f
    )
    v_high = value_asset(
        AssetKind.STOCK, 30.0, "Bancos", high, equity_settings, {"Bancos": 8.0}, f
    )
    assert v_high.required_margin_of_safety > v_low.required_margin_of_safety


def test_technical_rsi_direction():
    falling = [100 - i for i in range(60)]  # monotonic decline
    rising = [40 + i for i in range(60)]
    t_down = compute_technical(falling[-1], falling)
    t_up = compute_technical(rising[-1], rising)
    assert t_down.rsi_14 is not None and t_down.rsi_14 < 30
    assert t_up.rsi_14 is not None and t_up.rsi_14 > 70
    assert t_down.entry_score > t_up.entry_score


def test_quality_rewards_strong_business():
    strong = Fundamentals(
        roe=25, roic=22, net_margin=22, net_debt_ebitda=0.3, current_ratio=1.8,
        earnings_consistency=1.0, earnings_cagr_5y=12, shares_cagr_5y=-1,
    )
    weak = Fundamentals(
        roe=4, roic=2, net_margin=1, net_debt_ebitda=4.0, current_ratio=0.7,
        earnings_consistency=0.2, earnings_cagr_5y=-5, shares_cagr_5y=8,
    )
    assert stock_quality(strong)[0] > stock_quality(weak)[0]


def test_watchlist_detects_fresh_trigger(tmp_path):
    wl = Watchlist(tmp_path / "wl.json")
    first = wl.reconcile({"AAAA": WatchState.ARMED, "BBBB": WatchState.TRIGGERED})
    assert first == ["BBBB"]
    # Re-reconciling the same states yields no *new* triggers.
    second = wl.reconcile({"AAAA": WatchState.ARMED, "BBBB": WatchState.TRIGGERED})
    assert second == []
    # A fresh transition into TRIGGERED is detected, and it persists on reload.
    third = wl.reconcile({"AAAA": WatchState.TRIGGERED})
    assert third == ["AAAA"]
    assert Watchlist(tmp_path / "wl.json").previous("AAAA") is WatchState.TRIGGERED


@pytest.mark.asyncio
async def test_tracker_refresh_populates_state(tmp_path, equity_settings):
    tracker = EquityTracker(
        FixturesEquitySource(),
        equity_settings,
        build_market_provider(equity_settings),
        Watchlist(tmp_path / "wl.json"),
    )
    await tracker._refresh_market(force=True)
    state = await tracker.refresh_once()
    assert state.refresh_count == 1
    assert state.error is None
    assert len(state.opportunities) > 0
    assert state.state_counts.get(WatchState.TRIGGERED.value, 0) >= 1
    # First cycle reports the freshly triggered names.
    assert len(state.newly_triggered) >= 1
    # Second cycle: same states, so nothing is *newly* triggered.
    second = await tracker.refresh_once()
    assert second.newly_triggered == []


def test_api_endpoints_smoke(monkeypatch, tmp_path):
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
            assert client.get("/equities/health").status_code == 200
            opps = client.get("/equities/opportunities").json()
            assert isinstance(opps, list) and len(opps) > 0
            triggered = client.get("/equities/triggered").json()
            assert all(o["state"] == "TRIGGERED" for o in triggered)
            wl = client.get("/equities/watchlist").json()
            assert all(o["state"] != "REJECTED" for o in wl)
            one = client.get("/equities/PETR4").json()
            assert one["ticker"] == "PETR4"
            assert "valuation" in one and "technical" in one
            assert client.get("/equities/ZZZZ9").status_code == 404
            assert client.post("/equities/refresh").status_code == 200
    finally:
        get_settings.cache_clear()
