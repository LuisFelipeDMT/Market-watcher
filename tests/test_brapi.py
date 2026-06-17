"""Tests for brapi live mapping + fixtures fallback (mocked HTTP)."""

from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.equities.models import AssetKind
from app.equities.sources.brapi import BrapiEquitySource


def _payload_handler(price: float, n_bars: int = 40):
    def handler(request: httpx.Request) -> httpx.Response:
        # brapi returns one result per requested symbol; we only override PETR4.
        bars = [{"close": price - i} for i in range(n_bars)][::-1]
        return httpx.Response(
            200,
            json={"results": [{"symbol": "PETR4", "regularMarketPrice": price,
                               "historicalDataPrice": bars}]},
        )

    return handler


@pytest.mark.asyncio
async def test_brapi_overrides_live_price_and_history():
    transport = httpx.MockTransport(_payload_handler(99.9))
    src = BrapiEquitySource(Settings(equity_source="brapi"), transport=transport)
    snaps = await src.fetch_universe()
    by_ticker = {s.stock.ticker: s for s in snaps}
    petr = by_ticker["PETR4"]
    assert petr.stock.price == 99.9
    assert petr.stock.price_history[-1] == 99.9  # anchored to live price
    assert len(petr.stock.price_history) >= 30
    # A ticker not in the live payload keeps its fixtures price.
    assert by_ticker["VALE3"].stock.price == 55.0


@pytest.mark.asyncio
async def test_brapi_falls_back_to_fixtures_on_error():
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    src = BrapiEquitySource(
        Settings(equity_source="brapi"), transport=httpx.MockTransport(boom)
    )
    snaps = await src.fetch_universe()
    # Still a full universe from fixtures, with both asset kinds.
    kinds = {s.stock.asset_kind for s in snaps}
    assert AssetKind.STOCK in kinds and AssetKind.FII in kinds
    assert next(s for s in snaps if s.stock.ticker == "PETR4").stock.price == 38.0
