"""Camera DP transport: private IPv4 sockets only, with no cloud fallback."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
import time
from contextlib import suppress
from datetime import UTC, datetime
from inspect import iscoroutinefunction
from ipaddress import IPv4Address, IPv4Network
from math import isfinite
from pathlib import Path

import tinytuya
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from tinytuya import scanner

from .const import DOMAIN

PRIVATE_NETWORKS = tuple(IPv4Network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
_LIBRARY_CONTEXT = threading.local()
_LOGGER = logging.getLogger(__name__)


class _PrivateLogFilter(logging.Filter):
    """TinyTuya debug messages include keys/payloads; suppress our calls only."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not getattr(_LIBRARY_CONTEXT, "active", False)


for _name in list(logging.Logger.manager.loggerDict):
    if _name == "tinytuya" or _name.startswith("tinytuya."):
        logging.getLogger(_name).addFilter(_PrivateLogFilter())


def private_address(value: str) -> bool:
    """Reject DNS names, WAN, loopback and metadata endpoints."""
    try:
        address = IPv4Address(value)
        return any(address in network for network in PRIVATE_NETWORKS)
    except (ValueError, TypeError):
        return False


def _private_call(function, *args):
    _LIBRARY_CONTEXT.active = True
    try:
        return function(*args)
    finally:
        _LIBRARY_CONTEXT.active = False


def _send_battery_value(device, index: str, value, account_uid: str):
    """Use the account identity observed in native IPC CONTROL packets."""
    payload = device.generate_payload(tinytuya.CONTROL, {index: value}, uid=account_uid)
    return device.send(payload)


def discover(device_id: str, mac: str, host: str = "", version: str = "") -> tuple[str, str] | None:
    """Use an exact UDP device match, or the camera MAC in the LAN ARP table."""
    if private_address(host):
        return host, version
    try:
        found = _private_call(
            lambda: scanner.devices(verbose=False, poll=False, forcescan=False, scantime=3,
                                    byID=True, wantids=[device_id],
                                    tuyadevices=[{"id": device_id, "name": "", "key": ""}]),
        )
    except OSError:
        # An occupied discovery port must not prevent the ARP fallback.
        found = {}
    item = found.get(device_id, {})
    if private_address(item.get("ip", "")):
        return item["ip"], str(item.get("version", ""))
    if mac:
        with suppress(OSError):
            for line in Path("/proc/net/arp").read_text().splitlines()[1:]:
                fields = line.split()
                if len(fields) >= 4 and fields[3].lower() == mac.lower() and private_address(fields[0]):
                    return fields[0], version
    return None


def signal(entry_id: str, camera_id: str) -> str:
    return f"{DOMAIN}_{entry_id}_{camera_id}_lan"


def valid_scalar(definition: dict, value) -> bool:
    """Only camera values compatible with the declared function are evidence."""
    prop = definition.get("property", {})
    kind = prop.get("type")
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "enum":
        return isinstance(value, str) and value in prop.get("range", [])
    return (kind == "value" and isinstance(value, (int, float)) and not isinstance(value, bool)
            and isfinite(value) and prop.get("min", float("-inf")) <= value <= prop.get("max", float("inf")))


class BridgeLANDevice:
    """TinyTuya-shaped adapter to the Go-owned signaling/DP socket."""

    def __init__(self, bridge, camera_id: str) -> None:
        self.bridge, self.camera_id = bridge, camera_id

    async def status(self):
        return await self.bridge.local_request(self.camera_id, "status")

    async def receive(self):
        result = await self.bridge.local_request(self.camera_id, "receive")
        return result if result.get("dps") else None

    async def updatedps(self, ids, nowait=True):
        return None  # Status pushes share signaling; refresh can interrupt IPC video.

    async def set_value(self, index, value, nowait=True):
        await self.bridge.local_request(self.camera_id, "set", index=str(index), value=value)

    async def heartbeat(self):
        return None  # The signaling owner already sends heartbeats.

    async def close(self):
        return None  # A control consumer must not close the shared media socket.


