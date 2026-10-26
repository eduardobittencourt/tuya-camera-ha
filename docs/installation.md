# Installation and updates

## Requirements

| Requirement | Supported configuration |
| --- | --- |
| Home Assistant | 2026.9 or newer; real-camera validation used 2026.10.4 |
| Operating system | Linux; HA OS and Container include the required FFmpeg binary |
| Architecture | No project executable restriction; Python/media dependencies need compatible wheels. Live validation: Linux amd64 |
| Account | Tuya Smart or Smart Life, with a compatible camera already paired |
| Network | Tuya for provisioning/wake; GitHub and Python indexes for installation/dependency checks |
| FFmpeg | H.264/AAC encoders; other Linux installations must provide it |

Hardware acceleration is not configured. H.265-to-H.264 conversion uses software
encoding and can be expensive on small hosts.

## HACS

Tuya Camera Bridge is included in the [HACS default catalog](https://github.com/hacs/default/blob/master/integration).
You do not need to add a custom repository.

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=eduardobittencourt&repository=tuya-camera-ha&category=integration)

1. Open **HACS**, search for **Tuya Camera Bridge** and open its repository page.
2. Download the latest stable release. Enable beta versions only for prereleases.
3. Restart HA, then add **Tuya Camera Bridge** in Devices & services.
4. Select the app that owns the account and enter its credentials and country
   calling code. These app namespaces are different; choose the correct one.
5. Open a discovered camera. Wake-up and the first HLS segment can take several
   seconds. Enable audio in the player.

The configuration is completed in HA. A Tuya IoT developer project, cloud API
client keys, a separate add-on and manually configured RTSP ports are not required.
MFA/captcha challenges can prevent login; see [troubleshooting](troubleshooting.md).

If the repository does not appear in search, clear HACS filters and use the
**Open in HACS** button above.

A draft cannot be installed publicly. Releases contain `tuya_camera_bridge.zip`
and `SHA256SUMS`. Version 0.4.0b1 moves all protocols into Python and is available
only with beta versions enabled. The stable 0.3.x line retains the Go executable.

## Manual installation

Download `tuya_camera_bridge.zip` from a published release and extract its contents
into `/config/custom_components/tuya_camera_bridge/`. The resulting directory
must contain `manifest.json`, `__init__.py` and `brand/`, not an extra nested
`tuya_camera_bridge` directory. Restart HA and complete the same UI login flow.
HA installs the declared Python dependencies automatically; no protocol executable
is downloaded. See the beta [dependency compatibility note](architecture.md#dependencies-and-compatibility).

## Updates and rediscovery

Existing custom-repository installations use the same repository and integration
domain. Keep the installation and account configuration; catalog inclusion does
not require removal, reinstallation or another login.

Update through HACS and restart HA. The Python migration preserves account and
entity IDs and removes the obsolete managed executable cache after setup. Never
reuse a published version for different code.

Use **Reconfigure** on the integration entry to sign in again and refresh the
camera list. Recognized session-expiry errors start the HA reauthentication flow.
Signing in again must use the same account/app as the existing entry.

## Switching from the old integration or add-on

Version-1 entries of this repository's old custom integration migrate on setup.
Camera unique IDs are preserved and the obsolete root-level bridge JSON is removed.

For an existing standalone add-on/ONVIF setup, stop the add-on when switching and
remove its old ONVIF entries separately if you want to avoid duplicate entities.
The new integration does not remove or reconfigure other HA integrations.

## Removal

Delete the integration entry in HA. Its processes stop and its account runtime
directory is removed. Remove the files through HACS and restart HA if uninstalling
completely. Version 0.4.x does not maintain an executable cache.
Backups can still contain old sessions; treat them as sensitive.
