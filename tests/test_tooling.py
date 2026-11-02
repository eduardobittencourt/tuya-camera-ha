"""Keep public validation tooling inside its intended trust boundaries."""
import asyncio
import hashlib
import json
import tomllib
import zipfile
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiohttp import web
from aioice import Candidate, stun
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


def test_public_repository_and_generated_package(tmp_path, monkeypatch):
    manifest = check_repository.check_repository()
    output = tmp_path / "dist"
    with patch("sys.argv", ["package_release", "--output", str(output)]):
        package_release.main()
    for name in ("LICENSE", "NOTICE"):
        (tmp_path / name).write_bytes((check_repository.ROOT / name).read_bytes())
    monkeypatch.setattr(check_repository, "ROOT", tmp_path)
    check_repository.check_archive(output / "tuya_camera.zip", manifest)


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
    with patch.object(webrtc_probe, "ProbePeer") as peer, pytest.raises(ValueError):
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
        offer = webrtc_probe.SessionDescription.parse(await request.text())
        candidates = [c for media in offer.media for c in media.ice_candidates]
        assert candidates
        assert all(c.ip == "127.0.0.1" for c in candidates)
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


@pytest.mark.parametrize("host", ["127.0.0.1", "192.0.2.10", "169.254.169.254", "::1"])
async def test_probe_restricts_authenticated_peer_reflexive_learning(host):
    """Offer credentials do not authorize external STUN replies or triggered checks."""
    connection = webrtc_probe.LoopbackConnection(ice_controlling=False)
    connection.remote_username = "synthetic-peer"
    connection._early_checks_done = True
    protocol = Mock()
    protocol.local_candidate = Candidate("local", 1, "udp", 1, "127.0.0.1", 12345, "host")
    message = stun.Message(stun.Method.BINDING, stun.Class.REQUEST, attributes={
        "USERNAME": f"{connection.local_username}:synthetic-peer", "PRIORITY": 1,
        "ICE-CONTROLLING": 1,
    })
    message.add_message_integrity(connection.local_password.encode())
    raw = bytes(message)
    # Prove this is authenticated input, rather than a packet rejected as corrupt.
    stun.parse_message(raw, integrity_key=connection.local_password.encode())
    try:
        with patch.object(connection, "check_start_task") as check:
            connection.request_received(message, (host, 23456), protocol, raw)
        if host == "127.0.0.1":
            protocol.send_stun.assert_called_once()
            check.assert_called_once()
            assert len(connection.remote_candidates) == 1
            assert connection.remote_candidates[0].host == host
            assert connection.remote_candidates[0].type == "prflx"
        else:
            protocol.send_stun.assert_not_called()
            check.assert_not_called()
            assert not connection.remote_candidates
            assert not connection._early_checks
    finally:
        await connection.close()


def test_probe_restores_ice_factory_if_transceiver_creation_fails():
    """The private factory hook is confined to synchronous test-peer construction."""
    original = webrtc_probe.rtcicetransport.Connection
    peer = Mock()
    peer.addTransceiver.side_effect = RuntimeError("synthetic failure")
    with pytest.raises(RuntimeError, match="synthetic failure"):
        webrtc_probe.add_receivers(peer)
    assert webrtc_probe.rtcicetransport.Connection is original


@pytest.mark.parametrize("member", ["../outside", "/absolute", "directory/../../outside", "directory\\outside"])
def test_archive_rejects_unsafe_members_without_extracting_files(tmp_path, monkeypatch, member):
    component = tmp_path / "component"
    component.mkdir()
    monkeypatch.setattr(check_repository, "COMPONENT", component)
    for name in ("LICENSE", "NOTICE"):
        (tmp_path / name).write_text(name)
    monkeypatch.setattr(check_repository, "ROOT", tmp_path)
    output = tmp_path / "dist"
    output.mkdir()
    archive = output / "tuya_camera.zip"
    with zipfile.ZipFile(archive, "w") as candidate:
        candidate.writestr(member, "untrusted")
    with pytest.raises(SystemExit, match="Unsafe archive path"):
        check_repository.check_archive(archive, {})
    assert not (tmp_path / "outside").exists()


