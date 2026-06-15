"""Collector zone: the trusted producer of read-only brokerage data.

Public surface for the analysis zone is :class:`CollectorClient` +
:func:`build_collector_client`. The engine depends only on these, so the
collector can later move behind a socket / snapshot-file transport (a separate,
isolated service) without touching the analysis code.
"""

from __future__ import annotations

from app.collector.base import Collector, CollectorClient
from app.collector.inprocess import InProcessCollectorClient
from app.collector.sources import build_collector
from app.config import Settings


def build_collector_client(settings: Settings) -> CollectorClient:
    """Build the configured collector wrapped in the current transport.

    Today that is in-process; a future ``remote`` mode will return a
    ``RemoteCollectorClient`` with the same interface.
    """
    return InProcessCollectorClient(build_collector(settings))


__all__ = [
    "Collector",
    "CollectorClient",
    "InProcessCollectorClient",
    "build_collector",
    "build_collector_client",
]
