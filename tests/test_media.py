"""Real codec/transport tests with a synthetic camera; no Tuya account needed."""
import asyncio
import io
import json
import os
import socket
from pathlib import Path

import pytest
from homeassistant.components.camera import DynamicStreamSettings
from homeassistant.components.stream import create_stream
from homeassistant.components.stream.const import HLS_PROVIDER
from homeassistant.setup import async_setup_component

from custom_components.tuya_camera_bridge.bridge import stop_process
from custom_components.tuya_camera_bridge.transcoder import FfmpegRelay

pytestmark = pytest.mark.media


def media_binaries():
    ffmpeg = os.environ.get("TEST_FFMPEG_BINARY")
    mediamtx = os.environ.get("TEST_MEDIAMTX_BINARY")
    if not ffmpeg or not mediamtx:
        pytest.skip("Set TEST_FFMPEG_BINARY and TEST_MEDIAMTX_BINARY to run real media tests")
    return ffmpeg, mediamtx


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


async def inspect_webrtc(relay, ffmpeg, tmp_path):
    """Use HA's two-source go2rtc arrangement and receive actual WebRTC RTP."""
    go2rtc = os.environ.get("TEST_GO2RTC_BINARY")
    receiver = os.environ.get("TEST_WEBRTC_PROBE")
    if not go2rtc or not receiver:
        return
    api_port, rtsp_port, rtc_port = free_port(), free_port(), free_port()
    config = tmp_path / "go2rtc.yml"
    config.write_text(json.dumps({
        "log": {"level": "error"}, "api": {"listen": f"127.0.0.1:{api_port}"},
        "rtsp": {"listen": f"127.0.0.1:{rtsp_port}"},
        "webrtc": {
            "listen": f"127.0.0.1:{rtc_port}", "candidates": [f"127.0.0.1:{rtc_port}"], "ice_servers": [],
            "filters": {"loopback": True, "ips": ["127.0.0.1"], "networks": ["udp4"]},
        },
        "ffmpeg": {"bin": ffmpeg},
        "streams": {"camera": [relay.url, "ffmpeg:camera#audio=opus#query=log_level=debug"]},
    }))
    server = await asyncio.create_subprocess_exec(
        go2rtc, "-config", str(config), stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL, start_new_session=True,
    )
    probe = None
    try:
        async with asyncio.timeout(10):
            while True:
                try:
                    _, writer = await asyncio.open_connection("127.0.0.1", api_port)
                    writer.close()
                    await writer.wait_closed()
                    break
                except OSError:
                    await asyncio.sleep(.05)
        probe = await asyncio.create_subprocess_exec(
            receiver, f"http://127.0.0.1:{api_port}/api/webrtc?src=camera",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, start_new_session=True,
        )
        async with asyncio.timeout(60):
            stdout, stderr = await probe.communicate()
        assert probe.returncode == 0, stderr.decode()
        assert b"H.264 video and Opus audio" in stdout
    finally:
        if probe is not None:
            await stop_process(probe)
        await stop_process(server)


def inspect_stream(url):
    import av
    with av.open(url, timeout=(20, 15)) as container:
        assert container.streams.video[0].codec_context.name == "h264"
        assert container.streams.audio[0].codec_context.name == "aac"
        seen = set()
        for frame in container.decode():
            seen.add("video" if isinstance(frame, av.VideoFrame) else "audio")
            if seen == {"video", "audio"}:
                return
        raise AssertionError("The relay did not deliver both video and audio")


@pytest.mark.parametrize("codec", ["libx264", "libx265"])
async def test_synthetic_camera_delivers_video_audio_and_fresh_snapshot(codec, tmp_path, socket_enabled, hass):
    ffmpeg, mediamtx = media_binaries()
    port = free_port()
    config = Path(tmp_path / "mediamtx.yml")
    config.write_text(f"logLevel: error\nrtspAddress: 127.0.0.1:{port}\nrtspTransports: [tcp]\nrtmp: false\nhls: false\nwebrtc: false\nsrt: false\nmoq: false\npaths:\n  camera:\n    source: publisher\n")
    server = await asyncio.create_subprocess_exec(
        mediamtx, str(config), stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL, start_new_session=True,
    )
    source = f"rtsp://127.0.0.1:{port}/camera"
    publisher = None
    stream = None
    relay = FfmpegRelay(ffmpeg, lambda: source, lambda: codec == "libx265")
    try:
        async with asyncio.timeout(10):
            while True:
                try:
                    _, writer = await asyncio.open_connection("127.0.0.1", port)
                    writer.close()
                    await writer.wait_closed()
                    break
                except OSError:
                    await asyncio.sleep(.05)
        publisher = await asyncio.create_subprocess_exec(
            ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-re", "-f", "lavfi", "-i",
            "testsrc2=size=320x180:rate=10", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000",
            "-c:v", codec, "-preset", "ultrafast", "-tune", "zerolatency", "-threads", "2", "-g", "20",
            "-c:a", "pcm_mulaw", "-ar", "8000", "-rtsp_transport", "tcp", "-f", "rtsp", source,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL, start_new_session=True,
        )
        # Wait for publisher registration without PLAY or consuming media.
        # A fixed startup sleep can race encoder startup on busy CI runners.
        async with asyncio.timeout(10):
            while True:
                assert publisher.returncode is None
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                try:
                    writer.write(f"DESCRIBE {source} RTSP/1.0\r\nCSeq: 1\r\nAccept: application/sdp\r\n\r\n".encode())
                    await writer.drain()
                    response = await reader.readline()
                finally:
                    writer.close()
                    await writer.wait_closed()
                if response.startswith(b"RTSP/1.0 200"):
                    break
                await asyncio.sleep(.05)
        await relay.start()
        # A dashboard snapshot is the first media consumer after startup.
        # Home Assistant cancels image requests at its ten-second deadline.
        async with asyncio.timeout(10):
            cold_image = await relay.snapshot()
        assert cold_image and cold_image.startswith(b"\xff\xd8")
        await asyncio.to_thread(inspect_stream, relay.url)
        assert await async_setup_component(hass, "stream", {})
        stream = create_stream(hass, relay.url, {}, DynamicStreamSettings())
        output = stream.add_provider(HLS_PROVIDER)
        await stream.start()
        async with asyncio.timeout(40):
            while not any(segment.complete for segment in output.get_segments()):
                await asyncio.sleep(.1)
        segment = next(segment for segment in output.get_segments() if segment.complete)
        import av
        fragment = segment.init + b"".join(part.data for part in segment.parts)
        with av.open(io.BytesIO(fragment)) as container:
            assert container.streams.video[0].codec_context.name == "h264"
            assert container.streams.audio[0].codec_context.name == "aac"
            assert any(container.decode(video=0))
        await stream.remove_provider(output)
        stream = None
        await inspect_webrtc(relay, ffmpeg, tmp_path)
        image = await relay.snapshot()
        assert image and image.startswith(b"\xff\xd8")
        await stop_process(publisher)
        assert await relay.snapshot() is None
    finally:
        if stream is not None:
            for provider in stream.outputs().values():
                await stream.remove_provider(provider)
            await stream.stop()
        await relay.stop()
        if publisher is not None:
            await stop_process(publisher)
        await stop_process(server)
    assert relay.active_processes == 0
