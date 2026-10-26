import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.ffmpeg import FFmpegManager
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import State
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_restore_cache_with_extra_data

from custom_components.tuya_camera_bridge import async_migrate_entry
from custom_components.tuya_camera_bridge.config_flow import entry_data
from custom_components.tuya_camera_bridge.const import DOMAIN

from .test_config_flow import LOGIN
from .test_lan import BATTERY_CAMERA, KEY, SCHEMA


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
         patch("custom_components.tuya_camera_bridge.MediaRuntime", return_value=bridge):
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


@pytest.mark.parametrize("battery", [False, True])
async def test_lan_entities_follow_schema_and_ha_services_use_only_local_commands(
    hass, tmp_path, socket_enabled, battery, entity_registry,
):
    data = entry_data(LOGIN)
    data["cameras"][0]["local"] = BATTERY_CAMERA["local"] if battery else {"local_key": KEY, "schema": SCHEMA}
    data["cameras"][0]["local"] = {
        **data["cameras"][0]["local"],
        "schema": [*data["cameras"][0]["local"]["schema"],
                   {"id": 999, "code": "basic_indicator", "mode": "rw", "property": {"type": "bool"}},
                   {"id": 998, "code": "basic_flip", "mode": "rw", "property": {"type": "bool"}},
                   {"id": 146, "code": "wireless_powermode", "mode": "ro",
                    "property": {"type": "enum", "range": ["0", "1"]}},
                   {"id": 110, "code": "sd_status", "mode": "ro",
                    "property": {"type": "enum", "range": ["0", "1", "2"]}},
                   {"id": 111, "code": "sd_format_state", "mode": "ro",
                    "property": {"type": "value", "min": 0, "max": 1000, "scale": 1}}],
    }
    entry = MockConfigEntry(domain=DOMAIN, version=2, unique_id="account", data=data)
    entry.add_to_hass(hass)
    camera_id = data["cameras"][0]["camera_id"]
    legacy = entity_registry.async_get_or_create(
        "switch", DOMAIN, f"{camera_id}_basic_indicator", config_entry=entry,
        suggested_object_id="custom_camera_indicator",
    )
    user_disabled = entity_registry.async_get_or_create(
        "switch", DOMAIN, f"{camera_id}_basic_flip", config_entry=entry,
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    motion = entity_registry.async_get_or_create(
        "binary_sensor", DOMAIN, f"{camera_id}_movement_detect_pic", config_entry=entry,
    )
    bridge = AsyncMock()
    bridge.ready, bridge.auth_required, bridge.camera_status = True, False, {}
    bridge.sources = {item["camera_id"]: {"hevc": False} for item in data["cameras"]}
    bridge.source_url.side_effect = lambda cid: f"rtsp://127.0.0.1:1234/{cid}"
    values = {"240": False, "108": "0", "241": 7, "146": "1", "110": "0", "111": 125}
    if battery:
        values["145"] = 80
    device = MagicMock()
    device.set_value.side_effect = lambda key, value, nowait=False: values.update({key: value}) or (
        None if nowait else {"dps": values.copy()})
    device.receive.side_effect = lambda: {"dps": values.copy()}
    device.generate_payload.side_effect = lambda command, data, **kwargs: data
    device.send.side_effect = values.update
    device.status.side_effect = lambda: {"dps": values.copy()}

    simulate_idle = False

    async def start(local):
        if local.schema and not simulate_idle:
            local.connected, local.status = True, "connected"
            local._ready.set()
            local._device = device
            local._apply({"dps": values})

    async def control_session(relay, ready):
        ready()
        await asyncio.Event().wait()

    with patch.object(FFmpegManager, "async_get_version", return_value=("7.0.2", 7)), \
         patch("custom_components.tuya_camera_bridge.MediaRuntime", return_value=bridge), \
         patch("custom_components.tuya_camera_bridge.lan.LocalCamera.start", start), \
         patch("custom_components.tuya_camera_bridge.transcoder.FfmpegRelay.control_session", control_session), \
         patch("custom_components.tuya_camera_bridge.api.TuyaCameraApi.async_prepare_local_controls") as cloud:
        assert await async_setup_component(hass, "ffmpeg", {})
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        cloud.assert_not_called()
        sensors = hass.states.async_all("sensor")
        assert len(sensors) == (4 if battery else 3)
        assert {sensor.state for sensor in sensors} == ({"80.0", "1", "0", "12.5"} if battery else {"1", "0", "12.5"})
        switch = hass.states.async_all("switch")[0]
        select = hass.states.async_all("select")[0]
        number = hass.states.async_all("number")[0]
        assert len(hass.states.async_all("switch")) == 1  # No invented privacy control.
        assert entity_registry.async_get(legacy.entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert entity_registry.async_get(motion.entity_id).disabled_by is (
            er.RegistryEntryDisabler.INTEGRATION if battery else None
        )
        assert switch.state == "off" and select.state == "auto" and number.state == "7.0"
        assert select.attributes["options"] == ["auto", "off", "on"]
        await hass.services.async_call("switch", "turn_on", {"entity_id": switch.entity_id}, blocking=True)
        await hass.services.async_call("select", "select_option",
                                      {"entity_id": select.entity_id, "option": "on"}, blocking=True)
        await hass.services.async_call("number", "set_value",
                                      {"entity_id": number.entity_id, "value": 8}, blocking=True)
        await hass.async_block_till_done()
        if battery:
            assert [call.args[0] for call in device.send.call_args_list] == [
                {"240": True}, {"108": "2"}, {"241": 8},
            ]
            assert all(call.kwargs == {"uid": data["uid"]}
                       for call in device.generate_payload.call_args_list)
        else:
            assert device.set_value.call_args_list[0].args == ("240", True)
            assert device.set_value.call_args_list[1].args == ("108", "2")
            assert device.set_value.call_args_list[2].args == ("241", 8)
        assert hass.states.get(switch.entity_id).state == "on"
        assert hass.states.get(select.entity_id).state == "on"
        assert hass.states.get(number.entity_id).state == "8.0"
        local = entry.runtime_data.local_cameras[camera_id]
        local._apply({"dps": {"999": "invalid boolean", "998": True}})
        await hass.async_block_till_done()
        assert hass.states.get(legacy.entity_id) is None
        assert entity_registry.async_get(user_disabled.entity_id).disabled_by is er.RegistryEntryDisabler.USER
        local._apply({"dps": {"999": False}})
        await hass.async_block_till_done()
        assert hass.states.get(legacy.entity_id).state == "off"
        assert entity_registry.async_get(legacy.entity_id).disabled_by is None
        assert len(hass.states.async_all("switch")) == 2
        if battery:
            local = next(iter(entry.runtime_data.local_cameras.values()))
            last_observed = local.observed_at["wireless_electricity"]
            local.status = "standby"
            await local._close()
            await hass.async_block_till_done()
            sensor = next(sensor for sensor in sensors if sensor.attributes.get("device_class") == "battery")
            sensor = hass.states.get(sensor.entity_id)
            assert float(sensor.state) == 80
            assert sensor.attributes["last_observed"] == last_observed
            assert sensor.attributes["connection_active"] is False
            connectivity = next(state for state in hass.states.async_all("binary_sensor")
                                if state.attributes.get("device_class") == "connectivity")
            assert connectivity.state == "off"
            assert hass.states.get(select.entity_id).state == "on"
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        device.close.assert_called_once()
        if battery:
            simulate_idle = True
            mock_restore_cache_with_extra_data(hass, [
                (State(sensor.entity_id, "80", {"last_observed": last_observed}),
                 {"native_value": 80, "native_unit_of_measurement": "%"}),
                *[(State(entity.entity_id, value, {"last_observed": last_observed}), None)
                  for entity, value in ((switch, "on"), (select, "on"), (number, "8.0"))],
            ])
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
            restored = hass.states.get(sensor.entity_id)
            assert float(restored.state) == 80
            assert restored.attributes["last_observed"] == last_observed
            assert restored.attributes["connection_active"] is False
            assert hass.states.get(switch.entity_id).state == "on"
            assert hass.states.get(select.entity_id).state == "on"
            assert hass.states.get(number.entity_id).state == "8.0"
            assert entity_registry.async_get(user_disabled.entity_id).disabled_by is er.RegistryEntryDisabler.USER
            assert await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()
