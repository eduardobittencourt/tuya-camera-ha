"""Keep public validation tooling inside its intended trust boundaries."""
import hashlib
import json
import tomllib
import zipfile
from unittest.mock import patch

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


@pytest.mark.parametrize("endpoint", [
    "http://192.168.0.2:1984/api/webrtc",
    "http://169.254.169.254:80/latest/meta-data",
    "http://localhost:1984/api/webrtc",
    "https://127.0.0.1:1984/api/webrtc",
    "http://127.0.0.1/api/webrtc",
    "http://user:password@127.0.0.1:1984/api/webrtc",
    "http://127.0.0.1:1984/api/webrtc#fragment",
])
async def test_synthetic_probe_rejects_external_endpoints_before_creating_peer(endpoint):
    with patch.object(webrtc_probe, "RTCPeerConnection") as peer, pytest.raises(ValueError):
        await webrtc_probe.run(endpoint)
    peer.assert_not_called()


async def test_synthetic_probe_does_not_follow_redirects(aiohttp_server, socket_enabled):
    followed = []

    async def redirect(_request):
        raise web.HTTPFound("/unexpected")

    async def unexpected(_request):
        followed.append(True)
        return web.Response(text="must not be contacted")

    app = web.Application()
    app.router.add_post("/redirect", redirect)
    app.router.add_get("/unexpected", unexpected)
    server = await aiohttp_server(app, host="127.0.0.1")
    with pytest.raises(ValueError, match="redirect"):
        await webrtc_probe.run(str(server.make_url("/redirect")))
    assert not followed


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
    (component / "manifest.json").write_text("{}")
    with pytest.raises(SystemExit, match="content differs"):
        check_repository.check_archive(archive, manifest)
