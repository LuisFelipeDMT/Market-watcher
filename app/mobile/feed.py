"""Project both engines' outputs onto the unified mobile proposal feed."""

from __future__ import annotations

from app.equities.models import AssetKind, EquityOpportunity, WatchState
from app.mobile.models import AssetClass, Proposal
from app.models import Opportunity


def _bond_proposal(opp: Opportunity) -> Proposal:
    o = opp.offer
    metrics = {
        "Net YTM": f"{opp.net_ytm:.2f}%",
        "% CDI": f"{opp.yield_pct_of_cdi:.0f}%",
        "Risk": f"{opp.risk.score:.0f}",
    }
    if opp.offer.market.value == "SECONDARY" and opp.cheapness_bps > 0:
        metrics["Cheap"] = f"{opp.cheapness_bps:.0f} bps"
    exempt = " · isento IR" if o.tax_exempt else ""
    return Proposal(
        id=f"rf:{o.id}",
        asset_class=AssetClass.RENDA_FIXA,
        title=f"{o.issuer} — {o.product_type.value}",
        subtitle=f"Net YTM {opp.net_ytm:.2f}% ({opp.yield_pct_of_cdi:.0f}% CDI){exempt}",
        score=opp.opportunity_score,
        metrics=metrics,
        reasons=opp.reasons,
        warnings=opp.warnings,
    )


def _equity_proposal(opp: EquityOpportunity) -> Proposal:
    v = opp.valuation
    asset_class = AssetClass.FII if opp.stock.asset_kind is AssetKind.FII else AssetClass.STOCK
    mos = f"{v.margin_of_safety * 100:.0f}%" if v.margin_of_safety is not None else "—"
    fair = f"R${v.fair_value_mid:.2f}" if v.fair_value_mid is not None else "—"
    return Proposal(
        id=f"eq:{opp.ticker}",
        asset_class=asset_class,
        title=f"{opp.ticker} — {opp.stock.name}",
        subtitle=f"R${opp.stock.price:.2f} vs justo {fair} (MoS {mos})",
        score=opp.opportunity_score,
        metrics={
            "Preço": f"R${opp.stock.price:.2f}",
            "Justo": fair,
            "MoS": mos,
            "Qualidade": f"{opp.quality_score:.0f}",
            "Entrada": f"{opp.technical.entry_score:.0f}",
        },
        reasons=opp.reasons,
        warnings=opp.warnings,
    )


def build_proposals(
    bond_opportunities: list[Opportunity],
    equity_opportunities: list[EquityOpportunity],
) -> list[Proposal]:
    """Merge flagged bonds + TRIGGERED equities, ranked best-first."""
    proposals = [
        _bond_proposal(o) for o in bond_opportunities if o.is_opportunity
    ]
    proposals += [
        _equity_proposal(o)
        for o in equity_opportunities
        if o.state is WatchState.TRIGGERED
    ]
    proposals.sort(key=lambda p: p.score, reverse=True)
    return proposals
