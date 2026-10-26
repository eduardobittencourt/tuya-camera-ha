#!/usr/bin/env python3
"""Receive actual H.264/Opus from a synthetic go2rtc endpoint (test tooling)."""
from __future__ import annotations

import asyncio
import sys

import aiohttp
from aiortc import RTCConfiguration, RTCPeerConnection, RTCRtpReceiver, RTCSessionDescription


async def run(endpoint):
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
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=35)) as session, session.post(
            endpoint, data=peer.localDescription.sdp, headers={"Content-Type": "application/sdp"},
        ) as response:
            response.raise_for_status()
            await peer.setRemoteDescription(RTCSessionDescription(sdp=await response.text(), type="answer"))
        await asyncio.wait_for(ready.wait(), 25)
        print("Received H.264 video and Opus audio via WebRTC")
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await peer.close()


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1]))
