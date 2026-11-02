# Development

Use Python 3.14.8 or newer in the 3.14 series for the Linux CI environment.
`pyproject.toml` declares test dependencies; `requirements-test.txt` locks the
resolved versions and hashes. Home Assistant and its pytest plugin pins must
be updated together, followed by a lock refresh. No Go toolchain is
required. Read [AGENTS.md](../AGENTS.md) before changing protocol code.

```sh
uv venv --python 3.14
uv pip install --require-hashes --only-binary=:all: -r requirements-build.txt
uv pip install --require-hashes --only-binary=:all: \
  --no-binary=aiortc,mock-open,pyric,pyturbojpeg,tuya-mobile \
  --no-build-isolation -r requirements-test.txt
.venv/bin/ruff check custom_components tests scripts
.venv/bin/pytest -m 'not media'
.venv/bin/python scripts/package_release.py
.venv/bin/python scripts/check_repository.py --archive dist/tuya_camera.zip
node --test --experimental-test-coverage --test-reporter=spec --test-reporter-destination=stdout \
  --test-reporter=lcov --test-reporter-destination=coverage-js.lcov tests/test_release_gate.cjs
```

The lock targets CPython 3.14 on Linux x86-64, matching CI. On other development
platforms, install `.[test]` from `pyproject.toml` and retain the same direct pins.
The five explicit source exceptions have no suitable wheels. Their archives are
hash-locked; build isolation is disabled so builds use the hash-locked tools in
`requirements-build.txt` instead of downloading additional build dependencies.
The aiortc archive still uses the same pinned upstream commit as the integration.

After changing dependencies, regenerate the locks, run `pip check`, and validate
both the Python and synthetic-media suites in a fresh environment:

```sh
uv pip compile pyproject.toml --extra test --generate-hashes --python-version 3.14.8 \
  --python-platform x86_64-unknown-linux-gnu --output-file requirements-test.txt --no-annotate
printf 'setuptools>=77\nwheel\n' | uv pip compile - --generate-hashes \
  --python-version 3.14.8 --output-file requirements-build.txt --no-annotate
```

A regression test checks that every declared test dependency matches the lock.
Dependabot changes to direct pins must include the corresponding lock refresh.

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

The synthetic WebRTC probe takes the go2rtc API **port**, not a URL:
`scripts/webrtc_probe.py 1984`. It always posts to
`http://127.0.0.1:PORT/api/webrtc?src=camera`, rejects redirects and checks the
answer's ICE candidates before giving them to aiortc. The test harness provides
the port of its own synthetic server. See [security boundaries](security-boundaries.md)
for the archive limits, probe restrictions and protocol-hash review.

Before publishing, run a clean dependency resolution for the declared test
extra, the complete suite, Ruff, archive checks, secret scanning, HACS and
hassfest. Synthetic peers cannot certify another retail camera. Record sanitized
real-camera results and limits; never retain private media or protocol payloads.

## SonarQube Cloud

See [SonarQube Cloud and coverage](sonarqube.md) for CI analysis, coverage artifacts and external-contribution limits.
The [quality review](quality-review.md) records the robustness changes and
protocol-specific findings that require contextual security review.
