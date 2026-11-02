"""Keep public validation tooling inside its intended trust boundaries."""
import asyncio
import hashlib
import json
import tomllib
import zipfile
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web
from packaging.requirements import Requirement

from scripts import check_repository, package_release, webrtc_probe


def test_locked_dependencies_match_declared_test_extra():
    root = check_repository.ROOT
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    locked = {}
    for line in (root / "requirements-test.txt").read_text().splitlines():
        if not line or line.startswith(("#", " ")):
            continue
        requirement = Requirement(line.removesuffix("\\").strip())
        locked[requirement.name.lower()] = requirement
    for declared in project["optional-dependencies"]["test"]:
        requirement = Requirement(declared)
        candidate = locked[requirement.name.lower()]
        if requirement.url:
            assert candidate.url == requirement.url
        else:
            version = next(iter(candidate.specifier)).version
            assert requirement.specifier.contains(version)


def test_public_repository_and_generated_package(tmp_path):
    manifest = check_repository.check_repository()
    with patch("sys.argv", ["package_release", "--output", str(tmp_path)]):
        package_release.main()
    check_repository.check_archive(tmp_path / "tuya_camera.zip", manifest)


@pytest.mark.parametrize("port", [
    0, -1, 65536, True, "1984",
    "http://192.168.0.2:1984/api/webrtc",
    "http://169.254.169.254:80/latest/meta-data",
    "http://localhost:1984/api/webrtc",
    "https://127.0.0.1:1984/api/webrtc",
    "http://127.0.0.1/api/webrtc",
    "http://user:password@127.0.0.1:1984/api/webrtc",
    "http://127.0.0.1:1984/api/webrtc#fragment",
])
async def test_synthetic_probe_rejects_invalid_ports_before_creating_peer(port):
    """Invalid input must not allocate a peer or reach the network."""
    with patch.object(webrtc_probe, "RTCPeerConnection") as peer, pytest.raises(ValueError):
        await webrtc_probe.run(port)
    peer.assert_not_called()


async def test_synthetic_probe_does_not_follow_redirects(aiohttp_server, socket_enabled):
    """A local response cannot redirect the SDP offer to another destination."""
    followed = []

    async def redirect(_request):
        raise web.HTTPFound("/unexpected")

    async def unexpected(_request):
        followed.append(True)
        return web.Response(text="must not be contacted")

    app = web.Application()
    app.router.add_post("/api/webrtc", redirect)
    app.router.add_get("/unexpected", unexpected)
    server = await aiohttp_server(app, host="127.0.0.1")
    with pytest.raises(ValueError, match="redirect"):
        await webrtc_probe.run(server.port)
    assert not followed


def synthetic_answer(host, related=""):
    """Build a minimal answer exposing only the candidate trust boundary."""
    return ("v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\n"
            "m=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"
            f"a=candidate:1 1 UDP 2130706431 {host} 12345 typ host{related}\r\n")


@pytest.mark.parametrize("host,related", [
    ("192.168.0.2", ""), ("169.254.169.254", ""), ("example.local", ""), ("::1", ""),
    ("127.0.0.1", " raddr 192.168.0.2 rport 12345"),
])
async def test_probe_rejects_remote_ice_before_setting_answer(host, related, aiohttp_server, socket_enabled):
    """A local HTTP server must not cause external ICE checks or mDNS lookup."""
    async def answer(request):
        assert request.query == {"src": "camera"}
        return web.Response(text=synthetic_answer(host, related))

    app = web.Application()
    app.router.add_post("/api/webrtc", answer)
    server = await aiohttp_server(app, host="127.0.0.1")
    with patch.object(webrtc_probe.RTCPeerConnection, "setRemoteDescription", new_callable=AsyncMock) as remote, \
         pytest.raises(ValueError, match="loopback ICE"):
        await webrtc_probe.run(server.port)
    remote.assert_not_awaited()


async def test_probe_bounds_answer_size(aiohttp_server, socket_enabled, monkeypatch):
    """An oversized answer is rejected before SDP parsing or peer negotiation."""
    monkeypatch.setattr(webrtc_probe, "MAX_ANSWER_SIZE", 100)

    async def answer(_request):
        return web.Response(body=b"x" * 101)

    app = web.Application()
    app.router.add_post("/api/webrtc", answer)
    server = await aiohttp_server(app, host="127.0.0.1")
    with pytest.raises(ValueError, match="size limit"):
        await webrtc_probe.run(server.port)


