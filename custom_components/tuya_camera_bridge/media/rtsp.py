"""Private RTSP/TCP adapter for Home Assistant's FFmpeg consumers."""
from __future__ import annotations

import asyncio
import secrets
import struct
import time
from collections.abc import Callable
from contextlib import suppress
from urllib.parse import urlsplit


def rtp(payload: bytes, sequence: int, timestamp: int, kind: str, marker: bool = False) -> bytes:
    return struct.pack("!BBHII", 0x80, (96 if kind == "video" else 97) | (0x80 if marker else 0),
                       sequence & 0xFFFF, timestamp & 0xFFFFFFFF, 1 if kind == "video" else 2) + payload


def h264_payloads(nal: bytes):
    if len(nal) <= 1200 or nal[0] & 31 >= 24:
        yield nal
        return
    for offset in range(1, len(nal), 1198):
        yield bytes(((nal[0] & 0xE0) | 28, (nal[0] & 31) | (0x80 if offset == 1 else 0) |
                     (0x40 if offset + 1198 >= len(nal) else 0))) + nal[offset:offset + 1198]


class MediaSource:
    """Share one camera session among consumers with bounded individual queues."""

    def __init__(self, factory: Callable, changed: Callable, ended: Callable | None = None):
        self.factory, self.changed = factory, changed
        self.ended = ended or (lambda failed: None)
        self.session = None
        self.consumers: set[asyncio.Queue] = set()
        self.lock = asyncio.Lock()
        self.sequence = {"video": 0, "audio": 0}
        self.parameters: dict[int, bytes] = {}
        self.monitor: asyncio.Task | None = None
        self.hevc = False
        self.audio_codec = "L16/8000/1"
        self.video_seen = False
        self.last_report = 0

    async def acquire(self) -> asyncio.Queue:
        async with self.lock:
            queue: asyncio.Queue = asyncio.Queue(512)
            self.consumers.add(queue)
            try:
                if self.session is None:
                    self.session = await self.factory(self.packet)
                    self.hevc = getattr(self.session, "hevc", False)
                    self.audio_codec = getattr(self.session, "audio_codec", "L16/8000/1")
                    self.monitor = asyncio.create_task(self._watch())
            except BaseException:
                self.consumers.discard(queue)
                if self.session:
                    await self.session.close()
                    self.session = None
                raise
            return queue

    async def _watch(self):
        await self.session.failed.wait()
        for queue in self.consumers:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(None)

    async def release(self, queue) -> None:
        async with self.lock:
            self.consumers.discard(queue)
            if not self.consumers:
                await self._stop()

    async def _stop(self):
        if self.monitor:
            self.monitor.cancel()
            await asyncio.gather(self.monitor, return_exceptions=True)
            self.monitor = None
        if self.session:
            failed = self.session.failed.is_set()
            await self.session.close()
            self.session = None
            self.ended(failed)
        self.parameters.clear()
        self.video_seen = False
        self.last_report = 0

    async def stop(self):
        async with self.lock:
            for queue in self.consumers:
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(None)
            await self._stop()
            self.consumers.clear()

    def packet(self, kind: str, payload: bytes, timestamp: int, marker: bool):
        if kind == "video":
            if not self.video_seen or time.monotonic() - self.last_report >= 5:
                self.video_seen = True
                self.last_report = time.monotonic()
                self.changed()
            if not payload:
                return
            nal = payload[0] & 31
            if not self.hevc and nal in (7, 8):
                self.parameters[nal] = payload
            if not self.hevc and (nal == 5 or (nal == 28 and len(payload) > 1 and payload[1] & 0x9F == 0x85)):
                for parameter in self.parameters.values():
                    self._broadcast(kind, parameter, timestamp, False)
            packets = h264_payloads(payload) if not self.hevc else [payload]
        else:
            packets = [payload]
        packets = list(packets)
        for index, chunk in enumerate(packets):
            self._broadcast(kind, chunk, timestamp, marker and index == len(packets) - 1)

    def _broadcast(self, kind, payload, timestamp, marker):
        self.sequence[kind] += 1
        packet = rtp(payload, self.sequence[kind], timestamp, kind, marker)
        for queue in self.consumers:
            if queue.full():
                queue.get_nowait()
                queue.put_nowait(None)  # Disconnect a slow reader rather than growing memory.
            else:
                queue.put_nowait((kind, packet))

    def sdp(self, base: str) -> str:
        return "\r\n".join(("v=0", "o=- 1 1 IN IP4 127.0.0.1", "s=Tuya Camera", "t=0 0", "a=control:*",
                             "m=video 0 RTP/AVP 96", f"a=rtpmap:96 {'H265' if self.hevc else 'H264'}/90000",
                             *( [] if self.hevc else ["a=fmtp:96 packetization-mode=1"] ),
                             f"a=control:{base}/video", "m=audio 0 RTP/AVP 97",
                             f"a=rtpmap:97 {self.audio_codec}", f"a=control:{base}/audio", ""))


