"""Trust-boundary contracts between the collector and analysis zones.

Two roles, deliberately separated:

- :class:`Collector` is the **producer** that lives in the trusted zone. It is
  the only code allowed to touch the brokerage (credentials, session, scraping)
  and it returns sanitized, typed models — never raw HTML.
- :class:`CollectorClient` is the **consumer** interface used by the analysis
  zone (the tracker). Today the implementation runs the collector in-process;
  later a remote implementation will speak to an isolated collector over a
  socket / signed snapshot files **with the same interface**, so the engine
  never changes when the transport does.
"""

from __future__ import annotations

import abc

from app.models import Offer, Portfolio


class Collector(abc.ABC):
    """Trusted-zone producer of read-only brokerage data.

    Implementations fetch the current offers (and optionally holdings). The
    in-process client calls :meth:`fetch_offers` each refresh cycle.
    """

    name: str = "base"

    async def startup(self) -> None:
        """Optional one-time setup (e.g. log in, open a browser session)."""

    async def shutdown(self) -> None:
        """Optional teardown (e.g. close browser / sessions)."""

    @abc.abstractmethod
    async def fetch_offers(self) -> list[Offer]:
        """Return the current offers available on the platform.

        Should include both primary and secondary-market offers.
        """
        raise NotImplementedError

    async def fetch_positions(self) -> Portfolio | None:
        """Return the investor's current holdings, if supported."""
        return None


class CollectorClient(abc.ABC):
    """Analysis-zone consumer interface for read-only brokerage data.

    The boundary the engine depends on. Verbs are deliberately consumer-side
    (``get_*``) to distinguish them from the producer's ``fetch_*``.
    """

    name: str = "base"

    async def startup(self) -> None:
        """Prepare the client / underlying collector."""

    async def shutdown(self) -> None:
        """Release the client / underlying collector."""

    @abc.abstractmethod
    async def get_offers(self) -> list[Offer]:
        """Return the latest offers from the collector."""
        raise NotImplementedError

    @abc.abstractmethod
    async def get_positions(self) -> Portfolio | None:
        """Return current holdings from the collector, if available."""
        raise NotImplementedError
