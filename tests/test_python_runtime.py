"""Integration-owned media lifecycle and private RTSP boundary."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from custom_components.tuya_camera_bridge.config_flow import entry_data
from custom_components.tuya_camera_bridge.media.rtsp import MediaSource, RtspServer
from custom_components.tuya_camera_bridge.media.runtime import MediaRuntime

from .test_config_flow import LOGIN


async def test_runtime_uses_no_binary_and_unload_closes_listener(socket_enabled):
    runtime = MediaRuntime(AsyncMock(), entry_data(LOGIN), lambda: None, lambda: None)
    runtime.account.call = AsyncMock(return_value={})
    await runtime.start()
    assert runtime.ready
    assert all(source["path"].startswith("/") for source in runtime.sources.values())
    assert all(runtime.source_url(cid).startswith("rtsp://127.0.0.1:") for cid in runtime.sources)
    port = runtime.server.port
    await runtime.stop()
    assert not runtime.ready
    with pytest.raises(OSError):
        await asyncio.open_connection("127.0.0.1", port)


async def test_rtsp_shares_session_and_stops_after_last_reader(socket_enabled):
    session = AsyncMock()
    session.hevc, session.audio_codec = False, "L16/8000/1"
    session.failed = asyncio.Event()
    factory = AsyncMock(return_value=session)
    source = MediaSource(factory, lambda: None)
    server = RtspServer({"/camera": source})
    await server.start()
    writers = []
    try:
        for _ in range(2):
            reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
            writers.append(writer)
            writer.write(f"DESCRIBE rtsp://127.0.0.1:{server.port}/camera RTSP/1.0\r\nCSeq: 1\r\n\r\n".encode())
            await writer.drain()
            response = await reader.readuntil(b"\r\n\r\n")
            assert b"200 OK" in response
        assert factory.await_count == 1
        assert len(source.consumers) == 2
        writers[0].close()
        await writers[0].wait_closed()
        await asyncio.sleep(.05)
        assert len(source.consumers) == 1
        session.close.assert_not_awaited()
    finally:
        for writer in writers:
            writer.close()
        await server.stop()
    session.close.assert_awaited_once()
    assert not server.tasks and source.session is None


async def test_disconnect_cancels_pending_camera_negotiation(socket_enabled):
    started, closed = asyncio.Event(), asyncio.Event()
    async def factory(packet):
        started.set()
        try:
            await asyncio.sleep(60)
        finally:
            closed.set()
    source = MediaSource(factory, lambda: None)
    server = RtspServer({"/camera": source})
    await server.start()
    try:
        _, writer = await asyncio.open_connection("127.0.0.1", server.port)
        writer.write(f"DESCRIBE rtsp://127.0.0.1:{server.port}/camera RTSP/1.0\r\nCSeq: 1\r\n\r\n".encode())
        await writer.drain()
        await asyncio.wait_for(started.wait(), 1)
        writer.close()
        await writer.wait_closed()
        await asyncio.wait_for(closed.wait(), 1)
        assert not source.consumers and source.session is None
    finally:
        await server.stop()


async def test_shutdown_during_disconnected_reader_cleanup(socket_enabled):
    closing = asyncio.Event()
    calls = 0
    async def close():
        nonlocal calls
        calls += 1
        if calls == 1:
            closing.set()
            await asyncio.sleep(60)
    session = AsyncMock()
    session.close.side_effect = close
    session.failed = asyncio.Event()
    session.hevc, session.audio_codec = False, "L16/8000/1"
    source = MediaSource(AsyncMock(return_value=session), lambda: None)
    server = RtspServer({"/camera": source})
    await server.start()
    reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
    writer.write(f"DESCRIBE rtsp://127.0.0.1:{server.port}/camera RTSP/1.0\r\nCSeq: 1\r\n\r\n".encode())
    await writer.drain()
    assert b"200 OK" in await reader.readuntil(b"\r\n\r\n")
    writer.close()
    await writer.wait_closed()
    await asyncio.wait_for(closing.wait(), 1)
    await asyncio.wait_for(server.stop(), 1)
    assert not server.tasks and not source.consumers and source.session is None
