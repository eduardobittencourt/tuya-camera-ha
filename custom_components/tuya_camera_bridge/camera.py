"""Native camera entities backed by the automatically managed bridge."""
from __future__ import annotations

import time
from contextlib import suppress
from datetime import UTC, datetime

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RuntimeData, status_signal
from .const import CONF_CAMERAS, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([TuyaBridgeCamera(entry, camera) for camera in entry.data[CONF_CAMERAS]])


class TuyaBridgeCamera(Camera):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = CameraEntityFeature.STREAM
    _attr_should_poll = True

    def __init__(self, entry: ConfigEntry, camera: dict) -> None:
        super().__init__()
        self._entry = entry
        self._runtime: RuntimeData = entry.runtime_data
        self._camera_id = camera["camera_id"]
        self._attr_unique_id = f"{self._camera_id}_camera"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._camera_id)}, "name": camera["camera_name"],
            "manufacturer": "Tuya", "model": "Mobile WebRTC camera",
        }

    @property
    def available(self) -> bool:
        return self._runtime.bridge.ready and not self._runtime.bridge.auth_required and not self._needs_probe()

    def _needs_probe(self) -> bool:
        status = self._runtime.bridge.camera_status.get(self._camera_id, {})
        if status.get("state") == "error":
            return True
        last_video = status.get("last_video")
        return bool(last_video and self._runtime.relays[self._camera_id].active_processes
                    and time.time() - last_video > 45)

    async def async_update(self) -> None:
        if self._runtime.bridge.ready and self._needs_probe():
            with suppress(OSError, TimeoutError):
                await self._runtime.relays[self._camera_id].snapshot()

    @property
    def extra_state_attributes(self) -> dict:
        status = self._runtime.bridge.camera_status.get(self._camera_id, {})
        last_video = status.get("last_video")
        return {
            "connection_status": status.get("state", "standby") if self.available else "disconnected",
            "last_video_received": datetime.fromtimestamp(last_video, UTC).isoformat() if last_video else None,
            "active_media_processes": self._runtime.relays[self._camera_id].active_processes,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def changed() -> None:
            self.async_write_ha_state()

        self.async_on_remove(async_dispatcher_connect(self.hass, status_signal(self._entry.entry_id), changed))

    async def stream_source(self) -> str | None:
        return self._runtime.relays[self._camera_id].url if self.available else None

    async def async_camera_image(self, width=None, height=None) -> bytes | None:
        if not self.available:
            return None
        try:
            return await self._runtime.relays[self._camera_id].snapshot()
        except (OSError, TimeoutError):
            return None
