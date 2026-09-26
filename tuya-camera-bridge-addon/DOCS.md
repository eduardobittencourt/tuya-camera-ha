# Tuya Camera Bridge

Install the companion **Tuya Camera Bridge** custom integration first or at the
same time as this add-on. The integration authenticates the selected mobile-app
account, discovers a camera and writes an owner-only configuration file. The
add-on watches that file and exposes the selected camera over RTSP on port
`38554` to Home Assistant Core.

There are no add-on options. Account passwords are never written to the add-on
configuration.
