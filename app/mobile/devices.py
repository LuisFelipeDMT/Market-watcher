"""Registry of phones to push to (FCM tokens), persisted to disk."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.mobile.models import DeviceRegistration

logger = logging.getLogger(__name__)


class DeviceRegistry:
    """Stores registered devices; small and JSON-backed (single user)."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._devices: dict[str, DeviceRegistration] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for item in data:
                reg = DeviceRegistration.model_validate(item)
                self._devices[reg.id] = reg
        except Exception as exc:
            logger.warning("Could not load device registry: %s", exc)

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = [d.model_dump(mode="json") for d in self._devices.values()]
            self._path.write_text(json.dumps(payload), encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not save device registry: %s", exc)

    def register(self, reg: DeviceRegistration) -> DeviceRegistration:
        self._devices[reg.id] = reg
        self._save()
        return reg

    def unregister(self, device_id: str) -> bool:
        existed = self._devices.pop(device_id, None) is not None
        if existed:
            self._save()
        return existed

    def list(self) -> list[DeviceRegistration]:
        return list(self._devices.values())

    def tokens(self) -> list[str]:
        return [d.token for d in self._devices.values()]