async def test_probe_reads_fragmented_answer_to_eof(aiohttp_server, socket_enabled):
    """A legitimate local answer remains intact when split across HTTP chunks."""
    sdp = synthetic_answer("127.0.0.1")

    async def answer(request):
        response = web.StreamResponse()
        await response.prepare(request)
        await response.write(sdp[:20].encode())
        await asyncio.sleep(.01)
        await response.write(sdp[20:].encode())
        return response

    app = web.Application()
    app.router.add_post("/api/webrtc", answer)
    server = await aiohttp_server(app, host="127.0.0.1")
    with patch.object(webrtc_probe.RTCPeerConnection, "setRemoteDescription", new_callable=AsyncMock,
                      side_effect=ValueError("answer received")) as remote, \
         pytest.raises(ValueError, match="answer received"):
        await webrtc_probe.run(server.port)
    remote.assert_awaited_once_with(webrtc_probe.RTCSessionDescription(sdp=sdp, type="answer"))


@pytest.mark.parametrize("member", ["../outside", "/absolute", "directory/../../outside", "directory\\outside"])
def test_archive_rejects_unsafe_members_without_extracting_files(tmp_path, monkeypatch, member):
    component = tmp_path / "component"
    component.mkdir()
    monkeypatch.setattr(check_repository, "COMPONENT", component)
    archive = tmp_path / "candidate.zip"
    with zipfile.ZipFile(archive, "w") as candidate:
        candidate.writestr(member, "untrusted")
    with pytest.raises(SystemExit, match="Unsafe archive path"):
        check_repository.check_archive(archive, {})
    assert not (tmp_path / "outside").exists()


def test_archive_verifies_exact_files_and_checksum(tmp_path, monkeypatch):
    """Reject changed bytes even when filenames and uncompressed sizes match."""
    component = tmp_path / "component"
    component.mkdir()
    manifest = {"version": "0.4.0"}
    (component / "manifest.json").write_text(json.dumps(manifest))
    for name in ("LICENSE", "NOTICE"):
        (tmp_path / name).write_text(name)
    monkeypatch.setattr(check_repository, "ROOT", tmp_path)
    monkeypatch.setattr(check_repository, "COMPONENT", component)
    archive = tmp_path / "candidate.zip"
    with zipfile.ZipFile(archive, "w") as candidate:
        for path in (component / "manifest.json", tmp_path / "LICENSE", tmp_path / "NOTICE"):
            candidate.write(path, path.name)
    checksum = tmp_path / "SHA256SUMS"
    checksum.write_text(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n")
    check_repository.check_archive(archive, manifest)
    checksum.write_text("incorrect\n")
    with pytest.raises(SystemExit, match="checksum differs"):
        check_repository.check_archive(archive, manifest)
    (component / "manifest.json").write_text(json.dumps({"version": "0.4.1"}))
    with pytest.raises(SystemExit, match="content differs"):
        check_repository.check_archive(archive, manifest)


def test_archive_rejects_compressed_bomb_before_reading_members(tmp_path, monkeypatch):
    """A tiny ZIP with the exact filenames cannot expand beyond reviewed sizes."""
    component = tmp_path / "component"
    component.mkdir()
    (component / "manifest.json").write_text("{}")
    for name in ("LICENSE", "NOTICE"):
        (tmp_path / name).write_text(name)
    monkeypatch.setattr(check_repository, "ROOT", tmp_path)
    monkeypatch.setattr(check_repository, "COMPONENT", component)
    archive = tmp_path / "candidate.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as candidate:
        candidate.writestr("manifest.json", b"x" * 1_000_000)
        for name in ("LICENSE", "NOTICE"):
            candidate.write(tmp_path / name, name)
    assert archive.stat().st_size < 4096
    with pytest.raises(SystemExit, match="member size differs"):
        check_repository.check_archive(archive, {})


def test_archive_rejects_oversized_container_before_zip_parsing(tmp_path, monkeypatch):
    """Reject excessive ZIP metadata or padding before the directory is loaded."""
    component = tmp_path / "component"
    component.mkdir()
    monkeypatch.setattr(check_repository, "COMPONENT", component)
    archive = tmp_path / "candidate.zip"
    archive.write_bytes(b"x" * 2_000_000)
    with pytest.raises(SystemExit, match="release size limit"):
        check_repository.check_archive(archive, {})
