"""Domain models for renda fixa (fixed income) offers and opportunities."""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, computed_field


class ProductType(str, Enum):
    """Type of fixed-income paper sold on the platform."""

    CDB = "CDB"
    LCI = "LCI"
    LCA = "LCA"
    LC = "LC"  # Letra de Câmbio
    CRI = "CRI"
    CRA = "CRA"
    DEBENTURE = "DEBENTURE"
    TESOURO = "TESOURO"  # Tesouro Direto


class IndexType(str, Enum):
    """How the paper's rate is indexed."""

    PRE = "PRE"  # Prefixado: rate is the full annual yield
    CDI = "CDI"  # Pós-fixado: rate is a percentage of CDI (e.g. 110 = 110% CDI)
    IPCA = "IPCA"  # rate is the spread over IPCA (e.g. 6.0 = IPCA + 6%)
    SELIC = "SELIC"  # rate is the spread over SELIC


class Liquidity(str, Enum):
    """Liquidity profile of the paper."""

    DAILY = "DAILY"  # liquidez diária
    AT_MATURITY = "AT_MATURITY"  # only at vencimento
    SCHEDULED = "SCHEDULED"  # carência then liquidity


class MarketKind(str, Enum):
    """Where the offer comes from."""

    PRIMARY = "PRIMARY"  # new issuance on the shelf
    SECONDARY = "SECONDARY"  # resold by another investor (the user's edge)


# Products that are NOT covered by the FGC and therefore carry pure issuer
# credit risk (handled via diversification rather than the R$250k guarantee).
NON_FGC_PRODUCTS = {
    ProductType.CRI,
    ProductType.CRA,
    ProductType.DEBENTURE,
    ProductType.TESOURO,  # sovereign: no FGC, but lowest credit risk
}


class InstitutionHealth(BaseModel):
    """Market-analysis signals about the issuing institution.

    These feed the "no bad signs about the institution" part of the
    opportunity definition. In mock mode they come from a static registry;
    with a real source they would be enriched from ratings agencies, the
    Banco Central, and news sentiment.
    """

    issuer: str
    rating: Optional[str] = None  # e.g. "AAA", "AA+", "BBB-"
    basel_index: Optional[float] = None  # Índice de Basileia (%), banks
    under_intervention: bool = False  # BACEN intervention / liquidation
    negative_news: bool = False  # adverse press / sentiment flag
    notes: list[str] = Field(default_factory=list)


