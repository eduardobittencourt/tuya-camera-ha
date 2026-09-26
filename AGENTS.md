# Contributor guidance

This repository ships two coupled components:

- `custom_components/tuya_camera_bridge`: Home Assistant config flow and camera entity.
- `bridge` + `tuya-camera-bridge-addon`: Tuya WebRTC/MQTT media bridge and HA add-on.

User-facing setup must remain UI driven. Do not require users to copy device IDs,
sessions, keys or YAML between the integration and add-on. Any bridge contract
change must be implemented and tested on both the Python and Go sides.

Never commit user credentials, session IDs, encryption codes, local keys,
captured MQTT payloads or generated bridge JSON. The versioned application
profile constants under `vendor/tuya_mobile/profiles.py` identify public mobile
application builds and are intentionally shared by all users.

Run Python lint/tests, Go tests/build and the add-on Docker build before release.
