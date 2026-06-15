"""Market-data provider factory + a resilient live provider.

The live provider fetches each piece (BCB rates, Focus, Tesouro curve, ANBIMA
spreads) independently and falls back to the fixtures snapshot for any piece
that fails, so a single flaky endpoint never blanks the whole context.
"""

from __future__ import annotations

import logging
from datetime import date

import httpx

from app.config import Settings
from app.market import anbima, bcb, tesouro
from app.market.base import MarketDataProvider
from app.market.fixtures import FixturesMarketProvider, fixtures_context
from app.models import MarketContext

logger = logging.getLogger(__name__)


class LiveMarketProvider(MarketDataProvider):
    """Fetches reference data from free public sources, fixtures on failure."""

    name = "live"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def refresh(self) -> MarketContext:
        s = self._settings
        ctx = fixtures_context(s, source="live")  # start from fixtures, override
        used_live = False

        # A browser-like UA avoids 403s from some public endpoints (BCB/B3).
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept": "application/json, text/csv, */*",
        }
        async with httpx.AsyncClient(
            timeout=s.market_http_timeout, headers=headers, follow_redirects=True
        ) as client:
            try:
                rates = await bcb.fetch_benchmark_rates(client, s.bcb_sgs_base_url)
                ctx.cdi_annual = rates["cdi"]
                ctx.selic_annual = rates["selic"]
                ctx.ipca_annual = rates["ipca"]
                used_live = True
            except Exception as exc:
                logger.warning("BCB SGS unavailable, using fixtures: %s", exc)

            try:
                years = [date.today().year, date.today().year + 1]
                focus = await bcb.fetch_focus(client, s.bcb_olinda_base_url, years)
                if focus:
                    ctx.focus = focus
                    ctx.rate_path_uncertainty = bcb.rate_path_uncertainty(focus)
                    used_live = True
            except Exception as exc:
                logger.warning("BCB Focus unavailable, using fixtures: %s", exc)

            try:
                curve = await tesouro.fetch_risk_free_curve(client, s.tesouro_url)
                if curve:
                    ctx.risk_free_curve = curve
                    used_live = True
            except Exception as exc:
                logger.warning("Tesouro curve unavailable, using fixtures: %s", exc)

            try:
                spreads = await anbima.fetch_credit_spreads(
                    client, s.anbima_debentures_url
                )
                if spreads:
                    ctx.credit_spreads_bps = spreads
                    used_live = True
            except Exception as exc:
                logger.warning("ANBIMA spreads unavailable, using fixtures: %s", exc)

        ctx.source = "live" if used_live else "fixtures"
        return ctx


def build_market_provider(settings: Settings) -> MarketDataProvider:
    """Construct the configured market-data provider."""
    mode = settings.market_source.lower()
    if mode == "fixtures":
        return FixturesMarketProvider(settings)
    # "auto" and "live" both use the resilient live provider (it self-falls
    # back to fixtures per-component).
    return LiveMarketProvider(settings)
