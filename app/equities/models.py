"""Domain models for renda variável (equities): stocks and FIIs.

Mirrors the renda fixa models in :mod:`app.models.offer` but for the
two-stage equity flow: fundamentals select the company (quality + value +
margin of safety) and a per-ticker timing state machine waits for the price
to enter the buy zone.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, computed_field


class AssetKind(str, Enum):
    """What kind of listed asset this is."""

    STOCK = "STOCK"  # ação
    FII = "FII"  # fundo de investimento imobiliário


class WatchState(str, Enum):
    """State of a ticker in the two-stage pipeline.

    The fundamentals arm a name; the price/timing engine triggers it.
    """

    WATCH = "WATCH"  # good company, not cheap enough yet (wait for price)
    ARMED = "ARMED"  # cheap enough on valuation, waiting for the timing signal
    TRIGGERED = "TRIGGERED"  # in the buy zone AND technicals say "now"
    REJECTED = "REJECTED"  # disqualified (low quality / red flag / unvaluable)


class Stock(BaseModel):
    """Identity + last price for a listed asset."""

    ticker: str
    name: str
    asset_kind: AssetKind = AssetKind.STOCK
    sector: Optional[str] = None
    price: float
    market_cap: Optional[float] = None
    # Trailing daily closes (oldest..newest), used for the technical engine.
    price_history: list[float] = Field(default_factory=list)
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class Fundamentals(BaseModel):
    """Per-share fundamentals + quality/value ratios (stocks).

    All fields optional so partial data from a flaky source still flows; the
    scoring/valuation code degrades gracefully when an input is missing.
    """

    eps: Optional[float] = None  # lucro por ação (TTM)
    bvps: Optional[float] = None  # valor patrimonial por ação (VPA)
    dps: Optional[float] = None  # dividendos por ação (TTM)
    fcf_per_share: Optional[float] = None  # free cash flow per share (TTM)

    roe: Optional[float] = None  # %
    roic: Optional[float] = None  # %
    gross_margin: Optional[float] = None  # %
    ebit_margin: Optional[float] = None  # %
    net_margin: Optional[float] = None  # %
    net_debt_ebitda: Optional[float] = None  # x (negative = net cash)
    current_ratio: Optional[float] = None  # x

    revenue_cagr_5y: Optional[float] = None  # %
    earnings_cagr_5y: Optional[float] = None  # %
    # Fraction of the last 5 years with positive earnings (0..1).
    earnings_consistency: Optional[float] = None
    # Share-count growth over 5y (dilution); negative = buybacks.
    shares_cagr_5y: Optional[float] = None

    payout: Optional[float] = None  # dividend payout ratio (0..1)

    # Trading multiples (as reported by the source).
    pl: Optional[float] = None  # P/L
    pvp: Optional[float] = None  # P/VP
    ev_ebitda: Optional[float] = None
    dy: Optional[float] = None  # dividend yield (0..1)
    fcf_yield: Optional[float] = None  # 0..1


class FiiMetrics(BaseModel):
    """FII-specific metrics used for quality + valuation."""

    dps: Optional[float] = None  # dividendos por cota (TTM)
    nav_per_share: Optional[float] = None  # valor patrimonial por cota (VPA)
    p_vp: Optional[float] = None  # preço / valor patrimonial
    dy: Optional[float] = None  # dividend yield (0..1)
    vacancy: Optional[float] = None  # vacância física/financeira (0..1)
    segment: Optional[str] = None  # logística, lajes, shoppings, papel, híbrido
    n_assets: Optional[int] = None  # number of properties / diversification
    management_fee: Optional[float] = None  # taxa de administração (0..1)


class Valuation(BaseModel):
    """Fair-value ensemble + margin of safety + the buy-zone trigger price."""

    fair_value_low: Optional[float] = None
    fair_value_mid: Optional[float] = None
    fair_value_high: Optional[float] = None
    # method name -> estimated fair value per share
    method_breakdown: dict[str, float] = Field(default_factory=dict)
    # (fair_mid - price) / fair_mid; >0 means trading below fair value.
    margin_of_safety: Optional[float] = None
    # MoS demanded before arming (macro-adjusted).
    required_margin_of_safety: float = 0.0
    # price at/below which the valuation buy condition is met.
    buy_zone_price: Optional[float] = None


class TechnicalSignals(BaseModel):
    """Price/timing signals — the second stage ("the right moment")."""

    drawdown_from_high_52w: Optional[float] = None  # 0..1 (0.30 = -30%)
    rsi_14: Optional[float] = None  # 0..100
    sma50: Optional[float] = None
    sma200: Optional[float] = None
    price_vs_sma50: Optional[float] = None  # (price-sma)/sma
    near_support: bool = False
    # 0..100 blended "is this a good entry moment" score.
    entry_score: float = 0.0


class EquityOpportunity(BaseModel):
    """A fully evaluated equity: fundamentals + valuation + timing + state."""

    stock: Stock
    fundamentals: Optional[Fundamentals] = None
    fii: Optional[FiiMetrics] = None
    valuation: Valuation
    technical: TechnicalSignals

    quality_score: float  # 0..100
    value_score: float  # 0..100
    opportunity_score: float  # 0..100 (blended, gated by red flags)

    state: WatchState
    is_opportunity: bool  # True only when TRIGGERED
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ticker(self) -> str:
        return self.stock.ticker
