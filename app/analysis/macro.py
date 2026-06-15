"""Macro / duration risk penalty.

A long-duration paper locks the investor into today's macro scenario. Even when
held to maturity, the longer the duration the greater the exposure to a change
in the rate/inflation outlook (and the higher the opportunity cost if the
scenario turns). The penalty scales with modified duration and the dispersion
of the market's forward rate path (Focus).
"""

from __future__ import annotations

from app.models import DurationMetrics, MarketContext

# Converts (modified_duration x uncertainty) into penalty points.
_SCALE = 8.0
_MAX_PENALTY = 40.0


def macro_penalty(
    duration: DurationMetrics,
    context: MarketContext,
    weight: float = 1.0,
) -> float:
    """Return a 0..40 macro-risk penalty for a paper's duration."""
    uncertainty = max(context.rate_path_uncertainty, 0.05)
    raw = duration.modified * uncertainty * _SCALE * max(weight, 0.0)
    return round(min(raw, _MAX_PENALTY), 2)
