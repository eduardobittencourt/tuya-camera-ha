"""Owned FFmpeg process groups must not outlive a cancelled shutdown."""
import asyncio
import os
import signal
import sys

import pytest

from custom_components.tuya_camera_bridge.process import stop_process


async def test_cancelled_stop_kills_and_reaps_process_ignoring_sigterm():
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c",
        "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('ready',flush=True); time.sleep(60)",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, start_new_session=True,
    )
    try:
        assert await asyncio.wait_for(process.stdout.readline(), 3) == b"ready\n"
        stopping = asyncio.create_task(stop_process(process))
        await asyncio.sleep(.02)
        stopping.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(stopping, 3)
        assert process.returncode == -signal.SIGKILL
    finally:
        if process.returncode is None:
            os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
