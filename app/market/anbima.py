"""ANBIMA reference data: secondary debenture taxas → credit spread tiers.

ANBIMA publishes daily secondary-market debenture rates (free, ~5 business
days). We use them to nudge the curated per-tier credit-spread table toward the
current market. The credit-curves page itself is JS-rendered; parsing the
published debenture taxas CSV is the robust free path. On any failure the
caller falls back to the curated fixture spreads.
"""

from __future__ import annotations

import csv
import io
import logging

import httpx

logger = logging.getLogger(__name__)

# Curated spread-over-risk-free by credit tier, basis points. Live data shifts
# these proportionally via the market-wide average when available.
BASE_SPREADS_BPS: dict[str, float] = {
    "SOVEREIGN": 0,
    "AAA": 80,
    "AA": 140,
    "A": 220,
    "BBB": 360,
    "BB": 600,
    "B": 950,
}


async def fetch_credit_spreads(
    client: httpx.AsyncClient, url: str
) -> dict[str, float]:
    """Return per-tier credit spreads (bps), adjusted by live ANBIMA data."""
    resp = await client.get(url)
    resp.raise_for_status()
    text = resp.content.decode("latin-1", errors="ignore")
    reader = csv.reader(io.StringIO(text), delimiter=";")
    rows = [r for r in reader if r]
    if len(rows) < 2:
        raise ValueError("Empty ANBIMA debentures CSV")

    # Find a numeric "taxa de compra" column heuristically and average it.
    rates: list[float] = []
    for row in rows[1:]:
        for cell in row:
            cell = cell.strip().replace(",", ".")
            try:
                val = float(cell)
            except ValueError:
                continue
            if 0.5 < val < 30.0:  # plausible annual % range for a taxa
                rates.append(val)
                break
    if not rates:
        raise ValueError("No parseable rates in ANBIMA debentures CSV")

    avg = sum(rates) / len(rates)
    # Anchor the AA tier to the market average spread (rough), scale the rest.
    # avg here is an indicative IPCA+ spread level in %; convert to bps.
    market_aa_bps = max(60.0, min(avg * 100.0, 400.0))
    scale = market_aa_bps / BASE_SPREADS_BPS["AA"]
    spreads = {tier: round(bps * scale, 1) for tier, bps in BASE_SPREADS_BPS.items()}
    spreads["SOVEREIGN"] = 0.0
    logger.info("ANBIMA credit spreads scaled by %.2f (n=%d)", scale, len(rates))
    return spreads
