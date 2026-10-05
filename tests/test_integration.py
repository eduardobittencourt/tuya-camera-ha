from pathlib import Path
from unittest.mock import AsyncMock, patch

from homeassistant.components.ffmpeg import FFmpegManager
from homeassistant.config_entries import ConfigEntryState
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tuya_camera_bridge import async_migrate_entry
from custom_components.tuya_camera_bridge.config_flow import entry_data
from custom_components.tuya_camera_bridge.const import DOMAIN

from .test_config_flow import LOGIN


async def test_setup_creates_native_cameras_and_unload_stops_every_process(hass, tmp_path, socket_enabled):
    data = entry_data(LOGIN)
    entry = MockConfigEntry(domain=DOMAIN, version=2, unique_id="tuya_smart_account", data=data)
    entry.add_to_hass(hass)
    bridge = AsyncMock()
    bridge.ready = True
    bridge.auth_required = False
    bridge.camera_status = {}
    bridge.sources = {item["camera_id"]: {"hevc": False} for item in data["cameras"]}
    bridge.source_url.side_effect = lambda cid: f"rtsp://127.0.0.1:1234/{cid}"
    with patch.object(FFmpegManager, "async_get_version", return_value=("7.0.2", 7)), \
         patch("custom_components.tuya_camera_bridge.ensure_binary", return_value=tmp_path / "bridge"), \
         patch("custom_components.tuya_camera_bridge.ManagedBridge", return_value=bridge):
        assert await async_setup_component(hass, "ffmpeg", {})
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        cameras = hass.states.async_all("camera")
        assert len(cameras) == 2
        assert all(camera.state == "idle" for camera in cameras)
        assert all(camera.attributes["connection_status"] == "standby" for camera in cameras)
        relays = list(entry.runtime_data.relays.values())
        assert all(relay.url.startswith("http://127.0.0.1:") for relay in relays)
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
    bridge.stop.assert_awaited_once()
    assert all(relay._server is None for relay in relays)
    assert all(camera.state == "unavailable" for camera in hass.states.async_all("camera"))


async def test_migration_removes_legacy_file_and_preserves_camera_identity(hass):
    data = entry_data(LOGIN)
    camera = data.pop("cameras")[0]
    data.update(camera)
    entry = MockConfigEntry(domain=DOMAIN, version=1, unique_id="account", data=data,
                            options={"bridge_host": "old-addon", "bridge_port": 38554})
    entry.add_to_hass(hass)
    with patch.object(Path, "unlink") as unlink:
        assert await async_migrate_entry(hass, entry)
    assert entry.version == 2
    assert entry.data["cameras"] == [camera]
    assert entry.options == {}
    assert "camera_id" not in entry.data
    unlink.assert_called_once_with(True)
