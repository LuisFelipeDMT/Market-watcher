"""Extract metric points from the engines' evaluated state."""

from __future__ import annotations

from app.equities.models import EquityOpportunity
from app.history.store import MetricPoint
from app.models import Opportunity


def metrics_from_bonds(opportunities: list[Opportunity]) -> list[MetricPoint]:
    """Record yield + score per offer so we can spot relative cheapness later."""
    points: list[MetricPoint] = []
    for o in opportunities:
        points.append(MetricPoint(metric="bond.net_ytm", key=o.offer.id, value=o.net_ytm))
        points.append(
            MetricPoint(metric="bond.score", key=o.offer.id, value=o.opportunity_score)
        )
        if o.cheapness_bps:
            points.append(
                MetricPoint(metric="bond.cheapness_bps", key=o.offer.id, value=o.cheapness_bps)
            )
    return points


def metrics_from_equities(opportunities: list[EquityOpportunity]) -> list[MetricPoint]:
    """Record price + score per ticker for trend/norm comparisons."""
    points: list[MetricPoint] = []
    for o in opportunities:
        points.append(MetricPoint(metric="equity.price", key=o.ticker, value=o.stock.price))
        points.append(
            MetricPoint(metric="equity.score", key=o.ticker, value=o.opportunity_score)
        )
        if o.valuation.margin_of_safety is not None:
            points.append(
                MetricPoint(
                    metric="equity.mos", key=o.ticker, value=o.valuation.margin_of_safety
                )
            )
    return points
