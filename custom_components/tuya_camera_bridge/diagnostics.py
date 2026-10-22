"""Diagnostics that never include account identifiers, sessions or stream URLs."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .binary import manifest


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    runtime = entry.runtime_data
    media_stats = []
    for camera_id in runtime.relays:
        if runtime.bridge.sources.get(camera_id, {}).get("transport") == "lan":
            try:
                response = await runtime.bridge.local_request(camera_id, "stats")
                media_stats.append(response.get("dps", {}))
            except Exception:  # noqa: BLE001 - never expose IPC/dependency details
                media_stats.append({"active": False})
    return {
        "local_media_stats": media_stats,
        "bridge_version": (await hass.async_add_executor_job(manifest))["version"],
        "bridge_ready": runtime.bridge.ready,
        "reauth_required": runtime.bridge.auth_required,
        "local_controls": [{"status": local.status, "connected": local.connected,
                            "supported_functions": sorted(local.schema), "on_demand": local.on_demand,
                            "last_observed": dict(local.observed_at)}
                           for local in runtime.local_cameras.values()],
        "cameras": [
            {"media_transport": runtime.bridge.sources.get(camera_id, {}).get("transport", "cloud"),
             "cloud_wakes": runtime.bridge.camera_status.get(camera_id, {}).get("cloud_wakes", 0),
             "connection_status": runtime.bridge.camera_status.get(camera_id, {}).get("state", "standby"),
             "active_media_processes": relay.active_processes}
            for camera_id, relay in runtime.relays.items()
        ],
    }
