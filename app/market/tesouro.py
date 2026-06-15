"""Tesouro Direto prices → a nominal risk-free zero curve anchor.

Uses the public B3 Tesouro Direto JSON. Prefixado bonds (Tesouro Prefijado /
LTN / NTN-F) give nominal annual rates by maturity, which anchor the risk-free
curve used to judge how cheap a credit paper is.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

import httpx

logger = logging.getLogger(__name__)


def _parse_maturity(value: str) -> date | None:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value[: len(fmt) + 2], fmt).date()
        except (ValueError, TypeError):
            continue
    return None


async def fetch_risk_free_curve(
    client: httpx.AsyncClient, url: str
) -> dict[str, float]:
    """Return ``{years: annual_rate_%}`` from prefixado Tesouro bonds."""
    resp = await client.get(url)
    resp.raise_for_status()
    payload = resp.json()
    bonds = payload.get("response", {}).get("TrsrBdTradgList", [])

    curve: dict[str, float] = {}
    today = date.today()
    for item in bonds:
        bd = item.get("TrsrBd", {})
        name = (bd.get("nm") or "").lower()
        if "prefixado" not in name and "ltn" not in name and "ntn-f" not in name:
            continue
        rate = bd.get("anulInvstmtRate")
        maturity = _parse_maturity(str(bd.get("mtrtyDt", "")))
        if rate is None or maturity is None:
            continue
        years = round((maturity - today).days / 365.0, 1)
        if years <= 0:
            continue
        # Keep the longest-dated rate per tenor bucket.
        curve[str(years)] = round(float(rate), 4)
    if not curve:
        raise ValueError("No prefixado bonds parsed from Tesouro feed")
    return curve