class LocalCamera:
    """Serialize LAN operations, using media windows for battery cameras."""

    def __init__(self, hass: HomeAssistant, entry_id: str, camera: dict, account_uid: str = "") -> None:
        self.hass = hass
        self.camera_id = camera["camera_id"]
        self._account_uid = account_uid
        self.config = camera.get("local", {})
        self.schema = {item["code"]: item for item in self.config.get("schema", [])}
        self.values: dict = {}
        self.observed_at: dict[str, str] = {}
        self.on_demand = "wireless_electricity" in self.schema
        self._media_users = 0
        self._media_until = 0.0
        self._wake = asyncio.Event()
        self._ready = asyncio.Event()
        self.wake_media = None
        self.media_bridge = None
        self._media_wake_task: asyncio.Task | None = None
        self._command_media_task: asyncio.Task | None = None
        self._command_media_ready = asyncio.Event()
        self._command_users = 0
        self._command_release_task: asyncio.Task | None = None
        self._command_cleanup_tasks: set[asyncio.Task] = set()
        self._revisions: dict[str, int] = {}
        self._connection_observed: set[str] = set()
        self._control_initialized = True
        self.connected = False
        self.status = "not_provisioned" if not self.config.get("local_key") else "disconnected"
        self.motion = False
        self.sound = False
        self._signal = signal(entry_id, self.camera_id)
        self._device = None
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()
        self._motion_until = 0.0
        self._sound_until = 0.0
        self._event_fingerprints: dict[str, bytes] = {}
        self._versions = ("3.3", "3.4", "3.5", "3.1")

    def changed(self) -> None:
        async_dispatcher_send(self.hass, self._signal)

    def media_activity(self, active: bool) -> None:
        """Share one LAN session across all media consumers; never wake media here."""
        if self._stopping.is_set():
            return
        self._media_users = max(0, self._media_users + (1 if active else -1))
        # Match the bridge's existing 30-second shutdown grace, without extending it.
        self._media_until = time.monotonic() + 30
        self._wake.set()

    def _window_open(self) -> bool:
        return not self.on_demand or self._media_users > 0 or time.monotonic() < self._media_until

    async def start(self) -> None:
        if self.config.get("local_key"):
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping.set()
        self._wake.set()
        if self._command_release_task is not None:
            self._command_release_task.cancel()
            self._command_release_task = None
        await asyncio.gather(*tuple(self._command_cleanup_tasks), return_exceptions=True)
        if self._media_wake_task:
            self._media_wake_task.cancel()
            await asyncio.gather(self._media_wake_task, return_exceptions=True)
            self._media_wake_task = None
        if self._command_media_task:
            self._command_media_task.cancel()
            await asyncio.gather(self._command_media_task, return_exceptions=True)
            self._command_media_task = None
        if self._task:
            # Let the bounded socket operation finish before closing its socket.
            await self._task
            self._task = None
        async with self._lock:
            await self._close()

    async def _call(self, function, *args):
        started = time.monotonic()
        if iscoroutinefunction(function):
            result = await function(*args)
        else:
            result = await self.hass.async_add_executor_job(_private_call, function, *args)
        # Timing/type only: dependency payloads and errors may contain secrets.
        _LOGGER.debug("LAN operation %s completed in %.3fs (%s)",
                      getattr(function, "__name__", "unknown"), time.monotonic() - started, type(result).__name__)
        return result

    async def _close(self) -> None:
        if self._device:
            await self._call(self._device.close)
            self._device = None
        self.connected = False
        self._ready.clear()
        self._connection_observed.clear()
        if not self.on_demand:
            self.values.clear()
            self.observed_at.clear()
        self.motion = self.sound = False
        self.changed()

    def _apply(self, response, *, live: bool = False) -> bool:
        """Never retain raw alarm packets, images, URLs or unknown DPs."""
        if not isinstance(response, dict) or response.get("Err") or response.get("Error"):
            return False
        dps = response.get("dps")
        if not isinstance(dps, dict):
            return False
        now = time.monotonic()
        for code, definition in self.schema.items():
            key = str(definition["id"])
            if key not in dps:
                continue
            value = dps[key]
            if valid_scalar(definition, value):
                self.values[code] = value
                self.observed_at[code] = datetime.now(UTC).isoformat()
                self._revisions[code] = self._revisions.get(code, 0) + 1
                self._connection_observed.add(code)
            # Initial status is a snapshot, not a new detection event.
            if code in ("movement_detect_pic", "decibel_upload") and isinstance(value, (str, bytes)) and value:
                fingerprint = hashlib.sha256(value.encode() if isinstance(value, str) else value).digest()
                fresh = fingerprint != self._event_fingerprints.get(code)
                self._event_fingerprints[code] = fingerprint
                if live and fresh and code == "movement_detect_pic":
                    self.motion, self._motion_until = True, now + 10
                if live and fresh and code == "decibel_upload":
                    self.sound, self._sound_until = True, now + 10
        self.changed()
        return True

    async def _connect(self) -> bool:
        if self.media_bridge:
            self._device = BridgeLANDevice(self.media_bridge, self.camera_id)
            result = await self._device.status()
            if not self._apply(result):
                return False
            self.connected, self.status = True, "connected"
            self._control_initialized = True
            self._ready.set()
            self.changed()
            return True
        endpoint = await self._call(discover, self.camera_id, self.config.get("mac", ""),
                                    self.config.get("host", ""), self.config.get("version", ""))
        if not endpoint:
            self.status = "not_discovered"
            self.changed()
            return False
        host, version = endpoint
        if not private_address(host):
            self.status = "not_discovered"
            self.changed()
            return False
        for candidate in ([version] if version in self._versions else self._versions):
            if self._stopping.is_set():
                return False
            self._device = await self._call(
                lambda v=candidate: tinytuya.Device(self.camera_id, host, self.config["local_key"],
                                                   version=float(v), persist=True,
                                                   connection_timeout=1, connection_retry_limit=1),
            )
            if self.on_demand:
                # These IPCs reject DP_QUERY but push valid reports afterwards.
                # Device22 auto-detection would switch to an incompatible query.
                self._device.disabledetect = True
                self._control_initialized = False
            result = await self._call(self._device.status)
            if self.on_demand and not self._apply(result):
                deadline = time.monotonic() + 8
                while (not self._stopping.is_set() and self._window_open()
                       and time.monotonic() < deadline):
                    if isinstance(result, dict) and str(result.get("Err")) in ("901", "905"):
                        break
                    result = await self._call(self._device.receive)
                    if self._apply(result):
                        break
            if self._apply(result):
                self.config = {**self.config, "host": host, "version": candidate}
                self.connected, self.status = True, "connected"
                if self.on_demand:
                    # The first telemetry packet is not the end of IPC startup.
                    # Drain the initial reports before asking for settings;
                    # these cameras can ignore an immediate refresh.
                    for _ in range(3):
                        if self._stopping.is_set() or not self._window_open():
                            break
                        response = await self._call(self._device.receive)
                        if isinstance(response, dict) and str(response.get("Err")) in ("901", "905"):
                            await self._close()
                            return False
                        self._apply(response)
                    if self._stopping.is_set() or not self._window_open():
                        await self._close()
                        return False
                    # Battery IPCs push only a few values spontaneously. Ask for
                    # readable scalar DPs once per connection and drain their
                    # delayed reports in _run; waiting for an ACK here can make
                    # TinyTuya close a perfectly usable socket.
                    indices = [int(item["id"]) for item in self.schema.values()
                               if "r" in item.get("mode", "")
                               and item.get("property", {}).get("type") in ("bool", "enum", "value")]
                    if indices:
                        await self._call(self._device.updatedps, indices, True)
                self._ready.set()
                self.changed()
                return True
            await self._close()
            # A refused/offline socket cannot be repaired by changing protocol.
            if isinstance(result, dict) and str(result.get("Err")) in ("901", "905"):
                break
        self.status = "connection_failed"
        self.changed()
        return False

    async def _pause(self, seconds: float) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(self._wake.wait(), seconds)
        self._wake.clear()

    async def _run(self) -> None:
        last_heartbeat = last_status = 0.0
        while not self._stopping.is_set():
            try:
                if not self._window_open():
                    async with self._lock:
                        self.status = "standby"
                        await self._close()
                    await self._pause(3600)
                    continue
                async with self._lock:
                    if not self.connected:
                        await self._connect()
                        last_heartbeat = last_status = time.monotonic()
                    elif not self.on_demand and not self.media_bridge and time.monotonic() - last_status >= 30:
                        if not self._apply(await self._call(self._device.status)):
                            self.status = "disconnected"
                            await self._close()
                        last_status = time.monotonic()
                    else:
                        if time.monotonic() - last_heartbeat >= 10:
                            await self._call(self._device.heartbeat)
                            last_heartbeat = time.monotonic()
                        response = await self._call(self._device.receive)
                        rejected_query = (self.on_demand and isinstance(response, dict)
                                          and str(response.get("Err")) in ("900", "904", "908"))
                        if (isinstance(response, dict) and (response.get("Err") or response.get("Error"))
                                and not rejected_query):
                            self.status = "disconnected"
                            await self._close()
                        else:
                            # Empty acknowledgements/heartbeats are not DP failures.
                            self._apply(response, live=True)
                    now = time.monotonic()
                    if self.motion and now >= self._motion_until:
                        self.motion = False
                        self.changed()
                    if self.sound and now >= self._sound_until:
                        self.sound = False
                        self.changed()
            except Exception:  # noqa: BLE001 - protocol errors can contain keys and raw payloads
                async with self._lock:
                    self.status = "connection_failed"
                    await self._close()
            if not self.connected:
                # Re-evaluate the LAN address after DHCP changes, without cloud discovery.
                self.config = {key: value for key, value in self.config.items() if key not in ("host", "version")}
            await self._pause(0.05 if self.connected else (1 if self.on_demand or self.media_bridge else 30))

    async def _wake_for_command(self) -> None:
        try:
            if self._command_media_task is None or self._command_media_task.done():
                self._command_media_ready.clear()

                async def hold_media():
                    with suppress(Exception):
                        await self.wake_media(self._command_media_ready.set)

                self._command_media_task = asyncio.create_task(hold_media())
            async with asyncio.timeout(50):
                await self._command_media_ready.wait()
                await self._ready.wait()
        except Exception:  # noqa: BLE001 - no dependency details in HA errors
            raise HomeAssistantError("The camera LAN connection is unavailable") from None

    async def _prepare_battery_command(self, code: str) -> None:
        """Finish the initial read burst before sending the first CONTROL."""
        if self._control_initialized:
            return
        _LOGGER.debug("Waiting for initial report for %s", code)
        # Restored observations may include settings/sensors that this session
        # never reports. Only the requested setting gates its own command.
        deadline = time.monotonic() + 20
        retry_at = time.monotonic() + 5
        refreshed = False
        heartbeat = time.monotonic()
        while code not in self._connection_observed:
            if self._stopping.is_set() or time.monotonic() >= deadline:
                raise HomeAssistantError("The camera did not finish its initial LAN state report")
            if time.monotonic() - heartbeat >= 10:
                await self._call(self._device.heartbeat)
                heartbeat = time.monotonic()
            if not refreshed and time.monotonic() >= retry_at:
                # The startup refresh can be ignored while a battery IPC wakes.
                # Retry only the requested setting, once and before CONTROL.
                await self._call(self._device.updatedps, [int(self.schema[code]["id"])], True)
                refreshed = True
            self._apply(await self._call(self._device.receive))
        # Drain duplicates and the tail of the initialization batch. A timeout
        # ends the drain; no extra DP query may overtake the following CONTROL.
        deadline = time.monotonic() + 3
        while not self._stopping.is_set() and time.monotonic() < deadline:
            response = await self._call(self._device.receive)
            if response is None:
                break
            self._apply(response)
        self._control_initialized = True
        _LOGGER.debug("Initial report ready for %s", code)

    async def write(self, code: str, value) -> None:
        if self._command_release_task is not None:
            self._command_release_task.cancel()
            self._command_release_task = None
        self._command_users += 1
        try:
            await self._write(code, value)
        finally:
            self._command_users -= 1
            if (not self._command_users and self._command_media_task is not None
                    and not self._stopping.is_set()):
                task = asyncio.create_task(self._release_command_media())
                self._command_release_task = task
                self._command_cleanup_tasks.add(task)
                task.add_done_callback(self._command_cleanup_tasks.discard)

    async def _release_command_media(self) -> None:
        # Sequential HA service calls can reuse the same media/LAN negotiation.
        try:
            await asyncio.sleep(2)
        except asyncio.CancelledError:
            return
        self._command_release_task = None
        task, self._command_media_task = self._command_media_task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _write(self, code: str, value) -> None:
        definition = self.schema.get(code, {})
        if "w" not in definition.get("mode", ""):
            raise HomeAssistantError("This camera function is read-only")
        prop = definition.get("property", {})
        kind = prop.get("type")
        valid = kind == "bool" and isinstance(value, bool)
        if kind == "enum":
            valid = isinstance(value, str) and value in prop.get("range", [])
        if kind == "value":
            minimum, maximum, step = prop.get("min", 0), prop.get("max", 0), prop.get("step", 1)
            valid = (isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum
                     and step > 0 and (value - minimum) % step == 0)
        if not valid:
            raise HomeAssistantError("Invalid value for this camera function")
        if (self.on_demand and self.wake_media and not self._stopping.is_set()
                and not (self.media_bridge and self.connected and self._window_open())):
            if self._media_wake_task is None or self._media_wake_task.done():
                self._media_wake_task = asyncio.create_task(self._wake_for_command())
            await asyncio.shield(self._media_wake_task)
        async with self._lock:
            if not self.connected or self._stopping.is_set():
                raise HomeAssistantError("The camera LAN connection is unavailable")
            try:
                if self.on_demand:
                    await self._prepare_battery_command(code)
                revision = self._revisions.get(code, 0)
                _LOGGER.debug("Sending LAN command for %s", code)
                if self.on_demand or self.media_bridge:
                    # Responses to the initial refresh may still be queued. A
                    # synchronous CONTROL can mistake them for its own reply
                    # and close the socket before the actual DP report arrives.
                    if self._account_uid and not self.media_bridge:
                        response = await self._call(_send_battery_value, self._device,
                                                    str(definition["id"]), value, self._account_uid)
                    else:
                        response = await self._call(self._device.set_value, str(definition["id"]), value, True)
                else:
                    response = await self._call(self._device.set_value, str(definition["id"]), value)
                if isinstance(response, dict) and (response.get("Err") or response.get("Error")):
                    raise HomeAssistantError("The camera rejected the LAN command")
                self._apply(response)
                # Confirm from the camera; do not invent an optimistic state.
                if not self.on_demand and not self.media_bridge:
                    self._apply(await self._call(self._device.status))
                deadline = time.monotonic() + (5 if self.on_demand or self.media_bridge else 0)
                while (self._revisions.get(code, 0) == revision or self.values.get(code) != value):
                    if self._stopping.is_set() or time.monotonic() >= deadline:
                        raise HomeAssistantError("The camera did not confirm the LAN command")
                    self._apply(await self._call(self._device.receive), live=True)
                _LOGGER.debug("LAN command confirmed for %s", code)
            except Exception:  # noqa: BLE001 - keep dependency errors out of HA logs/UI
                self.status = "disconnected"
                await self._close()
                raise HomeAssistantError("The camera did not confirm the LAN command") from None
