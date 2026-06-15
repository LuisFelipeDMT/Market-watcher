"""Offer data sources (mock + XP scraper) and a factory to build them."""

from __future__ import annotations

from app.config import Settings
from app.sources.base import OfferSource
from app.sources.mock_source import MockOfferSource


def build_source(settings: Settings) -> OfferSource:
    """Construct the configured offer source.

    Falls back to the mock source for any unknown value so the app always
    boots into a working state.
    """
    if settings.offer_source.lower() == "xp":
        # Imported lazily so the app runs without Playwright installed when
        # using the mock source.
        from app.sources.xp_scraper import XPOfferSource

        return XPOfferSource(settings)
    return MockOfferSource(settings)


__all__ = ["OfferSource", "MockOfferSource", "build_source"]
