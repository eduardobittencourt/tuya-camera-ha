"""Private, on-demand FFmpeg relay using Home Assistant's existing binary."""
from __future__ import annotations

import asyncio
import secrets
from collections.abc import Callable

from .bridge import stop_process


class FfmpegRelay:
    """Expose H.264/AAC MPEG-TS over loopback for native HA streaming."""

    def __init__(self, binary: str, source: Callable[[], str], hevc: Callable[[], bool]) -> None:
        self.binary = binary
        self.source = source
        self.hevc = hevc
        self._path = f"/{secrets.token_urlsafe(24)}.ts"
        self._server: asyncio.Server | None = None
        self._tasks: set[asyncio.Task] = set()
        self._processes: set[asyncio.subprocess.Process] = set()
        self._slots = asyncio.Semaphore(4)
        self._snapshot_lock = asyncio.Lock()

    @property
    def url(self) -> str:
        if self._server is None or not self._server.sockets:
            raise RuntimeError("Relay is not running")
        return f"http://127.0.0.1:{self._server.sockets[0].getsockname()[1]}{self._path}"

    @property
    def active_processes(self) -> int:
        return len(self._processes)

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._accept, "127.0.0.1", 0, limit=16*1024)

    async def stop(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            server.close()
            server.abort_clients()
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.gather(*(stop_process(process) for process in tuple(self._processes)))
        self._processes.clear()
        if server is not None:
            await server.wait_closed()

    def command(self) -> list[str]:
        video = ["-c:v", "copy"]
        if self.hevc():
            video = ["-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
                     "-pix_fmt", "yuv420p", "-vf", "scale=-2:720,fps=15", "-g", "30", "-b:v", "1200k"]
        return [
            self.binary, "-hide_banner", "-loglevel", "error", "-nostdin", "-rtsp_transport", "tcp",
            "-timeout", "35000000", "-i", self.source(), "-map", "0:v:0", "-map", "0:a:0?", *video,
            "-c:a", "aac", "-ac", "1", "-ar", "16000", "-b:a", "48k", "-f", "mpegts",
            "-mpegts_flags", "+resend_headers", "-muxdelay", "0", "pipe:1",
        ]

    async def snapshot(self) -> bytes | None:
        """Return a fresh frame; an old image must not hide a disconnected camera."""
        async with self._snapshot_lock:
            # Leave time for Tuya signaling within HA's ten-second image deadline;
            # the default five-second FFmpeg input probe can consume that budget.
            process = await asyncio.create_subprocess_exec(
                self.binary, "-hide_banner", "-loglevel", "error", "-nostdin", "-rtsp_transport", "tcp",
                "-timeout", "35000000", "-allowed_media_types", "video", "-fpsprobesize", "0",
                "-analyzeduration", "1000000", "-probesize", "512000",
                "-i", self.source(), "-frames:v", "1", "-f", "image2pipe",
                "-c:v", "mjpeg", "pipe:1", stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, start_new_session=True,
            )
            self._processes.add(process)
            try:
                async with asyncio.timeout(40):
                    content, _ = await process.communicate()
                if process.returncode == 0 and content.startswith(b"\xff\xd8"):
                    return content
                return None
            finally:
                await stop_process(process)
                self._processes.discard(process)

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task is None:
            writer.close()
            return
        self._tasks.add(task)
        process: asyncio.subprocess.Process | None = None
        try:
            async with asyncio.timeout(5):
                headers = await reader.readuntil(b"\r\n\r\n")
            if headers.split(b"\r\n", 1)[0] != f"GET {self._path} HTTP/1.1".encode():
                writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                await writer.drain()
                return
            async with self._slots:
                process = await asyncio.create_subprocess_exec(
                    *self.command(), stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL, start_new_session=True,
                )
                self._processes.add(process)
                assert process.stdout is not None
                async with asyncio.timeout(40):
                    first = await process.stdout.read(65536)
                if not first:
                    writer.write(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\n\r\n")
                    await writer.drain()
                    return
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: video/MP2T\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n")
                writer.write(first)
                await writer.drain()
                while True:
                    async with asyncio.timeout(40):
                        data = await process.stdout.read(65536)
                    if not data:
                        break
                    writer.write(data)
                    await writer.drain()
        except (OSError, ConnectionError, TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            pass
        finally:
            if process is not None:
                await stop_process(process)
                self._processes.discard(process)
            writer.close()
            try:
                async with asyncio.timeout(2):
                    await writer.wait_closed()
            except (OSError, ConnectionError, TimeoutError):
                writer.transport.abort()
            self._tasks.discard(task)
