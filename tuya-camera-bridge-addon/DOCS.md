# Tuya Camera Bridge

This standalone add-on exposes Tuya Smart and Smart Life cameras to Home
Assistant through its built-in ONVIF integration. HACS and YAML configuration
are not required.

## Setup

1. Start the add-on and open its web UI.
2. Select the same Tuya application used by the account.
3. Enter the international country calling code, account and password.
4. Wait for the success message. The password is used only for that request and
   is not stored.
5. Open **Settings → Devices & services** and confirm each discovered ONVIF
   camera.

The add-on stores the resulting Tuya session and a snapshot cache in its private
data directory. It discovers all compatible cameras on the account and assigns
one ONVIF device to each. The first live view can take several seconds while a
camera wakes; later snapshots use the last valid image while refreshing in the
background.

## Network and security

The setup UI accepts traffic only from Home Assistant's authenticated Ingress
proxy and is visible only to administrators. ONVIF and RTSP remain available on
the local network so Home Assistant can discover and play the cameras. Do not
forward ports 8081+, 8554 or 38554 to the internet.

This is an experimental add-on based on Tuya's private mobile APIs. MFA and
interactive captcha are not yet supported, and changes to the Tuya apps can
require an update.
