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

    # Tracker
    refresh_interval_seconds: float = 10.0
    opportunity_threshold: float = 70.0

    # Market assumptions (annual %) used to normalize yields for comparison.
    cdi_annual: float = 10.65
    selic_annual: float = 10.75
    ipca_annual: float = 4.50

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
