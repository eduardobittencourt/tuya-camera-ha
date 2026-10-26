# Development

Use Python 3.14. Install the test dependencies from `pyproject.toml`; its Home
Assistant and pytest plugin pins must be updated together. No Go toolchain is
required. Read [AGENTS.md](../AGENTS.md) before changing protocol code.

```sh
uv venv --python 3.14
uv pip install '.[test]'
.venv/bin/ruff check custom_components tests scripts
.venv/bin/pytest -m 'not media'
.venv/bin/python scripts/package_release.py
.venv/bin/python scripts/check_repository.py --archive dist/tuya_camera_bridge.zip
node --test tests/test_release_gate.cjs
```

## Protocol and media validation

`test_python_transport.py` exercises signal framing, AES padding/corruption,
KCP wire vectors, loss, duplication, reordering, retransmission and limits.
`test_python_runtime.py` checks session sharing and cleanup. The synthetic peers
in `test_python_webrtc.py` test H.264 RTP and Tuya H.265/datachannel negotiation.
The aiortc raw RTP hook is version-sensitive and must be tested on upgrades.

The `media` tests use real FFmpeg and synthetic pictures/audio. One test runs a
synthetic Tuya TCP/UDP camera through encrypted AES/KCP, the Python RTSP server
and FFmpeg, checks JPEG/video/audio and confirms a shared-socket DP command.
The existing codec tests cover H.264/H.265, HLS, WebRTC and source loss using
MediaMTX 1.21.1 and go2rtc 1.9.14 as test tools. The WebRTC receiver is Python.

```sh
TEST_FFMPEG_BINARY=/usr/bin/ffmpeg \
TEST_MEDIAMTX_BINARY=/path/to/mediamtx \
TEST_GO2RTC_BINARY=/path/to/go2rtc \
TEST_WEBRTC_PROBE=scripts/webrtc_probe.py \
.venv/bin/pytest -m media --timeout=120
```

Activate `.venv` when using the executable probe so its Python dependencies
are found. Research/tools belong under `~/research/tuya-camera-ha/`, outside
release payloads. The [CI workflow](../.github/workflows/ci.yml) defines tool
versions and downloads. Its checksum-pinned FFmpeg wheel is test tooling only.

Before publishing, run a clean dependency resolution for the declared test
extra, the complete suite, Ruff, archive checks, secret scanning, HACS and
hassfest. Synthetic peers cannot certify another retail camera. Record sanitized
real-camera results and limits; never retain private media or protocol payloads.
