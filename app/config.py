"""Application configuration loaded from environment / .env file."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the tracker and API.

    Values are read from environment variables (and a local ``.env`` file).
    See ``.env.example`` for documentation of each field.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Data source
    offer_source: str = "mock"  # "mock" | "xp"
    xp_username: str = ""
    xp_password: str = ""
    xp_cpf: str = ""
    xp_totp_secret: str = ""
    xp_positions_url: str = "https://www.xpi.com.br/conta-corrente/extrato/"

    # Tracker
    refresh_interval_seconds: float = 10.0
    opportunity_threshold: float = 70.0
    # Market context (reference rates/curves) refreshes on a slower cadence.
    market_refresh_seconds: float = 300.0

    # Market data sources
    market_source: str = "auto"  # "auto" | "live" | "fixtures"
    bcb_sgs_base_url: str = "https://api.bcb.gov.br/dados/serie"
    bcb_olinda_base_url: str = (
        "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata"
    )
    tesouro_url: str = (
        "https://www.tesourodireto.com.br/json/br/com/b3/tesourodireto/"
        "service/api/treasurybondsinfo.json"
    )
    anbima_debentures_url: str = (
        "https://www.anbima.com.br/informacoes/merc-sec-debentures/"
        "arqs/db_taxas.csv"
    )
    market_http_timeout: float = 8.0

    # Market assumptions (annual %) — fallback when live data is unavailable.
    cdi_annual: float = 10.65
    selic_annual: float = 10.75
    ipca_annual: float = 4.50

    # Secondary-market edge: minimum cheapness (offered YTM - reference) in bps
    # for a secondary offer to earn its cheapness bonus.
    min_cheapness_bps: float = 30.0

    # Macro/duration penalty weight (higher => penalize long duration more).
    macro_penalty_weight: float = 1.0

    # --- Equities (renda variável: stocks + FIIs) --------------------------
    equity_source: str = "fixtures"  # "fixtures" | "brapi"
    brapi_base_url: str = "https://brapi.dev/api"
    brapi_token: str = ""
    # Where the persisted per-ticker watch state lives.
    equity_watchlist_path: str = "data/equity_watchlist.json"

    # Valuation: discount rate = Selic + this equity risk premium (fraction).
    equity_risk_premium: float = 0.05
    # Base margin of safety demanded before arming (fraction of fair value).
    stock_base_mos: float = 0.15
    fii_base_mos: float = 0.08
    # MoS macro tightening: extra MoS per point of Selic above the neutral level.
    mos_neutral_selic: float = 8.0
    mos_macro_factor: float = 1.0
    # FII valuation anchors.
    fii_target_dy: float = 0.085  # dividend yield used for the DY fair value
    fii_target_pvp: float = 1.0  # fair price-to-NAV

    # Stage gates.
    equity_quality_min: float = 55.0  # below this a name is rejected
    equity_entry_min: float = 50.0  # entry_score needed to flip ARMED→TRIGGERED

    # FGC limits (BRL).
    fgc_per_institution: float = 250_000.0
    fgc_global_4y: float = 1_000_000.0
    # Non-FGC diversification caps (fraction of total portfolio value).
    max_issuer_concentration: float = 0.05
    max_sector_concentration: float = 0.20
    # Assumed total investable capital when no portfolio is loaded (BRL).
    default_portfolio_value: float = 100_000.0

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
