#!/usr/bin/env python3
"""Build a deterministic, Python-only HACS archive and its checksum."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "tuya_camera_bridge"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    version = json.loads((COMPONENT / "manifest.json").read_text())["version"]
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "tuya_camera_bridge.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        files = {
            path.relative_to(COMPONENT).as_posix(): path
            for path in COMPONENT.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        }
        files.update({name: ROOT / name for name in ("LICENSE", "NOTICE")})
        for relative, path in sorted(files.items()):
            zip_info = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
            zip_info.compress_type = zipfile.ZIP_DEFLATED
            zip_info.external_attr = 0o644 << 16
            archive.writestr(zip_info, path.read_bytes())
    (args.output / "SHA256SUMS").write_text(f"{hashlib.sha256(target.read_bytes()).hexdigest()}  {target.name}\n")
    print(f"Prepared v{version}: Python HACS archive and checksum")


if __name__ == "__main__":
    main()
