"""Abstract interface every equity source must implement."""

from __future__ import annotations

import abc

from pydantic import BaseModel, Field

from app.equities.models import Fundamentals, FiiMetrics, Stock


class EquitySnapshot(BaseModel):
    """One asset's identity/price plus whatever fundamentals are available."""

    stock: Stock
    fundamentals: Fundamentals | None = None
    fii: FiiMetrics | None = None


class EquitySource(abc.ABC):
    """A source of the equity universe (stocks + FIIs) with fundamentals.

    Implementations fetch the tracked universe each refresh cycle. Price moves
    fast (10s cadence); fundamentals change slowly, so a source may cache them.
    """

    name: str = "base"

    # Sector -> typical P/L multiple, used by the peer-multiple valuation.
    peer_multiples: dict[str, float] = Field(default_factory=dict)

    async def startup(self) -> None:
        """Optional one-time setup."""

    async def shutdown(self) -> None:
        """Optional teardown."""

    @abc.abstractmethod
    async def fetch_universe(self) -> list[EquitySnapshot]:
        """Return the current universe of tracked stocks and FIIs."""
        raise NotImplementedError

    def sector_multiples(self) -> dict[str, float]:
        """Sector -> peer P/L multiples for relative valuation."""
        return dict(self.peer_multiples)
