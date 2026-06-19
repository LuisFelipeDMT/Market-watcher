"""Scaffolding for external fundamentals + broker research.

Maps a documented dict shape (Fundamentus / Status Invest / brapi fundamental
modules, or a CVM-derived export) onto our :class:`Fundamentals`, and a broker
research payload onto :class:`ResearchNote`. The live scrapers (which produce
these dicts) are integration-later; this keeps the mapping testable now against
saved samples and gives the engine a clean ingestion point.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.equities.models import Fundamentals


class ResearchNote(BaseModel):
    ticker: str
    broker: str
    recommendation: str | None = None  # e.g. "BUY" / "COMPRA"
    target_price: float | None = None
    thesis: str | None = None
    as_of: str | None = None


def _f(data: dict, *keys: str) -> float | None:
    """First present numeric value among ``keys`` (tolerant to source variance)."""
    for k in keys:
        v = data.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def parse_fundamentals(data: dict) -> Fundamentals:
    """Map a Fundamentus/Status-Invest-style dict (percent ratios) to Fundamentals.

    Yields (``dy``, ``fcf_yield``) are converted from percent to fraction to match
    our model's convention.
    """
    dy = _f(data, "dy", "dividend_yield")
    fcfy = _f(data, "fcf_yield")
    return Fundamentals(
        eps=_f(data, "eps", "lpa"),
        bvps=_f(data, "bvps", "vpa"),
        dps=_f(data, "dps"),
        fcf_per_share=_f(data, "fcf_per_share"),
        roe=_f(data, "roe"),
        roic=_f(data, "roic"),
        gross_margin=_f(data, "gross_margin", "marg_bruta"),
        ebit_margin=_f(data, "ebit_margin", "marg_ebit"),
        net_margin=_f(data, "net_margin", "marg_liquida"),
        net_debt_ebitda=_f(data, "net_debt_ebitda", "div_liq_ebitda"),
        current_ratio=_f(data, "current_ratio", "liq_corrente"),
        revenue_cagr_5y=_f(data, "revenue_cagr_5y"),
        earnings_cagr_5y=_f(data, "earnings_cagr_5y"),
        payout=_f(data, "payout"),
        pl=_f(data, "pl", "p_l"),
        pvp=_f(data, "pvp", "p_vp"),
        ev_ebitda=_f(data, "ev_ebitda"),
        dy=dy / 100.0 if dy is not None else None,
        fcf_yield=fcfy / 100.0 if fcfy is not None else None,
    )


def parse_research(data: dict) -> ResearchNote:
    """Map a broker research payload onto a ResearchNote."""
    return ResearchNote(
        ticker=str(data.get("ticker", "")).upper(),
        broker=str(data.get("broker", "")),
        recommendation=data.get("recommendation") or data.get("rating"),
        target_price=_f(data, "target_price", "preco_alvo"),
        thesis=data.get("thesis") or data.get("resumo"),
        as_of=data.get("as_of") or data.get("data"),
    )
