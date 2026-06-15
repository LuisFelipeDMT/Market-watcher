"""Normalize heterogeneous offer rates into comparable annual yields.

Different index types quote their rate differently (a % of CDI, a spread over
IPCA, a flat prefixado rate...). To rank them on one scale we convert each to
an estimated gross annual yield using current benchmark assumptions, then to a
net (after-IR) yield using the regressive income-tax table.
"""

from __future__ import annotations

from app.config import Settings
from app.models import IndexType, Offer


def _income_tax_rate(days_to_maturity: int) -> float:
    """Brazil's regressive IR table for fixed income (fraction, e.g. 0.15)."""
    if days_to_maturity <= 180:
        return 0.225
    if days_to_maturity <= 360:
        return 0.20
    if days_to_maturity <= 720:
        return 0.175
    return 0.15


def gross_annual_yield(offer: Offer, settings: Settings) -> float:
    """Estimated gross annual yield (%) for an offer."""
    if offer.index_type is IndexType.PRE:
        value = offer.rate
    elif offer.index_type is IndexType.CDI:
        value = offer.rate / 100.0 * settings.cdi_annual
    elif offer.index_type is IndexType.IPCA:
        value = settings.ipca_annual + offer.rate
    elif offer.index_type is IndexType.SELIC:
        value = settings.selic_annual + offer.rate
    else:
        value = offer.rate
    return round(value, 6)


def normalize_yield(offer: Offer, settings: Settings) -> tuple[float, float, float]:
    """Return ``(gross_annual, net_annual, pct_of_cdi)`` for an offer.

    ``net_annual`` accounts for the tax exemption on incentivized papers
    (LCI/LCA/CRI/CRA and incentivized debentures); otherwise it applies the
    regressive IR rate based on the time to maturity.
    """
    gross = gross_annual_yield(offer, settings)

    if offer.tax_exempt:
        net = gross
    else:
        net = gross * (1.0 - _income_tax_rate(offer.days_to_maturity))

    pct_of_cdi = (gross / settings.cdi_annual * 100.0) if settings.cdi_annual else 0.0
    return round(gross, 4), round(net, 4), round(pct_of_cdi, 2)
