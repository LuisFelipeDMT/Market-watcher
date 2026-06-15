"""Analysis-zone clients that read from an *isolated* collector.

Both implement :class:`CollectorClient`, so the engine is unchanged regardless
of transport:

- :class:`SnapshotFileCollectorClient` reads signed snapshot files (the data
  diode — recommended; no inbound to the collector).
- :class:`RemoteHttpCollectorClient` calls the collector's read-only HTTP API
  over a Unix domain socket with a bearer token.

Neither imports the credential-bearing producer or the secrets module — the
analysis zone has no code path to the brokerage credentials.
"""

from __future__ import annotations

import logging

import httpx

from app.collector.base import CollectorClient
from app.collector.snapshot import SnapshotReader
from app.config import Settings
from app.models import Offer, Portfolio

logger = logging.getLogger(__name__)


class SnapshotFileCollectorClient(CollectorClient):
    """Reads signed snapshots written by the collector (one-way, no inbound)."""

    name = "snapshot"

    def __init__(self, settings: Settings, reader: SnapshotReader | None = None) -> None:
        self._reader = reader or SnapshotReader(
            settings.snapshot_dir, settings.snapshot_key
        )

    async def get_offers(self) -> list[Offer]:
        return self._reader.read_offers()

    async def get_positions(self) -> Portfolio | None:
        return self._reader.read_positions()


class RemoteHttpCollectorClient(CollectorClient):
    """Calls the collector's read-only API over a Unix socket + bearer token."""

    name = "remote-http"

    def __init__(
        self, settings: Settings, client: httpx.AsyncClient | None = None
    ) -> None:
        self._settings = settings
        self._client = client  # injectable for tests
        self._owns_client = client is None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            transport = httpx.AsyncHTTPTransport(uds=self._settings.collector_socket_path)
            headers = {"Authorization": f"Bearer {self._settings.collector_token}"}
            self._client = httpx.AsyncClient(
                transport=transport,
                base_url=self._settings.collector_url,
                headers=headers,
                timeout=self._settings.market_http_timeout,
            )
        return self._client

    async def shutdown(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_offers(self) -> list[Offer]:
        resp = await self._ensure_client().get("/offers")
        resp.raise_for_status()
        return [Offer.model_validate(item) for item in resp.json()]

    async def get_positions(self) -> Portfolio | None:
        resp = await self._ensure_client().get("/positions")
        resp.raise_for_status()
        data = resp.json()
        return Portfolio.model_validate(data) if data else None
