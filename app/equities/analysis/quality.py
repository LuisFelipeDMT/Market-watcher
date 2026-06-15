"""Quality scoring — "is this a good business?" (stage 1).

Stocks are scored on profitability, margins, leverage, liquidity, earnings
consistency/growth and shareholder dilution. FIIs are scored on vacancy,
diversification, price-to-NAV reasonableness and fee drag. Both return a 0..100
score plus the human-readable reasons that drove it.
"""

from __future__ import annotations

from app.equities.models import FiiMetrics, Fundamentals


def _band(value: float | None, low: float, high: float) -> float:
    """Map ``value`` onto 0..1 between ``low`` (=0) and ``high`` (=1)."""
    if value is None:
        return 0.5  # neutral when unknown
    if high == low:
        return 0.5
    return max(0.0, min(1.0, (value - low) / (high - low)))


def stock_quality(f: Fundamentals) -> tuple[float, list[str]]:
    """Score a stock's business quality (0..100)."""
    reasons: list[str] = []

    # Weighted components, each scored 0..1.
    roe = _band(f.roe, 5, 25)
    roic = _band(f.roic, 5, 20)
    margin = _band(f.net_margin, 2, 25)
    # Lower leverage is better: invert net_debt/ebitda (3x=0, 0x=1).
    leverage = 1.0 - _band(f.net_debt_ebitda, 0.0, 3.0)
    liquidity = _band(f.current_ratio, 0.8, 2.0)
    consistency = f.earnings_consistency if f.earnings_consistency is not None else 0.5
    growth = _band(f.earnings_cagr_5y, 0, 15)
    # Dilution: buybacks (negative cagr) good, issuance bad.
    dilution = 1.0 - _band(f.shares_cagr_5y, 0.0, 5.0)

    components = {
        "roe": (roe, 0.18),
        "roic": (roic, 0.18),
        "margin": (margin, 0.12),
        "leverage": (leverage, 0.14),
        "liquidity": (liquidity, 0.08),
        "consistency": (consistency, 0.12),
        "growth": (growth, 0.10),
        "dilution": (dilution, 0.08),
    }
    score = sum(val * weight for val, weight in components.values()) * 100.0

    if f.roe is not None and f.roe >= 18:
        reasons.append(f"High ROE {f.roe:.0f}%")
    if f.roic is not None and f.roic >= 15:
        reasons.append(f"Strong ROIC {f.roic:.0f}%")
    if f.net_debt_ebitda is not None and f.net_debt_ebitda <= 1.0:
        reasons.append(f"Low leverage (net debt/EBITDA {f.net_debt_ebitda:.1f}x)")
    if f.earnings_consistency is not None and f.earnings_consistency >= 0.8:
        reasons.append("Consistent earnings (5y)")
    if f.shares_cagr_5y is not None and f.shares_cagr_5y < 0:
        reasons.append("Net buybacks (no dilution)")
    return round(score, 2), reasons


def fii_quality(m: FiiMetrics) -> tuple[float, list[str]]:
    """Score a FII's quality (0..100)."""
    reasons: list[str] = []

    occupancy = 1.0 - _band(m.vacancy, 0.0, 0.20)  # low vacancy is good
    diversification = _band(float(m.n_assets) if m.n_assets else None, 1, 25)
    # P/VP near or below 1 is healthier than a big premium.
    pvp_quality = 1.0 - _band(m.p_vp, 0.9, 1.4)
    fee = 1.0 - _band(m.management_fee, 0.005, 0.015)  # lower fee better
    yield_q = _band(m.dy, 0.05, 0.12)

    components = {
        "occupancy": (occupancy, 0.32),
        "diversification": (diversification, 0.22),
        "pvp": (pvp_quality, 0.20),
        "fee": (fee, 0.10),
        "yield": (yield_q, 0.16),
    }
    score = sum(val * weight for val, weight in components.values()) * 100.0

    if m.vacancy is not None and m.vacancy <= 0.05:
        reasons.append(f"Low vacancy {m.vacancy * 100:.0f}%")
    if m.n_assets is not None and m.n_assets >= 15:
        reasons.append(f"Diversified ({m.n_assets} assets)")
    if m.dy is not None and m.dy >= 0.08:
        reasons.append(f"Dividend yield {m.dy * 100:.1f}%")
    if m.p_vp is not None and m.p_vp <= 1.0:
        reasons.append(f"Trading at/below NAV (P/VP {m.p_vp:.2f})")
    return round(score, 2), reasons
