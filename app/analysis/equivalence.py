"""Cross-index equivalence for fixed-income papers.

Papers quote on different bases — prefixado (PRE), % of CDI, IPCA+spread,
Selic+spread — which makes them hard to compare. This converts any quote to a
common **nominal annual gross yield** using the current market rates, then
re-expresses it in every basis, so you can ask "this IPCA+6% — what prefixado /
% of CDI is that equivalent to?".

Conventions: CDI papers earn a percentage of the CDI accrual; IPCA/Selic papers
compound a real spread on top of the index. IPCA conversions can use either the
spot IPCA or the forward (Focus) expectation, which matters for IPCA+ papers.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.models import IndexType, MarketContext, Offer


class IndexEquivalence(BaseModel):
    input_index: str
    input_rate: float
    nominal_annual: float  # gross nominal % a.a.
    as_pre: float  # equivalent prefixado % a.a.
    as_cdi_pct: float  # equivalent % of CDI
    as_ipca_spread: float  # equivalent IPCA + x
    as_selic_spread: float  # equivalent Selic + x
    ipca_assumed: float
    cdi: float
    selic: float
    basis: str  # "current" | "expected_ipca"


def expected_ipca(context: MarketContext) -> float:
    """Forward IPCA from Focus (next year) if available, else spot."""
    yr = date.today().year + 1
    for f in context.focus:
        if f.indicator.lower() == "ipca" and f.reference_year == yr:
            return f.median
    return context.ipca_annual


def nominal_gross(
    index_type: IndexType, rate: float, context: MarketContext,
    use_expected_ipca: bool = False,
) -> float:
    """Convert a quote on any index to a nominal annual gross yield (%)."""
    cdi = context.cdi_annual
    selic = context.selic_annual
    ipca = expected_ipca(context) if use_expected_ipca else context.ipca_annual
    if index_type is IndexType.PRE:
        return rate
    if index_type is IndexType.CDI:
        return rate / 100.0 * cdi
    if index_type is IndexType.IPCA:
        return ((1 + ipca / 100.0) * (1 + rate / 100.0) - 1) * 100.0
    if index_type is IndexType.SELIC:
        return ((1 + selic / 100.0) * (1 + rate / 100.0) - 1) * 100.0
    return rate


def equivalents(
    index_type: IndexType, rate: float, context: MarketContext,
    use_expected_ipca: bool = False,
) -> IndexEquivalence:
    """Express a quote as the equivalent rate in every index basis."""
    cdi = context.cdi_annual
    selic = context.selic_annual
    ipca = expected_ipca(context) if use_expected_ipca else context.ipca_annual
    nominal = nominal_gross(index_type, rate, context, use_expected_ipca)

    as_cdi = nominal / cdi * 100.0 if cdi else 0.0
    as_ipca = ((1 + nominal / 100.0) / (1 + ipca / 100.0) - 1) * 100.0
    as_selic = ((1 + nominal / 100.0) / (1 + selic / 100.0) - 1) * 100.0

    return IndexEquivalence(
        input_index=index_type.value,
        input_rate=rate,
        nominal_annual=round(nominal, 4),
        as_pre=round(nominal, 4),
        as_cdi_pct=round(as_cdi, 2),
        as_ipca_spread=round(as_ipca, 4),
        as_selic_spread=round(as_selic, 4),
        ipca_assumed=round(ipca, 4),
        cdi=cdi,
        selic=selic,
        basis="expected_ipca" if use_expected_ipca else "current",
    )


def offer_equivalence(
    offer: Offer, context: MarketContext, use_expected_ipca: bool = False
) -> IndexEquivalence:
    """Equivalence for an offer using its effective (buy) rate."""
    return equivalents(offer.index_type, offer.effective_rate, context, use_expected_ipca)