@pytest.fixture
def reviewed_archive(tmp_path, monkeypatch):
    """Create a small reviewed tree and its release ZIP inside the allowed directory."""
    component = tmp_path / "component"
    component.mkdir()
    manifest = {"version": "0.4.0"}
    (component / "manifest.json").write_text(json.dumps(manifest))
    for name in ("LICENSE", "NOTICE"):
        (tmp_path / name).write_text(name)
    monkeypatch.setattr(check_repository, "ROOT", tmp_path)
    monkeypatch.setattr(check_repository, "COMPONENT", component)
    output = tmp_path / "dist"
    output.mkdir()
    archive = output / "tuya_camera.zip"
    with zipfile.ZipFile(archive, "w") as candidate:
        for path in (component / "manifest.json", tmp_path / "LICENSE", tmp_path / "NOTICE"):
            candidate.write(path, path.name)
    checksum = output / "SHA256SUMS"
    checksum.write_text(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n")
    return archive, manifest, component


def test_archive_verifies_exact_files_and_checksum(reviewed_archive):
    """Reject changed bytes even when filenames and uncompressed sizes match."""
    archive, manifest, component = reviewed_archive
    checksum = archive.parent / "SHA256SUMS"
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
    output = tmp_path / "dist"
    output.mkdir()
    archive = output / "tuya_camera.zip"
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
    for name in ("LICENSE", "NOTICE"):
        (tmp_path / name).write_text(name)
    monkeypatch.setattr(check_repository, "ROOT", tmp_path)
    output = tmp_path / "dist"
    output.mkdir()
    archive = output / "tuya_camera.zip"
    archive.write_bytes(b"x" * 2_000_000)
    with pytest.raises(SystemExit, match="release size limit"):
        check_repository.check_archive(archive, {})


@pytest.mark.parametrize("kind", ["outside", "archive_symlink", "directory_symlink"])
def test_archive_rejects_paths_outside_release_directory(tmp_path, monkeypatch, kind):
    """CLI paths and symlinks cannot select an input outside the release artifact."""
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.zip"
    outside.write_bytes(b"untrusted input")
    monkeypatch.setattr(check_repository, "ROOT", root)
    output = root / "dist"
    if kind == "directory_symlink":
        output.symlink_to(tmp_path, target_is_directory=True)
        archive = output / "tuya_camera.zip"
    else:
        output.mkdir()
        if kind == "archive_symlink":
            archive = output / "tuya_camera.zip"
            archive.symlink_to(outside)
        else:
            archive = outside
    with pytest.raises(SystemExit, match=r"symlink|repository's dist"):
        check_repository.check_archive(archive, {})
    assert outside.read_bytes() == b"untrusted input"


def test_archive_rejects_checksum_symlink_outside_release_directory(reviewed_archive, tmp_path):
    """The adjacent checksum cannot redirect reads to another local file."""
    archive, manifest, _ = reviewed_archive
    outside = tmp_path / "outside"
    outside.write_bytes(b"untrusted checksum")
    checksum = archive.parent / "SHA256SUMS"
    checksum.unlink()
    checksum.symlink_to(outside)
    with pytest.raises(SystemExit, match="checksum must not be a symlink"):
        check_repository.check_archive(archive, manifest)
    assert outside.read_bytes() == b"untrusted checksum"


@pytest.mark.parametrize("name", ["tuya_camera.zip", "SHA256SUMS"])
def test_archive_inputs_must_be_regular_files(reviewed_archive, name):
    """Reject directories at either input path instead of treating them as files."""
    archive, manifest, _ = reviewed_archive
    target = archive.parent / name
    target.unlink()
    target.mkdir()
    with pytest.raises(SystemExit, match="regular file"):
        check_repository.check_archive(archive, manifest)
