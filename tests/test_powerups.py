"""Tests for the allocator and the Copom-aware macro view."""

from __future__ import annotations

import asyncio
from datetime import date

from app.analysis import evaluate_offers
from app.analysis.allocator import allocate
from app.analysis.copom import macro_view
from app.collector.sources import MockCollector
from app.config import Settings
from app.market.fixtures import fixtures_context
from app.models import FocusExpectation, MarketContext
from app.portfolio import PortfolioService


def _flagged(settings):
    ctx = fixtures_context(settings)
    service = PortfolioService(settings)
    offers = asyncio.run(MockCollector(settings).fetch_offers())
    return evaluate_offers(offers, ctx, service, settings), service


def test_allocator_respects_budget_and_minimums():
    settings = Settings(opportunity_threshold=50)
    opps, service = _flagged(settings)
    plan = allocate(80_000.0, opps, service, settings)
    assert plan.allocated <= plan.budget
    assert abs(plan.allocated + plan.leftover - plan.budget) < 0.01
    # Every allocation meets the offer minimum and is positive.
    by_id = {o.offer.id: o.offer for o in opps}
    for a in plan.allocations:
        assert a.amount >= by_id[a.offer_id].min_investment
        assert a.amount > 0


def test_allocator_no_opportunities():
    settings = Settings(opportunity_threshold=50)
    _, service = _flagged(settings)
    plan = allocate(50_000.0, [], service, settings)
    assert plan.allocated == 0.0 and plan.leftover == 50_000.0
    assert any("No flagged" in n for n in plan.notes)


def _ctx(selic_now: float, selic_next: float) -> MarketContext:
    yr = date.today().year + 1
    return MarketContext(
        cdi_annual=selic_now - 0.1,
        selic_annual=selic_now,
        ipca_annual=4.5,
        focus=[
            FocusExpectation(indicator="Selic", reference_year=yr, median=selic_next),
            FocusExpectation(indicator="IPCA", reference_year=yr, median=4.0),
        ],
    )


def test_macro_view_directions():
    assert macro_view(_ctx(10.75, 9.0)).direction == "CUTTING"
    assert macro_view(_ctx(10.75, 12.5)).direction == "HIKING"
    assert macro_view(_ctx(10.75, 10.80)).direction == "HOLD"


def test_macro_view_surfaces_ipca_and_posture():
    view = macro_view(_ctx(10.75, 9.0))
    assert view.expected_ipca == 4.0
    assert "duration" in view.duration_posture.lower() or "lock" in view.rationale.lower()
