# Rotator Resolution

The rotator uses one backend resolver for cluster spots, manual QSO actions, QRZ/Wavelog enrichment, and WSJT-X auto-rotate. The resolver calculates short-path and long-path bearings, reports the data source, and decides whether AUTO is allowed to move.

## Source Priority

1. QRZ station grid or coordinates.
2. Wavelog station grid or coordinates.
3. Explicit/manual grid or coordinates from the active logging form.
4. Exact-call `cty.dat` entity coordinates.
5. Prefix/entity-center `cty.dat` coordinates.

## Confidence Rules

- `high`: Station-level data from QRZ, Wavelog, WSJT-X grid, or a manually entered grid/coordinate.
- `medium`: Exact-call `cty.dat` data. This can be useful, but it is still entity metadata rather than a confirmed station QTH.
- `low`: Prefix/entity-center `cty.dat` data. This is country/entity-level only.

AUTO movement is allowed for `high` and `medium` targets when the configured band is enabled. Low-confidence CTY entity-center targets still produce SP/LP bearings for manual use, but AUTO does not move the rotator from them.

## UI Indicator

The beaming panel shows the resolved source beside the callsign. Blue indicates high-confidence station-level data, amber indicates medium confidence, and orange indicates approximate CTY data.

## Backend Contract

Use `POST /api/rotor/resolve` to calculate a target without moving. Use `POST /api/rotor/auto/goto` to calculate and move when AUTO is enabled and the resolved target permits automatic movement.

Important response fields:

- `source`: Machine-readable source such as `qrz_grid`, `wavelog_grid`, or `cty_grid`.
- `source_label`: Human-readable source shown in the UI.
- `confidence`: `high`, `medium`, or `low`.
- `approximate`: `true` when the target should be treated as approximate.
- `auto_allowed`: `true` only when AUTO may move for this resolved target and band.
- `short_path_bearing` and `long_path_bearing`: Bearings for display and manual SP/LP movement.
