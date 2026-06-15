"""Background tracker for equities: refresh, evaluate, persist, broadcast.

Mirrors :class:`app.tracker.OpportunityTracker` but for the two-stage equity
flow. Each cycle it pulls the universe, reuses the slow-cadence MarketContext
(for the Selic-aware required margin of safety), evaluates every name, persists
the watch states and emits the snapshot to subscribers. Newly TRIGGERED tickers
are surfaced so consumers can alert on "buy now" moments.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel

from app.config import Settings
from app.equities.analysis import evaluate_universe
from app.equities.models import EquityOpportunity, WatchState
from app.equities.sources.base import EquitySource
from app.equities.watchlist import Watchlist
from app.market.base import MarketDataProvider
from app.models import MarketContext

logger = logging.getLogger(__name__)


class EquityTrackerState(BaseModel):
    """A point-in-time snapshot of the equity tracker."""

    updated_at: Optional[datetime] = None
    refresh_count: int = 0
    source: str = ""
    market_source: str = ""
    error: Optional[str] = None
    opportunities: list[EquityOpportunity] = []
    # Tickers that newly entered TRIGGERED this cycle.
    newly_triggered: list[str] = []
    # Count of names in each state.
    state_counts: dict[str, int] = {}


class EquityTracker:
    """Owns the equity refresh loop and the latest evaluated state."""

    def __init__(
        self,
        source: EquitySource,
        settings: Settings,
        market_provider: MarketDataProvider,
        watchlist: Watchlist,
    ) -> None:
        self._source = source
        self._settings = settings
        self._market = market_provider
        self._watchlist = watchlist
        self._context: Optional[MarketContext] = None
        self._last_market_refresh: float = 0.0
        self._state = EquityTrackerState(source=source.name)
        self._task: Optional[asyncio.Task] = None
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    # --- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        await self._source.startup()
        await self._refresh_market(force=True)
        self._task = asyncio.create_task(self._run(), name="equity-tracker")
        logger.info("Equity tracker started (source=%s)", self._source.name)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._source.shutdown()
        logger.info("Equity tracker stopped")

    # --- state access ------------------------------------------------------

    @property
    def state(self) -> EquityTrackerState:
        return self._state

    @property
    def market_context(self) -> Optional[MarketContext]:
        return self._context

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    # --- internals ---------------------------------------------------------

    async def _refresh_market(self, force: bool = False) -> None:
        now = asyncio.get_event_loop().time()
        due = now - self._last_market_refresh >= self._settings.market_refresh_seconds
        if not force and not due and self._context is not None:
            return
        try:
            self._context = await self._market.refresh()
            self._last_market_refresh = now
        except Exception as exc:
            logger.warning("Market refresh failed: %s", exc)

    async def refresh_once(self) -> EquityTrackerState:
        async with self._lock:
            try:
                await self._refresh_market()
                if self._context is None:
                    raise RuntimeError("No market context available")
                snapshots = await self._source.fetch_universe()
                opportunities = evaluate_universe(
                    snapshots,
                    self._context,
                    self._settings,
                    self._source.sector_multiples(),
                )

                states = {o.ticker: o.state for o in opportunities}
                newly_triggered = self._watchlist.reconcile(states)
                counts: dict[str, int] = {}
                for o in opportunities:
                    counts[o.state.value] = counts.get(o.state.value, 0) + 1

                self._state = EquityTrackerState(
                    updated_at=datetime.now(timezone.utc),
                    refresh_count=self._state.refresh_count + 1,
                    source=self._source.name,
                    market_source=self._context.source,
                    error=None,
                    opportunities=opportunities,
                    newly_triggered=newly_triggered,
                    state_counts=counts,
                )
                if newly_triggered:
                    logger.info("Newly triggered: %s", ", ".join(newly_triggered))
            except Exception as exc:
                logger.exception("Equity refresh failed: %s", exc)
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

    async def _broadcast(self, state: EquityTrackerState) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(state)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(state)
                except asyncio.QueueEmpty:
                    pass
