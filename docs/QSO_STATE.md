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
- `logs/qso_log.adif` is the normal local archive.
- If Wavelog cannot be reached, the failed upload is also written to
  `logs/wavelog_outbox.adif` for replay.

Wavelog outbox:
- `logs/wavelog_outbox.adif` contains only QSOs that still need to be uploaded
  to Wavelog.
- The retry task starts with the backend and periodically submits queued ADIF
  records to Wavelog.
- Manual controls:
  - `GET /api/qso/outbox/status`
  - `POST /api/qso/outbox/retry`

DuckDB QSO cache:
- Rebuildable read cache, not a second logbook.
- Used for fast UI queries and live spot classification.
- Refreshed from Wavelog by `radio_control.wavelog_duckdb_sync`.
- It is acceptable to delete and rebuild this cache from Wavelog.

Spot DuckDB:
- Historical DX cluster spot store.
- Stores received spots and their precomputed display statuses.
- This is not a QSO log.

## Retired Legacy Paths

- Runtime ADIF-to-DuckDB endpoints are retired. Frontend log views now use
  `/api/wavelog-log/*`, and offline upload visibility uses `/api/qso/outbox/*`.
- Historical notes for the old ADIF/DuckDB approach remain under
  `docs/archive/legacy/`.
- Existing DuckDB files should be treated as cache files. The app should never
  require them as the only copy of a QSO.

## Classification Dependency

Live DX spot classification needs fast DXCC worked/confirmed lookups. Wavelog
`private_lookup` provides callsign worked fields but only DXCC confirmation
fields, so the app uses the local Wavelog DuckDB read cache for DXCC worked
state. That cache is loaded into in-memory sets and refreshed when the cache file
changes.
