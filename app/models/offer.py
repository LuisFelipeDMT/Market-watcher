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
    # Meaning depends on index_type (see IndexType docstring).
    rate: float
    maturity: date
    min_investment: float
    liquidity: Liquidity = Liquidity.AT_MATURITY
    fgc_eligible: bool = False  # covered by FGC up to R$250k
    tax_exempt: bool = False  # IR-exempt for individuals (LCI/LCA/CRI/CRA...)
    rating: Optional[str] = None
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


class RiskAssessment(BaseModel):
    """Result of scoring the risk of an offer (0 = safest, 100 = riskiest)."""

    score: float  # 0..100
    rating_factor: float
    product_factor: float
    fgc_factor: float
    maturity_factor: float
    liquidity_factor: float
    institution_factor: float
    flags: list[str] = Field(default_factory=list)


class Opportunity(BaseModel):
    """An offer evaluated for attractiveness, with derived analytics."""

    offer: Offer
    institution: InstitutionHealth
    risk: RiskAssessment

    # Yield normalized to a comparable gross annual % so different index
    # types can be ranked on the same scale.
    normalized_gross_yield: float
    # Net (after-IR) normalized annual %, accounting for tax exemption.
    normalized_net_yield: float
    # Yield expressed as % of CDI for quick comparison.
    yield_pct_of_cdi: float

    # 0..100, higher = better risk-adjusted opportunity.
    opportunity_score: float
    is_opportunity: bool
    reasons: list[str] = Field(default_factory=list)
