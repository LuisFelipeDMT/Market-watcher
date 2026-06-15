"""Value scoring — "is it cheap on its multiples?" (stage 1).

Complements the absolute fair-value ensemble in :mod:`valuation` with a quick
relative read on trading multiples (P/L, P/VP, EV/EBITDA, dividend & FCF
yields). Returns 0..100 where higher = cheaper.
"""

from __future__ import annotations

from app.equities.models import FiiMetrics, Fundamentals


def _cheap_band(value: float | None, cheap: float, rich: float) -> float:
    """Score where ``cheap`` maps to 1.0 and ``rich`` maps to 0.0."""
    if value is None or value <= 0:
        return 0.5
    if cheap == rich:
        return 0.5
    return max(0.0, min(1.0, (rich - value) / (rich - cheap)))


def _high_is_cheap(value: float | None, low: float, high: float) -> float:
    """For yields: a higher number is cheaper."""
    if value is None:
        return 0.5
    if high == low:
        return 0.5
    return max(0.0, min(1.0, (value - low) / (high - low)))


def stock_value(f: Fundamentals) -> tuple[float, list[str]]:
    """Score how cheap a stock looks on its multiples (0..100)."""
    reasons: list[str] = []
    pl = _cheap_band(f.pl, 6, 25)
    pvp = _cheap_band(f.pvp, 0.8, 4.0)
    ev = _cheap_band(f.ev_ebitda, 4, 14)
    dy = _high_is_cheap(f.dy, 0.0, 0.10)
    fcfy = _high_is_cheap(f.fcf_yield, 0.0, 0.12)

    components = {
        "pl": (pl, 0.30),
        "pvp": (pvp, 0.20),
        "ev_ebitda": (ev, 0.15),
        "dy": (dy, 0.20),
        "fcf_yield": (fcfy, 0.15),
    }
    score = sum(val * weight for val, weight in components.values()) * 100.0

    if f.pl is not None and 0 < f.pl <= 10:
        reasons.append(f"Low P/L {f.pl:.1f}")
    if f.dy is not None and f.dy >= 0.06:
        reasons.append(f"Dividend yield {f.dy * 100:.1f}%")
    if f.fcf_yield is not None and f.fcf_yield >= 0.08:
        reasons.append(f"FCF yield {f.fcf_yield * 100:.1f}%")
    return round(score, 2), reasons


def fii_value(m: FiiMetrics) -> tuple[float, list[str]]:
    """Score how cheap a FII looks (0..100)."""
    reasons: list[str] = []
    pvp = _cheap_band(m.p_vp, 0.8, 1.3)
    dy = _high_is_cheap(m.dy, 0.05, 0.13)

    components = {"pvp": (pvp, 0.5), "dy": (dy, 0.5)}
    score = sum(val * weight for val, weight in components.values()) * 100.0

    if m.p_vp is not None and m.p_vp <= 0.95:
        reasons.append(f"Discount to NAV (P/VP {m.p_vp:.2f})")
    if m.dy is not None and m.dy >= 0.09:
        reasons.append(f"Dividend yield {m.dy * 100:.1f}%")
    return round(score, 2), reasons
