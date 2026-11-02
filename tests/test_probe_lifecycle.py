"""Exercise the probe's private ICE factory through real peer negotiation."""
import asyncio
from unittest.mock import patch

import pytest
from aiohttp import web
from aioice import stun

from scripts import webrtc_probe


def guarded_transports(peer):
    """Inspect live transports, including the gatherer/transport connection alias."""
    transports = {t.sender.transport.transport for t in peer.getTransceivers()}
    assert transports
    for transport in transports:
        assert isinstance(transport._connection, webrtc_probe.LoopbackConnection)
        assert transport.iceGatherer._connection is transport._connection
    return transports


def reject_external_stun(connection):
    """Offer credentials cannot bypass the guard on the actual negotiated object."""
    message = stun.Message(stun.Method.BINDING, stun.Class.REQUEST, attributes={
        "USERNAME": f"{connection.local_username}:{connection.remote_username}",
        "PRIORITY": 1, "ICE-CONTROLLING": 1,
    })
    message.add_message_integrity(connection.local_password.encode())
    raw = bytes(message)
    stun.parse_message(raw, integrity_key=connection.local_password.encode())
    protocol = connection._protocols[0]
    with patch.object(protocol, "send_stun") as reply, patch.object(connection, "check_incoming") as check:
        connection.request_received(message, ("192.0.2.10", 23456), protocol, raw)
    reply.assert_not_called()
    check.assert_not_called()
    assert all(c.host == "127.0.0.1" for c in connection.remote_candidates)


@pytest.mark.parametrize("failure", [False, True])
async def test_probe_guard_survives_negotiation_and_cleanup(failure, aiohttp_server, socket_enabled):
    """The live factory guard survives real SDP application, failure and cancellation."""
    factory = webrtc_probe.rtcicetransport.Connection
    peer = webrtc_probe.ProbePeer(webrtc_probe.RTCConfiguration(iceServers=[]))
    remote = webrtc_probe.ProbePeer(webrtc_probe.RTCConfiguration(iceServers=[]))
    applied = asyncio.Event()
    transports = set()
    negotiations = set()
    original = peer.setRemoteDescription

    async def answer(request):
        transports.update(guarded_transports(peer))
        webrtc_probe.add_receivers(remote)
        for transceiver in remote.getTransceivers():
            transceiver.direction = "sendonly"
        await remote.setRemoteDescription(webrtc_probe.RTCSessionDescription(sdp=await request.text(), type="offer"))
        await remote.setLocalDescription(await remote.createAnswer())
        return web.Response(text=remote.localDescription.sdp)

    async def apply(description):
        await original(description)
        negotiations.update(peer._negotiations)
        transports.update(guarded_transports(peer))
        for transport in guarded_transports(peer):
            reject_external_stun(transport._connection)
        applied.set()
        if failure:
            raise ValueError("synthetic negotiation failure")

    app = web.Application()
    app.router.add_post("/api/webrtc", answer)
    server = await aiohttp_server(app, host="127.0.0.1")
    with patch.object(webrtc_probe, "ProbePeer", return_value=peer), \
         patch.object(peer, "setRemoteDescription", side_effect=apply):
        task = asyncio.create_task(webrtc_probe.run(server.port))
        try:
            await asyncio.wait_for(applied.wait(), 3)
            if failure:
                with pytest.raises(ValueError, match="synthetic negotiation failure"):
                    await task
            else:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await remote.close()
    assert peer.connectionState == "closed"
    assert negotiations
    assert all(task.done() for task in negotiations)
    assert not peer._negotiations
    assert not remote._negotiations
    assert all(transport.state == "closed" for transport in transports)
    guarded_transports(peer)
    assert webrtc_probe.rtcicetransport.Connection is factory
