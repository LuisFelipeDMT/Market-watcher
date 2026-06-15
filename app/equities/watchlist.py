"""Persisted per-ticker watch state, so transitions survive restarts.

The timing decision itself is stateless (see :mod:`analysis.timing`); this
store remembers each ticker's previous state so the tracker can detect *fresh*
transitions (e.g. a name that just became TRIGGERED) and so the WATCH/ARMED
pipeline is durable across the ephemeral container being recycled.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.equities.models import WatchState

logger = logging.getLogger(__name__)


class Watchlist:
    """A tiny JSON-backed map of ticker -> last observed state."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._states: dict[str, str] = {}
        self._updated: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._states = dict(data.get("states", {}))
            self._updated = dict(data.get("updated", {}))
        except Exception as exc:  # corrupt file shouldn't break startup
            logger.warning("Could not load watchlist %s: %s", self._path, exc)

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps({"states": self._states, "updated": self._updated}),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Could not save watchlist %s: %s", self._path, exc)

    def previous(self, ticker: str) -> WatchState | None:
        value = self._states.get(ticker)
        return WatchState(value) if value else None

    def reconcile(self, current: dict[str, WatchState]) -> list[str]:
        """Persist the latest states; return tickers that *entered* TRIGGERED."""
        newly_triggered: list[str] = []
        now = datetime.now(timezone.utc).isoformat()
        for ticker, state in current.items():
            prev = self._states.get(ticker)
            if state is WatchState.TRIGGERED and prev != WatchState.TRIGGERED.value:
                newly_triggered.append(ticker)
            if prev != state.value:
                self._updated[ticker] = now
            self._states[ticker] = state.value
        self._save()
        return sorted(newly_triggered)
