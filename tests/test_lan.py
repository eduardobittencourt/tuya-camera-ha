"""LAN isolation, privacy, state confirmation and actual encrypted TCP traffic."""
import asyncio
import json
import logging
import struct
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


async def test_encrypted_local_camera_read_write_event_and_shutdown(hass, socket_enabled):
    """Use the real TinyTuya encryption/client and a synthetic TCP camera."""
    values = {"240": False, "108": "0", "241": 7}
    commands = []
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
                    values.update(request["dps"])
                    commands.append(request["dps"])
                elif message.cmd not in (CT.DP_QUERY, CT.HEART_BEAT):
                    raise AssertionError(f"Unexpected command {message.cmd}")
                response = cipher.encrypt(json.dumps({"dps": values}).encode(), use_base64=False)
                writer.write(pack_message(TuyaMessage(message.seqno, message.cmd, 0,
                                                       struct.pack(">I", 0) + response, 0)))
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            tasks.discard(task)
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(camera, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    real_device = tinytuya.Device

    def device(*args, **kwargs):
        # The test fixture routes the private target to its loopback camera.
        instance = real_device(args[0], "127.0.0.1", args[2], **kwargs)
        instance.port = port
        return instance

    local = LocalCamera(hass, "entry", CAMERA)
    try:
        with patch("custom_components.tuya_camera_bridge.lan.discover", return_value=("192.168.0.81", "3.3")), \
             patch("tinytuya.Device", side_effect=device):
            assert await local._connect()
            assert local.values["ipc_pir_switch"] is False
            await local.write("ipc_pir_switch", True)
            await local.write("basic_nightvision", "2")
            await local.write("ipc_pir_sensitivity", 9)
            assert local.values == {"ipc_pir_switch": True, "basic_nightvision": "2", "ipc_pir_sensitivity": 9}
            assert commands == [{"240": True}, {"108": "2"}, {"241": 9}]
            payload = cipher.encrypt(json.dumps({"dps": {"115": "synthetic-motion-event"}}).encode(),
                                     use_base64=False)
            clients[0].write(pack_message(TuyaMessage(99, CT.STATUS, 0, struct.pack(">I", 0) + payload, 0)))
            await clients[0].drain()
            assert local._apply(await local._call(local._device.receive), live=True)
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
