"""XP web platform collector (trusted zone).

XP Brazil exposes no public API for its renda fixa shelf, so this collector
drives a headless browser (Playwright) to authenticate with the user's own
investor credentials and read the offers table from the renda fixa page.

This is a scaffold with the structure in place; the page selectors must be
filled in against the live site (they change over time and require an
authenticated session to inspect). Until then it raises a clear error so the
operator knows credentials/selectors still need wiring. Use OFFER_SOURCE=mock
for development.

Respect XP's Terms of Service: only scrape data your own account can already
see, and keep the refresh interval reasonable.
"""

from __future__ import annotations

import logging

from app.collector.base import Collector
from app.config import Settings
from app.models import Offer, Portfolio

logger = logging.getLogger(__name__)

LOGIN_URL = "https://www.xpi.com.br/login"
RENDA_FIXA_URL = "https://www.xpi.com.br/investimentos/renda-fixa/"
SECONDARY_URL = "https://www.xpi.com.br/investimentos/renda-fixa/mercado-secundario/"


class XPCollector(Collector):
    """Scrapes renda fixa offers from the XP web platform via Playwright."""

    name = "xp"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._browser = None
        self._context = None
        self._page = None

    async def startup(self) -> None:
        if not self._settings.xp_username or not self._settings.xp_password:
            raise RuntimeError(
                "OFFER_SOURCE=xp requires XP_USERNAME and XP_PASSWORD to be set."
            )
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover - depends on env
            raise RuntimeError(
                "Playwright is required for the XP collector. Install it with:\n"
                "  pip install playwright && playwright install chromium"
            ) from exc

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)
        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()
        await self._login()

    async def shutdown(self) -> None:
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if getattr(self, "_pw", None) is not None:
            await self._pw.stop()

    async def _login(self) -> None:
        """Authenticate against the XP login flow.

        Selectors below are placeholders — inspect the live login page with an
        authenticated session and replace them. Handle the CPF step and the
        2FA prompt via the phone-push approval broker (see the secure-delivery
        plan); the TOTP seed stays on the phone, never on this host.
        """
        assert self._page is not None
        await self._page.goto(LOGIN_URL)
        # TODO: fill in the real selectors for the XP login form, e.g.:
        # await self._page.fill("#username", self._settings.xp_username)
        # await self._page.fill("#password", self._settings.xp_password)
        # await self._page.click("button[type=submit]")
        # ...handle CPF + phone-push 2FA approval...
        raise NotImplementedError(
            "XP login selectors are not yet wired. Inspect the live page and "
            "complete _login(), or run with OFFER_SOURCE=mock."
        )

    async def fetch_offers(self) -> list[Offer]:
        """Read and parse the renda fixa offers (primary + secondary).

        Implementation outline:
          1. Navigate to RENDA_FIXA_URL (primary) and SECONDARY_URL.
          2. Wait for each offers table/grid to render.
          3. Extract each row into the fields of :class:`Offer`. For secondary
             rows also capture PU (``unit_price``), the taxa de compra
             (``offered_ytm``) and ``quantity_available``, and set
             ``market=MarketKind.SECONDARY``.
          4. Return the combined list.
        """
        raise NotImplementedError(
            "XP offer parsing is not yet wired. Complete fetch_offers(), or "
            "run with OFFER_SOURCE=mock."
        )

    async def fetch_positions(self) -> Portfolio | None:
        """Scrape current holdings from the XP positions/extrato page.

        Implementation outline:
          1. Navigate to ``settings.xp_positions_url``.
          2. Parse each renda fixa position into a :class:`Holding`
             (issuer, product type, current amount, FGC eligibility).
          3. Map issuer -> conglomerate/sector via app.portfolio.conglomerates.
          4. Return a :class:`Portfolio`.
        """
        raise NotImplementedError(
            "XP positions parsing is not yet wired. Complete fetch_positions()."
        )
