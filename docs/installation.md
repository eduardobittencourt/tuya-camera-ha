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

Tuya Camera is included in the [HACS default catalog](https://github.com/hacs/default/blob/master/integration).
You do not need to add a custom repository.

The name **Tuya Camera**, domain `tuya_camera` and archive `tuya_camera.zip`
apply starting with **0.4.0b2**. Stable 0.3.x and beta 0.4.0b1 use the former
**Tuya Camera Bridge** name, domain and archive. Enable beta versions to install
the renamed integration.

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=eduardobittencourt&repository=tuya-camera-ha&category=integration)

1. Open **HACS**, search for **Tuya Camera** and open its repository page.
2. Choose stable **0.3.x** for **Tuya Camera Bridge**, or enable beta versions
   and select **0.4.0b2** for **Tuya Camera**. Download the selected release.
3. Restart HA, then add **Tuya Camera Bridge** for stable 0.3.x or **Tuya Camera**
   for beta 0.4.0b2 in Devices & services.
4. Select the app that owns the account and enter its credentials and country
   calling code. These app namespaces are different; choose the correct one.
5. Open a discovered camera. Wake-up and the first HLS segment can take several
   seconds. Enable audio in the player.

The configuration is completed in HA. A Tuya IoT developer project, cloud API
client keys, a separate add-on and manually configured RTSP ports are not required.
MFA/captcha challenges can prevent login; see [troubleshooting](troubleshooting.md).

If the repository does not appear in search, clear HACS filters and use the
**Open in HACS** button above.

A draft cannot be installed publicly. Releases contain `tuya_camera.zip`
and `SHA256SUMS`. The 0.4.0 beta line runs all protocols in Python. The stable
0.3.x line retains the Go executable and the previous archive name.

## Manual installation

Download `tuya_camera.zip` from a published release and extract its contents
into `/config/custom_components/tuya_camera/`. The resulting directory
must contain `manifest.json`, `__init__.py` and `brand/`, not an extra nested
`tuya_camera` directory. Restart HA and complete the same UI login flow.
HA installs the declared Python dependencies automatically; no protocol executable
is downloaded. See the beta [dependency compatibility note](architecture.md#dependencies-and-compatibility).

## Updates and rediscovery

Catalog inclusion itself does not require reinstallation. However, **0.4.0b2
changes the integration domain** from `tuya_camera_bridge` to `tuya_camera`.
Updating files and restarting alone does not migrate an existing account entry.

For a clean reinstall from an earlier version, remove the old integration entry
in Devices & services, uninstall its files through HACS, then refresh the
repository and select 0.4.0b2 with beta versions enabled. HACS can retain the
former folder/ZIP in its repository cache; uninstall/reinstall alone did not
clear this on the validated installation. If it still requests the former
`tuya_camera_bridge` manifest, use the published ZIP following
[manual installation](#manual-installation) and seek maintainer assistance
before restoring HACS tracking. Restart HA and add **Tuya Camera** using the
same account/app. Check dashboards and automations
against the newly created entity IDs. The old component directory must not be
left alongside the new one. An operator can instead perform an offline registry
migration, retaining entry/entity/device IDs; this is not automatic in this beta.
Downgrading to the former domain also requires a reinstall or an inverse offline
migration. Selecting an older release in HACS alone does not change account or
registry domains.

For this beta, the validated HACS installation required operator reconciliation
of this repository’s cached metadata and an explicit **v0.4.0b2** selection.
Keep that selection while the stable channel still describes the former domain;
no HACS source patch is needed. This is a beta transition limitation, not an
automatic migration feature. Subsequent releases under the same domain should
follow the normal update/restart path after this cache transition is resolved.
Never reuse a published version for different code.

Use **Reconfigure** on the integration entry to sign in again and refresh the
camera list. Recognized session-expiry errors start the HA reauthentication flow.
Signing in again must use the same account/app as the existing entry.

## Switching from the old integration or add-on

The legacy `tuya_camera_bridge` domain requires the explicit reinstall or
operator migration above. The new integration does not automatically load
entries registered under the old domain.

For an existing standalone add-on/ONVIF setup, stop the add-on when switching and
remove its old ONVIF entries separately if you want to avoid duplicate entities.
The new integration does not remove or reconfigure other HA integrations.

## Removal

Delete the integration entry in HA. Its processes stop and its account runtime
directory is removed. Remove the files through HACS and restart HA if uninstalling
completely. Version 0.4.x does not maintain an executable cache.
Backups can still contain old sessions; treat them as sensitive.
