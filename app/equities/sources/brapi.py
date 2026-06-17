"""Live equity source backed by brapi.dev, with per-ticker fixtures fallback.

brapi.dev exposes free quotes, OHLCV history and fundamental modules for B3
tickers. This source starts from the fixtures universe (so the tracked list and
any missing fundamentals are always populated) and overlays live price, price
history and a few fundamental fields when the API is reachable — mirroring the
resilient, self-falling-back design of :class:`LiveMarketProvider`.
"""

from __future__ import annotations

import logging

import httpx

from app.config import Settings
from app.equities.sources.base import EquitySnapshot
from app.equities.sources.fixtures import FixturesEquitySource
from app.security import validate_public_url

logger = logging.getLogger(__name__)


class BrapiEquitySource(FixturesEquitySource):
    """Fixtures universe enriched with live brapi data when available."""

    name = "brapi"

    def __init__(self, settings: Settings, transport=None) -> None:
        self._settings = settings
        self._transport = transport  # injectable for tests (httpx.MockTransport)

    async def fetch_universe(self) -> list[EquitySnapshot]:
        snapshots = await super().fetch_universe()
        tickers = ",".join(s.stock.ticker for s in snapshots)
        token = self._settings.brapi_token
        params = {"range": "1y", "interval": "1d"}
        if token:
            params["token"] = token
        url = f"{self._settings.brapi_base_url.rstrip('/')}/quote/{tickers}"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept": "application/json",
        }
        try:
            if self._transport is None:
                validate_public_url(url)  # SSRF guard before any outbound fetch
            async with httpx.AsyncClient(
                timeout=self._settings.market_http_timeout,
                headers=headers,
                follow_redirects=True,
                transport=self._transport,
            ) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                payload = resp.json()
        except Exception as exc:  # any failure → pure fixtures snapshot
            logger.warning("brapi unavailable, using fixtures: %s", exc)
            return snapshots

        by_ticker = {item.get("symbol"): item for item in payload.get("results", [])}
        for snap in snapshots:
            data = by_ticker.get(snap.stock.ticker)
            if not data:
                continue
            price = data.get("regularMarketPrice")
            if isinstance(price, (int, float)) and price > 0:
                snap.stock.price = float(price)
            history = [
                bar.get("close")
                for bar in data.get("historicalDataPrice", [])
                if isinstance(bar.get("close"), (int, float))
            ]
            if len(history) >= 30:
                history[-1] = snap.stock.price
                snap.stock.price_history = [float(c) for c in history]
        return snapshots
