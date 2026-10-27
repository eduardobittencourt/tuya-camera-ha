# Sanitized local-wake evidence

These files accompany the [implementation decision](../../offline-operation.md)
and [chronological hardware report](../../local-wake-investigation.md).
They concern **one stock Positivo SKU 11188736, firmware 1.1.48**. Dates are UTC.

| File | Origin and selection | What it can establish |
| --- | --- | --- |
| [public-schema.json](public-schema.json) | Final 2026-10-27 account read; whitelist of DP id/code/access/property definitions, API names/versions and firmware versions | Fresh advertised schema matches cached schema; DP149 exists as boolean `rw`. No live DP states or LAN write behavior are implied |
| [tls-name-controls.json](tls-name-controls.json) | Completed 2026-10-27 local TLS experiment; whitelist of selection, alert, setup and cleanup event fields | Exact eight TLS rejection observations, variant order and UTC times. Normal cloud wake and WAN were deliberately allowed; this is not an offline-cycle test |

DP numbers identify public functions, not individual cameras. The files exclude
account/product/device IDs, addresses, MACs, keys, sessions, signed URLs, state
values, MQTT contents, images and packet payloads. The shared Tuya TLS hostname
is retained because service identity is the tested variable. The public-schema
export excludes default values and other unneeded product metadata.

The matrix held issuer CA, root and leaf keys, validity, usages and TLS settings
constant. `both_match` means CN and DNS SAN matched the service; `cn_only_match`
means only CN matched; `san_only_match` means only SAN matched; `both_wrong`
means neither matched. An independent client that trusted the experimental CA
first checked hostname outcomes `[true, false, true, false]` in that order.
The camera did not receive that CA. These are eight connections on one camera,
not eight devices or independent firmware implementations. No camera handshake
completed; no MQTT application exchange was observed against the replacement.

The JSON is a selected observation record, not a raw capture or signed attestation.
Private research logs remain outside this repository. A reader can inspect the
reasoning and repeat the method on their own device, but cannot independently
reconstruct every original packet from this bundle. See the report for failed
controls, the corrected relay segmentation issue, bounded negative windows,
isolation limits and recovery. No credential-bearing research harness is shipped.

For a consistency check, parse both files with Python's standard `json` module:
the schema has 21 definitions, including DP149 `wireless_awake` / `rw` / `bool`;
the matrix has two rejections per variant, with `UNKNOWN_CA` for matching SAN and
`BAD_CERTIFICATE` otherwise. Those counts validate this record's structure;
they do not rerun the hardware experiment.
