"""Tests for marcação-a-mercado → sell / exit signals."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from app.analysis.marktomarket import mark_holding, mark_portfolio
from app.collector.sources import MockCollector
from app.config import Settings
from app.market.fixtures import fixtures_context
from app.models import Holding, IndexType, ProductType


def _ctx(settings):
    return fixtures_context(settings)


def test_holding_without_entry_details_is_skipped():
    settings = Settings()
    h = Holding(issuer="X", conglomerate="X", product_type=ProductType.CDB, amount=1000)
    assert mark_holding(h, _ctx(settings), settings) is None


def test_appreciated_prefixado_flags_consider_sell():
    settings = Settings()
    h = Holding(
        issuer="Banco BTG Pactual", conglomerate="BTG", product_type=ProductType.CDB,
        amount=180_000, fgc_eligible=True, index_type=IndexType.PRE, entry_rate=15.0,
        maturity=date.today() + timedelta(days=365 * 3), cost_amount=170_000, rating="AAA",
    )
    mark = mark_holding(h, _ctx(settings), settings)
    assert mark is not None
    assert mark.unrealized_pct > 0  # yields fell since entry → price up
    assert mark.signal == "CONSIDER_SELL"
    assert mark.mark_value > mark.cost_amount


def test_negative_news_issuer_flags_exit():
    settings = Settings()
    h = Holding(
        issuer="Banco Master", conglomerate="Master", product_type=ProductType.CDB,
        amount=250_000, fgc_eligible=True, index_type=IndexType.PRE, entry_rate=14.0,
        maturity=date.today() + timedelta(days=365 * 2), rating="BBB",
    )
    mark = mark_holding(h, _ctx(settings), settings)
    assert mark is not None and mark.signal == "EXIT"


def test_mark_portfolio_on_mock_holdings():
    settings = Settings()
    portfolio = asyncio.run(MockCollector(settings).fetch_positions())
    marks = {m.issuer: m for m in mark_portfolio(portfolio, _ctx(settings), settings)}
    assert marks["Banco BTG Pactual"].signal == "CONSIDER_SELL"
    assert marks["Banco Master"].signal == "EXIT"
    assert marks["Vale S.A."].signal == "HOLD"  # IPCA+ marked at a small loss


def test_portfolio_marks_api(monkeypatch, tmp_path):
    monkeypatch.setenv("MARKET_SOURCE", "fixtures")
    monkeypatch.setenv("OFFER_SOURCE", "mock")
    monkeypatch.setenv("EQUITY_SOURCE", "fixtures")
    monkeypatch.setenv("EQUITY_WATCHLIST_PATH", str(tmp_path / "wl.json"))
    monkeypatch.setenv("HISTORY_PATH", str(tmp_path / "h.jsonl"))
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "a.log"))
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            marks = client.get("/portfolio/marks").json()
            assert isinstance(marks, list) and len(marks) == 3
            signals = {m["issuer"]: m["signal"] for m in marks}
            assert "CONSIDER_SELL" in signals.values()
            assert "EXIT" in signals.values()
    finally:
        get_settings.cache_clear()