class Offer(BaseModel):
    """A single fixed-income offer (paper) available on the platform."""

    id: str
    issuer: str
    product_type: ProductType
    index_type: IndexType
    # Meaning depends on index_type (see IndexType docstring). For PRE this is
    # the YTM; for CDI it is % of CDI; for IPCA/SELIC it is the spread.
    rate: float
    maturity: date
    min_investment: float
    liquidity: Liquidity = Liquidity.AT_MATURITY
    fgc_eligible: bool = False  # covered by FGC up to R$250k
    tax_exempt: bool = False  # IR-exempt for individuals (LCI/LCA/CRI/CRA...)
    rating: Optional[str] = None

    # --- secondary-market fields (the mid-day resale edge) -----------------
    market: MarketKind = MarketKind.PRIMARY
    unit_price: Optional[float] = None  # PU offered
    quantity_available: Optional[int] = None  # how many units on offer
    face_value: Optional[float] = None  # PU at maturity / par (for cheapness)
    coupon_rate: Optional[float] = None  # annual coupon %, if it pays coupons
    # The actual buy yield-to-maturity offered for a secondary paper
    # (taxa de compra). For PRE this is the YTM directly; for IPCA/SELIC it is
    # the spread. When set it overrides ``rate`` for yield/cheapness math.
    offered_ytm: Optional[float] = None

    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def days_to_maturity(self) -> int:
        return max((self.maturity - date.today()).days, 0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def years_to_maturity(self) -> float:
        return round(self.days_to_maturity / 365.0, 3)

    @property
    def effective_rate(self) -> float:
        """The rate to use for yield math: secondary YTM if present."""
        return self.offered_ytm if self.offered_ytm is not None else self.rate


class DurationMetrics(BaseModel):
    """Interest-rate sensitivity of a paper."""

    macaulay: float  # years
    modified: float  # %-price change per 1% rate move
    dv01: float  # price change (per 100 face) for a 1bp rate move


class RiskAssessment(BaseModel):
    """Result of scoring the risk of an offer (0 = safest, 100 = riskiest)."""

    score: float  # 0..100
    rating_factor: float
    product_factor: float
    fgc_factor: float
    maturity_factor: float
    liquidity_factor: float
    institution_factor: float
    duration_factor: float = 0.0
    macro_factor: float = 0.0
    flags: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Market context (external reference data)
# --------------------------------------------------------------------------


class FocusExpectation(BaseModel):
    """A forward market expectation point from the BCB Focus survey."""

    indicator: str  # e.g. "Selic", "IPCA"
    reference_year: int
    median: float
    std_dev: Optional[float] = None


class MarketContext(BaseModel):
    """External reference data used to evaluate and normalize offers.

    Sourced from BCB (SGS + Focus), Tesouro Direto and ANBIMA. All rates are
    annual percentages.
    """

    as_of: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "fixtures"

    cdi_annual: float
    selic_annual: float
    ipca_annual: float

    # Forward expectations (Focus) keyed for quick access; raw list kept too.
    focus: list[FocusExpectation] = Field(default_factory=list)
    # Dispersion of the rate path (proxy for macro uncertainty), 0..1-ish.
    rate_path_uncertainty: float = 0.0

    # Risk-free zero curve anchor points: {years: annual_rate_%} from Tesouro.
    risk_free_curve: dict[str, float] = Field(default_factory=dict)
    # Credit spreads over the risk-free curve by credit tier (bps).
    credit_spreads_bps: dict[str, float] = Field(default_factory=dict)


# --------------------------------------------------------------------------
# Portfolio (holdings, FGC exposure, diversification)
# --------------------------------------------------------------------------


class Holding(BaseModel):
    """A current position held by the investor."""

    issuer: str
    conglomerate: str
    product_type: ProductType
    amount: float  # current value in BRL (principal + accrued)
    fgc_eligible: bool = False
    sector: Optional[str] = None


class Portfolio(BaseModel):
    """The investor's current holdings."""

    holdings: list[Holding] = Field(default_factory=list)
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_value(self) -> float:
        return round(sum(h.amount for h in self.holdings), 2)


class PositionSizing(BaseModel):
    """Recommended sizing for a candidate buy, respecting FGC + diversification."""

    fgc_room: Optional[float] = None  # BRL still coverable in the conglomerate
    max_recommended: float  # BRL it is prudent to allocate to this offer
    concentration_pct: float  # resulting issuer concentration (% of portfolio)
    notes: list[str] = Field(default_factory=list)


class Opportunity(BaseModel):
    """An offer evaluated for attractiveness, with derived analytics."""

    offer: Offer
    institution: InstitutionHealth
    risk: RiskAssessment

    # Yield normalized to a comparable gross annual % so different index
    # types can be ranked on the same scale.
    normalized_gross_yield: float
    # Net (after-IR / IOF) normalized annual %, accounting for tax exemption.
    normalized_net_yield: float
    # Net yield-to-maturity for a buy-and-hold investor.
    net_ytm: float
    # Yield expressed as % of CDI for quick comparison.
    yield_pct_of_cdi: float

    # Secondary-market edge: offered YTM minus fair reference YTM, in bps.
    cheapness_bps: float = 0.0
    duration: Optional[DurationMetrics] = None
    macro_penalty: float = 0.0

    # FGC coverage given the *current* portfolio (room may already be used).
    fgc_covered_now: bool = False
    sizing: Optional[PositionSizing] = None

    # 0..100, higher = better risk-adjusted opportunity.
    opportunity_score: float
    is_opportunity: bool
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
