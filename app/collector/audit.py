"""Append-only audit log for the collector (trusted zone).

Records what the collector did and when — logins, fetches, 2FA approvals — as
structured JSON lines, so there is a tamper-evident trail for incident response.
Callers must pass only non-secret fields; secret *values* never go in here (the
log redaction filter is a second line of defence for stdout/stderr).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class AuditLog:
    """Appends JSON-line audit entries to a 0600 file."""

    def __init__(self, path: str) -> None:
        self._path = path

    def record(self, event: str, **fields: object) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **fields,
        }
        try:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            # Create 0600 if absent, then append.
            fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except Exception as exc:  # auditing must never crash the collector
            logger.warning("Audit write failed (%s): %s", event, exc)


class NullAuditLog(AuditLog):
    """No-op audit log (when auditing is disabled)."""

    def __init__(self) -> None:  # noqa: D107
        super().__init__("")

    def record(self, event: str, **fields: object) -> None:
        pass


def build_audit_log(settings) -> AuditLog:
    """Construct the configured audit log (Null when no path is set)."""
    path = getattr(settings, "audit_log_path", "")
    return AuditLog(path) if path else NullAuditLog()
