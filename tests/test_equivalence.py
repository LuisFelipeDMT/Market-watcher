"""Tests for cross-index equivalence (compare papers on a common basis)."""

from __future__ import annotations

from datetime import date

import pytest

from app.analysis.equivalence import equivalents, nominal_gross, offer_equivalence
from app.models import FocusExpectation, IndexType, MarketContext, Offer, ProductType


def _ctx(cdi=10.0, selic=10.5, ipca=4.0, ipca_next=None) -> MarketContext:
    focus = []
    if ipca_next is not None:
        focus = [
            FocusExpectation(indicator="IPCA", reference_year=date.today().year + 1, median=ipca_next)
        ]
    return MarketContext(cdi_annual=cdi, selic_annual=selic, ipca_annual=ipca, focus=focus)


def test_nominal_gross_per_index():
    ctx = _ctx()
    assert nominal_gross(IndexType.PRE, 13.0, ctx) == 13.0
    assert nominal_gross(IndexType.CDI, 110.0, ctx) == pytest.approx(11.0)
    assert nominal_gross(IndexType.IPCA, 6.0, ctx) == pytest.approx(10.24, abs=1e-6)
    assert nominal_gross(IndexType.SELIC, 0.1, ctx) == pytest.approx(10.6105, abs=1e-4)


def test_pre_to_cdi_equivalent():
    eq = equivalents(IndexType.PRE, 13.0, _ctx(cdi=10.0))
    assert eq.as_pre == 13.0
    assert eq.as_cdi_pct == pytest.approx(130.0)  # 13 / 10 * 100


def test_ipca_roundtrips_to_itself():
    eq = equivalents(IndexType.IPCA, 6.0, _ctx())
    assert eq.nominal_annual == pytest.approx(10.24, abs=1e-4)
    assert eq.as_ipca_spread == pytest.approx(6.0, abs=1e-4)  # back to IPCA+6
    assert eq.as_cdi_pct == pytest.approx(102.4, abs=0.1)  # vs CDI 10%


def test_expected_ipca_uses_focus():
    eq = equivalents(IndexType.IPCA, 6.0, _ctx(ipca=4.0, ipca_next=5.5), use_expected_ipca=True)
    assert eq.ipca_assumed == 5.5
    assert eq.basis == "expected_ipca"


def test_offer_equivalence_uses_effective_rate():
    ctx = _ctx()
    offer = Offer(
        id="o-1",
        issuer="Vale S.A.",
        product_type=ProductType.DEBENTURE,
        index_type=IndexType.IPCA,
        rate=6.0,
        offered_ytm=8.0,  # secondary buy yield overrides
        maturity=date.today().replace(year=date.today().year + 5),
        min_investment=1000.0,
    )
    eq = offer_equivalence(offer, ctx)
    assert eq.input_rate == 8.0
    assert eq.nominal_annual == pytest.approx(((1.04) * (1.08) - 1) * 100, abs=1e-6)


def test_compare_api_normalizes_and_ranks(monkeypatch, tmp_path):
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
            eq = client.get("/equivalence", params={"index": "IPCA", "rate": 6.0}).json()
            assert eq["as_cdi_pct"] > 0 and eq["input_index"] == "IPCA"
            rows = client.get("/compare").json()
            assert len(rows) > 0
            nominals = [r["nominal_annual"] for r in rows]
            assert nominals == sorted(nominals, reverse=True)
            assert {"as_cdi_pct", "as_ipca_spread", "as_selic_spread"} <= set(rows[0])
    finally:
        get_settings.cache_clear()
