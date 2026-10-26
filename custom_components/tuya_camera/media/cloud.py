"""Tuya MQTT signaling and WebRTC, owned by the integration's asyncio loop."""
from __future__ import annotations

import asyncio
import json
import secrets
import struct
import time
import zlib
from contextlib import suppress

import paho.mqtt.client as mqtt
from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCRtpReceiver, RTCSessionDescription
from aiortc.rtcicetransport import parse_stun_turn_uri
from aiortc.rtp import RtpPacket, unwrap_rtx
from aiortc.sdp import candidate_from_sdp

from ..vendor.tuya_mobile import TuyaMobileApp, TuyaPasswordClient
from ..vendor.tuya_mobile.mqtt_auth import mqtt_password, mqtt_username


class MediaError(RuntimeError):
    """Sanitized media error safe to expose to Home Assistant."""


class MediaAuthenticationError(MediaError):
    """Account session needs UI reauthentication."""


def ice_servers(config: dict) -> list[RTCIceServer]:
    """Normalize Tuya's nonstandard STUN transport suffix for aiortc.

    Keep the original token untouched when sending the offer to the camera.
    Unknown endpoint schemes are not ICE servers and are never contacted.
    """
    servers = []
    for server in config.get("p2pConfig", {}).get("ices", []):
        urls = server.get("urls", [])
        urls = [urls] if isinstance(urls, str) else urls
        usable = []
        for uri in urls:
            if not isinstance(uri, str):
                continue
            normalized = uri.split("?", 1)[0] if uri.startswith(("stun:", "stuns:")) else uri
            try:
                parse_stun_turn_uri(normalized)
            except ValueError:
                continue
            usable.append(normalized)
        if usable:
            servers.append(RTCIceServer(urls=usable, username=server.get("username"), credential=server.get("credential")))
    return servers


class CloudAccount:
    """Reuse the Python mobile API client; never duplicate API signing in Go."""

    def __init__(self, session, data, auth_required):
        self.data, self.auth_required = data, auth_required
        self.client = TuyaPasswordClient.for_application(
            TuyaMobileApp(data["application"]), session, username=data["username"],
            endpoint=f"https://{data['api_host']}/api.json")
        self.client.sid, self.client.ecode, self.client.uid = data["sid"], data["ecode"], data["uid"]
        self.client.device_id = data["phone_device_id"]

    async def call(self, action, payload):
        try:
            result = await self.client._call(action, payload)
            return result.get("result", result)
        except RuntimeError as err:
            # Vendor errors may contain private response material; never propagate them.
            if any(code in str(err).upper() for code in ("SESSION_INVALID", "SID_INVALID", "USER_SESSION_INVALID", "LOGIN_SESSION_EXPIRED")):
                self.auth_required()
                raise MediaAuthenticationError("Sign in to Tuya again") from None
            raise MediaError("Tuya media request failed") from None

    async def broker(self):
        info = await self.call("smartlife.m.user.info.get", {})
        host = info.get("domain", {}).get("mobileMqttsUrl", "")
        if not host or "/" in host or ":" in host:
            raise MediaError("Invalid Tuya signaling endpoint")
        broker = Broker(self, host)
        try:
            await broker.start()
        except BaseException:
            await broker.close()
            raise
        return broker


class Broker:
    """Paho's network thread hands messages to bounded asyncio queues."""

    def __init__(self, account, host):
        self.account, self.host = account, host
        self.loop = asyncio.get_running_loop()
        self.ready = self.loop.create_future()
        self.messages: asyncio.Queue = asyncio.Queue(128)
        self.failed = asyncio.Event()
        data, signer = account.data, account.client.signer
        # A fresh installation suffix avoids disconnecting another account camera or the app.
        identifier = f"{account.client.profile.package}_mb_{secrets.token_hex(16)}_DEFAULT"
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=identifier, reconnect_on_failure=False)
        self.client.username_pw_set(mqtt_username(signer.app_id, signer.channel_key(), data["sid"], data["ecode"], data["partner_identity"]),
                                    mqtt_password(signer.global_material(), data["ecode"]))
        self.client.on_connect = self._connected
        self.client.on_subscribe = self._subscribed
        self.client.on_message = self._message
        self.client.on_disconnect = lambda *_: self.loop.call_soon_threadsafe(self.failed.set)
        self.started = False

    def _connected(self, client, userdata, flags, code, properties):
        if code.is_failure:
            self.loop.call_soon_threadsafe(self._reject)
        else:
            client.subscribe(f"/av/u/{self.account.data['uid']}", qos=1)

    def _reject(self):
        if not self.ready.done():
            self.ready.set_exception(MediaError("Tuya signaling rejected the connection"))

    def _subscribed(self, client, userdata, mid, reasons, properties):
        def complete():
            if any(reason.is_failure for reason in reasons):
                self._reject()
            elif not self.ready.done():
                self.ready.set_result(None)
        self.loop.call_soon_threadsafe(complete)

    def _message(self, client, userdata, message):
        if len(message.payload) > 1024 * 1024:
            return
        try:
            value = json.loads(message.payload)
        except (ValueError, UnicodeError):
            return
        def deliver():
            if isinstance(value, dict) and not self.messages.full():
                self.messages.put_nowait(value)
        self.loop.call_soon_threadsafe(deliver)

    async def start(self):
        await asyncio.to_thread(self.client.tls_set)
        await asyncio.to_thread(self.client.connect, self.host, 8883, 60)
        self.client.loop_start()
        self.started = True
        await asyncio.wait_for(self.ready, 12)

    async def publish(self, topic, payload):
        info = self.client.publish(topic, payload, qos=1)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise MediaError("Tuya signaling publish failed")
        await asyncio.to_thread(info.wait_for_publish, 5)
        if not info.is_published():
            raise TimeoutError("Tuya signaling publish timed out")

    async def wake(self, camera):
        await self.publish(f"m/w/{camera['camera_id']}", struct.pack("!I", zlib.crc32(camera["local"]["local_key"].encode("latin1"))))

    async def close(self):
        await asyncio.to_thread(self.client.disconnect)
        if self.started:
            await asyncio.to_thread(self.client.loop_stop)
        self.failed.set()


