"""Protocol boundary tests: corruption, loss, reordering and resource bounds."""
import hashlib
import struct
import zlib

import pytest

from custom_components.tuya_camera_bridge.media.crypto import (
    decrypt,
    encrypt,
    open_media,
    pack_signal,
    seal,
    unpack_signal,
)
from custom_components.tuya_camera_bridge.media.kcp import HEADER, KCP
from custom_components.tuya_camera_bridge.media.rtsp import MediaSource

KEY = b"0123456789abcdef"


def test_native_33_signal_layout_and_corruption():
    frame = pack_signal(KEY, 1, 32, {"header": {"type": "offer"}})
    assert struct.unpack_from("!IIII", frame)[:3] == (0x55AA, 1, 32)
    assert not frame[16:].startswith(b"3.3")
    assert unpack_signal(KEY, frame) == (32, {"header": {"type": "offer"}})
    control = pack_signal(KEY, 2, 7, {"dps": {"1": True}})
    assert control[16:31] == b"3.3" + bytes(12)
    # Device responses include a return code in front of the version prefix.
    body = bytes(4) + control[16:-8]
    response = struct.pack("!IIII", 0x55AA, 2, 7, len(body) + 8) + body
    response += struct.pack("!II", zlib.crc32(response), 0xAA55)
    assert unpack_signal(KEY, response)[1] == {"dps": {"1": True}}
    with pytest.raises(ValueError, match="checksum"):
        unpack_signal(KEY, frame[:-1] + b"\0")
    with pytest.raises(ValueError):
        decrypt(KEY, encrypt(KEY, b"hello")[:-1])


@pytest.mark.parametrize("long", [False, True])
def test_media_header_forms_and_padding(long):
    nal = b"\x65" + bytes(range(256))
    header = struct.pack("<I", 0x10003) + bytes(28)
    sub = struct.pack("<IQI", len(nal) + 12, 100, 0) if long else struct.pack("<II", 100, 0)
    sealed = seal(KEY, header + sub + nal)
    assert open_media(KEY, sealed) == (0x10003, nal)
    with pytest.raises(ValueError):
        open_media(KEY, sealed[:-1])


def test_kcp_wire_vector_and_retransmission():
    wire, messages = [], []
    sender = KCP(23, wire.append, messages.append)
    sender.send(b"hello")
    sender.update(100)
    assert wire[0] == HEADER.pack(23, 81, 0, 512, 100, 0, 0, 5) + b"hello"
    wire.clear()
    sender.update(500)  # Lost first datagram: retransmit it.
    assert len(wire) == 1
    ack = HEADER.pack(23, 82, 0, 512, 500, 0, 1, 0)
    sender.input(ack, 510)
    sender.update(1500)
    assert not sender.sending
    assert not messages


def test_kcp_loss_duplicates_reordering_and_wrap():
    left_wire, right_wire, received = [], [], []
    left = KCP(1, left_wire.append, lambda _: None)
    right = KCP(1, right_wire.append, received.append)
    payload = bytes(range(256)) * 100
    left.send(payload)
    left.update(0xFFFFFFF0)
    packets = list(left_wire)
    left_wire.clear()
    # Lose first packet, reverse all others, deliver duplicates.
    for packet in reversed(packets[1:]):
        right.input(packet, 0xFFFFFFF5)
        right.input(packet, 0xFFFFFFF5)
    assert not received
    for packet in right_wire:
        left.input(packet, 10)
    left.update(400)
    for packet in left_wire:
        right.input(packet, 401)
    assert received == [payload]
    assert not right.pending and not right.fragments
    assert hashlib.sha256(received[0]).digest() == hashlib.sha256(payload).digest()


def test_kcp_rejects_bad_lengths_and_limits_memory():
    channel = KCP(1, lambda _: None, lambda _: None)
    with pytest.raises(ValueError):
        channel.input(HEADER.pack(1, 81, 0, 512, 0, 0, 0, 100), 0)
    assert not channel.pending
    with pytest.raises(BufferError):
        channel.send(bytes(1376 * 256))
    # Far-future data cannot allocate outside the receive window.
    channel.input(HEADER.pack(1, 81, 0, 512, 0, 999999, 0, 1) + b"x", 0)
    assert not channel.pending


async def test_cancelled_source_start_releases_session_and_consumer():
    import asyncio
    from unittest.mock import AsyncMock
    session = AsyncMock()
    async def factory(packet):
        await asyncio.sleep(60)
        return session
    source = MediaSource(factory, lambda: None)
    task = asyncio.create_task(source.acquire())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not source.consumers
    assert source.session is None


def test_camera_address_follows_only_exact_private_mac(monkeypatch):
    from custom_components.tuya_camera_bridge.media.lan import resolve_host
    monkeypatch.setattr("pathlib.Path.read_text", lambda _: "192.168.0.22 0 0 aa:bb:cc:dd:ee:ff 0 eth0\n203.0.113.5 0 0 aa:bb:cc:dd:ee:01 0 eth0")
    assert resolve_host({"mac": "AA-BB-CC-DD-EE-FF", "host": "192.168.0.10"}) == "192.168.0.22"
    assert resolve_host({"mac": "00:11:22:33:44:55", "host": "192.168.0.10"}) == "192.168.0.10"
