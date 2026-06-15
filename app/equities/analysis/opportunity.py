"""Equity opportunity engine: snapshot → evaluated EquityOpportunity.

Stage 1 (fundamentals) scores quality + value and builds the fair-value
ensemble / margin of safety. Stage 2 (timing) scores the entry moment. The
state machine combines them, red flags disqualify, and the blended
``opportunity_score`` ranks the survivors.
"""

from __future__ import annotations

from app.config import Settings
from app.equities.analysis.quality import fii_quality, stock_quality
from app.equities.analysis.technical import compute_technical
from app.equities.analysis.timing import decide_state
from app.equities.analysis.value import fii_value, stock_value
from app.equities.analysis.valuation import value_asset
from app.equities.models import (
    AssetKind,
    EquityOpportunity,
    WatchState,
)
from app.equities.sources.base import EquitySnapshot
from app.models import MarketContext


def _red_flags(snap: EquitySnapshot) -> list[str]:
    """Hard disqualifiers (mirror the institution gate on the bond side)."""
    flags: list[str] = []
    f = snap.fundamentals
    if f is not None:
        if f.eps is not None and f.eps < 0:
            flags.append("Negative earnings")
        if f.net_debt_ebitda is not None and f.net_debt_ebitda >= 3.0:
            flags.append(f"Excessive leverage (net debt/EBITDA {f.net_debt_ebitda:.1f}x)")
        if f.shares_cagr_5y is not None and f.shares_cagr_5y >= 5.0:
            flags.append("Heavy share dilution")
        if f.fcf_per_share is not None and f.fcf_per_share < 0 and (f.roe or 0) < 0:
            flags.append("Negative FCF and ROE")
    m = snap.fii
    if m is not None:
        if m.vacancy is not None and m.vacancy >= 0.20:
            flags.append(f"High vacancy {m.vacancy * 100:.0f}%")
    return flags


def _soft_warnings(snap: EquitySnapshot) -> list[str]:
    warnings: list[str] = []
    f = snap.fundamentals
    if f is not None:
        if f.payout is not None and f.payout > 0.9:
            warnings.append("Very high payout (limited reinvestment)")
        if f.net_debt_ebitda is not None and 2.0 <= f.net_debt_ebitda < 3.0:
            warnings.append("Elevated leverage")
    m = snap.fii
    if m is not None and m.vacancy is not None and 0.10 <= m.vacancy < 0.20:
        warnings.append(f"Rising vacancy {m.vacancy * 100:.0f}%")
    return warnings


def evaluate_equity(
    snap: EquitySnapshot,
    context: MarketContext,
    settings: Settings,
    peer_multiples: dict[str, float],
) -> EquityOpportunity:
    """Evaluate a single snapshot into an :class:`EquityOpportunity`."""
    stock = snap.stock
    is_fii = stock.asset_kind is AssetKind.FII

    if is_fii and snap.fii is not None:
        quality_score, q_reasons = fii_quality(snap.fii)
        value_score, v_reasons = fii_value(snap.fii)
    elif snap.fundamentals is not None:
        quality_score, q_reasons = stock_quality(snap.fundamentals)
        value_score, v_reasons = stock_value(snap.fundamentals)
    else:
        quality_score, q_reasons = 0.0, []
        value_score, v_reasons = 0.0, []

    valuation = value_asset(
        asset_kind=stock.asset_kind,
        price=stock.price,
        sector=stock.sector,
        context=context,
        settings=settings,
        peer_multiples=peer_multiples,
        fundamentals=snap.fundamentals,
        fii=snap.fii,
    )
    technical = compute_technical(stock.price, stock.price_history)

    flags = _red_flags(snap)
    warnings = _soft_warnings(snap)
    state, state_reasons = decide_state(
        quality_score, valuation, technical, bool(flags), settings
    )

    # Blended score: quality + value + margin of safety, lifted by entry
    # readiness. Disqualified names score 0.
    mos = valuation.margin_of_safety or 0.0
    mos_score = max(0.0, min(mos / 0.40, 1.0)) * 100.0
    base = 0.40 * quality_score + 0.25 * value_score + 0.35 * mos_score
    entry_factor = 0.6 + 0.4 * (technical.entry_score / 100.0)
    score = 0.0 if state is WatchState.REJECTED else base * entry_factor
    score = round(max(0.0, min(100.0, score)), 2)

    reasons = list(state_reasons)
    if state is not WatchState.REJECTED:
        reasons.extend(q_reasons[:2])
        reasons.extend(v_reasons[:1])
        if valuation.fair_value_mid is not None:
            reasons.append(
                f"Fair value ~R${valuation.fair_value_mid:.2f} "
                f"(range {valuation.fair_value_low:.2f}–{valuation.fair_value_high:.2f})"
            )
    else:
        reasons.extend(f"Red flag: {flag}" for flag in flags)

    return EquityOpportunity(
        stock=stock,
        fundamentals=snap.fundamentals,
        fii=snap.fii,
        valuation=valuation,
        technical=technical,
        quality_score=quality_score,
        value_score=value_score,
        opportunity_score=score,
        state=state,
        is_opportunity=state is WatchState.TRIGGERED,
        reasons=reasons,
        warnings=warnings,
    )


def evaluate_universe(
    snapshots: list[EquitySnapshot],
    context: MarketContext,
    settings: Settings,
    peer_multiples: dict[str, float],
) -> list[EquityOpportunity]:
    """Evaluate and rank a universe (TRIGGERED first, then by score)."""
    evaluated = [
        evaluate_equity(s, context, settings, peer_multiples) for s in snapshots
    ]
    # Order: triggered first, then by blended score.
    state_rank = {
        WatchState.TRIGGERED: 0,
        WatchState.ARMED: 1,
        WatchState.WATCH: 2,
        WatchState.REJECTED: 3,
    }
    evaluated.sort(key=lambda o: (state_rank[o.state], -o.opportunity_score))
    return evaluated
