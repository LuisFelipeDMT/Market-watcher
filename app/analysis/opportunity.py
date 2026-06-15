"""Opportunity engine v2: turn offers into evaluated, sized opportunities.

Blends, on a risk-adjusted basis:
  - reward: net yield-to-maturity vs CDI (longer holds => lower IR => first-
    class benefit for buy-and-hold);
  - cheapness: for secondary offers, how far the offered YTM sits above the
    fair reference yield (the deságio / urgency edge);
  - macro penalty: long-duration papers are penalized for scenario risk;
  - position sizing: FGC room per conglomerate and non-FGC diversification.

An offer is flagged only when it clears the score threshold AND has no
disqualifying institution signs and acceptable risk. Sizing/diversification
issues surface as warnings, not hard cuts.
"""

from __future__ import annotations

from app.analysis.cheapness import cheapness_bps
from app.analysis.credit import credit_tier
from app.analysis.duration import compute_duration
from app.analysis.institution import get_institution_health
from app.analysis.macro import macro_penalty
from app.analysis.risk import assess_risk
from app.analysis.yields import net_ytm, normalize_yield
from app.config import Settings
from app.models import (
    NON_FGC_PRODUCTS,
    MarketContext,
    MarketKind,
    Offer,
    Opportunity,
)
from app.portfolio.service import PortfolioService
from app.portfolio.sizing import recommend_size

# Net-yield / CDI ratios that map to reward 0 and 100 respectively.
_REWARD_FLOOR = 0.75
_REWARD_CAP = 1.05

# How much risk discounts the reward (0..1). 0.6 => max 60% haircut.
_RISK_PENALTY_WEIGHT = 0.6

# An offer above this risk score is never flagged, regardless of yield.
_MAX_RISK_FOR_OPPORTUNITY = 60.0

# Caps and weights for the secondary cheapness bonus and macro deduction.
_CHEAPNESS_BONUS_CAP = 25.0
_CHEAPNESS_BONUS_PER_BPS = 0.1  # 250bps cheap -> +25
_MACRO_DEDUCTION_WEIGHT = 0.5


def _reward_score(net_yield: float, cdi_annual: float) -> float:
    if cdi_annual <= 0:
        return 0.0
    ratio = net_yield / cdi_annual
    pct = (ratio - _REWARD_FLOOR) / (_REWARD_CAP - _REWARD_FLOOR) * 100.0
    return max(0.0, min(100.0, pct))


def evaluate_offer(
    offer: Offer,
    context: MarketContext,
    service: PortfolioService,
    settings: Settings,
) -> Opportunity:
    """Evaluate a single offer into an :class:`Opportunity`."""
    health = get_institution_health(offer.issuer, offer.rating)
    duration = compute_duration(offer, context)
    risk = assess_risk(offer, health, duration)

    gross, net, pct_of_cdi = normalize_yield(offer, context)
    nytm = net_ytm(offer, context)
    cheap = cheapness_bps(offer, context, health)
    macro_pen = macro_penalty(duration, context, settings.macro_penalty_weight)

    reward = _reward_score(nytm, context.cdi_annual)
    cheap_bonus = 0.0
    if offer.market is MarketKind.SECONDARY and cheap > 0:
        cheap_bonus = min(cheap * _CHEAPNESS_BONUS_PER_BPS, _CHEAPNESS_BONUS_CAP)

    risk_discount = 1.0 - _RISK_PENALTY_WEIGHT * (risk.score / 100.0)
    score = (reward + cheap_bonus) * risk_discount - macro_pen * _MACRO_DEDUCTION_WEIGHT
    score = round(max(0.0, min(100.0, score)), 2)

    # FGC coverage given the *current* portfolio.
    fgc_now = (
        offer.fgc_eligible
        and offer.product_type not in NON_FGC_PRODUCTS
        and service.fgc_room(offer.issuer) >= offer.min_investment
    )
    sizing = recommend_size(offer, service, settings)

    reasons: list[str] = []
    warnings: list[str] = []
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

    # Soft warnings (do not disqualify).
    if offer.market is MarketKind.SECONDARY and cheap < 0:
        warnings.append(f"Rich vs reference ({cheap:.0f} bps below fair)")
    if sizing.max_recommended <= 0:
        if offer.fgc_eligible and offer.product_type not in NON_FGC_PRODUCTS:
            warnings.append("No FGC room left in this conglomerate")
        else:
            warnings.append("Issuer/sector diversification cap reached")
    if offer.product_type in NON_FGC_PRODUCTS and offer.product_type.value != "TESOURO":
        warnings.append("No FGC — size sparsely across issuers")

    is_opportunity = not disqualified and score >= settings.opportunity_threshold

    if is_opportunity:
        exempt = " (IR-exempt)" if offer.tax_exempt else ""
        reasons.append(f"Net YTM {nytm:.2f}% ({pct_of_cdi:.0f}% of CDI){exempt}")
        reasons.append(f"Risk {risk.score} ({credit_tier(offer, health)})")
        if offer.market is MarketKind.SECONDARY and cheap > 0:
            reasons.append(f"Secondary: {cheap:.0f} bps cheap vs fair")
        if duration.modified >= 4:
            reasons.append(f"Duration {duration.modified:.1f} (macro risk priced in)")
        if fgc_now:
            reasons.append("FGC-covered now")
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
        net_ytm=nytm,
        yield_pct_of_cdi=pct_of_cdi,
        cheapness_bps=cheap,
        duration=duration,
        macro_penalty=macro_pen,
        fgc_covered_now=fgc_now,
        sizing=sizing,
        opportunity_score=score,
        is_opportunity=is_opportunity,
        reasons=reasons,
        warnings=warnings,
    )


def evaluate_offers(
    offers: list[Offer],
    context: MarketContext,
    service: PortfolioService,
    settings: Settings,
) -> list[Opportunity]:
    """Evaluate and rank a list of offers (best opportunity first)."""
    evaluated = [evaluate_offer(o, context, service, settings) for o in offers]
    evaluated.sort(key=lambda o: o.opportunity_score, reverse=True)
    return evaluated
