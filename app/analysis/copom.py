"""Copom-aware macro view: rate direction → duration posture.

Reads the Selic path from the BCB Focus expectations in the MarketContext and
turns it into a plain-language posture: when cuts are expected, locking in long
prefixados/IPCA+ is attractive; when hikes are expected, stay short/pós-fixado.
Also surfaces the expected IPCA so IPCA+ real yields can be judged in context.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models import MarketContext


class MacroView(BaseModel):
    selic_now: float
    selic_next_year: float | None = None
    expected_ipca: float | None = None
    direction: str  # "CUTTING" | "HIKING" | "HOLD"
    duration_posture: str
    rationale: str
    notes: list[str] = Field(default_factory=list)


def _focus_median(context: MarketContext, indicator: str, year: int) -> float | None:
    for f in context.focus:
        if f.indicator.lower() == indicator.lower() and f.reference_year == year:
            return f.median
    return None


def macro_view(context: MarketContext) -> MacroView:
    """Derive the rate-direction view and a duration posture."""
    now = context.selic_annual
    from datetime import date

    next_year = date.today().year + 1
    selic_next = _focus_median(context, "Selic", next_year)
    ipca_next = _focus_median(context, "IPCA", next_year)

    notes: list[str] = []
    if selic_next is None:
        direction = "HOLD"
        posture = "Neutral duration — no forward Selic path available"
        rationale = "Focus Selic expectation missing; defaulting to neutral."
    else:
        delta = selic_next - now
        if delta <= -0.25:
            direction = "CUTTING"
            posture = "Favour longer duration (prefixado / IPCA+) to lock current rates"
            rationale = (
                f"Selic seen at {selic_next:.2f}% next year vs {now:.2f}% now "
                f"({delta:+.2f} pp) — cuts reward locked-in long rates."
            )
        elif delta >= 0.25:
            direction = "HIKING"
            posture = "Stay short / pós-fixado (CDI/Selic); avoid long prefixado"
            rationale = (
                f"Selic seen at {selic_next:.2f}% next year vs {now:.2f}% now "
                f"({delta:+.2f} pp) — hikes punish long fixed rates."
            )
        else:
            direction = "HOLD"
            posture = "Balanced; modest duration, ladder maturities"
            rationale = (
                f"Selic broadly stable ({now:.2f}% → {selic_next:.2f}%); no strong "
                "duration tilt."
            )

    if context.rate_path_uncertainty >= 0.4:
        notes.append("High rate-path uncertainty — size duration bets smaller.")
    if ipca_next is not None:
        notes.append(
            f"Expected IPCA {ipca_next:.2f}% — judge IPCA+ real yields against it."
        )

    return MacroView(
        selic_now=now,
        selic_next_year=selic_next,
        expected_ipca=ipca_next,
        direction=direction,
        duration_posture=posture,
        rationale=rationale,
        notes=notes,
    )
