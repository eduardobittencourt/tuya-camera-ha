"""Native Home Assistant camera backed by the Tuya RTSP bridge."""
from __future__ import annotations

from urllib.parse import quote

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.ffmpeg import async_get_image
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_BRIDGE_HOST,
    CONF_BRIDGE_PORT,
    CONF_CAMERA_ID,
    CONF_CAMERA_NAME,
    DEFAULT_BRIDGE_HOST,
    DEFAULT_BRIDGE_PORT,
    DOMAIN,
)
from .payload import sanitize_rtsp_path


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([TuyaBridgeCamera(entry)])


class TuyaBridgeCamera(Camera):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__()
        data = entry.data
        self._camera_id = data[CONF_CAMERA_ID]
        self._camera_name = data[CONF_CAMERA_NAME]
        self._attr_unique_id = f"{self._camera_id}_camera"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._camera_id)},
            "name": self._camera_name,
            "manufacturer": "Tuya",
            "model": "Cloud WebRTC camera",
        }
        host = entry.options.get(CONF_BRIDGE_HOST, DEFAULT_BRIDGE_HOST)
        port = entry.options.get(CONF_BRIDGE_PORT, DEFAULT_BRIDGE_PORT)
        path = quote(sanitize_rtsp_path(self._camera_name, self._camera_id), safe="_")
        self._stream_url = f"rtsp://{host}:{port}/{path}"

    async def stream_source(self) -> str:
        return self._stream_url

    async def async_camera_image(self, width=None, height=None) -> bytes | None:
        return await async_get_image(self.hass, self._stream_url, width=width, height=height)