class CloudSession:
    """WebRTC adapter including Tuya's H.265 RTP-over-datachannel variant."""

    def __init__(self, account, camera, packet, config=None):
        self.account, self.camera, self.packet = account, camera, packet
        self.config = config
        self.failed = asyncio.Event()
        self.first_video = asyncio.Event()
        self.last_video = time.monotonic()
        self.phase = "config"
        self.failure = None
        self.peer = None
        self.broker = None
        self.tasks: set[asyncio.Task] = set()
        self.session_id = secrets.token_hex(16)
        self.hevc = False
        self.audio_codec = "PCMU/8000/1"
        self.ssrcs = {}

    def task(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        def completed(task):
            if not task.cancelled() and task.exception() is not None:
                self.failure = type(task.exception()).__name__
                self.failed.set()
        task.add_done_callback(completed)

    async def start(self):
        if self.config is None:
            self.config = await self.account.call("smartlife.m.rtc.config.get", {"devId": self.camera["camera_id"]})
        skill = self.config.get("skill") or {}
        if isinstance(skill, str):
            skill = json.loads(skill)
        video = max(skill.get("videos", []), key=lambda v: v.get("width", 0) * v.get("height", 0), default={})
        self.hevc = video.get("codecType") == 4
        self.stream_type = 0 if self.hevc else video.get("streamType", 1)
        audio = next(iter(skill.get("audios", [])), {})
        self.pcm = self.hevc and audio.get("codecType") == 101
        if self.pcm:
            self.audio_codec = f"L16/{audio.get('sampleRate') or 8000}/{audio.get('channels') or 1}"
        elif audio.get("codecType") == 106:
            self.audio_codec = "PCMA/8000/1"
        servers = ice_servers(self.config)
        self.phase = "peer"
        self.peer = RTCPeerConnection(RTCConfiguration(iceServers=servers))
        self.phase = "broker"
        self.broker = await self.account.broker()
        self.peer.on("connectionstatechange", self._state)
        self.peer.on("track", lambda track: self.task(self._drain(track)))
        self.phase = "transceivers"
        for kind in ("audio", "video"):
            transceiver = self.peer.addTransceiver(kind, direction="recvonly")
            if not self.hevc:
                mime = "video/H264" if kind == "video" else "audio/" + self.audio_codec.split("/")[0]
                transceiver.setCodecPreferences([codec for codec in RTCRtpReceiver.getCapabilities(kind).codecs
                                                 if codec.mimeType.lower() == mime.lower()])
                self._receive_rtp(transceiver.receiver, kind)
        if self.hevc:
            channel = self.peer.createDataChannel("fmp4Stream", ordered=True, maxRetransmits=5)
            channel.on("open", lambda: channel.send(json.dumps({"type": "codec", "msg": ""}).encode()))
            channel.on("message", lambda message: self._datachannel(channel, message))
        self.task(self._signals())
        self.task(self._watch())
        self.phase = "offer"
        offer = await self.peer.createOffer()
        self.phase = "gather"
        await self.peer.setLocalDescription(offer)
        # Send candidates explicitly; Tuya's answers may use only trickle ICE.
        lines = self.peer.localDescription.sdp.splitlines()
        sdp = "\r\n".join(line for line in lines if not line.startswith(("a=candidate:", "a=end-of-candidates", "a=extmap:"))) + "\r\n"
        self.phase = "publish"
        await self.send("offer", {"mode": "webrtc", "sdp": sdp, "stream_type": self.stream_type,
                                 "auth": self.config.get("auth", ""), "token": self.config.get("p2pConfig", {}).get("ices", []),
                                 "replay": {"is_replay": 0}, "datachannel_enable": self.hevc})
        for line in lines:
            if line.startswith("a=candidate:"):
                await self.send("candidate", {"mode": "webrtc", "candidate": line})

    def _receive_rtp(self, receiver, kind):
        """Isolate the pinned aiortc raw-packet hook; preserve its RTCP/NACK handling.

        aiortc's public tracks expose decoded frames only. Forward the original
        compressed packet before its normal receiver processing, avoiding encode.
        A synthetic peer test covers this hook when upgrading aiortc.
        """
        original = receiver._handle_rtp_packet
        async def handle(packet, arrival_time_ms):
            codec = receiver._RTCRtpReceiver__codecs.get(packet.payload_type)
            forwarded = packet
            if codec is not None and codec.name.lower() == "rtx":
                apt = codec.parameters.get("apt")
                ssrc = receiver._RTCRtpReceiver__rtx_ssrc.get(packet.ssrc)
                if isinstance(apt, int) and ssrc is not None and len(packet.payload) >= 2:
                    forwarded = unwrap_rtx(packet, payload_type=apt, ssrc=ssrc)
                    codec = receiver._RTCRtpReceiver__codecs.get(apt)
                else:
                    codec = None
            if codec is not None:
                if kind == "audio":
                    self.audio_codec = f"{codec.name}/{codec.clockRate}/{codec.channels or 1}"
                elif codec.name.upper() != "H264":
                    return
                self.packet(kind, forwarded.payload, forwarded.timestamp, forwarded.marker)
                if kind == "video":
                    self.last_video = time.monotonic()
                    self.first_video.set()
            await original(packet, arrival_time_ms)
        receiver._handle_rtp_packet = handle

    async def _drain(self, track):
        while True:
            await track.recv()

    async def _watch(self):
        while not self.failed.is_set():
            await asyncio.sleep(5)
            if self.broker.failed.is_set() or time.monotonic() - self.last_video > 30:
                self.failed.set()

    async def _state(self):
        if self.peer is not None and self.peer.connectionState in ("closed", "failed"):
            self.failed.set()

    def _datachannel(self, channel, message):
        try:
            if isinstance(message, str):
                value = json.loads(message)
                if value.get("type") == "codec":
                    channel.send(json.dumps({"type": "start", "msg": "frame"}).encode())
                elif value.get("type") == "recv":
                    tracks = value.get("msg", {})
                    if isinstance(tracks, str):
                        tracks = json.loads(tracks)
                    self.ssrcs = {item.get("ssrc"): kind for kind, item in tracks.items() if kind in ("video", "audio")}
                    channel.send(json.dumps({"type": "complete", "msg": ""}).encode())
            else:
                packet = RtpPacket.parse(message)
                kind = self.ssrcs.get(packet.ssrc)
                if kind:
                    payload = packet.payload
                    if kind == "audio" and self.pcm:
                        if len(payload) % 2:
                            return
                        pcm = bytearray(payload)
                        pcm[0::2], pcm[1::2] = payload[1::2], payload[0::2]
                        payload = bytes(pcm)
                    self.packet(kind, payload, packet.timestamp, packet.marker)
                    if kind == "video":
                        self.last_video = time.monotonic()
                        self.first_video.set()
        except (ValueError, TypeError, AttributeError):
            self.failed.set()

    async def send(self, kind, message, protocol=302):
        header = {"type": kind, "from": self.account.data["uid"], "to": self.camera["camera_id"],
                  "sessionid": self.session_id, "moto_id": self.config.get("motoId", ""),
                  "tid": "", "seq": 0, "rtx": 0}
        value = {"protocol": protocol, "pv": "2.2", "t": int(time.time() * 1000), "data": {"header": header, "msg": message}}
        await self.broker.publish(f"/av/moto/{header['moto_id']}/u/{header['to']}", json.dumps(value, separators=(",", ":")))

    async def _signals(self):
        pending = []
        answered = False
        while True:
            value = await self.broker.messages.get()
            data = value.get("data", {})
            header, msg = data.get("header", {}), data.get("msg", {})
            if header.get("sessionid") != self.session_id or header.get("from") != self.camera["camera_id"]:
                continue
            kind = header.get("type")
            if kind == "answer":
                try:
                    await self.peer.setRemoteDescription(RTCSessionDescription(sdp=msg["sdp"], type="answer"))
                except (ValueError, AssertionError) as err:
                    known = ("ICE username fragment or password is missing", "RTCP mux is not enabled", "DTLS fingerprint does not match", "None is not in list", "Media sections in answer do not match offer", "No common codec")
                    self.failure = next((reason for reason in known if reason in str(err)), type(err).__name__)
                    self.failed.set()
                    return
                answered = True
                for candidate in pending:
                    await self.peer.addIceCandidate(candidate)
                pending.clear()
            elif header.get("type") == "candidate":
                raw = msg.get("candidate", "").strip().removeprefix("a=").removeprefix("candidate:")
                if not raw:
                    continue
                candidate = candidate_from_sdp(raw)
                candidate.sdpMLineIndex = 0
                if answered:
                    await self.peer.addIceCandidate(candidate)
                elif len(pending) < 64:
                    pending.append(candidate)
            elif header.get("type") == "disconnect":
                self.failure = "camera_disconnected"
                self.failed.set()
                return

    async def close(self):
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.broker:
            with suppress(OSError, TimeoutError, MediaError):
                await self.send("disconnect", {"mode": "webrtc"})
            await self.broker.close()
            self.broker = None
        if self.peer:
            await self.peer.close()
            self.peer = None
        self.failed.set()
