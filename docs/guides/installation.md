# Installation

[Documentation index](../README.md)

## Requirements

- Home Assistant **2026.9 or newer on Linux**.
- A compatible camera linked to Tuya Smart or Smart Life.
- Internet access for account authentication, signaling and Python dependencies.
- FFmpeg with H.264/AAC encoding support; HA OS and Container include it.

Dependency wheels must support the host architecture. H.265 conversion uses
software encoding; hardware acceleration is not configured by this integration.
See [compatibility](compatibility.md).

## HACS

Tuya Camera is in the default HACS catalog.

1. Search for **Tuya Camera** in HACS and download the latest stable release.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add integration → Tuya Camera**.
4. Complete [account configuration](configuration.md).

## Manual installation

Download `tuya_camera.zip` from a published release and extract its contents
into `/config/custom_components/tuya_camera/`. That directory must directly
contain `manifest.json`, `__init__.py` and `brand/`, without a nested component
directory. Restart HA and complete the same account setup.
HA installs the declared Python dependencies automatically.

## Updates

Update through HACS and restart HA. Updates within the `tuya_camera` domain
retain the account and entity identities. Read the [changelog](../../CHANGELOG.md)
for upgrade notes. Installations still using `tuya_camera_bridge` need the
[migration procedure](migrations.md), rather than a file-only update.

## Removal

Delete the integration entry in HA to stop its owned tasks and media processes.
To uninstall completely, remove its files through HACS and restart HA.
Backups can retain account sessions; treat them as private.
