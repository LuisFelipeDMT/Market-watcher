"""Collector producers (mock + XP scraper) and a factory to build them."""

from __future__ import annotations

from app.collector.base import Collector
from app.collector.sources.mock_source import MockCollector
from app.config import Settings


def build_collector(settings: Settings) -> Collector:
    """Construct the configured collector (trusted-zone producer).

    Falls back to the mock collector for any unknown value so the app always
    boots into a working state.
    """
    if settings.offer_source.lower() == "xp":
        # Imported lazily so the app runs without Playwright installed when
        # using the mock collector.
        from app.collector.sources.xp_scraper import XPCollector

        return XPCollector(settings)
    return MockCollector(settings)


__all__ = ["Collector", "MockCollector", "build_collector"]
