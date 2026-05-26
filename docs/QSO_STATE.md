# QSO State Model

The project should have one logbook source of truth and only rebuildable local
state around it.

## Intended Roles

Wavelog:
- Primary logbook and source of truth.
- Normal successful QSO logging writes here first.
- Worked/confirmed history should ultimately be derived from Wavelog.

Local ADIF:
- Offline safety net and portable backup.
- The app writes ADIF when a QSO is logged locally.
- If Wavelog cannot be reached, the QSO must still be preserved here so it can
  be replayed later.

DuckDB QSO cache:
- Rebuildable read cache, not a second logbook.
- Used for fast UI queries and live spot classification.
- Refreshed from Wavelog by `radio_control.wavelog_duckdb_sync`.
- It is acceptable to delete and rebuild this cache from Wavelog.

Spot DuckDB:
- Historical DX cluster spot store.
- Stores received spots and their precomputed display statuses.
- This is not a QSO log.

## Current Gaps

- Manual QSO logging always writes local ADIF after attempting Wavelog. The next
  improvement should split this into normal backup ADIF plus an explicit
  unsent/outbox ADIF for failed Wavelog uploads.
- Older ADIF-to-DuckDB code and endpoints still exist. They should be retired or
  clearly marked legacy after the Wavelog read cache and offline outbox are
  fully established.
- Existing DuckDB files should be treated as cache files. The app should never
  require them as the only copy of a QSO.

## Classification Dependency

Live DX spot classification needs fast DXCC worked/confirmed lookups. Wavelog
`private_lookup` provides callsign worked fields but only DXCC confirmation
fields, so the app uses the local Wavelog DuckDB read cache for DXCC worked
state. That cache is loaded into in-memory sets and refreshed when the cache file
changes.
