"""LAN isolation, privacy, state confirmation and actual encrypted TCP traffic."""
import asyncio
import json
import logging
import struct
from contextlib import suppress
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import tinytuya
from homeassistant.exceptions import HomeAssistantError
from tinytuya.core import command_types as CT
from tinytuya.core.message_helper import TuyaMessage, pack_message, parse_header, unpack_message

from custom_components.tuya_camera_bridge.lan import LocalCamera, _private_call, discover, private_address

KEY = "test-lan-key1234"
SCHEMA = [
    {"id": 240, "code": "ipc_pir_switch", "mode": "rw", "property": {"type": "bool"}},
    {"id": 108, "code": "basic_nightvision", "mode": "rw",
     "property": {"type": "enum", "range": ["0", "1", "2"]}},
    {"id": 241, "code": "ipc_pir_sensitivity", "mode": "rw",
     "property": {"type": "value", "min": 1, "max": 10, "step": 1, "scale": 0}},
    {"id": 115, "code": "movement_detect_pic", "mode": "ro", "property": {"type": "raw"}},
]
CAMERA = {"camera_id": "synthetic-camera", "camera_name": "Synthetic camera",
          "local": {"local_key": KEY, "schema": SCHEMA}}


@pytest.mark.parametrize("address", ["1.1.1.1", "169.254.169.254", "127.0.0.1", "0.0.0.0",
                                     "camera.example.org", "::1", "224.0.0.1", "100.64.0.1"])
def test_rejects_non_lan_endpoints(address):
    assert not private_address(address)


@pytest.mark.parametrize("address", ["10.0.0.1", "172.16.1.2", "192.168.0.81"])
def test_accepts_private_ipv4(address):
    assert private_address(address)


def test_discovery_matches_exact_camera_and_rejects_wan():
    with patch("tinytuya.scanner.devices", return_value={
        "other": {"ip": "192.168.0.20", "version": "3.3"},
        "wanted": {"ip": "1.1.1.1", "version": "3.3"},
    }), patch("pathlib.Path.read_text", return_value="IP HW Flags MAC Mask Device\n192.168.0.81 1 2 aa:bb * eth0"):
        assert discover("wanted", "aa:bb") == ("192.168.0.81", "")
        assert discover("wanted", "different") is None


def test_dependency_logging_does_not_expose_our_keys(caplog):
    logger = logging.getLogger("tinytuya.core.XenonDevice")
    with caplog.at_level(logging.DEBUG, logger=logger.name):
        _private_call(logger.debug, "key=%s raw_payload=%s", KEY, "private-event")
        logger.debug("other integration's message")
    assert KEY not in caplog.text
    assert "private-event" not in caplog.text
    assert "other integration's message" in caplog.text


def test_occupied_discovery_socket_still_uses_exact_mac_in_arp():
    with patch("tinytuya.scanner.devices", side_effect=OSError("port occupied")), \
         patch("pathlib.Path.read_text", return_value="IP HW Flags MAC Mask Device\n192.168.0.81 1 2 aa:bb * eth0"):
        assert discover("wanted", "aa:bb") == ("192.168.0.81", "")


def test_discovery_does_not_require_scanner_export_on_tinytuya(monkeypatch):
    # TinyTuya's top-level package does not export scanner on a fresh import.
    # Mock's dotted-path resolver can import it implicitly and hide this bug.
    from custom_components.tuya_camera_bridge.lan import scanner

    monkeypatch.delattr(tinytuya, "scanner", raising=False)
    monkeypatch.setattr(scanner, "devices", lambda **kwargs: {})
    with patch("pathlib.Path.read_text", return_value="IP HW Flags MAC Mask Device\n192.168.0.81 1 2 aa:bb * eth0"):
        assert discover("wanted", "aa:bb") == ("192.168.0.81", "")


async def test_cached_alarm_is_not_motion_and_raw_content_is_never_retained(hass):
    local = LocalCamera(hass, "entry", CAMERA)
    local._apply({"dps": {"115": "old-private-image-url", "240": False}})
    assert not local.motion
    local._apply({"dps": {"115": "old-private-image-url"}}, live=True)
    assert not local.motion
    local._apply({"dps": {"115": "new-private-image-url"}}, live=True)
    assert local.motion
    assert "movement_detect_pic" not in local.values
    assert "private-image" not in str(local.__dict__)


@pytest.mark.parametrize(("code", "value"), [("ipc_pir_switch", 1), ("basic_nightvision", "3"),
                                           ("ipc_pir_sensitivity", 11), ("ipc_pir_sensitivity", 1.5),
                                           ("movement_detect_pic", "payload")])
async def test_invalid_or_readonly_commands_never_open_a_socket(hass, code, value):
    local = LocalCamera(hass, "entry", CAMERA)
    with pytest.raises(HomeAssistantError), patch("tinytuya.Device") as device:
        await local.write(code, value)
    device.assert_not_called()


