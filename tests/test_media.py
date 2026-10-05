"""Real codec/transport tests with a synthetic camera; no Tuya account needed."""
import asyncio
import io
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
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
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
        await asyncio.sleep(1)
        assert publisher.returncode is None
        await relay.start()
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
