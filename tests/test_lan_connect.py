"""Preserve connection I/O ordering while decomposing the LAN state machine."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from custom_components.tuya_camera import lan

from .test_lan import BATTERY_CAMERA, CAMERA


class ScriptedDevice:
    """Record synthetic socket operations without opening another connection."""

    def __init__(self, events, initial, reports=(), name="device"):
        self.events, self.initial, self.reports, self.name = events, initial, list(reports), name
        self.disabledetect = False

    def status(self):
        self.events.append((self.name, "status"))
        return self.initial

    def receive(self):
        self.events.append((self.name, "receive"))
        return self.reports.pop(0) if self.reports else None

    def updatedps(self, indices, nowait):
        self.events.append((self.name, "updatedps", tuple(indices), nowait))

    def close(self):
        self.events.append((self.name, "close"))


async def test_battery_connect_orders_status_reports_and_one_nonblocking_refresh(hass):
    """Drain startup telemetry before requesting readable scalars without an ACK wait."""
    events = []
    device = ScriptedDevice(events, {"Err": "914"}, [{"dps": {"240": False}}, None, None, None])
    local = lan.LocalCamera(hass, "entry", BATTERY_CAMERA)
    local.media_activity(True)
    try:
        with patch.object(lan, "discover", return_value=("192.168.0.81", "3.3")), \
             patch.object(lan.tinytuya, "Device", return_value=device) as constructor:
            assert await local._connect()
        assert events == [("device", "status"), *[("device", "receive")] * 4,
                          ("device", "updatedps", (240, 108, 241, 145), True)]
        assert device.disabledetect
        assert local.connected
        assert local._ready.is_set()
        assert not local._control_initialized
        assert local._revisions["ipc_pir_switch"] == 2
        constructor.assert_called_once_with(local.camera_id, "192.168.0.81", local.config["local_key"],
                                            version=3.3, persist=True, connection_timeout=1,
                                            connection_retry_limit=1)
    finally:
        await local.stop()


@pytest.mark.parametrize("code", ["901", "905"])
async def test_offline_initial_status_closes_without_version_fallback(hass, code):
    """An offline socket cannot be repaired by trying other protocol versions."""
    events = []
    device = ScriptedDevice(events, {"Err": code})
    local = lan.LocalCamera(hass, "entry", BATTERY_CAMERA)
    local.media_activity(True)
    try:
        with patch.object(lan, "discover", return_value=("192.168.0.81", "unknown")), \
             patch.object(lan.tinytuya, "Device", return_value=device) as constructor:
            assert not await local._connect()
        assert events == [("device", "status"), ("device", "close")]
        constructor.assert_called_once()
        assert local._device is None
        assert not local.connected
        assert not local._ready.is_set()
    finally:
        await local.stop()


@pytest.mark.parametrize("code", ["901", "905"])
async def test_battery_startup_drain_failure_does_not_refresh_or_try_next_version(hass, code):
    """A failed startup report ends the chosen connection before requesting settings."""
    events = []
    device = ScriptedDevice(events, {"dps": {"240": False}}, [{"Err": code}])
    local = lan.LocalCamera(hass, "entry", BATTERY_CAMERA)
    local.media_activity(True)
    try:
        with patch.object(lan, "discover", return_value=("192.168.0.81", "unknown")), \
             patch.object(lan.tinytuya, "Device", return_value=device) as constructor:
            assert not await local._connect()
        assert events == [("device", "status"), ("device", "receive"), ("device", "close")]
        constructor.assert_called_once()
        assert not local.connected
        assert not local._ready.is_set()
    finally:
        await local.stop()


async def test_version_fallback_closes_previous_socket_before_opening_another(hass):
    """A protocol mismatch permits fallback, with exactly one socket owned at a time."""
    events = []
    first = ScriptedDevice(events, {"Err": "903"}, name="first")
    second = ScriptedDevice(events, {"dps": {"240": False}}, name="second")
    local = lan.LocalCamera(hass, "entry", CAMERA)

    def construct(*_args, **kwargs):
        """Choose a scripted socket and record each attempted protocol version."""
        events.append(("open", kwargs["version"]))
        return first if kwargs["version"] == 3.3 else second

    try:
        with patch.object(lan, "discover", return_value=("192.168.0.81", "unknown")), \
             patch.object(lan.tinytuya, "Device", side_effect=construct) as constructor:
            assert await local._connect()
        assert events == [("open", 3.3), ("first", "status"), ("first", "close"),
                          ("open", 3.4), ("second", "status")]
        assert [call.kwargs["version"] for call in constructor.call_args_list] == [3.3, 3.4]
        assert local.config["version"] == "3.4"
        assert local._device is second
        assert local.connected
    finally:
        await local.stop()


@pytest.mark.parametrize("endpoint", [None, ("203.0.113.1", "3.3")])
async def test_missing_or_nonprivate_discovery_never_constructs_device(hass, endpoint):
    """Discovery validation remains ahead of socket construction."""
    local = lan.LocalCamera(hass, "entry", CAMERA)
    with patch.object(lan, "discover", return_value=endpoint), patch.object(lan.tinytuya, "Device") as constructor:
        assert not await local._connect()
    constructor.assert_not_called()
    assert local.status == "not_discovered"
    assert not local._ready.is_set()
    await local.stop()


async def test_battery_status_wait_stops_at_deadline_without_real_sleep(hass, monkeypatch):
    """An absent pushed report does not keep the connection attempt unbounded."""
    clock = [0.0]
    monkeypatch.setattr(lan, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    events = []
    device = ScriptedDevice(events, {"Err": "914"})

    def receive():
        """Advance beyond the status deadline when no report arrives."""
        clock[0] = 9.0
        events.append(("device", "receive"))
        return None

    device.receive = receive
    local = lan.LocalCamera(hass, "entry", BATTERY_CAMERA)
    local.media_activity(True)
    try:
        with patch.object(lan, "discover", return_value=("192.168.0.81", "3.3")), \
             patch.object(lan.tinytuya, "Device", return_value=device):
            assert not await local._connect()
        assert events == [("device", "status"), ("device", "receive"), ("device", "close")]
        assert local.status == "connection_failed"
        assert not local._ready.is_set()
    finally:
        await local.stop()


@pytest.mark.parametrize("stopping", [False, True])
async def test_battery_startup_drain_aborts_before_refresh_when_window_closes(hass, stopping):
    """Closing the media window or stopping must prevent a late settings refresh."""
    events = []
    device = ScriptedDevice(events, {"dps": {"240": False}})
    local = lan.LocalCamera(hass, "entry", BATTERY_CAMERA)
    local.media_activity(True)

    def receive():
        """Close the startup window while delivering an empty report."""
        events.append(("device", "receive"))
        if stopping:
            local._stopping.set()
        else:
            local._media_users, local._media_until = 0, 0
        return None

    device.receive = receive
    try:
        with patch.object(lan, "discover", return_value=("192.168.0.81", "3.3")), \
             patch.object(lan.tinytuya, "Device", return_value=device):
            assert not await local._connect()
        assert events == [("device", "status"), ("device", "receive"), ("device", "close")]
        assert not local.connected
        assert not local._ready.is_set()
    finally:
        await local.stop()
