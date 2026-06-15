"""Normalize heterogeneous offer rates into comparable annual yields.

Different index types quote their rate differently (a % of CDI, a spread over
IPCA, a flat prefixado rate...). To rank them on one scale we convert each to
an estimated gross annual yield using current benchmark rates, then to a net
(after-IR/IOF) yield using the regressive income-tax table.

The ``ctx`` argument is any object exposing ``cdi_annual``/``selic_annual``/
``ipca_annual`` — both :class:`Settings` and :class:`MarketContext` qualify, so
callers can pass live market data or fall back to static settings.
"""

from __future__ import annotations

from typing import Protocol

from app.models import IndexType, Offer


class BenchmarkRates(Protocol):
    cdi_annual: float
    selic_annual: float
    ipca_annual: float


def income_tax_rate(days_to_maturity: int) -> float:
    """Brazil's regressive IR table for fixed income (fraction, e.g. 0.15).

    The longer the commitment, the lower the tax — the core reason a
    buy-and-hold investor favours longer papers.
    """
    if days_to_maturity <= 180:
        return 0.225
    if days_to_maturity <= 360:
        return 0.20
    if days_to_maturity <= 720:
        return 0.175
    return 0.15


def iof_factor(days_held: int) -> float:
    """Fraction of yield taken by IOF; only bites in the first 30 days.

    Returns 0.0 for any holding of 30 days or more (the buy-and-hold case).
    """
    if days_held >= 30:
        return 0.0
    # Regressive IOF table: ~96% on day 1 down to ~3% on day 29, 0% from day 30.
    return round(max(0.0, (30 - days_held) / 30.0), 4)


def gross_annual_yield(offer: Offer, ctx: BenchmarkRates) -> float:
    """Estimated gross annual yield (%) for an offer.

    Uses the offer's effective rate (the secondary ``offered_ytm`` when set).
    """
    rate = offer.effective_rate
    if offer.index_type is IndexType.PRE:
        value = rate
    elif offer.index_type is IndexType.CDI:
        value = rate / 100.0 * ctx.cdi_annual
    elif offer.index_type is IndexType.IPCA:
        value = ctx.ipca_annual + rate
    elif offer.index_type is IndexType.SELIC:
        value = ctx.selic_annual + rate
    else:
        value = rate
    return round(value, 6)


def net_annual_yield(offer: Offer, ctx: BenchmarkRates) -> float:
    """Gross yield net of IR (exemption-aware), for held-to-maturity."""
    gross = gross_annual_yield(offer, ctx)
    if offer.tax_exempt:
        return round(gross, 4)
    return round(gross * (1.0 - income_tax_rate(offer.days_to_maturity)), 4)


def net_ytm(offer: Offer, ctx: BenchmarkRates) -> float:
    """Net yield-to-maturity for a buy-and-hold investor (IR + IOF aware)."""
    gross = gross_annual_yield(offer, ctx)
    if offer.tax_exempt:
        ir = 0.0
    else:
        ir = income_tax_rate(offer.days_to_maturity)
    iof = iof_factor(offer.days_to_maturity)
    return round(gross * (1.0 - ir) * (1.0 - iof), 4)


def normalize_yield(offer: Offer, ctx: BenchmarkRates) -> tuple[float, float, float]:
    """Return ``(gross_annual, net_annual, pct_of_cdi)`` for an offer."""
    gross = gross_annual_yield(offer, ctx)
    net = net_annual_yield(offer, ctx)
    pct_of_cdi = (gross / ctx.cdi_annual * 100.0) if ctx.cdi_annual else 0.0
    return round(gross, 4), round(net, 4), round(pct_of_cdi, 2)
