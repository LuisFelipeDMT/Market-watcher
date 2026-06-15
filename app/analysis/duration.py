"""Duration / interest-rate sensitivity of a paper.

Macaulay duration is the PV-weighted average time to cash flows; modified
duration approximates the % price change per 1 percentage-point move in rates;
DV01 is the price change (per 100 of face) for a 1 basis-point move. Longer
duration => more exposure to a change in the macro/rate scenario.
"""

from __future__ import annotations

from app.analysis.yields import BenchmarkRates, gross_annual_yield
from app.models import DurationMetrics, IndexType, Offer

# Post-fixed (floating) papers reprice to the index continuously, so their
# price barely reacts to rate moves — duration ≈ time to next reset (~0).
_FLOATING_INDEX = {IndexType.CDI, IndexType.SELIC}


def compute_duration(offer: Offer, ctx: BenchmarkRates) -> DurationMetrics:
    """Estimate duration metrics for an offer held to maturity."""
    if offer.index_type in _FLOATING_INDEX:
        # Effectively no interest-rate (marcação a mercado) sensitivity.
        return DurationMetrics(macaulay=0.1, modified=0.1, dv01=0.001)

    years = max(offer.years_to_maturity, 0.01)
    ytm = gross_annual_yield(offer, ctx) / 100.0
    if ytm <= -0.99:
        ytm = 0.0001

    coupon = (offer.coupon_rate or 0.0) / 100.0
    face = 100.0

    if coupon <= 0:
        # Zero-coupon / bullet: single cash flow at maturity.
        price = face / (1.0 + ytm) ** years
        macaulay = years
    else:
        # Annual coupons + principal at maturity.
        n = max(int(round(years)), 1)
        cash_flows = [(t, coupon * face) for t in range(1, n + 1)]
        cash_flows[-1] = (n, coupon * face + face)
        pv_total = 0.0
        weighted = 0.0
        for t, cf in cash_flows:
            pv = cf / (1.0 + ytm) ** t
            pv_total += pv
            weighted += t * pv
        price = pv_total
        macaulay = weighted / pv_total if pv_total else years

    modified = macaulay / (1.0 + ytm)
    dv01 = modified * price * 0.0001
    return DurationMetrics(
        macaulay=round(macaulay, 4),
        modified=round(modified, 4),
        dv01=round(dv01, 6),
    )
