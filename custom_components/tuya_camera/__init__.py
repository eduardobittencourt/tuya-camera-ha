"""Tuya cameras with account-scoped Python media sessions."""
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
from .const import CONF_CAMERAS, DOMAIN
from .lan import LocalCamera, discover
from .media.cloud import MediaAuthenticationError, MediaError
from .media.runtime import MediaRuntime
from .transcoder import FfmpegRelay

VERSION = "0.4.0"
_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.CAMERA, Platform.SWITCH, Platform.SELECT, Platform.NUMBER,
             Platform.SENSOR, Platform.BINARY_SENSOR]


def status_signal(entry_id: str) -> str:
    return f"{DOMAIN}_{entry_id}_status"


@dataclass
class RuntimeData:
    media: MediaRuntime
    relays: dict[str, FfmpegRelay]
    local_cameras: dict[str, LocalCamera] = field(default_factory=dict)

    async def stop(self) -> None:
        await asyncio.gather(*(camera.stop() for camera in self.local_cameras.values()))
        await asyncio.gather(*(relay.stop() for relay in self.relays.values()))
        await self.media.stop()


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
    @callback
    def changed() -> None:
        async_dispatcher_send(hass, status_signal(entry.entry_id))

    @callback
    def reauth() -> None:
        if entry.state.value == "loaded":
            entry.async_start_reauth(hass)

    media = MediaRuntime(async_get_clientsession(hass), entry.data, changed, reauth)
    runtime = RuntimeData(media, {})
    try:
        await media.start()
        # Upgrade from <=0.3.x: no account or observation data lives in this cache.
        await hass.async_add_executor_job(shutil.rmtree, Path(hass.config.path(".storage", DOMAIN, "bin")), True)
        ffmpeg = get_ffmpeg_manager(hass).binary
        for camera in entry.data[CONF_CAMERAS]:
            local = LocalCamera(hass, entry.entry_id, camera, entry.data.get("uid", ""))
            if media.sources.get(camera["camera_id"], {}).get("transport") == "lan":
                local.media_client = media
            runtime.local_cameras[camera["camera_id"]] = local
        for camera in entry.data[CONF_CAMERAS]:
            camera_id = camera["camera_id"]
            relay = FfmpegRelay(
                ffmpeg, lambda cid=camera_id: media.source_url(cid),
                lambda cid=camera_id: bool(media.sources[cid].get("hevc", False)),
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
    except MediaAuthenticationError as err:
        await runtime.stop()
        raise ConfigEntryAuthFailed("The Tuya session expired; sign in again") from err
    except (MediaError, OSError, TimeoutError) as err:
        await runtime.stop()
        raise ConfigEntryNotReady("The camera media service could not start") from err
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
    legacy = Path(hass.config.path(f"{DOMAIN}_{entry.entry_id}.json"))
    await hass.async_add_executor_job(legacy.unlink, True)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.version > 2:
        return False
    if entry.version == 1:
        camera = {key: entry.data[key] for key in ("camera_id", "camera_name", "product_id") if key in entry.data}
        data = {**entry.data, CONF_CAMERAS: [camera]}
        for key in ("camera_id", "camera_name", "product_id"):
            data.pop(key, None)
        hass.config_entries.async_update_entry(entry, data=data, options={}, version=2)
        legacy = Path(hass.config.path(f"{DOMAIN}_{entry.entry_id}.json"))
        await hass.async_add_executor_job(legacy.unlink, True)
    return True
