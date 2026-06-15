"""Turn raw offers into evaluated opportunities.

An offer is flagged as an opportunity when it is attractively priced on a
risk-adjusted basis AND there are no disqualifying signs about the issuing
institution. The opportunity score blends a reward component (net yield vs
CDI) with the risk score.
"""

from __future__ import annotations

from app.analysis.institution import get_institution_health
from app.analysis.risk import assess_risk
from app.analysis.yields import normalize_yield
from app.config import Settings
from app.models import Offer, Opportunity

# Net-yield / CDI ratios that map to reward 0 and 100 respectively.
# Net-of-tax yields are compared against the gross CDI benchmark, so a taxed
# paper that nets ~CDI (i.e. pays well above 100% CDI gross) is already strong.
_REWARD_FLOOR = 0.75
_REWARD_CAP = 1.05

# How much risk discounts the reward (0..1). 0.6 => max 60% haircut.
_RISK_PENALTY_WEIGHT = 0.6

# An offer above this risk score is never flagged, regardless of yield.
_MAX_RISK_FOR_OPPORTUNITY = 60.0


def _reward_score(net_yield: float, settings: Settings) -> float:
    if settings.cdi_annual <= 0:
        return 0.0
    ratio = net_yield / settings.cdi_annual
    pct = (ratio - _REWARD_FLOOR) / (_REWARD_CAP - _REWARD_FLOOR) * 100.0
    return max(0.0, min(100.0, pct))


def evaluate_offer(offer: Offer, settings: Settings) -> Opportunity:
    """Evaluate a single offer into an :class:`Opportunity`."""
    health = get_institution_health(offer.issuer, offer.rating)
    risk = assess_risk(offer, health)
    gross, net, pct_of_cdi = normalize_yield(offer, settings)

    reward = _reward_score(net, settings)
    score = reward * (1.0 - _RISK_PENALTY_WEIGHT * (risk.score / 100.0))
    score = round(max(0.0, min(100.0, score)), 2)

    reasons: list[str] = []
    disqualified = False

    if health.under_intervention:
        reasons.append("Disqualified: issuer under BACEN intervention")
        disqualified = True
    if health.negative_news:
        reasons.append("Disqualified: adverse news/sentiment about issuer")
        disqualified = True
    if risk.score > _MAX_RISK_FOR_OPPORTUNITY:
        reasons.append(f"Disqualified: risk score too high ({risk.score})")
        disqualified = True

    is_opportunity = (
        not disqualified and score >= settings.opportunity_threshold
    )

    if is_opportunity:
        exempt = " (IR-exempt)" if offer.tax_exempt else ""
        reasons.append(
            f"Net yield {net:.2f}% ({pct_of_cdi:.0f}% of CDI){exempt}"
        )
        reasons.append(f"Risk score {risk.score} ({health.rating or 'N/R'})")
        if offer.fgc_eligible:
            reasons.append("FGC-covered")
    elif not disqualified:
        reasons.append(
            f"Below threshold: score {score} < {settings.opportunity_threshold}"
        )

    return Opportunity(
        offer=offer,
        institution=health,
        risk=risk,
        normalized_gross_yield=gross,
        normalized_net_yield=net,
        yield_pct_of_cdi=pct_of_cdi,
        opportunity_score=score,
        is_opportunity=is_opportunity,
        reasons=reasons,
    )


def evaluate_offers(
    offers: list[Offer], settings: Settings
) -> list[Opportunity]:
    """Evaluate and rank a list of offers (best opportunity first)."""
    evaluated = [evaluate_offer(o, settings) for o in offers]
    evaluated.sort(key=lambda o: o.opportunity_score, reverse=True)
    return evaluated
