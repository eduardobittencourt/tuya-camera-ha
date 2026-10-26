#!/usr/bin/env python3
"""Check public documentation, branding and the actual HACS release payload."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import tomllib
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "tuya_camera_bridge"
REQUIRED = (
    "README.md", "LICENSE", "NOTICE", "SECURITY.md", "SUPPORT.md", "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md", ".github/CODEOWNERS", ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/config.yml", ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/compatibility_report.yml", ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/workflows/validate.yml", "docs/README.pt-BR.md", "docs/installation.md",
    "docs/compatibility.md", "docs/troubleshooting.md", "docs/architecture.md",
    "docs/development.md", "docs/releasing.md", "docs/validation-0.3.0b1.md",
    "docs/validation-0.3.1.md",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def check_repository() -> dict:
    for name in REQUIRED:
        require((ROOT / name).is_file(), f"Missing public file: {name}")
    documents = [ROOT / name for name in REQUIRED if name.endswith(".md")]
    documents.append(COMPONENT / "BRAND_ASSETS.md")
    for path in documents:
        text = path.read_text()
        links = re.findall(r"\]\(([^\s)]+)(?:\s+[^)]*)?\)", text)
        links.extend(re.findall(r'<img\b[^>]*\bsrc="([^"]+)"', text))
        for link in links:
            url = urlsplit(link.strip("<>"))
            if url.scheme or url.netloc or not url.path:
                continue
            target = (path.parent / unquote(url.path)).resolve()
            require(target.is_relative_to(ROOT) and target.exists(),
                    f"Broken relative link in {path.relative_to(ROOT)}: {link}")
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    hacs = json.loads((ROOT / "hacs.json").read_text())
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    require(manifest["version"] == project["version"], "Release versions differ")
    require(f'VERSION = "{manifest["version"]}"' in (COMPONENT / "__init__.py").read_text(),
            "Runtime version differs from manifest")
    integrations = [p for p in (ROOT / "custom_components").iterdir() if (p / "manifest.json").exists()]
    require(integrations == [COMPONENT], "HACS repository must contain exactly one integration")
    require(not (ROOT / "bridge").exists(), "The integration must own all camera protocols in Python")
    require(not (ROOT / "repository.yaml").exists()
            and not (ROOT / "tuya-camera-bridge-addon").exists(),
            "Standalone add-on assets must not return to this integration-only repository")
    # hacs/default scans *manifest.json across the clone before running hassfest.
    # Keep auxiliary JSON names outside that glob to avoid ambiguous discovery.
    catalog_manifests = list((ROOT / "custom_components").rglob("*manifest.json"))
    require(catalog_manifests == [COMPONENT / "manifest.json"],
            "HACS catalog discovery must find only the integration manifest")
    require(manifest["domain"] == COMPONENT.name, "Integration domain differs from its directory")
    require(hacs["zip_release"] and hacs["filename"] == "tuya_camera_bridge.zip",
            "HACS release ZIP configuration is incorrect")
    require(hacs["hide_default_branch"], "Development branch must not bypass release assets")
    require(manifest["codeowners"] and manifest["issue_tracker"] and manifest["documentation"],
            "Missing integration support metadata")
    for name, expected in {"icon.png": (256, 256), "icon@2x.png": (512, 512),
                           "logo.png": (512, 256), "logo@2x.png": (1023, 512)}.items():
        data = (COMPONENT / "brand" / name).read_bytes()
        require(data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR", f"Invalid PNG: {name}")
        require(struct.unpack(">II", data[16:24]) == expected, f"Unexpected brand dimensions: {name}")
    return manifest


def check_archive(path: Path, manifest: dict) -> None:
    expected = {
        p.relative_to(COMPONENT).as_posix(): p
        for p in COMPONENT.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }
    expected.update({name: ROOT / name for name in ("LICENSE", "NOTICE")})
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "Archive has duplicate entries")
        for name in names:
            member = PurePosixPath(name)
            require(not member.is_absolute() and ".." not in member.parts and "\\" not in name,
                    f"Unsafe archive path: {name}")
        require(set(names) == set(expected), "Archive files differ from the reviewed integration")
        for name, source in expected.items():
            require(archive.read(name) == source.read_bytes(), f"Archive content differs: {name}")
        require(json.loads(archive.read("manifest.json")) == manifest, "Archive manifest differs")
    sums = f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
    require((path.parent / "SHA256SUMS").read_text() == sums, "Published archive checksum differs")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    manifest = check_repository()
    if args.archive:
        check_archive(args.archive, manifest)
    print(f"Public repository checks passed for {manifest['version']}"
          + ("; Python HACS ZIP verified" if args.archive else ""))


if __name__ == "__main__":
    main()
