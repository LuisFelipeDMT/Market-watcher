"""Interface for market-data providers (reference rates, curves, spreads)."""

from __future__ import annotations

import abc

from app.models import MarketContext


class MarketDataProvider(abc.ABC):
    """Supplies the :class:`MarketContext` used to evaluate offers."""

    name: str = "base"

    @abc.abstractmethod
    async def refresh(self) -> MarketContext:
        """Fetch and return the current market context."""
        raise NotImplementedError
