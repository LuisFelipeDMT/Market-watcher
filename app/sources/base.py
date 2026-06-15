"""Abstract interface every offer source must implement."""

from __future__ import annotations

import abc

from app.models import Offer, Portfolio


class OfferSource(abc.ABC):
    """A source of fixed-income offers.

    Implementations fetch the current list of papers available on the
    platform. The tracker calls :meth:`fetch_offers` on each refresh cycle.
    """

    name: str = "base"

    async def startup(self) -> None:
        """Optional one-time setup (e.g. log in, open a browser session)."""

    async def shutdown(self) -> None:
        """Optional teardown (e.g. close browser / sessions)."""

    @abc.abstractmethod
    async def fetch_offers(self) -> list[Offer]:
        """Return the current list of offers available on the platform.

        Should include both primary and secondary-market offers.
        """
        raise NotImplementedError

    async def fetch_positions(self) -> Portfolio | None:
        """Return the investor's current holdings, if the source supports it."""
        return None
