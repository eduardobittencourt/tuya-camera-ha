"""Lifecycle and private status protocol for the managed Go bridge."""
from __future__ import annotations

import asyncio
import json
import os
import signal
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from urllib.parse import quote

START_TIMEOUT = 90.0
STOP_TIMEOUT = 10.0
RESTART_MIN_DELAY = 2.0
RESTART_MAX_DELAY = 60.0


class BridgeError(RuntimeError):
    """The bridge failed to become ready."""


class BridgeAuthenticationError(BridgeError):
    """A new Tuya login is required."""


async def stop_process(process: asyncio.subprocess.Process) -> None:
    """Terminate the whole process group and reap it, including partial startup."""
    if process.returncode is not None:
        return
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)

    async def drain(stream: asyncio.StreamReader | None) -> None:
        if stream is not None:
            # An existing monitor/communicate task may already own this reader.
            with suppress(RuntimeError):
                while await stream.read(65536):
                    pass

    drains = [asyncio.create_task(drain(stream)) for stream in (process.stdout, process.stderr)]
    try:
        try:
            await asyncio.wait_for(process.wait(), STOP_TIMEOUT)
        except TimeoutError:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
    finally:
        for task in drains:
            task.cancel()
        await asyncio.gather(*drains, return_exceptions=True)


class ManagedBridge:
    """Start, monitor, restart and stop an isolated subprocess for one account."""

    def __init__(
        self, binary: Path, directory: Path, config: dict,
        on_change: Callable[[], None], on_auth_required: Callable[[], None],
    ) -> None:
        self.binary = binary
        self.directory = directory
        self.config = config
        self.on_change = on_change
        self.on_auth_required = on_auth_required
        self.process: asyncio.subprocess.Process | None = None
        self.task: asyncio.Task | None = None
        self.ready = False
        self.auth_required = False
        self.source_port = 0
        self.sources: dict[str, dict] = {}
        self.camera_status: dict[str, dict] = {}
        self._started = asyncio.Event()
        self._stopping = False

    async def start(self) -> None:
        await asyncio.to_thread(self.directory.mkdir, parents=True, exist_ok=True, mode=0o700)
        self._stopping = False
        self.task = asyncio.create_task(self._monitor())
        try:
            await asyncio.wait_for(self._started.wait(), START_TIMEOUT)
            if self.auth_required:
                raise BridgeAuthenticationError("The Tuya session expired")
            if not self.ready:
                raise BridgeError("The bridge could not start")
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        self._stopping = True
        task, self.task = self.task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if self.process is not None:
            await stop_process(self.process)
            self.process = None
        self.ready = False

    def source_url(self, camera_id: str) -> str:
        source = self.sources[camera_id]
        return f"rtsp://127.0.0.1:{self.source_port}{quote(source['path'], safe='/')}"

    async def _monitor(self) -> None:
        delay = RESTART_MIN_DELAY
        while not self._stopping and not self.auth_required:
            process: asyncio.subprocess.Process | None = None
            reader: asyncio.Task | None = None
            launched = time.monotonic()
            try:
                process = self.process = await asyncio.create_subprocess_exec(
                    str(self.binary), "addon", "--managed", "--config", "-",
                    "--data-dir", str(self.directory),
                    cwd=self.directory, stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                    start_new_session=True,
                )
                assert process.stdin is not None
                process.stdin.write(json.dumps(self.config, separators=(",", ":")).encode())
                await process.stdin.drain()
                process.stdin.close()
                reader = asyncio.create_task(self._read_events(process))
                await process.wait()
                await reader
            except (OSError, ConnectionError, ValueError):
                pass
            finally:
                self.ready = False
                if process is not None:
                    await stop_process(process)
                if reader is not None:
                    reader.cancel()
                    with suppress(asyncio.CancelledError):
                        await reader
                self.process = None
                self.on_change()
            if not self._started.is_set():
                self._started.set()
                return
            if self.auth_required or self._stopping:
                return
            if time.monotonic() - launched >= 60:
                delay = RESTART_MIN_DELAY
            await asyncio.sleep(delay)
            delay = min(delay * 2, RESTART_MAX_DELAY)

    async def _read_events(self, process: asyncio.subprocess.Process) -> None:
        assert process.stdout is not None
        while line := await process.stdout.readline():
            if not line.startswith(b'{"event":') and not line.startswith(b'{"cameras":') and not line.startswith(b'{"camera_id":'):
                continue
            try:
                event = json.loads(line)
                self._handle_event(event)
                if self.auth_required:
                    await stop_process(process)
                    return
            except (ValueError, KeyError, TypeError):
                continue

    def _handle_event(self, event: dict) -> None:
        kind = event.get("event")
        if kind == "ready":
            port = event["source_port"]
            cameras = event["cameras"]
            expected = {item["camera_id"] for item in self.config["cameras"]}
            if not isinstance(port, int) or not 0 < port <= 65535:
                return
            if not isinstance(cameras, list):
                return
            sources = {
                item["camera_id"]: item for item in cameras
                if isinstance(item, dict) and isinstance(item.get("path"), str)
                and item["path"].startswith("/")
            }
            if set(sources) != expected:
                return
            self.source_port = port
            self.sources = sources
            self.ready = True
            self._started.set()
            self.on_change()
        elif kind == "auth_required":
            self.auth_required = True
            self.ready = False
            self._started.set()
            self.on_auth_required()
            self.on_change()
        elif kind == "camera_status" and event.get("camera_id") in self.sources:
            state = event.get("state")
            if state in {"video", "error"}:
                previous = self.camera_status.get(event["camera_id"], {})
                self.camera_status[event["camera_id"]] = {
                    "state": state,
                    "last_video": time.time() if state == "video" else previous.get("last_video"),
                }
                self.on_change()
