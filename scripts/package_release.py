#!/usr/bin/env python3
"""Build deterministic bridge assets and a HACS zip; never include runtime data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "tuya_camera_bridge"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--go", default="go")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--verify", action="store_true", help="Fail if tracked checksums do not match")
    args = parser.parse_args()
    version = json.loads((COMPONENT / "manifest.json").read_text())["version"]
    args.output.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for arch in ("amd64", "arm64"):
        name = f"tuya-camera-bridge-linux-{arch}"
        target = args.output / name
        subprocess.run([
            args.go, "build", "-buildvcs=false", "-trimpath", "-ldflags",
            f"-s -w -buildid= -X main.VERSION={version}", "-o", str(target), ".",
        ], cwd=ROOT / "tuya-camera-bridge-addon" / "bridge",
            env={**os.environ, "GOOS": "linux", "GOARCH": arch, "CGO_ENABLED": "0"}, check=True)
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    info = {"version": version, "sha256": hashes}
    manifest_path = COMPONENT / "binary_manifest.json"
    if args.verify:
        if json.loads(manifest_path.read_text()) != info:
            raise SystemExit("Bridge binaries differ from the pinned manifest; rebuild with Go 1.26.8")
    else:
        manifest_path.write_text(json.dumps(info, indent=2) + "\n")
    with zipfile.ZipFile(args.output / "tuya_camera_bridge.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(COMPONENT.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                relative = path.relative_to(COMPONENT).as_posix()
                zip_info = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
                zip_info.compress_type = zipfile.ZIP_DEFLATED
                zip_info.external_attr = 0o644 << 16
                archive.writestr(zip_info, path.read_bytes())
    (args.output / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in hashes.items()))
    print(f"Prepared v{version}: amd64, arm64, checksum manifest and HACS zip")


if __name__ == "__main__":
    main()
