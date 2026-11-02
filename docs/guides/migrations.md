# Migration notes

[Documentation index](../README.md)

## Former Tuya Camera Bridge domain

The current component domain is `tuya_camera`. Entries registered under
`tuya_camera_bridge` are not automatically migrated by replacing files and
restarting HA. Normal updates already using `tuya_camera` do not need these steps.

1. Keep a private backup and note dashboard/automation references.
2. Remove the old entry in **Devices & services** and uninstall its files in HACS.
3. Refresh HACS, install **Tuya Camera**, restart HA and add the same account/app.
4. Check the new entity IDs and update dashboards or automations as needed.

Do not leave the old component directory alongside `tuya_camera`. If HACS still
requests the old manifest or archive, use the current release ZIP as described
in [manual installation](installation.md#manual-installation) and contact
[support](../../SUPPORT.md) before restoring HACS tracking. Editing private HA
registries is not part of the supported user procedure. Downgrading across the
domain change also requires a reinstall.

## Former standalone add-on or ONVIF setup

Stop the old add-on when switching to the integration. Remove its old ONVIF
entries separately if you want to avoid duplicate cameras; this integration
does not remove or reconfigure other integrations.
