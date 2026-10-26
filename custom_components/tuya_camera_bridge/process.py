"""Terminate owned FFmpeg process groups during cancellation and unload."""
from __future__ import annotations

import asyncio
import os
import signal
from contextlib import suppress

STOP_TIMEOUT = 10.0


async def stop_process(process: asyncio.subprocess.Process) -> None:
    """Terminate the whole process group and reap it, including partial startup."""
    if process.returncode is not None:
        return
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)

    async def drain(stream: asyncio.StreamReader | None) -> None:
        if stream is not None:
            # An existing monitor/communicate task may already own this reader.
            with suppress(RuntimeError):
                while await stream.read(65536):
                    pass

    drains = [asyncio.create_task(drain(stream)) for stream in (process.stdout, process.stderr)]
    try:
        try:
            await asyncio.wait_for(process.wait(), STOP_TIMEOUT)
        except asyncio.CancelledError:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
            raise
        except TimeoutError:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
    finally:
        for task in drains:
            task.cancel()
        await asyncio.gather(*drains, return_exceptions=True)
