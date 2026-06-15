"""Banco Central data: SGS benchmark rates + Olinda Focus expectations.

All functions are defensive — they raise on failure so the caller can fall
back to fixtures, and they never block the event loop (httpx async).
"""

from __future__ import annotations

import logging

import httpx

from app.models import FocusExpectation

logger = logging.getLogger(__name__)

# SGS series codes.
SGS_SELIC_META = 432  # Selic meta, annual %
SGS_CDI_ANNUAL = 4389  # CDI annualized (base 252), %
SGS_IPCA_12M = 13522  # IPCA accumulated over 12 months, %


async def _sgs_last(client: httpx.AsyncClient, base_url: str, code: int) -> float:
    url = f"{base_url}/bcdata.sgs.{code}/dados/ultimos/1?formato=json"
    resp = await client.get(url)
    resp.raise_for_status()
    data = resp.json()
    return float(data[-1]["valor"].replace(",", "."))


async def fetch_benchmark_rates(
    client: httpx.AsyncClient, base_url: str
) -> dict[str, float]:
    """Return ``{cdi, selic, ipca}`` annual percentages from SGS."""
    selic = await _sgs_last(client, base_url, SGS_SELIC_META)
    try:
        cdi = await _sgs_last(client, base_url, SGS_CDI_ANNUAL)
    except Exception:  # CDI series occasionally lags; approximate from Selic.
        cdi = round(selic - 0.10, 2)
    ipca = await _sgs_last(client, base_url, SGS_IPCA_12M)
    return {"cdi": cdi, "selic": selic, "ipca": ipca}


async def fetch_focus(
    client: httpx.AsyncClient, base_url: str, years: list[int]
) -> list[FocusExpectation]:
    """Fetch the latest annual Focus medians for Selic and IPCA."""
    out: list[FocusExpectation] = []
    for indicator in ("Selic", "IPCA"):
        for year in years:
            params = {
                "$filter": f"Indicador eq '{indicator}' and DataReferencia eq '{year}'",
                "$orderby": "Data desc",
                "$top": "1",
                "$format": "json",
                "$select": "Indicador,DataReferencia,Media,DesvioPadrao",
            }
            url = f"{base_url}/ExpectativasMercadoAnuais"
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            rows = resp.json().get("value", [])
            if not rows:
                continue
            row = rows[0]
            out.append(
                FocusExpectation(
                    indicator=indicator,
                    reference_year=year,
                    median=float(row["Media"]),
                    std_dev=(
                        float(row["DesvioPadrao"])
                        if row.get("DesvioPadrao") is not None
                        else None
                    ),
                )
            )
    return out


def rate_path_uncertainty(focus: list[FocusExpectation]) -> float:
    """A 0..1-ish proxy for macro uncertainty from Focus Selic dispersion."""
    selic_sd = [
        f.std_dev for f in focus if f.indicator == "Selic" and f.std_dev is not None
    ]
    if not selic_sd:
        return 0.25
    # Normalize: ~1.0pp std dev maps to ~0.5 uncertainty.
    return min(max(sum(selic_sd) / len(selic_sd) / 2.0, 0.0), 1.0)
