"""Index-consistent IPCA cheapness via breakeven inflation.

An IPCA+ paper and a prefixado are only comparable once you fix an inflation
assumption. The **breakeven inflation** is the IPCA at which an IPCA+real paper
exactly matches a comparable prefixado; above it the IPCA+ wins, below it the
prefixado wins. We compare each IPCA+ offer's implied nominal (at the forward
Focus IPCA) to the prefixado fair yield for the same risk/tenor.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.analysis.cheapness import reference_ytm
from app.analysis.equivalence import expected_ipca, nominal_gross
from app.analysis.institution import get_institution_health
from app.models import IndexType, MarketContext, Offer


class IpcaView(BaseModel):
    offer_id: str
    issuer: str
    real_spread: float  # IPCA + this
    expected_ipca: float
    implied_nominal: float  # nominal at the expected IPCA
    comparable_pre: float  # prefixado fair yield, same risk/tenor
    cheapness_vs_pre_bps: float  # implied_nominal - comparable_pre, in bps
    breakeven_inflation: float  # IPCA that equalises the two
    verdict: str


def breakeven_inflation(prefixado_pct: float, real_spread_pct: float) -> float:
    """Inflation (%) at which IPCA+real equals a prefixado of ``prefixado_pct``."""
    return ((1 + prefixado_pct / 100.0) / (1 + real_spread_pct / 100.0) - 1) * 100.0


def ipca_view(offer: Offer, context: MarketContext) -> IpcaView:
    """Evaluate one IPCA-indexed offer against the comparable prefixado."""
    real = offer.effective_rate
    exp_ipca = expected_ipca(context)
    implied = nominal_gross(IndexType.IPCA, real, context, use_expected_ipca=True)
    health = get_institution_health(offer.issuer, offer.rating)
    comparable_pre = reference_ytm(offer, context, health)
    cheap_bps = round((implied - comparable_pre) * 100.0, 1)
    be = breakeven_inflation(comparable_pre, real)

    if exp_ipca > be and cheap_bps > 0:
        verdict = "IPCA+ attractive vs prefixado at expected inflation"
    elif cheap_bps < 0:
        verdict = "Prefixado better at expected inflation"
    else:
        verdict = "Roughly fair vs prefixado"

    return IpcaView(
        offer_id=offer.id,
        issuer=offer.issuer,
        real_spread=round(real, 4),
        expected_ipca=round(exp_ipca, 4),
        implied_nominal=round(implied, 4),
        comparable_pre=round(comparable_pre, 4),
        cheapness_vs_pre_bps=cheap_bps,
        breakeven_inflation=round(be, 4),
        verdict=verdict,
    )


def ipca_views(offers: list[Offer], context: MarketContext) -> list[IpcaView]:
    views = [ipca_view(o, context) for o in offers if o.index_type is IndexType.IPCA]
    views.sort(key=lambda v: v.cheapness_vs_pre_bps, reverse=True)
    return views
