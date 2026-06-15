"""Tests for the collector/analysis trust boundary (Phase 1)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.collector import (
    CollectorClient,
    InProcessCollectorClient,
    build_collector_client,
)
from app.collector.base import Collector
from app.collector.sources import MockCollector, build_collector
from app.config import Settings
from app.market import build_market_provider
from app.models import (
    IndexType,
    MarketKind,
    Offer,
    Portfolio,
    ProductType,
)
from app.portfolio import PortfolioService
from app.tracker import OpportunityTracker


def test_factory_builds_inprocess_client_over_mock():
    client = build_collector_client(Settings(offer_source="mock"))
    assert isinstance(client, InProcessCollectorClient)
    assert client.name == "mock"


def test_build_collector_selects_producer():
    assert isinstance(build_collector(Settings(offer_source="mock")), MockCollector)
    # Unknown values fall back to the mock collector (always boots).
    assert isinstance(build_collector(Settings(offer_source="???")), MockCollector)


@pytest.mark.asyncio
async def test_inprocess_client_delegates_to_collector():
    client = build_collector_client(Settings(offer_source="mock"))
    await client.startup()
    try:
        offers = await client.get_offers()
        positions = await client.get_positions()
    finally:
        await client.shutdown()
    assert offers and all(isinstance(o, Offer) for o in offers)
    assert isinstance(positions, Portfolio)


class _FakeRemoteClient(CollectorClient):
    """Stands in for a future out-of-process collector: the engine only sees
    the CollectorClient interface, so this drives the tracker with no source."""

    name = "fake-remote"

    def __init__(self, offers: list[Offer]) -> None:
        self._offers = offers
        self.started = False

    async def startup(self) -> None:
        self.started = True

    async def get_offers(self) -> list[Offer]:
        return self._offers

    async def get_positions(self) -> Portfolio | None:
        return None


@pytest.mark.asyncio
async def test_engine_runs_against_any_collector_client():
    settings = Settings(market_source="fixtures", opportunity_threshold=50)
    offer = Offer(
        id="x-1",
        issuer="Banco BTG Pactual",
        product_type=ProductType.CDB,
        index_type=IndexType.CDI,
        rate=115,
        maturity=date.today() + timedelta(days=365 * 2),
        min_investment=1000.0,
        fgc_eligible=True,
        rating="AAA",
        market=MarketKind.PRIMARY,
    )
    client = _FakeRemoteClient([offer])
    tracker = OpportunityTracker(
        client,
        settings,
        build_market_provider(settings),
        PortfolioService(settings),
    )
    await tracker._refresh_market(force=True)
    state = await tracker.refresh_once()
    assert client.started is False  # refresh_once doesn't need startup
    assert state.error is None
    assert len(state.opportunities) == 1
    assert state.source == "fake-remote"


def test_collector_base_is_distinct_from_client():
    # Producer and consumer are different roles in the boundary.
    assert issubclass(MockCollector, Collector)
    assert not issubclass(MockCollector, CollectorClient)
