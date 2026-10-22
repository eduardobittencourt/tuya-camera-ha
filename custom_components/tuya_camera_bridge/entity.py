"""Shared schema-driven LAN entity support."""
from __future__ import annotations

from datetime import datetime

from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .lan import signal, valid_scalar

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


async def async_setup_confirmed_entities(hass, entry, async_add_entities, platform, entities) -> None:
    """Discover reported functions and retire old schema-only entities safely."""
    registry = er.async_get(hass)
    pending = []
    for entity in entities:
        entity_id = registry.async_get_entity_id(platform, DOMAIN, entity.unique_id)
        registered = registry.async_get(entity_id) if entity_id else None
        if registered:
            entity.hass, entity.entity_id = hass, registered.entity_id
            entity.restore_observation(await entity.async_get_last_state())
        if entity.code not in entity.local.values and registered and registered.disabled_by is None:
            registry.async_update_entity(registered.entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION)
        pending.append(entity)

    @callback
    def discover_entities() -> None:
        discovered = []
        for entity in tuple(pending):
            if entity.code not in entity.local.values:
                continue
            pending.remove(entity)
            entity_id = registry.async_get_entity_id(platform, DOMAIN, entity.unique_id)
            registered = registry.async_get(entity_id) if entity_id else None
            if registered and registered.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
                registry.async_update_entity(registered.entity_id, disabled_by=None)
            discovered.append(entity)
        if discovered:
            async_add_entities(discovered)

    for camera_id in entry.runtime_data.local_cameras:
        entry.async_on_unload(async_dispatcher_connect(hass, signal(entry.entry_id, camera_id), discover_entities))
    discover_entities()


class LocalEntity(RestoreEntity):
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
        return (self.local.connected or self.local.on_demand) and self.code in self.local.values

    @property
    def extra_state_attributes(self) -> dict:
        return {"transport": "lan", "last_observed": self.local.observed_at.get(self.code),
                "connection_active": self.local.connected}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.restore_observation(await self.async_get_last_state())

        @callback
        def changed() -> None:
            self.async_write_ha_state()

        self.async_on_remove(async_dispatcher_connect(
            self.hass, signal(self._entry_id, self.local.camera_id), changed,
        ))

    def restore_observation(self, state) -> None:
        """Restore a timestamped observation without asserting a live connection."""
        if not self.local.on_demand or self.code in self.local.values or state is None:
            return
        timestamp = state.attributes.get("last_observed")
        if not isinstance(timestamp, str):
            return
        try:
            if datetime.fromisoformat(timestamp).tzinfo is None:
                return
            value = self.restored_value(state.state)
        except (ValueError, TypeError, OverflowError):
            return
        if valid_scalar(self.local.schema[self.code], value):
            self.local.values[self.code] = value
            self.local.observed_at[self.code] = timestamp

    def restored_value(self, value: str):
        return None
