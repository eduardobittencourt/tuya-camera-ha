import asyncio
import json
import os
import signal
import sys
from unittest.mock import Mock

import pytest

from custom_components.tuya_camera_bridge import bridge as bridge_module
from custom_components.tuya_camera_bridge.bridge import BridgeAuthenticationError, ManagedBridge


@pytest.fixture
def bridge_executable(tmp_path):
    path = tmp_path / "bridge"
    path.write_text(f"#!{sys.executable}\n" + '''
import json, sys, time
config = json.load(sys.stdin)
if config.get("stall"):
    time.sleep(60)
if config.get("auth"):
    print(json.dumps({"event": "auth_required"}), flush=True)
else:
    print("this private log must never be forwarded", flush=True)
    print(json.dumps({"event": "ready", "source_port": 14567,
        "cameras": [{"camera_id": item["camera_id"], "path": "/" + item["camera_name"].replace(" / ", "_").replace(" ", "_"), "hevc": False}
                    for item in config["cameras"]]}), flush=True)
time.sleep(60)
''')
    path.chmod(0o700)
    return path


def managed(path, directory, **extras):
    return ManagedBridge(path, directory, {
        "sid": "test-session", "cameras": [{"camera_id": "one", "camera_name": "Câmera / Kitchen"}], **extras,
    }, Mock(), Mock())


async def test_bridge_reads_stdin_and_stops_without_writing_session(bridge_executable, tmp_path):
    runtime = managed(bridge_executable, tmp_path / "runtime")
    await runtime.start()
    process = runtime.process
    assert runtime.ready
    assert runtime.source_url("one") == "rtsp://127.0.0.1:14567/C%C3%A2mera_Kitchen"
    assert list(runtime.directory.iterdir()) == []
    await runtime.stop()
    assert process.returncode is not None
    assert not runtime.ready


async def test_bridge_restarts_after_unexpected_exit(bridge_executable, tmp_path, monkeypatch):
    monkeypatch.setattr(bridge_module, "RESTART_MIN_DELAY", 0.01)
    runtime = managed(bridge_executable, tmp_path / "runtime")
    await runtime.start()
    first = runtime.process
    os.killpg(first.pid, signal.SIGKILL)
    async with asyncio.timeout(3):
        while runtime.process is first or not runtime.ready:
            await asyncio.sleep(0.01)
    assert runtime.process.pid != first.pid
    await runtime.stop()


async def test_authentication_failure_stops_process_and_requests_reauth(bridge_executable, tmp_path):
    runtime = managed(bridge_executable, tmp_path / "runtime", auth=True)
    with pytest.raises(BridgeAuthenticationError):
        await runtime.start()
    assert runtime.process is None
    assert runtime.task is None
    runtime.on_auth_required.assert_called_once()


async def test_cancelled_start_does_not_leave_a_process(bridge_executable, tmp_path):
    runtime = managed(bridge_executable, tmp_path / "runtime", stall=True)
    task = asyncio.create_task(runtime.start())
    async with asyncio.timeout(3):
        while runtime.process is None:
            await asyncio.sleep(0.01)
    process = runtime.process
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.returncode is not None
    assert runtime.task is None


def test_untrusted_status_does_not_change_readiness(tmp_path):
    runtime = managed(tmp_path / "none", tmp_path)
    runtime._handle_event({"event": "ready", "source_port": 1234, "cameras": []})
    assert not runtime.ready
    runtime._handle_event({"event": "ready", "source_port": 1234,
                           "cameras": [{"camera_id": "one", "path": "/camera", "hevc": True}]})
    runtime._handle_event({"event": "camera_status", "camera_id": "one", "state": "video", "sid": "secret"})
    status = runtime.camera_status["one"]
    assert status["last_video"] is not None
    assert "sid" not in json.dumps(status)
