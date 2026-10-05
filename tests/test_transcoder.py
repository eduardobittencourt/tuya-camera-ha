import asyncio
import sys
from urllib.parse import urlsplit

from custom_components.tuya_camera_bridge.transcoder import FfmpegRelay


def test_h264_is_copied_and_audio_is_retained():
    relay = FfmpegRelay("ffmpeg", lambda: "rtsp://127.0.0.1:1234/test", lambda: False)
    command = relay.command()
    assert command[command.index("-c:v") + 1] == "copy"
    assert command[command.index("-c:a") + 1] == "aac"
    assert "-an" not in command
    relay.hevc = lambda: True
    assert relay.command()[relay.command().index("-c:v") + 1] == "libx264"


async def test_private_url_and_disconnect_cleanup(tmp_path, socket_enabled):
    executable = tmp_path / "ffmpeg"
    executable.write_text(f"#!{sys.executable}\nimport sys,time\nwhile True:\n sys.stdout.buffer.write(b'x'*188)\n sys.stdout.buffer.flush()\n time.sleep(.01)\n")
    executable.chmod(0o700)
    relay = FfmpegRelay(str(executable), lambda: "rtsp://127.0.0.1:1234/test", lambda: False)
    await relay.start()
    parsed = urlsplit(relay.url)
    assert parsed.hostname == "127.0.0.1"
    reader, writer = await asyncio.open_connection(parsed.hostname, parsed.port)
    writer.write(b"GET /wrong HTTP/1.1\r\nHost: localhost\r\n\r\n")
    await writer.drain()
    assert (await reader.read()).startswith(b"HTTP/1.1 404")
    writer.close()
    await writer.wait_closed()
    reader, writer = await asyncio.open_connection(parsed.hostname, parsed.port)
    writer.write(f"GET {parsed.path} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode())
    await writer.drain()
    assert (await reader.readuntil(b"\r\n\r\n")).startswith(b"HTTP/1.1 200")
    assert relay.active_processes == 1
    writer.close()
    await writer.wait_closed()
    async with asyncio.timeout(3):
        while relay.active_processes:
            await asyncio.sleep(0.01)
    await relay.stop()
    assert not relay._tasks


async def test_stop_reaps_live_transcoders(tmp_path, socket_enabled):
    executable = tmp_path / "ffmpeg"
    executable.write_text(f"#!{sys.executable}\nimport sys,time\nprint('transport-stream',flush=True)\ntime.sleep(60)\n")
    executable.chmod(0o700)
    relay = FfmpegRelay(str(executable), lambda: "rtsp://127.0.0.1:1234/test", lambda: False)
    await relay.start()
    parsed = urlsplit(relay.url)
    reader, writer = await asyncio.open_connection(parsed.hostname, parsed.port)
    writer.write(f"GET {parsed.path} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode())
    await writer.drain()
    await reader.readuntil(b"\r\n\r\n")
    processes = tuple(relay._processes)
    await relay.stop()
    assert all(process.returncode is not None for process in processes)
    writer.close()
    await writer.wait_closed()
