"""Equity data sources (fixtures + brapi) and a factory to build them."""

from __future__ import annotations

from app.config import Settings
from app.equities.sources.base import EquitySnapshot, EquitySource
from app.equities.sources.fixtures import FixturesEquitySource


def build_equity_source(settings: Settings) -> EquitySource:
    """Construct the configured equity source.

    Falls back to the fixtures source for any unknown value so the app always
    boots into a working state.
    """
    if settings.equity_source.lower() == "brapi":
        from app.equities.sources.brapi import BrapiEquitySource

        return BrapiEquitySource(settings)
    return FixturesEquitySource()


__all__ = [
    "EquitySnapshot",
    "EquitySource",
    "FixturesEquitySource",
    "build_equity_source",
]
