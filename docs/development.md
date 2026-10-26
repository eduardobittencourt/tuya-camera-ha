# Development

Use Python 3.14 and Go 1.26.8. The Home Assistant test version and its matching
pytest plugin are pinned together in `pyproject.toml`. Work from the
repository root and read [AGENTS.md](../AGENTS.md) before changing code.

```sh
python3.14 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
ruff check custom_components tests scripts
python scripts/check_repository.py
node --test tests/test_dependency_automation.cjs
pytest -m 'not media'
```

For the managed Go bridge:

```sh
cd bridge
gofmt -l .
go test -race ./...
cd ..
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
mkdir -p "$HOME/research/tuya-camera-ha/media-validation/tools"
cd bridge
go build -o "$HOME/research/tuya-camera-ha/media-validation/tools/webrtc-probe" ./internal/testmedia/webrtc
cd ..
TEST_FFMPEG_BINARY=/usr/bin/ffmpeg \
TEST_MEDIAMTX_BINARY=/path/to/mediamtx \
TEST_GO2RTC_BINARY=/path/to/go2rtc \
TEST_WEBRTC_PROBE="$HOME/research/tuya-camera-ha/media-validation/tools/webrtc-probe" \
pytest -m media --timeout=120
```

Run pytest from the repository root. Keep downloaded tools and investigation
artifacts under `~/research/tuya-camera-ha/`, outside the release payload.

The [CI workflow](../.github/workflows/ci.yml) shows exact downloads and checksums.
Its media job uses the checksum-pinned Linux x86_64 `imageio-ffmpeg` wheel in
[`requirements-media.txt`](../requirements-media.txt), which bundles FFmpeg 7.0.2.
This avoids an APT update/install on each runner. It is test tooling only;
the integration continues to use Home Assistant's FFmpeg. Python downloads are
cached, external media-tool downloads have bounded retries, and the media job
has a ten-minute limit, including setup. Both codec cases still exercise actual
FFmpeg, HLS, WebRTC, audio, snapshots and source loss on every PR.

CI runs on pull requests and pushes to `main`, avoiding duplicate branch-push
and PR runs. New commits cancel superseded runs for the same PR. Maintainers
can also run CI manually on a branch before opening a PR.
Build artifacts expire after seven days to limit retained CI storage.

It also scans secrets. The separate
[validation workflow](../.github/workflows/validate.yml) runs official hassfest
and HACS validators without skipped checks on pushes, pull requests, daily and
on demand, so upstream validation changes are detected between releases.

Never record private account sessions or media fixtures in the repository.
Real-camera validation belongs in a sanitized [compatibility report](compatibility.md).
