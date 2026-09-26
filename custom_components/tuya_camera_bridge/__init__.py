"""Tuya Camera Bridge integration."""
from __future__ import annotations

from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .payload import bridge_config_filename, build_bridge_config, write_bridge_config_file

PLATFORMS = ["camera"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Write the add-on contract and expose camera entities."""
    config = build_bridge_config(entry.data)
    path = Path(hass.config.path(bridge_config_filename(entry.entry_id)))
    await hass.async_add_executor_job(write_bridge_config_file, path, config)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "bridge_config": config,
        "bridge_path": path,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload entities without deleting the config needed during a reload."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the bridge contract when the account is deleted."""
    path = Path(hass.config.path(bridge_config_filename(entry.entry_id)))
    if await hass.async_add_executor_job(path.exists):
        await hass.async_add_executor_job(path.unlink)


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
