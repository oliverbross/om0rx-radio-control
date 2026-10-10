# MSHV DXpedition watch contract

OM0RX may provide native MSHV with DXpedition metadata, but it does not select
targets, tune, authorize transmit, or call stations. MSHV remains the only
automation planner.

## Authority and refresh

The sidecar is built only from Activity Intelligence records normalized by the
reviewed `NG3K_ADXO` and `DXCAL_ICS` adapters. Arbitrary web or cluster text is
not allowed to declare a station a known DXpedition. After a successful source
refresh, the scheduler may call
`publish_repository_dxpedition_watch(repository, runtime_path)`. It writes the
complete replacement atomically with `os.replace`; a failed source refresh or
write leaves the prior file intact.

Canonical runtime path:

`settings/database/dxpedition_watch.json`

This path is mutable operator/runtime state and is carried across atomic runtime
replacement. The default catalog lifetime is 24 hours, twice the normal 12-hour
NG3K polling period. Once it expires, native code must ignore it and continue
ordinary AutoDX operation.

## Schema 1

```json
{
  "schema": 1,
  "generated_at_utc": "2026-10-05T20:00:00Z",
  "watch_max_age_seconds": 86400,
  "spot_max_age_seconds": 120,
  "entries": [
    {
      "callsign": "A31WW",
      "aliases": ["A31WW", "A31DX"],
      "bands": ["20m", "15m"],
      "modes": ["FT8"],
      "status": "ACTIVE",
      "start_utc": "2026-10-01T00:00:00Z",
      "end_utc": "2026-10-10T23:59:59.999999Z",
      "source_id": "NG3K_ADXO"
    }
  ]
}
```

Empty `bands` or `modes` means the catalog did not make that restriction. It
does not relax live evidence validation.

## Native consumption invariant

The native spot adapter should reload on atomic file replacement and fail
closed for a missing, malformed, unknown-schema, future-dated, or expired
catalog. A known-DXpedition match may add priority to a cluster watch/QSY only
when the live spot:

- names the primary call or an alias;
- explicitly identifies FT8 (frequency proximity is not mode evidence);
- is no more than `spot_max_age_seconds` old;
- is inside a supported amateur band and any catalog band/mode restriction;
- has a dedupe identity of call, band, and 100 Hz frequency bucket.

The match is metadata, never permission to transmit. MSHV must still enforce
its enabled-band schedule, perform its own direct CAT QSY, wait for a matching
local decode, and call through its native queue/state machine. An unverified
spot times out and returns to the origin/standard dial. OM0RX station profile
following remains asynchronous and cannot veto or roll back native QSY/PTT.

## Integration hook

The safe backend hook is immediately after Activity Intelligence commits a
successful trusted-source refresh. It should only publish the sidecar and emit
telemetry. Native ingestion belongs at the spot-to-candidate boundary, before
DXpedition priority and off-standard dial interpretation; it must not bypass
the existing external-mode, age, history-authority, schedule, or local-decode
checks.
