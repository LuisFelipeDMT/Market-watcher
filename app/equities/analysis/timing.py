"""The two-stage state machine: fundamentals arm, timing triggers.

    REJECTED  ← red flag / low quality / cannot value
    WATCH     → good business, not cheap enough yet (wait for a lower price)
    ARMED     → cheap enough on valuation, waiting for the technical entry
    TRIGGERED → in the buy zone AND the timing signals say "now"

This is a pure decision function; persistence of the previous state (to detect
fresh transitions) lives in :mod:`app.equities.watchlist`.
"""

from __future__ import annotations

from app.config import Settings
from app.equities.models import (
    TechnicalSignals,
    Valuation,
    WatchState,
)


def decide_state(
    quality_score: float,
    valuation: Valuation,
    technical: TechnicalSignals,
    disqualified: bool,
    settings: Settings,
) -> tuple[WatchState, list[str]]:
    """Return the pipeline state and the reasons that produced it."""
    reasons: list[str] = []

    if disqualified:
        return WatchState.REJECTED, reasons

    if valuation.fair_value_mid is None or valuation.margin_of_safety is None:
        reasons.append("Cannot value with available data")
        return WatchState.REJECTED, reasons

    if quality_score < settings.equity_quality_min:
        reasons.append(
            f"Quality {quality_score:.0f} < {settings.equity_quality_min:.0f}"
        )
        return WatchState.REJECTED, reasons

    mos = valuation.margin_of_safety
    if mos < valuation.required_margin_of_safety:
        reasons.append(
            f"Wait for price: MoS {mos * 100:.0f}% < required "
            f"{valuation.required_margin_of_safety * 100:.0f}%"
        )
        return WatchState.WATCH, reasons

    # Valuation buy condition met — now it is a timing question.
    if technical.entry_score >= settings.equity_entry_min:
        reasons.append(
            f"In buy zone (MoS {mos * 100:.0f}%) and entry signal "
            f"{technical.entry_score:.0f} — buy now"
        )
        return WatchState.TRIGGERED, reasons

    reasons.append(
        f"Armed (MoS {mos * 100:.0f}%); waiting for entry "
        f"({technical.entry_score:.0f} < {settings.equity_entry_min:.0f})"
    )
    return WatchState.ARMED, reasons
