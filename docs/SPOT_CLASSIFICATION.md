# Spot Classification

This document describes how incoming DX cluster spots become the `call_status` and
`dxcc_status` values shown in the web UI and sent to SmartSDR.

## Runtime Flow

1. `services/background_tasks.py` receives a cluster spot.
2. `radio_control.spot_processor` derives the band and likely emission mode from
   frequency and comment text.
3. `radio_control.cty_resolvers.CtyDatResolver` resolves callsign to country,
   CQ/ITU zone, continent, coordinates, and ADIF/DXCC number using `data/cty.dat`
   plus ADIF IDs from `data/cty.csv`.
4. `radio_control.classifier_api.ClassifierAPI` checks Wavelog state.
5. `radio_control.spot_classification` applies the display rules.
6. `radio_control.spots_logger` stores the spot and its statuses in
   `data/spots.duckdb`.
7. The frontend renders the persisted/broadcast statuses from
   `frontend/js/dx-spots.js`.

## Data Sources

CTY:
- `data/cty.dat` is the authority for prefix matching and special calls.
- `data/cty.csv` supplies ADIF/DXCC IDs that `cty.dat` does not directly expose.
- Prefix tokens must not be split on slash, equals, or hyphen. Doing so can turn
  portable/special calls into bogus one-letter prefixes.

Wavelog:
- `/api/private_lookup` is used for callsign worked/confirmed fields.
- Wavelog documents DXCC fields from this endpoint as confirmation fields:
  `dxcc_confirmed`, `dxcc_confirmed_on_band`, and
  `dxcc_confirmed_on_band_mode`.
- Because `private_lookup` does not provide DXCC worked fields, DXCC worked
  status is read from the local Wavelog DuckDB mirror at `data/qso_log.duckdb`.
- The DuckDB mirror is loaded into compact in-memory DXCC worked/confirmed sets
  and refreshed when the mirror file changes, so live spot classification does
  not scan the QSO table per spot.

## Status Rules

Call status:
- `New Call`: callsign has never been worked.
- `Confirmed`: this callsign is confirmed on the current band/mode.
- `New Band+Mode`: worked before, but both the band and band/mode are new.
- `New Band`: worked before, but the band is new.
- `New Mode`: worked before on the band, but this band/mode is new.
- `Worked`: worked before without a stronger status.

DXCC status:
- `ATNO`: the ADIF/DXCC entity has never been worked in the local QSO mirror.
- `Confirmed`: current DXCC band/mode is LoTW-confirmed.
- `C/New Band`, `C/New Mode`, `C/New Band+Mode`: DXCC is confirmed overall,
  but the current band/mode dimension is new.
- `W/New Band`, `W/New Mode`, `W/New Band+Mode`: DXCC is worked overall but
  not confirmed overall, and the current band/mode dimension is new.
- `Worked`: DXCC is worked on this band/mode but not confirmed.

## Known Follow-Ups

- Add an explicit CTY update command/scheduled task so `data/cty.dat` and
  `data/cty.csv` are refreshed from the official source in a controlled way.
- Store the resolved ADIF/DXCC number in `data/spots.duckdb` alongside country
  and status so historic spot audits can explain exactly which entity was used.
- Add an admin/debug endpoint that explains one callsign classification:
  CTY match, resolved ADIF, Wavelog call flags, local QSO DXCC flags, and final
  display status.
