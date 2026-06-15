"""Snapshot producer loop (collector trusted zone).

Periodically pulls the local collector and writes signed snapshot files for the
analysis zone to consume — the data-diode transport (no inbound to the
collector). Run with:  python -m app.collector.producer
"""

from __future__ import annotations

import asyncio
import logging

from app.collector.snapshot import SnapshotWriter
from app.collector.sources import build_collector
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


async def run_snapshot_producer(settings: Settings) -> None:
    if not settings.snapshot_key:
        raise RuntimeError("SNAPSHOT_KEY must be set to sign snapshots.")
    collector = build_collector(settings)
    writer = SnapshotWriter(settings.snapshot_dir, settings.snapshot_key)
    await collector.startup()
    try:
        interval = max(settings.collector_snapshot_interval, 1.0)
        while True:
            try:
                offers = await collector.fetch_offers()
                writer.write_offers(offers)
                writer.write_positions(await collector.fetch_positions())
            except Exception as exc:  # keep the loop alive
                logger.warning("Snapshot write failed: %s", exc)
            await asyncio.sleep(interval)
    finally:
        await collector.shutdown()


def main() -> None:  # pragma: no cover - process entrypoint
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    asyncio.run(run_snapshot_producer(settings))


if __name__ == "__main__":  # pragma: no cover
    main()
