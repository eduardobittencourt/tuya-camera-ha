import hashlib
from unittest.mock import AsyncMock

import pytest

from custom_components.tuya_camera_bridge import binary


def test_install_rejects_tampering_without_replacing_existing_binary(tmp_path):
    path = tmp_path / "bridge"
    good = b"\x7fELFverified-binary"
    digest = hashlib.sha256(good).hexdigest()
    binary.install_binary(path, good, digest)
    with pytest.raises(binary.BinaryError):
        binary.install_binary(path, b"\x7fELFtampered", digest)
    assert path.read_bytes() == good
    assert path.stat().st_mode & 0o777 == 0o700
    assert list(tmp_path.iterdir()) == [path]


async def test_verified_cached_binary_works_without_internet(tmp_path, monkeypatch):
    good = b"\x7fELFverified-binary"
    digest = hashlib.sha256(good).hexdigest()
    monkeypatch.setattr(binary, "manifest", lambda: {
        "version": "test", "sha256": {"tuya-camera-bridge-linux-amd64": digest},
    })
    monkeypatch.setattr(binary, "architecture", lambda: "amd64")
    path = tmp_path / "bridge-test-amd64"
    binary.install_binary(path, good, digest)
    session = AsyncMock()
    assert await binary.ensure_binary(session, tmp_path) == path
    session.get.assert_not_called()


def test_unsupported_architecture_is_explicit(monkeypatch):
    monkeypatch.setattr(binary.platform, "system", lambda: "Linux")
    monkeypatch.setattr(binary.platform, "machine", lambda: "armv7l")
    with pytest.raises(binary.BinaryError, match="amd64 and aarch64"):
        binary.architecture()


async def test_download_is_verified_and_installed_atomically(tmp_path, monkeypatch, aioclient_mock, hass):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
    good = b"\x7fELFdownloaded-binary"
    digest = hashlib.sha256(good).hexdigest()
    monkeypatch.setattr(binary, "manifest", lambda: {
        "version": "test", "sha256": {"tuya-camera-bridge-linux-amd64": digest},
    })
    monkeypatch.setattr(binary, "architecture", lambda: "amd64")
    url = f"{binary.RELEASE_BASE}/vtest/tuya-camera-bridge-linux-amd64"
    aioclient_mock.get(url, content=good)
    result = await binary.ensure_binary(async_get_clientsession(hass), tmp_path)
    assert binary.valid_binary(result, digest)
    assert aioclient_mock.call_count == 1


async def test_download_checksum_failure_leaves_no_executable(tmp_path, monkeypatch, aioclient_mock, hass):
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
    monkeypatch.setattr(binary, "manifest", lambda: {
        "version": "test", "sha256": {"tuya-camera-bridge-linux-amd64": "0" * 64},
    })
    monkeypatch.setattr(binary, "architecture", lambda: "amd64")
    aioclient_mock.get(f"{binary.RELEASE_BASE}/vtest/tuya-camera-bridge-linux-amd64", content=b"\x7fELFbad")
    with pytest.raises(binary.BinaryError, match="checksum"):
        await binary.ensure_binary(async_get_clientsession(hass), tmp_path)
    assert not list(tmp_path.iterdir())
