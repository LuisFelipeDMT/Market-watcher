"""Optional bearer-token auth for the analysis dashboard.

The dashboard should live on localhost behind a VPN; this is defence-in-depth
app-level auth on top of that. When ``DASHBOARD_TOKEN`` is unset the API is open
(dev default); when set, every request needs ``Authorization: Bearer <token>``
except a small set of health/docs paths. WebSocket auth is handled separately
(via a ``token`` query param) since HTTP middleware doesn't see WS connections.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

_EXEMPT = {
    "/health",
    "/equities/health",
    "/alerts/health",
    "/docs",
    "/redoc",
    "/openapi.json",
}


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Requires a bearer token on all but a few exempt paths."""

    def __init__(self, app, token: str, exempt: set[str] | None = None) -> None:
        super().__init__(app)
        self._token = token
        self._exempt = exempt or _EXEMPT

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self._exempt:
            return await call_next(request)
        if request.headers.get("authorization") != f"Bearer {self._token}":
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)


def ws_authorized(websocket) -> bool:
    """True if the WebSocket connection carries the dashboard token (or none set)."""
    token = getattr(websocket.app.state.settings, "dashboard_token", "")
    if not token:
        return True
    provided = websocket.query_params.get("token", "")
    header = websocket.headers.get("authorization", "")
    return provided == token or header == f"Bearer {token}"
