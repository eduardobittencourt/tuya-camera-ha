#!/usr/bin/env python3
"""Receive actual H.264/Opus from a synthetic go2rtc endpoint (test tooling)."""
from __future__ import annotations

import argparse
import asyncio

import aiohttp
from aiortc import RTCConfiguration, RTCPeerConnection, RTCRtpReceiver, RTCSessionDescription
from aiortc.sdp import SessionDescription

MAX_ANSWER_SIZE = 256 * 1024


def loopback_answer(sdp: str) -> RTCSessionDescription:
    """Reject remote and mDNS ICE targets before aiortc can contact or resolve them."""
    description = SessionDescription.parse(sdp)
    for media in description.media:
        for candidate in media.ice_candidates:
            if candidate.ip != "127.0.0.1" or candidate.relatedAddress not in (None, "127.0.0.1"):
                raise ValueError("The synthetic WebRTC answer must use IPv4 loopback ICE candidates")
    return RTCSessionDescription(sdp=sdp, type="answer")


async def run(port: int):
    """Receive synthetic media from the fixed local go2rtc camera route."""
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("The synthetic WebRTC API port must be between 1 and 65535")
    endpoint = f"http://127.0.0.1:{port}/api/webrtc?src=camera"
    peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    seen = set()
    ready = asyncio.Event()
    tasks = []

    async def receive(track):
        for _ in range(10):
            await track.recv()
        seen.add(track.kind)
        if len(seen) == 2:
            ready.set()

    peer.on("track", lambda track: tasks.append(asyncio.create_task(receive(track))))
    try:
        for kind, codec in (("video", "video/H264"), ("audio", "audio/opus")):
            transceiver = peer.addTransceiver(kind, direction="recvonly")
            transceiver.setCodecPreferences([c for c in RTCRtpReceiver.getCapabilities(kind).codecs if c.mimeType == codec])
        await peer.setLocalDescription(await peer.createOffer())
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=35), trust_env=False) as session, session.post(
            endpoint, data=peer.localDescription.sdp, headers={"Content-Type": "application/sdp"},
            allow_redirects=False,
        ) as response:
            response.raise_for_status()
            if 300 <= response.status < 400:
                raise ValueError("The synthetic WebRTC endpoint returned a redirect")
            try:
                answer = await response.content.readexactly(MAX_ANSWER_SIZE + 1)
            except asyncio.IncompleteReadError as error:
                answer = error.partial
            else:
                raise ValueError("The synthetic WebRTC answer exceeds the size limit")
            await peer.setRemoteDescription(loopback_answer(answer.decode("utf-8")))
        await asyncio.wait_for(ready.wait(), 25)
        print("Received H.264 video and Opus audio via WebRTC")
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await peer.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", type=int, help="Local synthetic go2rtc API port")
    asyncio.run(run(parser.parse_args().port))
