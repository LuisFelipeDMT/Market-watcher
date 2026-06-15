"""Offline reference-data snapshot, used as the dev default and live fallback.

Numbers approximate the Brazilian rate environment in mid-2026. They keep the
app fully functional (and tests deterministic) without any network access.
"""

from __future__ import annotations

from app.config import Settings
from app.market.base import MarketDataProvider
from app.models import FocusExpectation, MarketContext

# Risk-free zero curve (Tesouro-derived), annual % by tenor in years.
_RISK_FREE_CURVE: dict[str, float] = {
    "0.5": 10.6,
    "1": 11.2,
    "2": 11.8,
    "3": 12.1,
    "5": 12.4,
    "10": 12.7,
}

# Credit spread over the risk-free curve by tier, in basis points.
_CREDIT_SPREADS_BPS: dict[str, float] = {
    "SOVEREIGN": 0,
    "AAA": 80,
    "AA": 140,
    "A": 220,
    "BBB": 360,
    "BB": 600,
    "B": 950,
}

_FOCUS = [
    FocusExpectation(indicator="Selic", reference_year=2026, median=10.75, std_dev=0.35),
    FocusExpectation(indicator="Selic", reference_year=2027, median=10.0, std_dev=0.75),
    FocusExpectation(indicator="IPCA", reference_year=2026, median=4.5, std_dev=0.30),
    FocusExpectation(indicator="IPCA", reference_year=2027, median=4.0, std_dev=0.55),
]


def fixtures_context(settings: Settings, source: str = "fixtures") -> MarketContext:
    """Build a MarketContext from the static snapshot + settings fallbacks."""
    return MarketContext(
        source=source,
        cdi_annual=settings.cdi_annual,
        selic_annual=settings.selic_annual,
        ipca_annual=settings.ipca_annual,
        focus=list(_FOCUS),
        rate_path_uncertainty=0.25,
        risk_free_curve=dict(_RISK_FREE_CURVE),
        credit_spreads_bps=dict(_CREDIT_SPREADS_BPS),
    )


class FixturesMarketProvider(MarketDataProvider):
    """Returns the static snapshot. Never touches the network."""

    name = "fixtures"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def refresh(self) -> MarketContext:
        return fixtures_context(self._settings)
