"""Technical signals — "is now a good moment?" (stage 2).

From the trailing price history we derive a drawdown from the 52-week high,
RSI(14), moving averages and proximity to support, then blend them into a
single 0..100 ``entry_score``. A high score means the price is depressed/
oversold near support — the moment the fundamentals have been waiting for.
"""

from __future__ import annotations

from app.equities.models import TechnicalSignals


def _sma(prices: list[float], window: int) -> float | None:
    if len(prices) < window:
        return None
    return sum(prices[-window:]) / window


def _rsi(prices: list[float], period: int = 14) -> float | None:
    if len(prices) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for prev, cur in zip(prices[-period - 1 : -1], prices[-period:]):
        change = cur - prev
        if change >= 0:
            gains += change
        else:
            losses -= change
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def compute_technical(price: float, history: list[float]) -> TechnicalSignals:
    """Build the technical/timing signals for one asset."""
    if not history:
        return TechnicalSignals()

    high_52w = max(history[-252:]) if history else price
    drawdown = (high_52w - price) / high_52w if high_52w > 0 else 0.0

    rsi = _rsi(history)
    sma50 = _sma(history, 50)
    sma200 = _sma(history, 200)
    price_vs_sma50 = (price - sma50) / sma50 if sma50 else None

    recent_low = min(history[-60:]) if len(history) >= 1 else price
    near_support = recent_low > 0 and (price - recent_low) / recent_low <= 0.05

    # Blend the components (each 0..1, higher = better entry).
    dd_score = min(max(drawdown, 0.0) / 0.30, 1.0)
    rsi_score = 0.0 if rsi is None else max(0.0, min(1.0, (55 - rsi) / 35))
    trend_score = (
        0.0
        if price_vs_sma50 is None
        else max(0.0, min(1.0, -price_vs_sma50 / 0.15))
    )
    support_score = 1.0 if near_support else 0.0

    entry = (
        0.35 * dd_score
        + 0.35 * rsi_score
        + 0.20 * trend_score
        + 0.10 * support_score
    ) * 100.0

    return TechnicalSignals(
        drawdown_from_high_52w=round(drawdown, 4),
        rsi_14=rsi,
        sma50=round(sma50, 2) if sma50 else None,
        sma200=round(sma200, 2) if sma200 else None,
        price_vs_sma50=round(price_vs_sma50, 4) if price_vs_sma50 is not None else None,
        near_support=near_support,
        entry_score=round(entry, 2),
    )
