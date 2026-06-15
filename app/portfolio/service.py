"""Holds the investor's portfolio and computes FGC + concentration exposure."""

from __future__ import annotations

from app.config import Settings
from app.models import Holding, Portfolio
from app.portfolio.conglomerates import conglomerate_of, sector_of


class PortfolioService:
    """Owns the current Portfolio and answers exposure questions about it."""

    def __init__(self, settings: Settings, portfolio: Portfolio | None = None) -> None:
        self._settings = settings
        self._portfolio = portfolio or Portfolio()

    @property
    def portfolio(self) -> Portfolio:
        return self._portfolio

    def set_portfolio(self, portfolio: Portfolio) -> None:
        self._portfolio = portfolio

    def total_value(self) -> float:
        """Total portfolio value, or the configured default if empty."""
        total = self._portfolio.total_value
        return total if total > 0 else self._settings.default_portfolio_value

    # --- FGC exposure ------------------------------------------------------

    def fgc_exposure_by_conglomerate(self) -> dict[str, float]:
        """Sum FGC-eligible holdings per conglomerate."""
        out: dict[str, float] = {}
        for h in self._portfolio.holdings:
            if not h.fgc_eligible:
                continue
            key = h.conglomerate or conglomerate_of(h.issuer)
            out[key] = out.get(key, 0.0) + h.amount
        return out

    def fgc_room(self, issuer: str) -> float:
        """Remaining FGC-coverable amount for the issuer's conglomerate."""
        key = conglomerate_of(issuer)
        used = self.fgc_exposure_by_conglomerate().get(key, 0.0)
        return max(self._settings.fgc_per_institution - used, 0.0)

    def fgc_global_used(self) -> float:
        """Total FGC-eligible exposure (proxy for the R$1M / 4y global cap)."""
        return sum(self.fgc_exposure_by_conglomerate().values())

    def fgc_global_room(self) -> float:
        return max(self._settings.fgc_global_4y - self.fgc_global_used(), 0.0)

    # --- non-FGC concentration --------------------------------------------

    def issuer_exposure(self, issuer: str) -> float:
        return sum(h.amount for h in self._portfolio.holdings if h.issuer == issuer)

    def sector_exposure(self, issuer: str) -> float:
        sector = sector_of(issuer)
        return sum(
            h.amount
            for h in self._portfolio.holdings
            if (h.sector or sector_of(h.issuer)) == sector
        )
