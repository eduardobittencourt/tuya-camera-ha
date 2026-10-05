"""Install a pinned, checksum-verified bridge without system package changes."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
from pathlib import Path
from tempfile import NamedTemporaryFile

import aiohttp

RELEASE_BASE = "https://github.com/eduardobittencourt/tuya-camera-ha/releases/download"
MAX_BINARY_SIZE = 64 * 1024 * 1024


class BinaryError(RuntimeError):
    """The managed bridge could not be installed safely."""


def architecture() -> str:
    if platform.system() != "Linux":
        raise BinaryError("The managed bridge currently supports Linux installations")
    machine = platform.machine().lower()
    try:
        return {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}[machine]
    except KeyError as err:
        raise BinaryError("The managed bridge supports amd64 and aarch64") from err


def manifest() -> dict:
    return json.loads(Path(__file__).with_name("binary_manifest.json").read_text())


def valid_binary(path: Path, expected: str) -> bool:
    try:
        with path.open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                return False
            stream.seek(0)
            return hashlib.file_digest(stream, "sha256").hexdigest() == expected
    except OSError:
        return False


def install_binary(path: Path, content: bytes, expected: str) -> None:
    if not content.startswith(b"\x7fELF") or hashlib.sha256(content).hexdigest() != expected:
        raise BinaryError("Bridge download failed checksum verification")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile("wb", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            os.fchmod(stream.fileno(), 0o700)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


async def ensure_binary(session: aiohttp.ClientSession, directory: Path) -> Path:
    info = await asyncio.to_thread(manifest)
    arch = architecture()
    version = info["version"]
    asset = f"tuya-camera-bridge-linux-{arch}"
    expected = info["sha256"][asset]
    path = directory / f"bridge-{version}-{arch}"
    if await asyncio.to_thread(valid_binary, path, expected):
        await asyncio.to_thread(path.chmod, 0o700)
        return path
    try:
        async with session.get(
            f"{RELEASE_BASE}/v{version}/{asset}", timeout=aiohttp.ClientTimeout(total=120)
        ) as response:
            response.raise_for_status()
            content = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                content.extend(chunk)
                if len(content) > MAX_BINARY_SIZE:
                    raise BinaryError("Bridge download exceeds the maximum size")
    except (aiohttp.ClientError, TimeoutError) as err:
        raise BinaryError("Unable to download the bridge; check internet access and the installed release") from err
    await asyncio.to_thread(install_binary, path, bytes(content), expected)
    return path
