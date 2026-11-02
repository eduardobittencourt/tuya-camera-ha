# Configuration

[Documentation index](../README.md)

## Account setup

Choose **Tuya Smart** or **Smart Life** and enter the account, password and
country calling code used in that app (`55` for Brazil). The two apps use
separate account namespaces. OEM-branded app accounts are not supported by
this login flow. The integration discovers cameras associated with the account.

Open a camera and enable audio in the HA player. Initial wake-up and playback
can take several seconds. Discovery alone does not establish media compatibility.

## Reconfiguration and authentication

Use **Reconfigure** on the entry to sign in again and refresh the camera list.
Use the same account and app as the existing entry. Recognized session-expiry
errors trigger Home Assistant reauthentication. Interactive MFA and captcha
are not supported.

## Entities

Camera entities provide live video and fresh snapshots. Additional settings and
readings depend on valid camera reports; see [entities and controls](entities.md).
There is no separate add-on, ONVIF setup, developer cloud project or YAML account
configuration. Do not expose internal media listeners outside loopback.

## Account storage

The password is used for login and is not saved. Account sessions and device
credentials are stored in HA's private config entry. Protect configuration and
backups; see [security](../reference/security.md).
