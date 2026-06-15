"""In-process collector client — today's transport.

The collector runs in the same process as the analysis engine and is called
directly. This is the interim implementation of :class:`CollectorClient`; a
future ``RemoteCollectorClient`` will implement the same interface over a Unix
socket / signed snapshot files so the credential-bearing collector can run as a
separate, isolated service with no code change to the engine.
"""

from __future__ import annotations

from app.collector.base import Collector, CollectorClient
from app.models import Offer, Portfolio


class InProcessCollectorClient(CollectorClient):
    """Wraps a local :class:`Collector` and exposes the consumer interface."""

    def __init__(self, collector: Collector) -> None:
        self._collector = collector

    @property
    def name(self) -> str:  # type: ignore[override]
        return self._collector.name

    async def startup(self) -> None:
        await self._collector.startup()

    async def shutdown(self) -> None:
        await self._collector.shutdown()

    async def get_offers(self) -> list[Offer]:
        return await self._collector.fetch_offers()

    async def get_positions(self) -> Portfolio | None:
        return await self._collector.fetch_positions()
