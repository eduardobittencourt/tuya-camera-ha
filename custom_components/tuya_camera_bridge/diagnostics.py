"""Diagnostics that never include account identifiers, sessions or stream URLs."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .binary import manifest


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    runtime = entry.runtime_data
    return {
        "bridge_version": (await hass.async_add_executor_job(manifest))["version"],
        "bridge_ready": runtime.bridge.ready,
        "reauth_required": runtime.bridge.auth_required,
        "cameras": [
            {"connection_status": runtime.bridge.camera_status.get(camera_id, {}).get("state", "standby"),
             "active_media_processes": relay.active_processes}
            for camera_id, relay in runtime.relays.items()
        ],
    }
