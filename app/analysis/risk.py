"""Risk scoring for fixed-income offers.

Produces a 0-100 risk score (0 = safest, 100 = riskiest) from weighted
factors: issuer credit rating, market-analysis signals about the institution,
product type, time to maturity, liquidity, and FGC coverage.
"""

from __future__ import annotations

from app.models import (
    DurationMetrics,
    InstitutionHealth,
    Liquidity,
    Offer,
    ProductType,
    RiskAssessment,
)

# Credit rating -> base credit risk on a 0..100 scale.
_RATING_RISK: dict[str, float] = {
    "AAA": 2,
    "AA+": 6,
    "AA": 10,
    "AA-": 14,
    "A+": 18,
    "A": 23,
    "A-": 28,
    "BBB+": 36,
    "BBB": 44,
    "BBB-": 52,
    "BB+": 62,
    "BB": 70,
    "BB-": 76,
    "B": 84,
    "C": 92,
    "D": 100,
}

# Base product risk (before FGC reduction).
_PRODUCT_RISK: dict[ProductType, float] = {
    ProductType.TESOURO: 0,
    ProductType.CDB: 12,
    ProductType.LCI: 12,
    ProductType.LCA: 12,
    ProductType.LC: 18,
    ProductType.DEBENTURE: 28,
    ProductType.CRI: 32,
    ProductType.CRA: 32,
}

_LIQUIDITY_RISK: dict[Liquidity, float] = {
    Liquidity.DAILY: 0,
    Liquidity.SCHEDULED: 30,
    Liquidity.AT_MATURITY: 50,
}

# Weights for the blended score (excluding the FGC reduction).
_W_RATING = 0.35
_W_INSTITUTION = 0.25
_W_PRODUCT = 0.12
_W_MATURITY = 0.06
_W_LIQUIDITY = 0.07
_W_DURATION = 0.15  # interest-rate (marcação a mercado) sensitivity

# Points subtracted when the paper is covered by the FGC (up to R$250k).
_FGC_REDUCTION = 12.0

# FGC only protects up to R$250k per CPF per institution.
_FGC_CEILING = 250_000.0


def _rating_risk(rating: str | None) -> float:
    if not rating:
        return 50.0  # unknown rating -> neutral/cautious
    return _RATING_RISK.get(rating.upper(), 50.0)


def _institution_risk(health: InstitutionHealth, flags: list[str]) -> float:
    if health.under_intervention:
        flags.append("Issuer under BACEN intervention/liquidation")
        return 100.0
    risk = 0.0
    if health.negative_news:
        flags.append("Adverse news/sentiment about issuer")
        risk += 35.0
    if health.basel_index is not None and health.basel_index < 12.0:
        flags.append(f"Low Basileia index ({health.basel_index:.1f}%)")
        risk += (12.0 - health.basel_index) * 5.0
    return min(risk, 100.0)


def assess_risk(
    offer: Offer,
    health: InstitutionHealth,
    duration: DurationMetrics | None = None,
) -> RiskAssessment:
    """Score the risk of an offer given its issuer's health and duration."""
    flags: list[str] = []

    # Prefer the issuer-level rating; fall back to the offer's own rating.
    rating = health.rating or offer.rating
    rating_risk = _rating_risk(rating)
    if rating_risk >= 52:
        flags.append(f"Sub-investment-grade rating ({rating or 'N/A'})")

    product_risk = _PRODUCT_RISK.get(offer.product_type, 25.0)

    maturity_risk = min(offer.years_to_maturity / 10.0, 1.0) * 100.0
    if offer.years_to_maturity >= 6:
        flags.append(f"Long maturity ({offer.years_to_maturity:.1f}y)")

    liquidity_risk = _LIQUIDITY_RISK.get(offer.liquidity, 40.0)
    if offer.liquidity is Liquidity.AT_MATURITY:
        flags.append("No daily liquidity (resgate only at maturity)")

    institution_risk = _institution_risk(health, flags)

    # Duration risk: modified duration scaled (10y+ modified -> 100).
    modified = duration.modified if duration is not None else offer.years_to_maturity
    duration_risk = min(modified / 10.0, 1.0) * 100.0
    if modified >= 6:
        flags.append(f"High duration ({modified:.1f}) — rate-sensitive")

    fgc_reduction = 0.0
    if offer.fgc_eligible and offer.min_investment <= _FGC_CEILING:
        fgc_reduction = _FGC_REDUCTION
    elif not offer.fgc_eligible and offer.product_type is not ProductType.TESOURO:
        flags.append("No FGC coverage")

    blended = (
        _W_RATING * rating_risk
        + _W_INSTITUTION * institution_risk
        + _W_PRODUCT * product_risk
        + _W_MATURITY * maturity_risk
        + _W_LIQUIDITY * liquidity_risk
        + _W_DURATION * duration_risk
    )
    score = max(0.0, min(100.0, blended - fgc_reduction))

    return RiskAssessment(
        score=round(score, 2),
        rating_factor=round(_W_RATING * rating_risk, 2),
        product_factor=round(_W_PRODUCT * product_risk, 2),
        fgc_factor=round(-fgc_reduction, 2),
        maturity_factor=round(_W_MATURITY * maturity_risk, 2),
        liquidity_factor=round(_W_LIQUIDITY * liquidity_risk, 2),
        institution_factor=round(_W_INSTITUTION * institution_risk, 2),
        duration_factor=round(_W_DURATION * duration_risk, 2),
        flags=flags,
    )
