"""Analysis-side 2FA surface the phone talks to.

The app only ever talks to the analysis gateway (over the dashboard auth); the
gateway forwards approvals to the collector's authenticated 2FA endpoints. This
keeps the collector token off the phone and preserves the trust boundary.

- ``InProcessTwoFactorGateway`` — combined/dev: talks to a local broker.
- ``HttpTwoFactorGateway`` — split deployment: forwards to the collector's
  ``/2fa`` HTTP endpoints (the narrow, authenticated approval channel; separate
  from the read-only data transport).
"""

from __future__ import annotations

import abc
import logging

import httpx

logger = logging.getLogger(__name__)


class TwoFactorGateway(abc.ABC):
    @abc.abstractmethod
    async def pending(self) -> list[dict]:
        raise NotImplementedError

    @abc.abstractmethod
    async def approve(self, request_id: str, code: str) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    async def deny(self, request_id: str) -> bool:
        raise NotImplementedError


class InProcessTwoFactorGateway(TwoFactorGateway):
    def __init__(self, broker) -> None:
        self._broker = broker

    async def pending(self) -> list[dict]:
        return self._broker.pending()

    async def approve(self, request_id: str, code: str) -> bool:
        return self._broker.submit(request_id, code)

    async def deny(self, request_id: str) -> bool:
        return self._broker.deny(request_id)


class HttpTwoFactorGateway(TwoFactorGateway):
    def __init__(self, settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client

    def _ensure(self) -> httpx.AsyncClient:
        if self._client is None:
            transport = httpx.AsyncHTTPTransport(uds=self._settings.collector_socket_path)
            self._client = httpx.AsyncClient(
                transport=transport,
                base_url=self._settings.collector_url,
                headers={"Authorization": f"Bearer {self._settings.collector_token}"},
                timeout=self._settings.market_http_timeout,
            )
        return self._client

    async def pending(self) -> list[dict]:
        resp = await self._ensure().get("/2fa/pending")
        resp.raise_for_status()
        return resp.json()

    async def approve(self, request_id: str, code: str) -> bool:
        resp = await self._ensure().post(f"/2fa/{request_id}/approve", json={"code": code})
        return resp.status_code == 200

    async def deny(self, request_id: str) -> bool:
        resp = await self._ensure().post(f"/2fa/{request_id}/deny")
        return resp.status_code == 200


def build_twofa_gateway(settings, broker=None) -> TwoFactorGateway:
    """Build the gateway: HTTP forwarder for the split deployment, else local."""
    if settings.collector_transport.lower() == "http" and settings.collector_token:
        return HttpTwoFactorGateway(settings)
    if broker is None:
        from app.collector.twofa import TwoFactorBroker

        broker = TwoFactorBroker(settings)
    return InProcessTwoFactorGateway(broker)
