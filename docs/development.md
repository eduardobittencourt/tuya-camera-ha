# Development

Use Python 3.14 and Go 1.26.8. Tests pin Home Assistant 2026.9.4. Work from the
repository root and read [AGENTS.md](../AGENTS.md) before changing code.

```sh
python3.14 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
ruff check custom_components tuya-camera-bridge-addon/app tests scripts
python scripts/check_repository.py
pytest -m 'not media'
```

For the shared Go bridge:

```sh
cd tuya-camera-bridge-addon/bridge
gofmt -l .
go test -race ./...
cd ../..
python scripts/package_release.py --verify
python scripts/check_repository.py --archive dist/tuya_camera_bridge.zip
```

`--verify` rejects binaries that do not match the tracked manifest. After an
intentional Go change, build without `--verify` using the pinned toolchain,
review the manifest change and then verify again. Do not commit `dist/`.

## Real media tests without an account

The `media` tests use a synthetic camera and actual FFmpeg, MediaMTX, go2rtc and
a Go WebRTC receiver. They exercise H.264/H.265 video, audio, HLS, WebRTC, fresh
snapshots and source loss. No Tuya credentials are required.

Install FFmpeg, MediaMTX 1.21.1 and go2rtc 1.9.14, and build the receiver:

```sh
cd tuya-camera-bridge-addon/bridge
go build -o /tmp/webrtc-probe ./internal/testmedia/webrtc
cd ../..
TEST_FFMPEG_BINARY=/usr/bin/ffmpeg \
TEST_MEDIAMTX_BINARY=/path/to/mediamtx \
TEST_GO2RTC_BINARY=/path/to/go2rtc \
TEST_WEBRTC_PROBE=/tmp/webrtc-probe \
pytest -m media --timeout=120
```

The [CI workflow](../.github/workflows/ci.yml) shows exact downloads and checksums.
It also scans secrets and builds the legacy add-on container. The separate
[validation workflow](../.github/workflows/validate.yml) runs official hassfest
and HACS validators without skipped checks.

Never record private account sessions or media fixtures in the repository.
Real-camera validation belongs in a sanitized [compatibility report](compatibility.md).
