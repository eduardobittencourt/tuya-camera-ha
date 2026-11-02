"""Private RTSP/TCP adapter for Home Assistant's FFmpeg consumers."""
from __future__ import annotations

import asyncio
import secrets
import struct
import time
from collections.abc import Callable
from contextlib import suppress
from urllib.parse import urlsplit

REQUEST_TIMEOUT = 65
WRITE_TIMEOUT = 5


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
            if self.session is not None and not self.consumers:
                # Retry cleanup interrupted after the final reader released.
                # Keep the old session owned until close succeeds.
                await self._stop()
            if self.session is not None and self.session.failed.is_set():
                # Existing readers must release before another session can start.
                raise ConnectionError("Camera session is recovering")
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
        try:
            if len(self.tasks) <= 32:
                await RtspConnection(self.sources, reader, writer).run()
        finally:
            writer.close()
            with suppress(OSError, TimeoutError):
                await asyncio.wait_for(writer.wait_closed(), WRITE_TIMEOUT)
            self.tasks.discard(task)


class RtspConnection:
    """Own one reader's negotiation, RTP sender and camera lease."""

    def __init__(self, sources, reader, writer):
        self.sources, self.reader, self.writer = sources, reader, writer
        self.source = self.queue = self.sender = None
        self.channels = {}
        self.session = secrets.token_hex(12)
        self.lock = asyncio.Lock()

    async def response(self, cseq, status=200, headers=None, body=""):
        values = {"CSeq": cseq, "Session": self.session, **(headers or {})}
        if body:
            values["Content-Length"] = str(len(body.encode()))
        data = f"RTSP/1.0 {status} {'OK' if status == 200 else 'Unavailable'}\r\n"
        data += "".join(f"{k}: {v}\r\n" for k, v in values.items()) + "\r\n" + body
        async with self.lock:
            self.writer.write(data.encode())
            await asyncio.wait_for(self.writer.drain(), WRITE_TIMEOUT)

    async def send_packets(self):
        try:
            while item := await self.queue.get():
                kind, packet = item
                if kind in self.channels:
                    async with self.lock:
                        self.writer.write(b"$" + struct.pack("!BH", self.channels[kind], len(packet)) + packet)
                        await asyncio.wait_for(self.writer.drain(), WRITE_TIMEOUT)
        finally:
            self.writer.close()

    async def read_request(self):
        # Bound the whole request, including partial headers, bodies and RTCP.
        async with asyncio.timeout(REQUEST_TIMEOUT):
            first = await self.reader.readexactly(1)
            if first == b"$":
                frame = await self.reader.readexactly(3)
                await self.reader.readexactly(struct.unpack_from("!H", frame, 1)[0])
                return None
            request = first + await self.reader.readuntil(b"\r\n\r\n")
            lines = request.decode().split("\r\n")
            method, url, _ = lines[0].split(" ", 2)
            headers = {k.lower(): v.strip() for line in lines[1:] if ":" in line for k, v in [line.split(":", 1)]}
            length = int(headers.get("content-length", 0))
            if not 0 <= length <= 32768:
                raise ValueError("Invalid RTSP content length")
            if length:
                await self.reader.readexactly(length)
            return method, url, headers

    async def describe(self, seq, url, base_path):
        if self.source is not None or base_path not in self.sources:
            await self.response(seq, 404)
            return False
        self.source = self.sources[base_path]
        acquisition = asyncio.create_task(self.source.acquire())
        try:
            while not acquisition.done():
                if self.reader.at_eof():
                    raise ConnectionError("RTSP consumer disconnected")
                await asyncio.wait({acquisition}, timeout=.1)
            self.queue = await acquisition
        finally:
            if not acquisition.done():
                acquisition.cancel()
            await asyncio.gather(acquisition, return_exceptions=True)
            # Cancellation can arrive just after acquire returns its lease.
            if not acquisition.cancelled() and acquisition.exception() is None:
                self.queue = acquisition.result()
        await self.response(seq, headers={"Content-Type": "application/sdp", "Content-Base": url.rstrip("/") + "/"},
                            body=self.source.sdp(url.rstrip("/")))
        return True

    async def setup(self, seq, path, headers):
        transport = headers.get("transport", "")
        if not transport.upper().startswith("RTP/AVP/TCP") or "interleaved=" not in transport:
            await self.response(seq, 461)
            return False
        channel = int(transport.split("interleaved=", 1)[1].split("-", 1)[0])
        kind = path.rsplit("/", 1)[-1]
        if not 0 <= channel < 255 or kind not in ("video", "audio"):
            return False
        self.channels[kind] = channel
        await self.response(seq, headers={"Transport": f"RTP/AVP/TCP;unicast;interleaved={channel}-{channel + 1}"})
        return True

    async def dispatch(self, method, url, headers):
        seq = headers.get("cseq", "0")
        path = urlsplit(url).path.rstrip("/")
        base_path = path.removesuffix("/video").removesuffix("/audio")
        if method == "OPTIONS":
            await self.response(seq, headers={"Public": "OPTIONS, DESCRIBE, SETUP, PLAY, TEARDOWN, GET_PARAMETER"})
        elif method == "DESCRIBE":
            return await self.describe(seq, url, base_path)
        elif method == "SETUP" and self.source and self.sources.get(base_path) is self.source:
            return await self.setup(seq, path, headers)
        elif method == "PLAY" and self.source and self.channels and self.sender is None:
            await self.response(seq, headers={"Range": "npt=0.000-"})
            self.sender = asyncio.create_task(self.send_packets())
        elif method == "GET_PARAMETER":
            await self.response(seq)
        elif method == "TEARDOWN":
            await self.response(seq)
            return False
        else:
            await self.response(seq, 400)
            return False
        return True

    async def run(self):
        try:
            while True:
                request = await self.read_request()
                if request is not None and not await self.dispatch(*request):
                    break
        except (OSError, ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            # Malformed, disconnected or stalled consumers end their own lease.
            return
        finally:
            self.writer.close()
            if self.sender:
                self.sender.cancel()
                await asyncio.gather(self.sender, return_exceptions=True)
            if self.source and self.queue is not None:
                await self.source.release(self.queue)
