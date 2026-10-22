# Managed media bridge

This Go executable is an internal part of the Home Assistant integration.
The integration starts it without arguments and passes account/session data
through stdin. It always binds RTSP to loopback on an automatically allocated
port and emits structured lifecycle events on stdout. Camera routing is held
in memory; it does not create account or credential files.

Builds use Go 1.26.8 and `scripts/package_release.py`. The executable supports
`--version` for inspection. There is no independent login CLI, ONVIF service,
Docker image or standalone add-on.
