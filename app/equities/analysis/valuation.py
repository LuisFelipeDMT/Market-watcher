"""Fair-value ensemble + margin of safety (the heart of stage 1).

Rather than trusting one model, several independent methods each produce a
fair value per share and we keep the range (low/mid/high). The margin of
safety is measured against the median, and the buy-zone price is the median
discounted by a macro-adjusted required MoS (higher Selic ⇒ demand more
discount). FIIs use dividend-yield and price-to-NAV anchors instead.
"""

from __future__ import annotations

import statistics

from app.config import Settings
from app.equities.models import (
    AssetKind,
    FiiMetrics,
    Fundamentals,
    Valuation,
)
from app.models import MarketContext

# Perpetual growth must stay modest (long-run economy), or Gordon/terminal
# values explode as g approaches the discount rate.
_MAX_PERPETUAL_GROWTH = 0.05
_TERMINAL_GROWTH = 0.03


def required_return(context: MarketContext, settings: Settings) -> float:
    """Discount rate r = risk-free (Selic) + equity risk premium."""
    return context.selic_annual / 100.0 + settings.equity_risk_premium


def required_margin_of_safety(
    asset_kind: AssetKind, context: MarketContext, settings: Settings
) -> float:
    """How much discount to fair value we demand before arming a name.

    Tightens when Selic is high (cash competes harder with equities). FIIs use
    a lower base and macro sensitivity than stocks.
    """
    excess_selic = max(0.0, context.selic_annual - settings.mos_neutral_selic) / 100.0
    if asset_kind is AssetKind.FII:
        return settings.fii_base_mos + excess_selic * settings.mos_macro_factor * 0.5
    return settings.stock_base_mos + excess_selic * settings.mos_macro_factor


def _stock_fair_values(
    f: Fundamentals, price: float, sector: str | None, r: float,
    peer_multiples: dict[str, float],
) -> dict[str, float]:
    """Run each applicable valuation method; skip those without valid inputs."""
    methods: dict[str, float] = {}

    # Graham number: sqrt(22.5 * EPS * BVPS).
    if f.eps and f.bvps and f.eps > 0 and f.bvps > 0:
        methods["graham"] = round((22.5 * f.eps * f.bvps) ** 0.5, 2)

    # Gordon growth (dividend discount) with a conservative perpetual g.
    if f.dps and f.dps > 0:
        g = min(
            (f.roe or 0) / 100.0 * (1 - (f.payout if f.payout is not None else 0.5)),
            _MAX_PERPETUAL_GROWTH,
        )
        g = max(0.0, g)
        if r - g > 0.02:
            methods["gordon"] = round(f.dps * (1 + g) / (r - g), 2)

    # Two-stage DCF on free cash flow per share.
    if f.fcf_per_share and f.fcf_per_share > 0:
        g1 = max(0.0, min((f.earnings_cagr_5y or 0) / 100.0, 0.12))
        pv = 0.0
        fcf = f.fcf_per_share
        for t in range(1, 6):
            fcf_t = f.fcf_per_share * (1 + g1) ** t
            pv += fcf_t / (1 + r) ** t
            fcf = fcf_t
        terminal = fcf * (1 + _TERMINAL_GROWTH) / (r - _TERMINAL_GROWTH)
        pv += terminal / (1 + r) ** 5
        methods["dcf"] = round(pv, 2)

    # Peer multiple: sector P/L × EPS.
    peer_pl = peer_multiples.get(sector or "")
    if peer_pl and f.eps and f.eps > 0:
        methods["peer_multiple"] = round(peer_pl * f.eps, 2)

    return methods


def _fii_fair_values(m: FiiMetrics, settings: Settings) -> dict[str, float]:
    methods: dict[str, float] = {}
    if m.dps and m.dps > 0:
        methods["dividend_yield"] = round(m.dps / settings.fii_target_dy, 2)
    if m.nav_per_share and m.nav_per_share > 0:
        methods["price_to_nav"] = round(m.nav_per_share * settings.fii_target_pvp, 2)
    return methods


def value_asset(
    asset_kind: AssetKind,
    price: float,
    sector: str | None,
    context: MarketContext,
    settings: Settings,
    peer_multiples: dict[str, float],
    fundamentals: Fundamentals | None = None,
    fii: FiiMetrics | None = None,
) -> Valuation:
    """Produce the fair-value ensemble + MoS + buy-zone for one asset."""
    r = required_return(context, settings)
    req_mos = required_margin_of_safety(asset_kind, context, settings)

    if asset_kind is AssetKind.FII and fii is not None:
        methods = _fii_fair_values(fii, settings)
    elif fundamentals is not None:
        methods = _stock_fair_values(
            fundamentals, price, sector, r, peer_multiples
        )
    else:
        methods = {}

    if not methods:
        return Valuation(required_margin_of_safety=round(req_mos, 4))

    values = sorted(methods.values())
    fair_mid = round(statistics.median(values), 2)
    mos = (fair_mid - price) / fair_mid if fair_mid > 0 else None
    return Valuation(
        fair_value_low=values[0],
        fair_value_mid=fair_mid,
        fair_value_high=values[-1],
        method_breakdown=methods,
        margin_of_safety=round(mos, 4) if mos is not None else None,
        required_margin_of_safety=round(req_mos, 4),
        buy_zone_price=round(fair_mid * (1 - req_mos), 2),
    )
