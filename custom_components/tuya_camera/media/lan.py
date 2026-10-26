"""Async protocol-3.3 signaling and camera-only AES/KCP reception."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import secrets
import socket
import string
import struct
import time
import uuid
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from aioice import stun

from .crypto import authenticate, open_media, pack_signal, seal, unpack_signal
from .kcp import KCP

SIGNAL_PORT = 6668

STARTUP = (
    "7856341200000000000000000a0000000400000000000100",
    "785634120200000000000000020000000400000000000000",
    "78563412040001000000000009000000080000000000000002000000",
    "78563412030001000000000006000000080000000000000000000000",
    "78563412050001000000000006000400080000000000000004000000",
)


def random_ascii(length: int) -> str:
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))


def attribute(sdp: str, key: str) -> str:
    return next((line[len(key) + 3:] for line in sdp.splitlines() if line.startswith(f"a={key}:")), "")


def resolve_host(local: dict) -> str:
    """Follow an exact MAC in the local neighbor table after a DHCP change."""
    mac = local.get("mac", "").lower().replace("-", ":")
    if mac:
        with suppress(OSError):
            for line in Path("/proc/net/arp").read_text().splitlines():
                fields = line.split()
                if len(fields) >= 4 and fields[3].lower().replace("-", ":") == mac:
                    with suppress(ValueError):
                        if ipaddress.IPv4Address(fields[0]).is_private:
                            return fields[0]
    return local["host"]


class LanSession(asyncio.DatagramProtocol):
    """One owner for signaling, DP commands and all KCP conversations."""

    def __init__(self, camera: dict, uid: str, packet: Callable[[str, bytes, int, bool], None]):
        self.camera, self.uid, self.packet = camera, uid, packet
        self.local = camera["local"]
        self.host = self.local["host"]
        self.key = self.local["local_key"].encode("latin1")
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.transport: asyncio.DatagramTransport | None = None
        self.peer: tuple[str, int] | None = None
        self.ufrag, self.password = random_ascii(4), random_ascii(24)
        self.aes_key = b""
        self.tasks: set[asyncio.Task] = set()
        self.channels: dict[int, KCP] = {}
        self.peers: dict[int, tuple[str, int]] = {}
        self.signals: asyncio.Queue = asyncio.Queue(64)
        self.reports: asyncio.Queue = asyncio.Queue(64)
        self.values: dict = {}
        self.seq = 0
        self.phase = "lan_connect"
        self.failed = asyncio.Event()
        self.ice = asyncio.Event()
        self.checks: set[bytes] = set()
        self.stats = {"Datagrams": 0, "Accepted": 0, "BadMAC": 0, "Video": 0, "Audio": 0, "Malformed": 0}
        self.video_time = self.audio_time = 0
        self.picture_ended = True
        self.epoch = time.monotonic()
        self.last_video = self.epoch

    def task(self, coro) -> None:
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        task.add_done_callback(self._done)

    def _done(self, task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception() is not None:
            self.failed.set()

    async def connect(self) -> None:
        if not ipaddress.IPv4Address(self.host).is_private or len(self.key) != 16:
            raise ValueError("Invalid LAN endpoint")
        self.reader, self.writer = await asyncio.wait_for(asyncio.open_connection(self.host, SIGNAL_PORT), 1)

    async def start(self) -> None:
        self.task(self._read_signals())
        self.task(self._heartbeat())
        await self.send(10, {"gwId": self.camera["camera_id"], "devId": self.camera["camera_id"]})
        # Drain the initial status before offering, without issuing refresh queries.
        with suppress(TimeoutError):
            await asyncio.wait_for(self.reports.get(), 1)
        self.phase = "offer"
        loop = asyncio.get_running_loop()
        self.transport, _ = await loop.create_datagram_endpoint(lambda: self, local_addr=("0.0.0.0", 0))
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect((self.host, 6668))
            address = probe.getsockname()[0]
        port = self.transport.get_extra_info("sockname")[1]
        device_id = self.camera["camera_id"]
        session = f"{device_id}{int(time.time())}{random_ascii(8)}"
        header = {"from": self.uid, "to": device_id, "moto_id": "", "path": "lan", "is_pre": 0,
                  "p2p_skill": 1635, "security_level": 3, "sessionid": session,
                  "trace_id": f"{str(uuid.uuid4()).upper()}_{device_id}_{int(time.time()) * 1000}"}
        offered_key = random_ascii(16).encode()
        sdp = "\r\n".join(("v=0", f"o=- {int(time.time())} 1 IN IP4 127.0.0.1", "s=-", "t=0 0",
                             "a=group:BUNDLE imm0", f"a=msid-semantic: WMS {session}",
                             "m=application 9 imm 6001", "c=IN IP4 0.0.0.0", "a=rtcp:9 IN IP4 0.0.0.0",
                             f"a=ice-ufrag:{self.ufrag}", f"a=ice-pwd:{self.password}", "a=ice-options:trickle",
                             f"a=aes-key:{offered_key.hex()}", "a=mid:imm0", "a=rtpmap:6001 AES/KCP 330",
                             f"a=ssrc:0 cname:{self.uid}", ""))
        await self.send(32, {"header": {**header, "type": "offer"}, "msg": {
            "sdp": sdp, "preconnect": True, "token": [{"urls": "stun:192.0.2.1:3478"}]}})
        candidate = f"a=candidate:1 1 UDP 2130706431 {address} {port} typ host\r\n"
        await self.send(32, {"header": {**header, "type": "candidate"}, "msg": {"candidate": candidate, "token": []}})
        self.phase = "answer"
        remote_user = remote_password = ""
        async with asyncio.timeout(20):
            while not (self.peer and len(self.aes_key) == 16 and remote_user and remote_password):
                frame = await self.signals.get()
                h, msg = frame.get("header", {}), frame.get("msg", {})
                if (h.get("sessionid"), h.get("path"), h.get("from"), h.get("to")) != (
                    session, "lan", device_id, self.uid
                ):
                    continue
                if h.get("type") == "answer":
                    remote_user, remote_password = attribute(msg.get("sdp", ""), "ice-ufrag"), attribute(msg.get("sdp", ""), "ice-pwd")
                    self.aes_key = bytes.fromhex(attribute(msg.get("sdp", ""), "aes-key"))
                elif h.get("type") == "candidate":
                    parts = msg.get("candidate", "").strip().removeprefix("a=").split()
                    if len(parts) >= 8 and parts[2].upper() == "UDP" and parts[4] == self.host and 0 < int(parts[5]) < 65536:
                        self.peer = self.host, int(parts[5])
                elif h.get("type") == "disconnect":
                    raise ConnectionError("Camera refused LAN session")
        self.phase = "ice"
        async with asyncio.timeout(20):
            while not self.ice.is_set():
                request = stun.Message(stun.Method.BINDING, stun.Class.REQUEST, attributes={
                    "USERNAME": f"{remote_user}:{self.ufrag}", "PRIORITY": 2130706431,
                    "ICE-CONTROLLED": secrets.randbits(64)})
                request.add_message_integrity(remote_password.encode())
                self.checks.add(request.transaction_id)
                self.transport.sendto(bytes(request), self.peer)
                with suppress(TimeoutError):
                    await asyncio.wait_for(self.ice.wait(), .2)
        self.phase = "media_login"
        channel = self._channel(0)
        self.task(self._tick())
        # Firmware login token, not a password-storage hash; the camera requires MD5.
        token = hashlib.md5((self.local["media_password"] + "||" + self.local["local_key"]).encode()).hexdigest()
        login = struct.pack("<II", 0x12345678, 1) + b"admin".ljust(32, b"\0") + token.encode().ljust(32, b"\0") + bytes(32)
        for message in [login, *(bytes.fromhex(raw) for raw in STARTUP)]:
            channel.send(seal(self.aes_key, message))
            await asyncio.sleep(.12)
        self.phase = "media"

    async def send(self, cmd: int, body: dict | None = None) -> None:
        if self.writer is None:
            raise ConnectionError("LAN signaling inactive")
        self.seq = (self.seq + 1) & 0xFFFFFFFF
        self.writer.write(pack_signal(self.key, self.seq, cmd, body))
        await self.writer.drain()

    async def _read_signals(self) -> None:
        while True:
            head = await self.reader.readexactly(16)
            length = struct.unpack_from("!I", head, 12)[0]
            if not 8 <= length <= 1024 * 1024:
                raise ValueError("Invalid LAN frame size")
            cmd, body = unpack_signal(self.key, head + await self.reader.readexactly(length))
            if cmd == 32:
                if not self.signals.full():
                    self.signals.put_nowait(body)
            else:
                values = body.get("dps") or body.get("data", {}).get("dps") or {}
                allowed = {str(dp["id"]) for dp in self.local.get("schema", []) if dp.get("property", {}).get("type") in ("bool", "enum", "value")}
                safe = {str(k): v for k, v in values.items() if str(k) in allowed and (
                    type(v) in (bool, int, float) or (isinstance(v, str) and len(v) <= 256))}
                if safe:
                    self.values.update(safe)
                    if self.reports.full():
                        self.reports.get_nowait()
                    self.reports.put_nowait(safe)

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(7)
            await self.send(9)

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if addr[0] != self.host:
            return
        self.stats["Datagrams"] += 1
        try:
            if len(data) >= 20 and data[4:8] == b"\x21\x12\xa4\x42":
                msg = stun.parse_message(data)
                if msg.message_class == stun.Class.REQUEST:
                    response = stun.Message(stun.Method.BINDING, stun.Class.RESPONSE,
                                            transaction_id=msg.transaction_id, attributes={"XOR-MAPPED-ADDRESS": addr})
                    response.add_message_integrity(self.password.encode())
                    self.transport.sendto(bytes(response), addr)
                elif msg.message_class == stun.Class.RESPONSE and addr == self.peer and msg.transaction_id in self.checks:
                    # This firmware omits integrity on success; correlate the exact check and peer.
                    self.ice.set()
                return
            if not self.aes_key or len(data) < 44:
                return
            body = data[:-20]
            if not hmac.compare_digest(authenticate(self.aes_key, body), data[-20:]):
                self.stats["BadMAC"] += 1
                return
            self.stats["Accepted"] += 1
            while body:
                if len(body) < 24:
                    raise ValueError("Truncated KCP batch")
                conv = struct.unpack_from("<I", body)[0]
                size = 24 + struct.unpack_from("<I", body, 20)[0]
                if size > len(body):
                    raise ValueError("Invalid KCP batch length")
                self.peers[conv] = addr
                self._channel(conv).input(body[:size], int(time.monotonic() * 1000) & 0xFFFFFFFF)
                body = body[size:]
        except (ValueError, BufferError, struct.error):
            self.stats["Malformed"] += 1

    def _channel(self, conv: int) -> KCP:
        if conv not in self.channels:
            if len(self.channels) >= 8:
                raise BufferError("Too many camera conversations")
            def output(data):
                self.transport.sendto(data + authenticate(self.aes_key, data), self.peers.get(conv, self.peer))
            self.channels[conv] = KCP(conv, output, self._media)
        return self.channels[conv]

    async def _tick(self) -> None:
        while True:
            for channel in self.channels.values():
                channel.update(int(time.monotonic() * 1000) & 0xFFFFFFFF)
            if time.monotonic() - self.last_video > 30:
                raise TimeoutError("Camera media stalled")
            await asyncio.sleep(.01)

    def _media(self, data: bytes) -> None:
        cmd, payload = open_media(self.aes_key, data)
        if cmd == 0x10003 and len(payload) >= 2:
            end = bool(payload[1] & 0x40) if payload[0] & 31 in (28, 29) else payload[0] & 31 in (1, 5)
            if self.picture_ended:
                self.video_time = int((time.monotonic() - self.epoch) * 90000) & 0xFFFFFFFF
            self.picture_ended = end
            self.last_video = time.monotonic()
            self.stats["Video"] += 1
            self.packet("video", payload, self.video_time, end)
        elif cmd == 0x10005 and payload and len(payload) % 2 == 0:
            self.stats["Audio"] += 1
            # L16 RTP is network byte order; the verified camera supplies little endian PCM.
            pcm = bytearray(payload)
            pcm[0::2], pcm[1::2] = payload[1::2], payload[0::2]
            self.audio_time = (self.audio_time + len(payload) // 2) & 0xFFFFFFFF
            self.packet("audio", bytes(pcm), self.audio_time, False)

    async def set_dp(self, index: str, value) -> None:
        allowed = {str(dp["id"]) for dp in self.local.get("schema", []) if dp.get("property", {}).get("type") in ("bool", "enum", "value")}
        if index not in allowed or not (type(value) in (bool, int, float) or (isinstance(value, str) and len(value) <= 256)):
            raise ValueError("Invalid local command")
        while not self.reports.empty():
            self.reports.get_nowait()
        await self.send(7, {"devId": self.camera["camera_id"], "uid": self.uid, "t": str(int(time.time())), "dps": {index: value}})

    async def close(self) -> None:
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.transport:
            self.transport.close()
            self.transport = None
        if self.writer:
            self.writer.close()
            with suppress(OSError):
                await self.writer.wait_closed()
            self.writer = None
        self.failed.set()
