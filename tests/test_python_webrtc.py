"""Synthetic WebRTC camera checks the pinned aiortc adapter without Tuya."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from aiortc import AudioStreamTrack, RTCConfiguration, RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.rtp import RtpPacket
from aiortc.sdp import candidate_from_sdp

from custom_components.tuya_camera.media.cloud import CloudSession, ice_servers


@pytest.fixture(autouse=True)
def real_loopback_candidates(monkeypatch):
    monkeypatch.setattr("aioice.ice.get_host_addresses", lambda **_: ["127.0.0.1"])


class CameraBroker:
    def __init__(self, hevc=False):
        self.messages = asyncio.Queue()
        self.failed = asyncio.Event()
        self.peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        self.hevc = hevc
        self.started = asyncio.Event()
        self.commands = []
        if hevc:
            self.peer.on("datachannel", self.channel)
        else:
            self.peer.addTrack(AudioStreamTrack())
            self.peer.addTrack(VideoStreamTrack())

    def channel(self, channel):
        @channel.on("message")
        def receive(raw):
            value = json.loads(raw)
            self.commands.append(value["type"])
            if value["type"] == "codec":
                channel.send(json.dumps({"type": "codec", "msg": ""}))
            elif value["type"] == "start":
                channel.send(json.dumps({"type": "recv", "msg": json.dumps({"video": {"ssrc": 31}, "audio": {"ssrc": 32}})}))
            elif value["type"] == "complete":
                for ssrc, payload in ((31, b"\x26\x01\x80"), (32, b"\x01\x02\x03\x04")):
                    packet = RtpPacket(payload_type=96, marker=1, sequence_number=1, timestamp=1234, ssrc=ssrc)
                    packet.payload = payload
                    channel.send(packet.serialize())
                self.started.set()

    async def publish(self, topic, raw):
        value = json.loads(raw)
        header, msg = value["data"]["header"], value["data"]["msg"]
        if header["type"] == "offer":
            await self.peer.setRemoteDescription(RTCSessionDescription(sdp=msg["sdp"], type="offer"))
            await self.peer.setLocalDescription(await self.peer.createAnswer())
            self.messages.put_nowait({"data": {"header": {**header, "from": "camera"}, "msg": {"sdp": self.peer.localDescription.sdp}}})
            # Correct response type, same session; deliberately send no trickle answer candidates.
            item = self.messages.get_nowait()
            item["data"]["header"]["type"] = "answer"
            self.messages.put_nowait(item)
        elif header["type"] == "candidate":
            candidate = candidate_from_sdp(msg["candidate"].removeprefix("a=candidate:"))
            candidate.sdpMLineIndex = 0
            await self.peer.addIceCandidate(candidate)

    async def close(self):
        await self.peer.close()


def account(broker, hevc=False):
    result = AsyncMock()
    result.data = {"uid": "account-user"}
    result.call.return_value = {"motoId": "synthetic", "p2pConfig": {"ices": []}, "skill": {
        "videos": [{"codecType": 4 if hevc else 2, "streamType": 2, "width": 640, "height": 360}],
        "audios": [{"codecType": 101 if hevc else 105, "sampleRate": 8000, "channels": 1}]}}
    result.broker.return_value = broker
    return result


async def test_h264_webrtc_forwards_original_rtp_and_closes_every_task(socket_enabled):
    broker = CameraBroker()
    received = []
    session = CloudSession(account(broker), {"camera_id": "camera"}, lambda *args: received.append(args))
    try:
        await session.start()
        await asyncio.wait_for(session.first_video.wait(), 10)
        async with asyncio.timeout(10):
            while not any(packet[0] == "audio" for packet in received):
                await asyncio.sleep(.01)
        assert any(packet[0] == "video" and packet[1] for packet in received)
        assert session.audio_codec == "PCMU/8000/1"
    finally:
        await session.close()
    assert not session.tasks and session.peer is None and session.broker is None


async def test_hevc_datachannel_negotiates_and_preserves_pcm_byte_order(socket_enabled):
    broker = CameraBroker(hevc=True)
    received = []
    session = CloudSession(account(broker, hevc=True), {"camera_id": "camera"}, lambda *args: received.append(args))
    try:
        await session.start()
        await asyncio.wait_for(session.first_video.wait(), 10)
        async with asyncio.timeout(5):
            while len(received) < 2:
                await asyncio.sleep(.01)
        assert broker.commands == ["codec", "start", "complete"]
        assert session.hevc and session.audio_codec == "L16/8000/1"
        assert received[0] == ("video", b"\x26\x01\x80", 1234, 1)
        assert received[1] == ("audio", b"\x02\x01\x04\x03", 1234, 1)
    finally:
        await session.close()
    assert not session.tasks


def test_tuya_ice_normalization_preserves_token_and_turn_credentials():
    config = {"p2pConfig": {"ices": [
        {"urls": "stun:192.0.2.1:3478?transport=udp"},
        {"urls": ["turn:192.0.2.2:3478?transport=tcp"], "username": "test", "credential": "synthetic"},
        {"urls": "unsupported:192.0.2.3"},
    ]}}
    servers = ice_servers(config)
    assert servers[0].urls == ["stun:192.0.2.1:3478"]
    assert servers[1].urls == ["turn:192.0.2.2:3478?transport=tcp"]
    assert servers[1].credential == "synthetic"
    assert len(servers) == 2
    assert config["p2pConfig"]["ices"][0]["urls"].endswith("?transport=udp")
