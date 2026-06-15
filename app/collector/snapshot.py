"""Signed snapshot transport — the safest collector→analysis link.

The collector (trusted zone) periodically writes the read-only data as
HMAC-signed JSON files; the analysis zone reads and verifies them. Because data
flows one way through the filesystem there is **no inbound path to the
collector at all** (a software "data diode"). Signing is stdlib-only
(HMAC-SHA256), so this transport needs no extra dependencies.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from app.models import Offer, Portfolio

logger = logging.getLogger(__name__)

_OFFERS = "offers.json"
_POSITIONS = "positions.json"


def _sign(key: str, body: dict[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(key.encode(), canonical, sha256).hexdigest()


def _verify(key: str, body: dict[str, Any], sig: str) -> bool:
    return hmac.compare_digest(_sign(key, body), sig)


class SnapshotWriter:
    """Writes signed read-only snapshots to a directory (collector side)."""

    def __init__(self, directory: str, key: str) -> None:
        self._dir = directory
        self._key = key

    def _write(self, name: str, kind: str, payload: Any) -> None:
        body = {
            "kind": kind,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        envelope = {**body, "sig": _sign(self._key, body)}
        os.makedirs(self._dir, exist_ok=True)
        path = os.path.join(self._dir, name)
        tmp = f"{path}.tmp"
        # Write then atomically rename so readers never see a partial file.
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(envelope, fh)
        os.replace(tmp, path)

    def write_offers(self, offers: list[Offer]) -> None:
        self._write(_OFFERS, "offers", [o.model_dump(mode="json") for o in offers])

    def write_positions(self, portfolio: Portfolio | None) -> None:
        payload = portfolio.model_dump(mode="json") if portfolio is not None else None
        self._write(_POSITIONS, "positions", payload)


class SnapshotReader:
    """Reads and verifies signed snapshots (analysis side)."""

    def __init__(self, directory: str, key: str) -> None:
        self._dir = directory
        self._key = key

    def _read(self, name: str, kind: str) -> Any:
        path = os.path.join(self._dir, name)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as fh:
            envelope = json.load(fh)
        sig = envelope.pop("sig", None)
        if sig is None or envelope.get("kind") != kind or not _verify(
            self._key, envelope, sig
        ):
            raise ValueError(f"Snapshot {name}: signature verification failed")
        return envelope.get("payload")

    def read_offers(self) -> list[Offer]:
        payload = self._read(_OFFERS, "offers")
        if not payload:
            return []
        return [Offer.model_validate(item) for item in payload]

    def read_positions(self) -> Portfolio | None:
        payload = self._read(_POSITIONS, "positions")
        if payload is None:
            return None
        return Portfolio.model_validate(payload)
