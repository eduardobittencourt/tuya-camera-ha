# 0.3.3 validation

## Incident and correction

Home Assistant 2026.10.1 loaded the locally patched 0.3.2 integration, but rejected
four LAN sensors with `AttributeError: 'EntityDescription' object has no attribute
'state_class'`. The shared entity base assigned a generic description while
`SensorEntity` expects additional platform-specific fields. The shared base now
uses the native name attribute and leaves platform defaults intact.

The regression test registers battery, power source, SD status and formatting
progress through HA, checking all four states, battery units and numeric scale.
It also verifies switch/select/number writes and unloading. The release retains
the previous schema-driven LAN implementation and account/camera identities.

## Live-camera findings

On 2026-10-12 the tested Positivo battery camera was unavailable in HA and also
failed live viewing in its mobile app, as confirmed by the owner. A targeted,
read-only Tuya query reported it offline, with the last reported battery at 5%.
New bridge sessions authenticated and reached WebRTC connection establishment,
but produced no JPEG or video packets before their connection deadline.

The sensor registration bug and the camera's offline condition are separate.
The release fixes registration; it cannot charge or bring the camera online.
Successful live video recovery has not been verified. No account identifiers,
sessions, keys, private media or raw signaling logs are included here.

## Checks

- Python lint and 70 non-media tests passed locally, using the pinned HA 2026.9.4
  test environment.
- Go 1.26.8 race tests passed. No Go source changes were required.
- Both Linux release binaries were rebuilt for the new version.
- Release archive, synthetic H.264/H.265 media, compatibility add-on Docker build,
  secret scan, HACS and hassfest checks must pass on the final release candidate.
