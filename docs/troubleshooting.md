# Troubleshooting

Start with the integration entry and the camera's HA state. Share HA/integration
versions, host architecture, app and retail camera model in an issue. The
integration's diagnostics deliberately omit account/session fields and IDs;
review any attachment before publishing it.

## Integration does not appear after download

Restart HA and search for **Tuya Camera Bridge** in Devices & services. For a
manual install, confirm `manifest.json` is directly inside
`custom_components/tuya_camera_bridge/`. Check the minimum HA version.

## Bridge download or checksum failure

Install a published release with its matching executable assets. A development
checkout can reference an unpublished version. Check GitHub access and Linux
architecture. Do not disable checksum verification or paste an arbitrary binary
into the integration directory. Raise an issue if published files do not match.

## Login fails or finds no cameras

Choose the same app and country calling code used by the mobile account. Confirm
the account can see the camera in that app. Tuya Smart and Smart Life are
separate app namespaces; OEM-branded apps are not supported by this login flow.

Account lock, expired public app profiles, MFA and captcha can block login.
Completing a challenge in the mobile app does not guarantee that this integration
will be accepted. Avoid repeated login attempts on a locked/challenged account.
Use Reconfigure to refresh the camera list with the existing account.

## A discovered camera has no video

Discovery only proves that the account lists the device. Confirm it is online
in the mobile app, then wait for wake-up/connection establishment. The tested
camera's cold HLS startup was about 15–18 seconds; other devices can differ.
Check Tuya connectivity and that this model supports mobile WebRTC.

`connection_status: standby` means the bridge is ready; it does not prove the
camera is reachable. `video` and `last_video_received` report actual received
packets. `disconnected`/unavailable indicates bridge or detected media failure.
An old timestamp while idle is not a current connectivity test.

## Video opens without sound

Enable audio in the HA player and check the phone/browser's sound settings.
Include the camera's advertised codec if known, without raw captures or URLs.
Some codecs/firmware are not supported. Live sound reception does not mean
speaker/talkback support; two-way audio is not exposed.

## High CPU or multiple FFmpeg processes

H.265 requires software H.264 conversion. Independent streaming consumers can
start additional FFmpeg processes; native HLS viewers normally share a stream.
Snapshots also launch a short-lived decoder. Test one viewer before adding
multiple dashboards/consumers and compare with the measured validation results.
`active_media_processes` is an operational count, not an error by itself.

## Recovery and expired sessions

A crashed bridge restarts automatically with bounded backoff. Recognized expired
sessions require a new login in HA. An unreachable camera cannot be repaired by
restarting the bridge alone; it must come back online. Long camera/WAN outages
have not been fully validated on the real test device.

## Reporting safely

Use [the bug form](https://github.com/eduardobittencourt/tuya-camera-ha/issues/new?template=bug_report.yml).
Describe expected/actual behavior and repeatable steps. Share only reviewed,
sanitized HA error excerpts. Do not attach `.storage`, a backup, bridge JSON,
raw MQTT/WebRTC/SDK output, credentials, keys, IDs or a private camera image.
Security problems belong in [private reporting](../SECURITY.md).
