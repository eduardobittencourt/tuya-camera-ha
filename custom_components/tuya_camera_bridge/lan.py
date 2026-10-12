"""Camera DP transport: private IPv4 sockets only, with no cloud fallback."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
import time
from contextlib import suppress
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path

import tinytuya
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN

PRIVATE_NETWORKS = tuple(IPv4Network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
_LIBRARY_CONTEXT = threading.local()


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


def discover(device_id: str, mac: str, host: str = "", version: str = "") -> tuple[str, str] | None:
    """Use an exact UDP device match, or the camera MAC in the LAN ARP table."""
    if private_address(host):
        return host, version
    try:
        found = _private_call(
            lambda: tinytuya.scanner.devices(verbose=False, poll=False, forcescan=False, scantime=3,
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


class LocalCamera:
    """Own one persistent LAN socket and serialize receive/heartbeat/commands."""

    def __init__(self, hass: HomeAssistant, entry_id: str, camera: dict) -> None:
        self.hass = hass
        self.camera_id = camera["camera_id"]
        self.config = camera.get("local", {})
        self.schema = {item["code"]: item for item in self.config.get("schema", [])}
        self.values: dict = {}
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

    async def start(self) -> None:
        if self.config.get("local_key"):
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping.set()
        if self._task:
            # Let the bounded socket operation finish before closing its socket.
            await self._task
            self._task = None
        async with self._lock:
            await self._close()

    async def _call(self, function, *args):
        return await self.hass.async_add_executor_job(_private_call, function, *args)

    async def _close(self) -> None:
        if self._device:
            await self._call(self._device.close)
            self._device = None
        self.connected = False
        self.values.clear()
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
            kind = definition.get("property", {}).get("type")
            if kind in ("bool", "value", "enum") and isinstance(value, (bool, int, float, str)):
                self.values[code] = value
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
            result = await self._call(self._device.status)
            if self._apply(result):
                self.config = {**self.config, "host": host, "version": candidate}
                self.connected, self.status = True, "connected"
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
            await asyncio.wait_for(self._stopping.wait(), seconds)

    async def _run(self) -> None:
        last_heartbeat = last_status = 0.0
        while not self._stopping.is_set():
            try:
                async with self._lock:
                    if not self.connected:
                        await self._connect()
                        last_heartbeat = last_status = time.monotonic()
                    elif time.monotonic() - last_status >= 30:
                        if not self._apply(await self._call(self._device.status)):
                            self.status = "disconnected"
                            await self._close()
                        last_status = time.monotonic()
                    else:
                        if time.monotonic() - last_heartbeat >= 10:
                            await self._call(self._device.heartbeat)
                            last_heartbeat = time.monotonic()
                        response = await self._call(self._device.receive)
                        if isinstance(response, dict) and (response.get("Err") or response.get("Error")):
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
            await self._pause(0.05 if self.connected else 30)

    async def write(self, code: str, value) -> None:
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
        async with self._lock:
            if not self.connected or self._stopping.is_set():
                raise HomeAssistantError("The camera LAN connection is unavailable")
            try:
                response = await self._call(self._device.set_value, str(definition["id"]), value)
                if isinstance(response, dict) and (response.get("Err") or response.get("Error")):
                    raise HomeAssistantError("The camera rejected the LAN command")
                self._apply(response)
                # Confirm from the camera; do not invent an optimistic state.
                if not self._apply(await self._call(self._device.status)) or self.values.get(code) != value:
                    raise HomeAssistantError("The camera did not confirm the LAN command")
            except Exception:  # noqa: BLE001 - keep dependency errors out of HA logs/UI
                self.status = "disconnected"
                await self._close()
                raise HomeAssistantError("The camera did not confirm the LAN command") from None
