"""Actual AES/KCP -> Python RTSP -> FFmpeg media, with a synthetic camera."""
import asyncio
import hmac
import io
import os
import re
import struct
import time

import av
import pytest
from aioice import stun

from custom_components.tuya_camera_bridge.media import lan
from custom_components.tuya_camera_bridge.media.crypto import authenticate, pack_signal, seal, unpack_signal
from custom_components.tuya_camera_bridge.media.kcp import KCP
from custom_components.tuya_camera_bridge.media.rtsp import MediaSource, RtspServer
from custom_components.tuya_camera_bridge.transcoder import FfmpegRelay

pytestmark = pytest.mark.media
KEY = b"0123456789abcdef"


class SyntheticCamera(asyncio.DatagramProtocol):
    def __init__(self, nals):
        self.nals = nals
        self.transport = self.writer = None
        self.peer = None
        self.key = b""
        self.channels = {}
        self.task = None
        self.values = {"1": True}

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, address):
        self.peer = address
        if data[4:8] == b"\x21\x12\xa4\x42":
            request = stun.parse_message(data)
            if request.message_class == stun.Class.REQUEST:
                response = stun.Message(stun.Method.BINDING, stun.Class.RESPONSE, request.transaction_id)
                self.transport.sendto(bytes(response), address)
            return
        assert hmac.compare_digest(authenticate(self.key, data[:-20]), data[-20:])
        conv = struct.unpack_from("<I", data)[0]
        self.channel(conv).input(data[:-20], int(time.monotonic() * 1000) & 0xFFFFFFFF)

    def channel(self, conv):
        if conv not in self.channels:
            def output(data):
                self.transport.sendto(data + authenticate(self.key, data), self.peer)
            self.channels[conv] = KCP(conv, output, lambda _: None)
        return self.channels[conv]

    async def signaling(self, reader, writer):
        self.writer = writer
        self.channels = {}
        self.peer = None
        try:
            while True:
                head = await reader.readexactly(16)
                cmd, body = unpack_signal(KEY, head + await reader.readexactly(struct.unpack_from("!I", head, 12)[0]))
                if cmd == 10:
                    writer.write(pack_signal(KEY, 1, 8, {"dps": self.values}))
                elif cmd == 7:
                    assert body["uid"] == "account-user"
                    self.values.update(body["dps"])
                    writer.write(pack_signal(KEY, 2, 8, {"dps": self.values}))
                elif cmd == 32:
                    header, msg = body["header"], body["msg"]
                    reply = {**header, "from": header["to"], "to": header["from"]}
                    if header["type"] == "offer":
                        self.key = bytes.fromhex(lan.attribute(msg["sdp"], "aes-key"))
                        sdp = f"a=ice-ufrag:abcd\r\na=ice-pwd:abcdefghijklmnopqrstuvwx\r\na=aes-key:{self.key.hex()}\r\n"
                        writer.write(pack_signal(KEY, 2, 32, {"header": {**reply, "type": "answer"}, "msg": {"sdp": sdp}}))
                        port = self.transport.get_extra_info("sockname")[1]
                        writer.write(pack_signal(KEY, 3, 32, {"header": {**reply, "type": "candidate"}, "msg": {
                            "candidate": f"a=candidate:1 1 UDP 2130706431 127.0.0.1 {port} typ host"}}))
                    elif header["type"] == "candidate":
                        self.task = asyncio.create_task(self.media())
                await writer.drain()
        except (OSError, asyncio.IncompleteReadError):
            pass
        finally:
            if self.task:
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
            writer.close()

    async def media(self):
        # Wait for the client's first authenticated application datagram.
        while self.peer is None or not self.channels:
            await asyncio.sleep(.01)
        clock = index = 0
        while True:
            now = time.monotonic()
            if now >= clock:
                nal = self.nals[index % len(self.nals)]
                for cmd, payload in [(0x10003, nal), (0x10005, bytes(320))]:
                    message = struct.pack("<I", cmd) + bytes(28) + struct.pack("<II", index * 20, 0) + payload
                    self.channel(1).send(seal(self.key, message))
                index += 1
                clock = now + .02
            for channel in list(self.channels.values()):
                channel.update(int(now * 1000) & 0xFFFFFFFF)
            await asyncio.sleep(.01)


def inspect(url):
    seen = set()
    with av.open(url, timeout=(15, 10)) as container:
        for frame in container.decode():
            seen.add("video" if isinstance(frame, av.VideoFrame) else "audio")
            if len(seen) == 2:
                return seen
    return seen


async def test_synthetic_lan_camera_through_python_rtsp_and_ffmpeg(tmp_path, monkeypatch, socket_enabled):
    ffmpeg = os.environ.get("TEST_FFMPEG_BINARY")
    if not ffmpeg:
        pytest.skip("Set TEST_FFMPEG_BINARY for actual media validation")
    process = await asyncio.create_subprocess_exec(ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
        "-i", "testsrc2=size=320x240:rate=10", "-t", "2", "-c:v", "libx264", "-preset", "ultrafast",
        "-tune", "zerolatency", "-g", "10", "-f", "h264", "pipe:1", stdout=asyncio.subprocess.PIPE)
    raw, _ = await process.communicate()
    assert process.returncode == 0
    nals = [part for part in re.split(b"\x00\x00\x00?\x01", raw) if part]
    camera = SyntheticCamera(nals)
    transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(lambda: camera, local_addr=("127.0.0.1", 0))
    signaling = await asyncio.start_server(camera.signaling, "127.0.0.1", 0)
    monkeypatch.setattr(lan, "SIGNAL_PORT", signaling.sockets[0].getsockname()[1])
    config = {"camera_id": "synthetic", "local": {"host": "127.0.0.1", "version": "3.3", "local_key": KEY.decode(),
               "media_password": "synthetic-password", "schema": [{"id": 1, "property": {"type": "bool"}}]}}
    sessions = []
    async def factory(packet):
        session = lan.LanSession(config, "account-user", packet)
        sessions.append(session)
        try:
            await session.connect()
            await session.start()
            return session
        except BaseException:
            await session.close()
            raise
    source = MediaSource(factory, lambda: None)
    server = RtspServer({"/camera": source})
    await server.start()
    relay = FfmpegRelay(ffmpeg, lambda: f"rtsp://127.0.0.1:{server.port}/camera", lambda: False)
    await relay.start()
    try:
        jpeg = await relay.snapshot()
        assert jpeg and jpeg.startswith(b"\xff\xd8")
        with av.open(io.BytesIO(jpeg)) as picture:
            frame = next(picture.decode(video=0))
            assert (frame.width, frame.height) == (320, 240)
        assert await asyncio.to_thread(inspect, relay.url) == {"video", "audio"}
        # Exercise the DP socket while the media consumer keeps the camera active.
        ready = asyncio.Event()
        control = asyncio.create_task(relay.control_session(ready.set))
        try:
            await asyncio.wait_for(ready.wait(), 15)
            session = source.session
            assert session is not None
            await session.set_dp("1", False)
            async with asyncio.timeout(3):
                while session.values.get("1") is not False:
                    await asyncio.sleep(.01)
            assert session.stats["Video"] > 5 and session.stats["Audio"] > 5
        finally:
            control.cancel()
            await asyncio.gather(control, return_exceptions=True)
    finally:
        await relay.stop()
        await server.stop()
        signaling.close()
        await signaling.wait_closed()
        transport.close()
    assert all(not s.tasks and s.writer is None and s.transport is None for s in sessions)
    assert not server.tasks and source.session is None
