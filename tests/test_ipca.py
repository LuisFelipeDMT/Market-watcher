"""Tests for index-consistent IPCA cheapness / breakeven."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.analysis.ipca import breakeven_inflation, ipca_view
from app.config import Settings
from app.market.fixtures import fixtures_context
from app.models import IndexType, Offer, ProductType


def test_breakeven_inflation_formula():
    # (1.13 / 1.06 - 1) * 100
    assert breakeven_inflation(13.0, 6.0) == pytest.approx(6.6038, abs=1e-3)
    # A higher real spread needs less inflation to beat the same prefixado.
    assert breakeven_inflation(13.0, 8.0) < breakeven_inflation(13.0, 6.0)


def test_ipca_view_fields_and_verdict():
    settings = Settings()
    ctx = fixtures_context(settings)
    offer = Offer(
        id="rf-ipca",
        issuer="Vale S.A.",
        product_type=ProductType.DEBENTURE,
        index_type=IndexType.IPCA,
        rate=6.8,
        maturity=date.today() + timedelta(days=365 * 5),
        min_investment=1000.0,
        rating="AAA",
    )
    view = ipca_view(offer, ctx)
    assert view.real_spread == 6.8
    assert view.implied_nominal > view.expected_ipca  # nominal includes inflation
    assert view.breakeven_inflation > 0
    assert isinstance(view.verdict, str) and view.verdict


def test_ipca_api(monkeypatch, tmp_path):
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
            views = client.get("/ipca").json()
            assert isinstance(views, list) and len(views) > 0
            assert all("breakeven_inflation" in v for v in views)
            be = client.get("/ipca/breakeven", params={"pre": 13, "real": 6}).json()
            assert be["breakeven_inflation"] == pytest.approx(6.6038, abs=1e-3)
    finally:
        get_settings.cache_clear()
