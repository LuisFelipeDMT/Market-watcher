"""Background tracker that refreshes and evaluates offers on an interval.

It pulls offers from the configured source every ``REFRESH_INTERVAL_SECONDS``,
runs the opportunity analysis, stores the latest snapshot, and pushes updates
to any subscribers (e.g. WebSocket clients). It also tracks which offers newly
became opportunities so consumers can highlight them.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel

from app.analysis import evaluate_offers
from app.config import Settings
from app.models import Opportunity
from app.sources.base import OfferSource

logger = logging.getLogger(__name__)


class TrackerState(BaseModel):
    """A point-in-time snapshot of the tracker."""

    updated_at: Optional[datetime] = None
    refresh_count: int = 0
    source: str = ""
    error: Optional[str] = None
    opportunities: list[Opportunity] = []
    # IDs that newly crossed into opportunity status this cycle.
    new_opportunity_ids: list[str] = []


class OpportunityTracker:
    """Owns the refresh loop and the latest evaluated state."""

    def __init__(self, source: OfferSource, settings: Settings) -> None:
        self._source = source
        self._settings = settings
        self._state = TrackerState(source=source.name)
        self._task: Optional[asyncio.Task] = None
        self._subscribers: set[asyncio.Queue] = set()
        self._known_opportunity_ids: set[str] = set()
        self._lock = asyncio.Lock()

    # --- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        await self._source.startup()
        self._task = asyncio.create_task(self._run(), name="opportunity-tracker")
        logger.info("Tracker started (source=%s)", self._source.name)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._source.shutdown()
        logger.info("Tracker stopped")

    # --- state access ------------------------------------------------------

    @property
    def state(self) -> TrackerState:
        return self._state

    def subscribe(self) -> asyncio.Queue:
        """Register a subscriber queue for live snapshots."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    # --- internals ---------------------------------------------------------

    async def refresh_once(self) -> TrackerState:
        """Run a single refresh + evaluation cycle and update state."""
        async with self._lock:
            try:
                offers = await self._source.fetch_offers()
                opportunities = evaluate_offers(offers, self._settings)

                current_ids = {
                    o.offer.id for o in opportunities if o.is_opportunity
                }
                new_ids = sorted(current_ids - self._known_opportunity_ids)
                self._known_opportunity_ids = current_ids

                self._state = TrackerState(
                    updated_at=datetime.now(timezone.utc),
                    refresh_count=self._state.refresh_count + 1,
                    source=self._source.name,
                    error=None,
                    opportunities=opportunities,
                    new_opportunity_ids=new_ids,
                )
                if new_ids:
                    logger.info("New opportunities: %s", ", ".join(new_ids))
            except Exception as exc:  # keep the loop alive on transient errors
                logger.exception("Refresh failed: %s", exc)
                self._state = self._state.model_copy(
                    update={
                        "error": str(exc),
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
        await self._broadcast(self._state)
        return self._state

    async def _run(self) -> None:
        interval = max(self._settings.refresh_interval_seconds, 1.0)
        while True:
            await self.refresh_once()
            await asyncio.sleep(interval)

    async def _broadcast(self, state: TrackerState) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(state)
            except asyncio.QueueFull:
                # Slow consumer: drop the oldest, keep the newest snapshot.
                try:
                    queue.get_nowait()
                    queue.put_nowait(state)
                except asyncio.QueueEmpty:
                    pass