async def test_command_without_confirmation_does_not_invent_state(hass):
    local = LocalCamera(hass, "entry", CAMERA)
    local.connected = True
    local.values = {"ipc_pir_switch": False}
    local._device = MagicMock()
    local._device.status.return_value = {"dps": {"240": False}}
    local._device.set_value.return_value = {}
    with pytest.raises(HomeAssistantError, match="did not confirm"):
        await local.write("ipc_pir_switch", True)
    assert "ipc_pir_switch" not in local.values
    assert not local.connected
    assert local._device is None


async def test_empty_heartbeat_does_not_disconnect_and_motion_pulse_expires(hass):
    from unittest.mock import AsyncMock

    local = LocalCamera(hass, "entry", CAMERA)
    local.connected = True
    local.motion, local._motion_until = True, 0
    local._device = MagicMock()
    local._device.receive.return_value = {}

    async def stop_loop(_seconds):
        local._stopping.set()

    with patch.object(local, "_pause", AsyncMock(side_effect=stop_loop)), \
         patch("custom_components.tuya_camera_bridge.lan.time", SimpleNamespace(monotonic=lambda: 5.0)):
        await local._run()
    assert local.connected
    assert not local.motion
    await local.stop()


@pytest.mark.parametrize("battery", [False, True])
async def test_encrypted_local_camera_read_write_event_and_shutdown(hass, socket_enabled, battery):
    """Use the real TinyTuya encryption/client and a synthetic TCP camera."""
    values = {"240": False, "108": "0", "241": 7}
    if battery:
        values["145"] = 80
    commands = []
    refreshes = []
    clients = []
    tasks = set()
    cipher = tinytuya.AESCipher(KEY.encode())

    async def camera(reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        clients.append(writer)
        try:
            while True:
                header = await reader.readexactly(16)
                parsed = parse_header(header)
                message = unpack_message(header + await reader.readexactly(parsed.length), no_retcode=True)
                if message.cmd == CT.CONTROL:
                    body = message.payload[15:] if message.payload.startswith(b"3.3") else message.payload
                    request = json.loads(cipher.decrypt(body, use_base64=False))
                    if battery:
                        assert request["uid"] == "synthetic-account"
                    values.update(request["dps"])
                    commands.append(request["dps"])
                elif message.cmd == CT.UPDATEDPS:
                    request = json.loads(cipher.decrypt(message.payload, use_base64=False))
                    refreshes.append(request["dpId"])
                elif message.cmd not in (CT.DP_QUERY, CT.HEART_BEAT):
                    raise AssertionError(f"Unexpected command {message.cmd}")
                if battery:
                    # Actual battery IPC sequence: query rejection or control ACK,
                    # followed by a separate asynchronous STATUS report.
                    body = b"json obj data unvalid" if message.cmd == CT.DP_QUERY else b"{}"
                    ack = cipher.encrypt(body, use_base64=False)
                    writer.write(pack_message(TuyaMessage(message.seqno, message.cmd, 0,
                                                           struct.pack(">I", 0) + ack, 0)))
                    await writer.drain()
                    await asyncio.sleep(0.01)
                # Battery status initially reports telemetry only. Settings are
                # sent after the explicit read refresh, never as assumed defaults.
                report = {"145": values["145"]} if battery and message.cmd == CT.DP_QUERY else values
                response = cipher.encrypt(json.dumps({"dps": report}).encode(), use_base64=False)
                writer.write(pack_message(TuyaMessage(message.seqno, message.cmd, 0,
                                                       struct.pack(">I", 0) + response, 0)))
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            tasks.discard(task)
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()

    server = await asyncio.start_server(camera, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    real_device = tinytuya.Device

    def device(*args, **kwargs):
        # The test fixture routes the private target to its loopback camera.
        instance = real_device(args[0], "127.0.0.1", args[2], **kwargs)
        instance.port = port
        return instance

    camera_config = CAMERA
    if battery:
        camera_config = {**CAMERA, "local": {**CAMERA["local"], "schema": [*SCHEMA,
            {"id": 145, "code": "wireless_electricity", "mode": "ro",
             "property": {"type": "value", "min": 0, "max": 100}}]}}
    local = LocalCamera(hass, "entry", camera_config, "synthetic-account" if battery else "")
    local.media_activity(True)
    try:
        with patch("custom_components.tuya_camera_bridge.lan.discover", return_value=("192.168.0.81", "3.3")), \
             patch("tinytuya.Device", side_effect=device):
            assert await local._connect()
            if battery:
                assert "basic_nightvision" not in local.values
                async with asyncio.timeout(2):
                    while "basic_nightvision" not in local.values:
                        local._apply(await local._call(local._device.receive))
                assert refreshes == [[240, 108, 241, 145]]
            assert local.values["ipc_pir_switch"] is False
            await local.write("ipc_pir_switch", True)
            await local.write("basic_nightvision", "2")
            await local.write("ipc_pir_sensitivity", 9)
            assert {code: local.values[code] for code in ("ipc_pir_switch", "basic_nightvision", "ipc_pir_sensitivity")} == {
                "ipc_pir_switch": True, "basic_nightvision": "2", "ipc_pir_sensitivity": 9,
            }
            assert commands == [{"240": True}, {"108": "2"}, {"241": 9}]
            payload = cipher.encrypt(json.dumps({"dps": {"115": "synthetic-motion-event"}}).encode(),
                                     use_base64=False)
            clients[0].write(pack_message(TuyaMessage(99, CT.STATUS, 0, struct.pack(">I", 0) + payload, 0)))
            await clients[0].drain()
            async with asyncio.timeout(2):
                while not local.motion:
                    local._apply(await local._call(local._device.receive), live=True)
            assert local.motion
            await local.stop()
            assert not local.connected and local._device is None
    finally:
        await local.stop()
        server.close()
        await server.wait_closed()
        for writer in clients:
            writer.close()
        if tasks:
            await asyncio.gather(*tasks)


BATTERY_CAMERA = {**CAMERA, "local": {**CAMERA["local"], "schema": [*SCHEMA,
    {"id": 145, "code": "wireless_electricity", "mode": "ro",
     "property": {"type": "value", "min": 0, "max": 100}}]}}


async def test_battery_idle_has_no_discovery_and_concurrent_media_share_one_socket(hass):
    local = LocalCamera(hass, "entry", BATTERY_CAMERA)
    device = MagicMock()
    device.status.return_value = {"dps": {"145": 80}}
    device.receive.return_value = None
    idle = asyncio.Event()
    resumed = asyncio.Event()

    async def pause(seconds):
        if seconds == 3600:
            idle.set()
            await local._wake.wait()
            local._wake.clear()
        else:
            resumed.set()
            await asyncio.sleep(0.001)

    with patch.object(local, "_pause", side_effect=pause), \
         patch("custom_components.tuya_camera_bridge.lan.discover", return_value=("192.168.0.81", "3.3")) as discover_mock, \
         patch("tinytuya.Device", return_value=device) as factory:
        await local.start()
        await asyncio.wait_for(idle.wait(), 1)
        discover_mock.assert_not_called()
        local.media_activity(True)
        local.media_activity(True)
        await asyncio.wait_for(resumed.wait(), 1)
        assert local.connected and local.values["wireless_electricity"] == 80
        local.media_activity(False)
        assert local._window_open()  # Other consumer still holds the shared session.
        factory.assert_called_once()
        local.media_activity(False)
        local._media_until = 0
        idle.clear()
        await asyncio.wait_for(idle.wait(), 1)
        assert not local.connected and local.status == "standby"
        assert local.values["wireless_electricity"] == 80
        assert local.observed_at["wireless_electricity"]
        device.close.assert_called_once()
        # A new media consumer reconnects after sleeping, without an idle poll.
        resumed.clear()
        local.media_activity(True)
        await asyncio.wait_for(resumed.wait(), 1)
        assert factory.call_count == 2
        await local.stop()
    assert local._task is None and not local.connected


async def test_battery_command_cannot_confirm_itself_from_cached_value(hass):
    local = LocalCamera(hass, "entry", BATTERY_CAMERA)
    local.connected = True
    local.values["ipc_pir_switch"] = True
    local._device = MagicMock()
    local._device.set_value.return_value = {}
    local._device.status.return_value = {"dps": {"145": 80}}
    local._stopping.set()  # Bound the wait; an old matching value is still not proof.
    local._stopping.clear()
    # Stop immediately after sending the command, before any new matching DP.
    local._device.set_value.side_effect = lambda *_args: local._stopping.set() or {}
    with pytest.raises(HomeAssistantError, match="did not confirm"):
        await local.write("ipc_pir_switch", True)
    assert not local.connected
    assert local.values["ipc_pir_switch"] is True  # Historical state only.


async def test_battery_control_wakes_existing_media_path_and_waits_for_lan(hass):
    from unittest.mock import AsyncMock

    local = LocalCamera(hass, "entry", BATTERY_CAMERA)
    device = MagicMock()
    device.set_value.return_value = None
    device.receive.side_effect = [
        {"Err": "904", "Error": "Unexpected refresh acknowledgement"},
        {"dps": {"108": "2"}},
        {"dps": {"108": "2"}},
        {"dps": {"108": "2"}},
    ]
    device.status.return_value = {}

    closed = asyncio.Event()

    async def wake(ready):
        local._device = device
        local.connected = True
        local._ready.set()
        ready()
        try:
            await asyncio.Event().wait()
        finally:
            closed.set()

    local.wake_media = AsyncMock(side_effect=wake)
    async with asyncio.timeout(2):
        await asyncio.gather(local.write("basic_nightvision", "2"), local.write("basic_nightvision", "2"))
    await local.write("basic_nightvision", "2")
    local.wake_media.assert_awaited_once()  # Sequential calls share the short grace too.
    assert local.values["basic_nightvision"] == "2"
    device.set_value.assert_called_with("108", "2", True)
    device.updatedps.assert_not_called()
    assert not closed.is_set()
    await local.stop()
    assert closed.is_set()
    assert local._command_media_task is None


@pytest.mark.parametrize("restored_unreported", [False, True])
async def test_battery_write_drains_initial_reports_before_control(hass, restored_unreported):
    local = LocalCamera(hass, "entry", BATTERY_CAMERA)
    local.values = {"basic_nightvision": "0", "ipc_pir_switch": False}
    if restored_unreported:
        # HA restores observations from earlier sessions. A camera need not
        # report unrelated settings again before accepting this command.
        local.values["ipc_pir_sensitivity"] = 7
    local.connected = True
    local._control_initialized = False
    device = local._device = MagicMock()
    device.receive.side_effect = [
        {"dps": {"108": "0"}},
        {"dps": {"240": False}},
        {"dps": {"240": False}},  # Tail of the initial batch, after the target DP.
        None,
        {"dps": {"108": "2"}},
    ]

    def control(*args):
        assert device.receive.call_count == 4
        return None

    device.set_value.side_effect = control
    await local.write("basic_nightvision", "2")
    assert local.values["basic_nightvision"] == "2"
    assert local._control_initialized
    device.updatedps.assert_not_called()
    await local.stop()


@pytest.mark.parametrize("report_arrives", [True, False])
async def test_battery_command_retries_an_ignored_initial_read_once(hass, monkeypatch, report_arrives):
    from custom_components.tuya_camera_bridge import lan

    clock = [0.0]
    monkeypatch.setattr(lan, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    local = LocalCamera(hass, "entry", BATTERY_CAMERA)
    local.values = {"basic_nightvision": "0", "ipc_pir_sensitivity": 7}
    local.connected = True
    local._control_initialized = False
    device = local._device = MagicMock()
    reported = False

    def receive():
        nonlocal reported
        clock[0] += 1
        if device.set_value.called:
            return {"dps": {"108": "2"}}
        if report_arrives and device.updatedps.called and not reported:
            reported = True
            return {"dps": {"108": "0"}}
        return None

    def control(*args):
        assert reported
        device.updatedps.assert_called_once_with([108], True)

    device.receive.side_effect = receive
    device.set_value.side_effect = control
    if report_arrives:
        await local.write("basic_nightvision", "2")
        assert local.values["basic_nightvision"] == "2"
    else:
        with pytest.raises(HomeAssistantError, match="did not confirm"):
            await local.write("basic_nightvision", "2")
        device.set_value.assert_not_called()
        assert local.values["basic_nightvision"] == "0"
    device.updatedps.assert_called_once_with([108], True)
    await local.stop()


@pytest.mark.parametrize("battery", [False, True])
async def test_media_controls_share_go_socket_and_confirm_and_restore(hass, battery):
    from unittest.mock import AsyncMock

    local = LocalCamera(hass, "entry", BATTERY_CAMERA if battery else CAMERA, "synthetic-user")
    local.wake_media = AsyncMock(side_effect=AssertionError("Active media must be reused"))
    local.media_activity(True)
    bridge = MagicMock()
    pending = []

    async def request(camera_id, operation, **payload):
        assert camera_id == CAMERA["camera_id"]
        if operation == "status":
            return {"dps": {"108": "0", "240": False}}
        if operation == "receive":
            return {"dps": pending.pop(0) if pending else None}
        if operation == "set":
            pending.append({payload["index"]: payload["value"]})
        return {"dps": None}

    bridge.local_request = AsyncMock(side_effect=request)
    local.media_bridge = bridge
    with patch("tinytuya.Device", side_effect=AssertionError("A second socket must not open")):
        assert await local._connect()
        await local.write("basic_nightvision", "1")
        assert local.values["basic_nightvision"] == "1"
        await local.write("basic_nightvision", "0")
        assert local.values["basic_nightvision"] == "0"
        await local._close()
    assert not local.connected
    local.wake_media.assert_not_awaited()
    assert not any(call.args[1] == "query" for call in bridge.local_request.call_args_list)
    assert [call.kwargs for call in bridge.local_request.call_args_list if call.args[1] == "set"] == [
        {"index": "108", "value": "1"}, {"index": "108", "value": "0"},
    ]
