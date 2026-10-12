"""Shared schema-driven LAN entity support."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .lan import signal

SWITCHES = {
    "basic_indicator": "Indicator light", "basic_flip": "Flip image", "basic_osd": "Timestamp overlay",
    "basic_private": "Privacy mode", "basic_wdr": "Wide dynamic range", "motion_switch": "Motion detection",
    "ipc_pir_switch": "PIR detection", "humanoid_filter": "Person detection", "record_switch": "Recording",
    "siren_switch": "Siren", "decibel_switch": "Sound detection", "motion_tracking": "Motion tracking",
    "motion_area_switch": "Detection area", "ipc_alarm_ind": "Alarm reporting",
    "ipc_privacy_zone": "Privacy zones", "wireless_awake": "Keep awake",
}
SELECTS = {
    "basic_nightvision": ("Night vision", {"0": "auto", "1": "off", "2": "on"}),
    "motion_sensitivity": ("Motion sensitivity", {}), "decibel_sensitivity": ("Sound sensitivity", {}),
    "record_mode": ("Recording mode", {}), "basic_anti_flicker": ("Anti-flicker", {}),
    "ipc_work_mode": ("Working mode", {}), "ipc_light_mode": ("Light mode", {}),
}
NUMBERS = {
    "basic_device_volume": "Volume", "ipc_pir_sensitivity": "PIR sensitivity",
    "wireless_lowpower": "Low battery threshold", "motion_interval": "Motion alarm interval",
}
SENSORS = {
    "wireless_electricity": "Battery", "wireless_powermode": "Power source",
    "sd_status": "SD card status", "sd_format_state": "SD formatting progress",
}


def supported(local, code: str, kind: str, *, writable: bool = False) -> bool:
    definition = local.schema.get(code, {})
    return (definition.get("property", {}).get("type") == kind
            and (not writable or "w" in definition.get("mode", "")))


class LocalEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry, camera: dict, code: str, name: str) -> None:
        self.local = entry.runtime_data.local_cameras[camera["camera_id"]]
        self.code = code
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{camera['camera_id']}_{code}"
        self._attr_name = name
        self._attr_translation_key = code
        self._attr_device_info = {
            "identifiers": {(DOMAIN, camera["camera_id"])}, "name": camera["camera_name"],
            "manufacturer": "Tuya", "model": "Mobile WebRTC camera",
        }

    @property
    def available(self) -> bool:
        return self.local.connected and self.code in self.local.values

    @property
    def extra_state_attributes(self) -> dict:
        return {"transport": "lan"}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def changed() -> None:
            self.async_write_ha_state()

        self.async_on_remove(async_dispatcher_connect(
            self.hass, signal(self._entry_id, self.local.camera_id), changed,
        ))
