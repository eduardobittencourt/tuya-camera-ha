"""Tuya cameras with an automatically managed, private media bridge."""
from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from homeassistant.components.ffmpeg import get_ffmpeg_manager
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .api import TuyaCameraApi
from .binary import BinaryError, ensure_binary
from .bridge import BridgeAuthenticationError, BridgeError, ManagedBridge
from .const import CONF_CAMERAS, DOMAIN
from .lan import LocalCamera, discover
from .payload import bridge_config_filename, build_bridge_config
from .transcoder import FfmpegRelay

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.CAMERA, Platform.SWITCH, Platform.SELECT, Platform.NUMBER,
             Platform.SENSOR, Platform.BINARY_SENSOR]


def status_signal(entry_id: str) -> str:
    return f"{DOMAIN}_{entry_id}_status"


@dataclass
class RuntimeData:
    bridge: ManagedBridge
    relays: dict[str, FfmpegRelay]
    local_cameras: dict[str, LocalCamera] = field(default_factory=dict)

    async def stop(self) -> None:
        await asyncio.gather(*(camera.stop() for camera in self.local_cameras.values()))
        await asyncio.gather(*(relay.stop() for relay in self.relays.values()))
        await self.bridge.stop()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not entry.data.get("local_controls_initialized"):
        cameras = await TuyaCameraApi(async_get_clientsession(hass)).async_prepare_local_controls(entry.data)
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_CAMERAS: cameras,
                                                          "local_controls_initialized": True})
    if not entry.data.get("local_media_initialized"):
        cameras = await TuyaCameraApi(async_get_clientsession(hass)).async_prepare_local_media(entry.data)
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_CAMERAS: cameras,
                                                          "local_media_initialized": True})
    # Resolve locally, even on entries provisioned before media support. Never
    # fetch a cloud address or require users to enter host/key/port information.
    cameras = []
    for camera in entry.data[CONF_CAMERAS]:
        local = dict(camera.get("local") or {})
        if local.get("media_password"):
            endpoint = await hass.async_add_executor_job(
                discover, camera["camera_id"], local.get("mac", ""), local.get("host", ""), local.get("version", ""),
            )
            if endpoint:
                local.update(host=endpoint[0], version=endpoint[1] or "3.3")
        cameras.append({**camera, **({"local": local} if local else {})})
    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_CAMERAS: cameras})
    directory = Path(hass.config.path(".storage", DOMAIN))
    try:
        binary = await ensure_binary(async_get_clientsession(hass), directory / "bin")
    except BinaryError as err:
        raise ConfigEntryNotReady(str(err)) from err
    config = build_bridge_config(entry.data)
    config["bridge_port"] = 0

    @callback
    def changed() -> None:
        async_dispatcher_send(hass, status_signal(entry.entry_id))

    @callback
    def reauth() -> None:
        if entry.state.value == "loaded":
            entry.async_start_reauth(hass)

    bridge = ManagedBridge(binary, directory / entry.entry_id, config, changed, reauth)
    runtime = RuntimeData(bridge, {})
    try:
        await bridge.start()
        ffmpeg = get_ffmpeg_manager(hass).binary
        for camera in entry.data[CONF_CAMERAS]:
            local = LocalCamera(hass, entry.entry_id, camera, entry.data.get("uid", ""))
            if bridge.sources.get(camera["camera_id"], {}).get("transport") == "lan":
                local.media_bridge = bridge
            runtime.local_cameras[camera["camera_id"]] = local
        for camera in config["cameras"]:
            camera_id = camera["camera_id"]
            relay = FfmpegRelay(
                ffmpeg, lambda cid=camera_id: bridge.source_url(cid),
                lambda cid=camera_id: bool(bridge.sources[cid].get("hevc", False)),
                runtime.local_cameras[camera_id].media_activity,
            )
            await relay.start()
            runtime.relays[camera_id] = relay
        entry.runtime_data = runtime
        for camera_id, local in runtime.local_cameras.items():
            local.wake_media = runtime.relays[camera_id].control_session
            await local.start()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        if not entry.data.get("confirmed_entities_policy"):
            hass.config_entries.async_update_entry(entry, data={**entry.data, "confirmed_entities_policy": 1})
    except BridgeAuthenticationError as err:
        await runtime.stop()
        raise ConfigEntryAuthFailed("The Tuya session expired; sign in again") from err
    except (BridgeError, OSError, TimeoutError) as err:
        await runtime.stop()
        raise ConfigEntryNotReady("The media bridge could not start") from err
    except BaseException:
        await runtime.stop()
        raise

    async def stopped(_event) -> None:
        await runtime.stop()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stopped))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.stop()
        return True
    return False


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    directory = Path(hass.config.path(".storage", DOMAIN, entry.entry_id))
    await hass.async_add_executor_job(shutil.rmtree, directory, True)
    legacy = Path(hass.config.path(bridge_config_filename(entry.entry_id)))
    await hass.async_add_executor_job(legacy.unlink, True)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.version > 2:
        return False
    if entry.version == 1:
        config = build_bridge_config(entry.data)
        data = {**entry.data, CONF_CAMERAS: config["cameras"]}
        for key in ("camera_id", "camera_name", "product_id"):
            data.pop(key, None)
        hass.config_entries.async_update_entry(entry, data=data, options={}, version=2)
        legacy = Path(hass.config.path(bridge_config_filename(entry.entry_id)))
        await hass.async_add_executor_job(legacy.unlink, True)
    return True