class RtspServer:
    """Loopback listener; no camera credentials or configuration over RTSP."""

    def __init__(self, sources: dict[str, MediaSource]):
        self.sources = sources
        self.server: asyncio.Server | None = None
        self.tasks: set[asyncio.Task] = set()

    @property
    def port(self):
        return self.server.sockets[0].getsockname()[1]

    async def start(self):
        self.server = await asyncio.start_server(self._accept, "127.0.0.1", 0, limit=32768)

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.gather(*(source.stop() for source in self.sources.values()))

    async def _accept(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        source = queue = sender = None
        channels = {}
        session = secrets.token_hex(12)
        lock = asyncio.Lock()

        async def response(cseq, status=200, headers=None, body=""):
            values = {"CSeq": cseq, "Session": session, **(headers or {})}
            if body:
                values["Content-Length"] = str(len(body.encode()))
            data = f"RTSP/1.0 {status} {'OK' if status == 200 else 'Unavailable'}\r\n"
            data += "".join(f"{k}: {v}\r\n" for k, v in values.items()) + "\r\n" + body
            async with lock:
                writer.write(data.encode())
                await writer.drain()

        async def send_packets():
            try:
                while item := await queue.get():
                    kind, packet = item
                    if kind in channels:
                        async with lock:
                            writer.write(b"$" + struct.pack("!BH", channels[kind], len(packet)) + packet)
                            await asyncio.wait_for(writer.drain(), 5)
            finally:
                writer.close()

        try:
            if len(self.tasks) > 32:
                return
            while True:
                first = await asyncio.wait_for(reader.readexactly(1), 65)
                if first == b"$":
                    frame = await reader.readexactly(3)
                    await reader.readexactly(struct.unpack_from("!H", frame, 1)[0])
                    continue
                request = first + await reader.readuntil(b"\r\n\r\n")
                lines = request.decode().split("\r\n")
                method, url, _ = lines[0].split(" ", 2)
                headers = {k.lower(): v.strip() for line in lines[1:] if ":" in line for k, v in [line.split(":", 1)]}
                length = int(headers.get("content-length", 0))
                if not 0 <= length <= 32768:
                    break
                if length:
                    await reader.readexactly(length)
                seq = headers.get("cseq", "0")
                path = urlsplit(url).path.rstrip("/")
                base_path = path.removesuffix("/video").removesuffix("/audio")
                if method == "OPTIONS":
                    await response(seq, headers={"Public": "OPTIONS, DESCRIBE, SETUP, PLAY, TEARDOWN, GET_PARAMETER"})
                elif method == "DESCRIBE":
                    if source is not None or base_path not in self.sources:
                        await response(seq, 404)
                        break
                    source = self.sources[base_path]
                    acquisition = asyncio.create_task(source.acquire())
                    try:
                        while not acquisition.done():
                            if reader.at_eof():
                                raise ConnectionError("RTSP consumer disconnected")
                            await asyncio.wait({acquisition}, timeout=.1)
                        queue = await acquisition
                    finally:
                        if not acquisition.done():
                            acquisition.cancel()
                            await asyncio.gather(acquisition, return_exceptions=True)
                    await response(seq, headers={"Content-Type": "application/sdp", "Content-Base": url.rstrip("/") + "/"},
                                   body=source.sdp(url.rstrip("/")))
                elif method == "SETUP" and source and base_path in self.sources and self.sources[base_path] is source:
                    transport = headers.get("transport", "")
                    if not transport.upper().startswith("RTP/AVP/TCP") or "interleaved=" not in transport:
                        await response(seq, 461)
                        break
                    channel = int(transport.split("interleaved=", 1)[1].split("-", 1)[0])
                    if not 0 <= channel < 255 or path.rsplit("/", 1)[-1] not in ("video", "audio"):
                        break
                    channels[path.rsplit("/", 1)[-1]] = channel
                    await response(seq, headers={"Transport": f"RTP/AVP/TCP;unicast;interleaved={channel}-{channel + 1}"})
                elif method == "PLAY" and source and channels and sender is None:
                    await response(seq, headers={"Range": "npt=0.000-"})
                    sender = asyncio.create_task(send_packets())
                elif method == "GET_PARAMETER":
                    await response(seq)
                elif method == "TEARDOWN":
                    await response(seq)
                    break
                else:
                    await response(seq, 400)
                    break
        except (OSError, ValueError, TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            pass
        finally:
            writer.close()  # Close even if a second cancellation interrupts session cleanup.
            if sender:
                sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)
            if source and queue is not None:
                await source.release(queue)
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()
            self.tasks.discard(task)
