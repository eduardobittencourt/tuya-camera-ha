"""Integration-owned media lifecycle and private RTSP boundary."""
import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.tuya_camera.config_flow import entry_data
from custom_components.tuya_camera.media.cloud import MediaAuthenticationError, MediaError
from custom_components.tuya_camera.media.lan import LanSession
from custom_components.tuya_camera.media.rtsp import MediaSource, RtspConnection, RtspServer
from custom_components.tuya_camera.media.runtime import MediaRuntime

from .test_config_flow import LOGIN
from .test_python_transport import KEY


@pytest.mark.parametrize("lan", [False, True])
async def test_runtime_opens_selected_transport_and_reuses_cloud_configuration(lan):
    runtime = MediaRuntime(AsyncMock(), entry_data(LOGIN), Mock(), Mock())
    camera = {"camera_id": "camera", "local": {"host": "192.168.0.2"}}
    runtime.sources["camera"] = {}
    runtime.configs["camera"] = {"cached": True}
    session = AsyncMock()
    session.hevc = True
    packet = Mock()
    with patch("custom_components.tuya_camera.media.runtime.LanSession", return_value=session) as local, \
         patch("custom_components.tuya_camera.media.runtime.CloudSession", return_value=session) as cloud:
        assert await runtime._open(camera, lan, packet) is session
    session.start.assert_awaited_once()
    session.close.assert_not_awaited()
    if lan:
        session.connect.assert_awaited_once()
        local.assert_called_once_with(camera, runtime.data["uid"], packet)
        cloud.assert_not_called()
    else:
        cloud.assert_called_once_with(runtime.account, camera, packet, {"cached": True})
        assert runtime.sources["camera"]["hevc"]


@pytest.mark.parametrize("error", [RuntimeError("private-response"), MediaAuthenticationError("expired"),
                                 asyncio.CancelledError()])
async def test_runtime_start_failure_closes_session_and_preserves_cancellation(error):
    runtime = MediaRuntime(AsyncMock(), entry_data(LOGIN), Mock(), Mock())
    session = AsyncMock()
    session.start.side_effect = error
    expected = MediaError if type(error) is RuntimeError else type(error)
    packet = Mock()
    with patch("custom_components.tuya_camera.media.runtime.CloudSession", return_value=session), \
         pytest.raises(expected) as raised:
        await runtime._open({"camera_id": "camera"}, False, packet)
    session.close.assert_awaited_once()
    assert "private-response" not in str(raised.value)
    assert runtime.camera_status["camera"]["state"] == "error"


async def test_failed_cloud_wake_closes_broker_and_lan_session():
    runtime = MediaRuntime(AsyncMock(), entry_data(LOGIN), Mock(), Mock())
    broker = AsyncMock()
    broker.wake.side_effect = RuntimeError("private-response")
    runtime.account.broker = AsyncMock(return_value=broker)
    session = AsyncMock()
    session.connect.side_effect = OSError()
    camera = {"camera_id": "camera", "local": {"host": "192.168.0.2"}}
    packet = Mock()
    with patch("custom_components.tuya_camera.media.runtime.LanSession", return_value=session), \
         pytest.raises(MediaError, match="media connection failed"):
        await runtime._open(camera, True, packet)
    broker.wake.assert_awaited_once()
    broker.close.assert_awaited_once()
    session.start.assert_not_awaited()
    assert session.close.await_count >= 1
    assert runtime.camera_status["camera"]["cloud_wakes"] == 1


async def test_local_media_operations_share_active_session_and_return_copies():
    runtime = MediaRuntime(AsyncMock(), entry_data(LOGIN), Mock(), Mock())
    session = LanSession({"local": {"host": "192.168.0.2", "local_key": KEY.decode()}}, "test", Mock())
    session.values = {"1": True}
    session.set_dp = AsyncMock()
    runtime.media["camera"] = Mock(session=session)
    status = await runtime.local_request("camera", "status")
    status["dps"].clear()
    assert session.values == {"1": True}
    stats = await runtime.local_request("camera", "stats")
    stats["dps"].clear()
    assert session.stats
    session.reports.put_nowait({"1": False})
    assert await runtime.local_request("camera", "receive") == {"dps": {"1": False}}
    assert await runtime.local_request("camera", "receive") == {"dps": {}}
    assert await runtime.local_request("camera", "set", index="1", value=False) == {"dps": {}}
    session.set_dp.assert_awaited_once_with("1", False)
    with pytest.raises(MediaError, match="Unsupported"):
        await runtime.local_request("camera", "unknown")
    session.failed.set()
    with pytest.raises(MediaError, match="inactive"):
        await runtime.local_request("camera", "status")
    with pytest.raises(MediaError, match="inactive"):
        await runtime.local_request("missing", "status")


@pytest.mark.parametrize("partial", [
    b"D",
    b"GET_PARAMETER rtsp://127.0.0.1/camera RTSP/1.0\r\nContent-Length: 4\r\n\r\nx",
    b"$\x00\x00\x04x",
])
async def test_partial_rtsp_request_times_out_and_releases_client(socket_enabled, monkeypatch, partial):
    monkeypatch.setattr("custom_components.tuya_camera.media.rtsp.REQUEST_TIMEOUT", .05)
    server = RtspServer({})
    await server.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
        writer.write(partial)
        await writer.drain()
        assert await asyncio.wait_for(reader.read(), 1) == b""
        writer.close()
        await writer.wait_closed()
    finally:
        await server.stop()
    assert not server.tasks


async def test_cancel_after_acquisition_retains_lease_for_cleanup():
    session = AsyncMock()
    session.failed = asyncio.Event()
    source = MediaSource(AsyncMock(return_value=session), lambda: None)
    connection = RtspConnection({"/camera": source}, AsyncMock(), AsyncMock())
    connection.reader.at_eof = lambda: False
    original = source.acquire

    async def acquire_and_cancel():
        queue = await original()
        asyncio.get_running_loop().call_soon(describing.cancel)
        return queue

    source.acquire = acquire_and_cancel
    describing = asyncio.create_task(connection.describe("1", "rtsp://127.0.0.1/camera", "/camera"))
    try:
        with pytest.raises(asyncio.CancelledError):
            await describing
        assert connection.queue in source.consumers
        await source.release(connection.queue)
        session.close.assert_awaited_once()
        assert not source.consumers
    finally:
        await source.stop()


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
    assert not server.tasks
    assert source.session is None


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
        assert not source.consumers
        assert source.session is None
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
    assert not server.tasks
    assert not source.consumers
    assert source.session is None


async def test_failed_session_rejects_overlapping_reader_then_reconnects():
    failed, replacement = AsyncMock(), AsyncMock()
    for session in (failed, replacement):
        session.failed = asyncio.Event()
        session.hevc, session.audio_codec = False, "L16/8000/1"
    factory = AsyncMock(side_effect=[failed, replacement])
    source = MediaSource(factory, lambda: None)
    old = await source.acquire()
    failed.failed.set()
    # Test before the monitor gets a chance to notify existing readers.
    with pytest.raises(ConnectionError, match="recovering"):
        await source.acquire()
    assert source.consumers == {old}
    assert await asyncio.wait_for(old.get(), 1) is None
    await source.release(old)
    failed.close.assert_awaited_once()
    new = await source.acquire()
    try:
        assert source.session is replacement
        assert source.consumers == {new}
        assert factory.await_count == 2
        replacement.close.assert_not_awaited()
    finally:
        await source.release(new)
    replacement.close.assert_awaited_once()
