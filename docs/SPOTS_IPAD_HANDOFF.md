# Spots Section Handoff for iPad Implementation

This document describes how the current OM0RX spots section works so the same behavior can be implemented in another client. It is based on the current code paths in:

- `radio_control/cluster_client.py`
- `services/background_tasks.py`
- `radio_control/spot_processor.py`
- `radio_control/spot_classification.py`
- `radio_control/classifier_api.py`
- `radio_control/qso_status_store.py`
- `radio_control/spot_intelligence.py`
- `radio_control/spot_aggregation.py`
- `radio_control/spots_logger.py`
- `backend/api/spots.py`
- `frontend/js/dx-spots.js`
- `frontend/templates/dx-spots.html`

## High Level Flow

1. The backend connects to a DX cluster over telnet.
2. Cluster lines matching `DX de <spotter>: <freq_khz> <dxcall> <comment>` are parsed.
3. Obvious duplicate cluster lines are dropped by `(dxcall, frequency rounded to 0.1 kHz)`.
4. The backend derives band, mode, source type, country, DXCC, zones, special tags, Wavelog status, score, and map fields.
5. The enriched spot is saved to `data/spots.duckdb`.
6. The enriched spot is merged into an in-memory live cache.
7. The backend broadcasts the spot over WebSocket message type `spots`.
8. The frontend displays the live cache, filters it locally, and uses `/api/spots/filtered-search` when database-backed filtering is needed.

## Realtime WebSocket Contract

Endpoint:

```text
GET /ws/radio
```

Spot messages have this shape:

```json
{
  "type": "spots",
  "data": [
    {
      "callsign": "A31DX",
      "frequency": "14074.0",
      "frequency_mhz": 14.074,
      "spotter": "DL1ABC",
      "spotter_continent": "EU",
      "mode": "FT8",
      "spot_source": "cluster",
      "rbl_mode_group": "",
      "band": "20m",
      "comment": "FT8",
      "country": "TONGA",
      "dxcc": 160,
      "cq": "32",
      "call_status": "New Band",
      "dxcc_status": "W/New Band",
      "needed": { "call": false },
      "needed_on_band": { "call": true, "mode": false },
      "special": "POTA, WWFF",
      "tag": "New band",
      "timestamp": 1782200000.0,
      "time": "12:34:56",
      "latitude": -21.1,
      "longitude": -175.2,
      "gridsquare": "AH13xx",
      "location_source": "cty_prefix",
      "location_confidence": "low",
      "rbl_snr": null,
      "spot_score": 52,
      "spot_score_reasons": ["new worked DXCC band", "new call band"]
    }
  ]
}
```

The client should not recompute the key statuses if the backend provides them. Treat `call_status`, `dxcc_status`, `tag`, `spot_score`, `priority_score`, `activity_tags`, and `recommended_actions` as display-ready.

## Main Spot Table

The current table has these columns:

| Column | Field / logic |
| --- | --- |
| Details | Info button. Opens `/api/spots/explain/{callsign}` and Activity Intelligence detail. |
| Time | `timestamp`, formatted as UTC time. |
| Score | `priority_score` if present, otherwise `spot_score`, otherwise `0`. |
| Band | `band`. |
| Frequency | `frequency_mhz` preferred, fallback `frequency / 1000`. |
| Callsign | `callsign`. |
| Mode | `mode`, plus a `HEARD` sublabel if `local_heard` is true. |
| Country | `country`; prefix with `RBL` label if `spot_source == "rbl"`. |
| CQ | `cq`. |
| DX de | `spotter` or aggregate spotter summary. For RBL aggregation also show seen count, last seen, best SNR. |
| Call Status | `call_status`, colored by status. |
| DXCC Status | `dxcc_status`, colored by status. |
| Special | Badges from comma-separated `special`, plus optional `activity_tags` and propagation badge. |
| Worked b4 | Local Wavelog match for `CALL-BAND-MODE`, formatted as `DD/MM/YYYY`. |
| Comment | `comment`. |

Clicking a row tunes the radio, fills the logging form, broadcasts a digital target selection for FT8/FT4/FT2, optionally triggers rotor calculation, loads QRZ/Wavelog/DXCC enrichment, and can add a panadapter spot to SmartSDR.

## Band and Mode Derivation

Band is derived from frequency in kHz:

| Range kHz | Band |
| --- | --- |
| 1800-1999 | 160m |
| 3500-3999 | 80m |
| 5250-5449 | 60m |
| 7000-7299 | 40m |
| 10100-10149 | 30m |
| 14000-14349 | 20m |
| 18068-18167 | 17m |
| 21000-21449 | 15m |
| 24890-24989 | 12m |
| 28000-29699 | 10m |
| 50000-53999 | 6m |
| 144000-147999 | 2m |
| 220000-224999 | 1.25m |
| 430000-449999 | 70cm |
| Other supported microwave ranges | 33cm, 23cm, 13cm, 9cm, 5cm, 3cm, 1.25cm |
| Anything else | OTHER |

Mode inference order:

1. Comment text wins first: `FT8`, `FT4`, `FT2`, `RTTY`, `OLIVIA`, `PSK`, `JT65`, `JT9`, `HELL`, `MFSK`, `SSTV`, `AM`, `FM`, `SSB`/`USB`/`LSB`/`PH`, `CW`/`CWT`.
2. Frequency near known FT8/FT4/FT2 calling frequencies, within about 1.6 kHz.
3. Phone band segments imply `SSB`.
4. CW band segments imply `CW`.
5. CW edge fallback if below the CW segment upper edge.
6. Default is `SSB`.

Radio mode mapping when tuning:

- Spot `SSB` becomes `LSB` below 14 MHz, otherwise `USB`.
- Digital modes `FT8`, `FT4`, `FT2`, `JT65`, `JT9`, `PSK`, `DIGI`, `MFSK`, `OLIVIA` become Flex `DIGU`.
- Other accepted radio modes pass through.

## Source Types: Cluster vs RBL

`spot_source` is:

- `rbl` if the spotter ends with `-#` or the comment contains `RBL`, `RBN`, or `SKIMMER`.
- `cluster` otherwise.

For RBL spots, `rbl_mode_group` is:

- `CW` for mode `CW`.
- `SSB` for phone modes `SSB`, `AM`, `FM`.
- `DIGI` for digital modes such as `FT8`, `FT4`, `FT2`, `RTTY`, `PSK`, `JT65`, etc.
- `OTHER` otherwise.

Live RBL aggregation:

- RBL key: `rbl:<CALLSIGN>:<BAND>:<MODE>`.
- Cluster key: `cluster:<CALLSIGN>:<frequency_mhz rounded to 0.001>`.
- Repeated live rows are merged, moved to the top, and get:
  - `aggregate_key`
  - `aggregate_count`
  - `aggregate_spotters`
  - `aggregate_spotter_count`
  - `aggregate_first_timestamp`
  - `aggregate_last_timestamp`
  - `aggregate_best_snr`

The live cache keeps the last 200 visible rows on the backend. The browser also trims its local display to `maxSpots`.

## Country, DXCC, Zones, and Location

Country and zone resolution uses `data/cty.dat` plus `data/cty.csv`.

Resolution details:

- `cty.dat` is used for longest-prefix and exact-call matching.
- `data/cty.csv` supplies ADIF/DXCC IDs when CTY data does not expose them directly.
- `=CALL` entries in `cty.dat` are treated as exact matches.
- Slash calls are handled by testing the full call and slash parts.
- Ignored suffixes include `P`, `M`, `MM`, `AM`, `QRP`, `QRPP`, `A`, `B`, and `QTH`.
- Current overrides include `PJ6Y -> 305` and `PJ -> 305`.
- `KG4` plus three letters is treated as a normal US call, not Guantanamo Bay.

Fields returned from CTY:

- `country`
- `dxcc`
- `cq`
- `itu`
- `continent`
- `latitude`
- `longitude`
- `utc_offset`
- `primary_prefix`
- matching prefix details

Important longitude detail:

- CTY longitude is stored in the CTY convention. The backend normalizes it for maps by multiplying by `-1`, so west-positive CTY longitudes become normal east-positive map longitudes.

Location fields:

- If CTY coordinates exist, the live spot gets `latitude`, normalized `longitude`, and a generated 6-character Maidenhead `gridsquare`.
- `location_source` is `cty_exact` for exact call matches, otherwise `cty_prefix`.
- `location_confidence` is `medium` for exact matches, otherwise `low`.

## Wavelog Comparison

The app compares spots with Wavelog in two layers:

1. Wavelog `private_lookup` API for callsign status.
2. Local Wavelog QSO status cache for true DXCC worked/confirmed status.

Why two layers:

- Wavelog `private_lookup` gives reliable call worked/confirmed fields.
- Wavelog `private_lookup` exposes DXCC confirmation fields, but not reliable DXCC worked fields.
- Therefore DXCC worked status comes from the local QSO mirror.

The local QSO status cache reads from:

- PostgreSQL `qso_records` when PostgreSQL is enabled.
- Otherwise DuckDB `data/qso_log.duckdb` when explicitly used.
- Otherwise the configured Wavelog/MySQL table `TABLE_HRD_CONTACTS_V01`.

The QSO status cache stores in-memory sets for:

- Calls worked and confirmed.
- Calls worked by band.
- Calls worked by mode.
- Calls confirmed by band+mode.
- DXCCs worked and confirmed.
- DXCCs worked by band.
- DXCCs worked by mode.
- DXCCs confirmed by band+mode.
- Grids worked overall, by band, and by mode.

Confirmation is true when any of these fields contains a confirmed-like value:

- `lotw_qsl_rcvd`
- `lotw_qsl`
- `eqsl_qsl_rcvd`
- `eqsl_qsl`
- `qsl_rcvd`

Truthy values include `Y`, `YES`, `TRUE`, `1`, and `CONFIRMED`.

The cache TTL is about 300 seconds. On a newly logged QSO, `record_qso()` can hot-update the in-memory sets without waiting for a full reload.

## Call Status Rules

Call status is about the specific callsign, not the DXCC entity.

Inputs:

- `worked`: whether the call has ever been worked.
- `new_band`: whether this band is new for this call.
- `new_mode`: whether this mode is new for this call.
- `bandmode_confirmed`: whether this call is confirmed on this band+mode.

Output rules:

| Condition | `call_status` |
| --- | --- |
| Not worked before | `New Call` |
| Confirmed on this band+mode | `Confirmed` |
| Worked before and both band and mode are new | `New Band+Mode` |
| Worked before and band is new | `New Band` |
| Worked before and mode is new | `New Mode` |
| Otherwise worked before | `Worked` |

Current frontend call status filter options:

```text
New Call, New Band, New Mode, New Band+Mode, Worked, Confirmed
```

## DXCC Status Rules

DXCC status is about the ADIF/DXCC entity, using the resolved `dxcc` number.

Inputs:

- `worked`: whether this DXCC has ever been worked.
- `confirmed`: whether this DXCC is confirmed overall.
- `new_band`: whether this DXCC has not been worked on this band.
- `new_mode`: whether this DXCC has not been worked in this mode.
- `bandmode_confirmed`: whether this DXCC is confirmed on this band+mode.

Output rules:

| Condition | `dxcc_status` | `tag` |
| --- | --- | --- |
| Not worked before | `ATNO` | `ATNO` |
| Confirmed on this band+mode | `Confirmed` | empty |
| Confirmed overall, new band and new mode | `C/New Band+Mode` | `New band+mode` |
| Confirmed overall, new band | `C/New Band` | `New band` |
| Confirmed overall, new mode | `C/New Mode` | `New mode` |
| Worked overall, not confirmed overall, new band and new mode | `W/New Band+Mode` | `New band+mode` |
| Worked overall, not confirmed overall, new band | `W/New Band` | `New band` |
| Worked overall, not confirmed overall, new mode | `W/New Mode` | `New mode` |
| Worked but not confirmed and no new slot | `Worked` | `Need LoTW` |

If DXCC cannot be resolved, or if the local DXCC worked source is unavailable and unsafe fallback is disabled, the status is `Unknown`. This is intentional to avoid showing false `ATNO` rows while the QSO cache is warming or unavailable.

Current frontend DXCC status filter options:

```text
ATNO, C/New Band, C/New Mode, C/New Band+Mode,
W/New Band, W/New Mode, W/New Band+Mode,
Worked, Confirmed, Unknown
```

## Worked b4 Column

This is separate from `call_status`.

The browser loads:

```text
GET /api/wavelog-log/entries?limit=5000
```

It builds a map keyed by:

```text
CALL-BAND-MODE
```

Example:

```text
A31DX-20M-FT8
```

If a key exists, the table displays:

```text
worked DD/MM/YYYY
```

This column is only a quick display/filter helper for exact call+band+mode worked history. The authoritative status classification is still the backend `call_status` and `dxcc_status`.

## Special Stations and Activity Tags

There are two special-station systems.

### Simple Comment Tags

The backend extracts comma-separated `special` tags from the spot comment using these patterns:

| Tag | Pattern intent |
| --- | --- |
| `POTA` | `POTA` text or references like `K-1234`, `US-1234`, `XX-1234`. |
| `SOTA` | `SOTA` text or references like `XX/YY-123`. |
| `IOTA` | `IOTA` text or references like `EU-001`, `NA-123`. |
| `WWFF` | `WWFF` text or references like `OMFF-1234`. |
| `CASTLE` | `WCA`, `CASTLE`, or castle-style references. |
| `LIGHTHOUSE` | `LIGHTHOUSE` or `ARLHS`. |
| `CONTEST` | `CONTEST`. |
| `IARU` | `IARU`. |

The spot can contain multiple tags, for example:

```text
POTA, WWFF
```

The frontend splits on `, ` and renders one badge per tag.

### Activity Intelligence Tags

If Activity Intelligence is enabled, spots can also get:

- `activity_tags`
- `priority_score`
- `recommended_actions`
- `propagation`

Supported enrichments include:

- DXpeditions from configured DXpedition sources.
- Active or scheduled POTA, SOTA, WWFF, and ParksnPeaks references.
- New vs worked portable references by checking Wavelog fields such as `pota_ref`, `sota_ref`, and `wwff_ref`.
- Propagation tags using SWPC/NOAA data and RBN evidence.
- Duplicate tags for repeated live sightings.
- Recommended actions such as opening DXpedition details or filling portable reference fields in the log form.

The table's Special column shows simple `special` badges first, then up to three `activity_tags`, then a propagation badge if present.

## Scoring

The visible Score column uses:

```text
priority_score ?? spot_score ?? 0
```

### Base Spot Score

Base scoring returns 0-100 and reasons. It is calculated from DXCC status, call status, special tags, local decodes, RBL source, and RBL SNR.

DXCC weights:

| Status | Points | Reason |
| --- | ---: | --- |
| `ATNO` | 85 | ATNO |
| `C/New Band+Mode` | 68 | new confirmed DXCC band+mode |
| `W/New Band+Mode` | 62 | new worked DXCC band+mode |
| `C/New Band` | 58 | new confirmed DXCC band |
| `W/New Band` | 52 | new worked DXCC band |
| `C/New Mode` | 48 | new confirmed DXCC mode |
| `W/New Mode` | 42 | new worked DXCC mode |
| `Worked` | 18 | worked DXCC |
| `Confirmed` | 8 | confirmed DXCC |

Call weights:

| Status | Points | Reason |
| --- | ---: | --- |
| `New Call` | 42 | new call |
| `New Band+Mode` | 34 | new call band+mode |
| `New Band` | 28 | new call band |
| `New Mode` | 22 | new call mode |
| `Worked` | 8 | worked call |
| `Confirmed` | 4 | confirmed call |

Other base scoring:

| Condition | Points |
| --- | ---: |
| Any simple `special` tag | +14 |
| Decoded locally recently | +25 |
| RBL spot | +5 |
| RBL SNR >= 15 dB | +8 |
| RBL SNR >= 8 dB | +4 |
| RBL SNR < 0 dB | -6 |

Scores are clamped to 0-100. Only the first four base reasons are kept unless Activity Intelligence later replaces the reason list.

Score labels and colors:

| Score | Label | Style intent |
| ---: | --- | --- |
| >= 80 | Hot | red/danger |
| >= 55 | Good | amber |
| >= 30 | Watch | green |
| < 30 | Low | gray |

### Activity Intelligence Priority Score

Activity Intelligence starts with a default AI score of 20 and adds or subtracts configured weights:

| Signal | Default points |
| --- | ---: |
| Active DXpedition | +30 |
| DXpedition upcoming within 24h | +10 |
| Active portable reference | +20 |
| New portable reference | +25 |
| ATNO | +40 |
| Needed band slot | +25 |
| Propagation excellent | +15 |
| Propagation good | +10 |
| Propagation marginal | -8 |
| Propagation poor | -15 |
| Duplicate/repeated spot | -35 |

Final Activity Intelligence priority is:

```text
max(base_score, ai_score), clamped to 0-100
```

When Activity Intelligence enriches a spot, it writes the final value to both `priority_score` and `spot_score`.

### WSJT Planner Score

The WSJT planner uses a separate large-number score for automation target ordering. This does not directly drive the visible Score column.

Default planner scores:

| Target reason | Score |
| --- | ---: |
| Direct caller | 99999 |
| ATNO | 10000 |
| DXCC worked but not confirmed | 9000 |
| DXCC new band | 8000 |
| Non-EU new call | 7500 |
| Call new band | 6500 |
| Needed reference | 6000 |
| Grid | 5000 |
| New mode | 3500 |
| New call | 2000 |
| Worked or unneeded | 0 |

Use this only when implementing the FT8/FT4/FT2 planner behavior.

## Local Heard

The backend correlates spots with recent local decoded messages from the built-in FT8/FT4 service.

Rules:

- Compare decoded callsign with spot `callsign`.
- Default window is 600 seconds.
- If found, the spot gets:
  - `local_heard: true`
  - `local_heard_message`
  - `local_heard_snr`
  - `local_heard_at`
  - `local_heard_mode`
- Base score gets +25.
- The Mode column shows `HEARD` and SNR.

## Filtering

Default filter state:

```json
{
  "callsign": "",
  "bands": [],
  "modes": [],
  "continents": [],
  "cqs": [],
  "callStatuses": [],
  "dxccStatuses": [],
  "specials": [],
  "spotSources": ["cluster"],
  "rblModes": [],
  "rblMinSnr": "",
  "rblDedupeMinutes": 0,
  "sortBy": "time",
  "workedB4Include": false,
  "workedB4Exclude": false
}
```

Available values:

- Bands: `160m`, `80m`, `40m`, `30m`, `20m`, `17m`, `15m`, `12m`, `10m`, `6m`
- Modes: `CW`, `SSB`, `FT8`, `FT4`, `FT2`, `RTTY`, `PSK`, `DIGI`, `AM`, `FM`, `JT65`, `SSTV`
- Continents: `EU`, `NA`, `AS`, `AF`, `SA`, `OC`
- CQ zones: `1` through `75`
- Spot sources: `cluster`, `rbl`
- RBL groups: `CW`, `SSB`, `DIGI`
- Sort: `time` or `score`

Local cache filters:

- Callsign: case-insensitive substring match.
- Band: exact `band`.
- Mode: exact `mode`.
- Continent: `spotter_continent`, not DX country continent.
- CQ: string comparison against `cq`.
- Call status: exact `call_status`.
- DXCC status: exact `tag || dxcc_status`.
- Special: `special` contains selected value.
- Source: exact `spot_source`, defaulting to `cluster`.
- RBL group: only applied to RBL rows.
- Worked b4: checks the browser's `CALL-BAND-MODE` worked map.

Database-backed filters use:

```text
POST /api/spots/filtered-search
```

Request body:

```json
{
  "limit": 100,
  "callsign": "A31",
  "bands": ["20m"],
  "modes": ["FT8"],
  "zones_cq": [32],
  "continents": ["EU"],
  "special_tags": ["POTA"],
  "spot_sources": ["cluster", "rbl"],
  "rbl_modes": ["CW"],
  "rbl_min_snr": 8,
  "rbl_dedupe_minutes": 5,
  "max_age_minutes": 60,
  "sort_by": "score",
  "visual_map": false
}
```

Database search details:

- Callsign search is prefix-only: `UPPER(callsign) LIKE '<TERM>%'`.
- Bands, modes, CQ zones, continents, source, RBL groups, age, and special tags are applied in DuckDB.
- RBL minimum SNR and RBL de-dupe are applied after retrieval.
- If sorting by score, the backend fetches extra rows, enriches scores, sorts by `(spot_score, timestamp)` descending, then trims to limit.
- The browser still applies source/RBL filters, DXCC status filters, and Worked b4 filters locally after database results are returned.

Filter presets:

| Preset | Behavior |
| --- | --- |
| DX hunt | DXCC statuses `ATNO`, all C/W new band/mode statuses, sort by score. |
| RBL CW | Source `rbl`, RBL group `CW`, min SNR 8, de-dupe 5 minutes, sort by score. |
| Digital | Modes `FT8`, `FT4`, `FT2`, sort by score. |
| New DXCC | DXCC status `ATNO`, sort by score. |
| Worked | Worked b4 include. |

## Sorting

Sort by `time`:

- Keep newest-first order from live cache or database query.

Sort by `score`:

```text
spot_score descending, then timestamp descending
```

The frontend uses `getSpotScore()`, which reads `priority_score` first and `spot_score` second.

## Styling and Colors

Call status text colors:

| Status | Color |
| --- | --- |
| `New Call` | `#FF6B35` |
| `New Band` | `#00BFFF` |
| `New Mode` | `#FFC000` |
| `New Band+Mode` | `#E91E63` |
| `Worked` | `#B0B0B0` |
| `Confirmed` | `#10B981` |
| `Unknown` | `#666666` |

DXCC status text colors:

| Status | Color |
| --- | --- |
| `ATNO` | `#FF6B35` |
| `C/New Band` | `#4A9EFF` |
| `C/New Mode` | `#FFD93D` |
| `C/New Band+Mode` | `#9C27B0` |
| `W/New Band` | `#00BCD4` |
| `W/New Mode` | `#FFA726` |
| `W/New Band+Mode` | `#FF5722` |
| `Worked` | `#B0B0B0` |
| `Confirmed` | `#10B981` |
| `Unknown` | `#666666` |

Row class is based on `tag || dxcc_status`:

| Tag/status | Row class |
| --- | --- |
| `ATNO` | `spot-atno` |
| `New band` | `spot-new-band` |
| `New mode` | `spot-new-mode` |
| `New band+mode` | `spot-new-bandmode` |
| `Need LoTW` | `spot-need-lotw` |
| `Worked` | `spot-worked` |
| `Confirmed` | `spot-confirmed` |

SmartSDR panadapter DXCC colors use ARGB strings:

| DXCC status | Color |
| --- | --- |
| `ATNO` | `#FFFF8C00` |
| `Confirmed` | `#FF00D000` |
| `C/...New...` | `#FF32CD32` |
| `Worked` | `#FF0066FF` |
| `W/New Band+Mode` | `#FFFF00FF` |
| `W/New Band` | `#FF00FFFF` |
| `W/New Mode` | `#FFFFFF00` |
| `Unknown` | `#FFB0B0B0` |

SmartSDR call labels append a call-status abbreviation:

| Call status | Label |
| --- | --- |
| `New Call` | `(NC)` |
| `New Band` | `(NB)` |
| `New Mode` | `(NM)` |
| `New Band+Mode` | `(NB+NM)` |
| `Confirmed` | `(C)` |
| `Worked` | `(W)` |

## Important API Endpoints

### Live spots

```text
GET /api/spots
```

Returns current cache with optional query filters. It also refreshes uncertain DXCC classifications and enriches cached spots.

Optional query parameters:

- `band`
- `mode`
- `cq`
- `call_status`
- `dxcc_status`
- `special`

### Raw live cache

```text
GET /api/spots/live-cache?limit=250
```

Returns up to 500 current in-memory rows without expensive enrichment.

### Filtered historical search

```text
POST /api/spots/filtered-search
```

Searches `data/spots.duckdb` with the filter body described above.

### Explain one classification

```text
GET /api/spots/explain/{callsign}?band=20m&mode=FT8&frequency_khz=14074&comment=FT8
```

Returns:

- normalized inputs
- CTY lookup result
- call status and flags
- DXCC status and flags
- source labels
- QSO cache diagnostics

Use this endpoint for an iPad "why is this spot colored like this?" view.

### Spot source stats

```text
GET /api/spots/source-stats
GET /api/spots/source-stats?fast=true
```

Returns live and persisted counts for cluster/RBL monitoring.

### Tune to spot

```text
POST /api/spots/tune
```

Body:

```json
{
  "frequency": 14.074,
  "mode": "FT8"
}
```

The backend maps the spot mode to the radio mode and broadcasts the updated radio status.

## Persistent Spots Database

Spots are stored in `data/spots.duckdb`, table `spots`.

Important columns:

- `received_at`
- `date_utc`
- `time_utc`
- `frequency_khz`
- `callsign`
- `spotter`
- `comment`
- `band`
- `mode`
- `spot_source`
- `rbl_mode_group`
- `country`
- `zone_cq`
- `zone_itu`
- `continent`
- `special_tags`
- `call_status`
- `dxcc_status`
- `created_at`

The database stores computed classifications to avoid recomputing status during historical searches.

## Implementation Notes for iPad

Use the backend as the source of truth for:

- Band and mode.
- Country, DXCC, CQ/ITU zones, continent, coordinates.
- `call_status`.
- `dxcc_status`.
- `tag`.
- `special`.
- `spot_score` / `priority_score`.
- RBL aggregation fields.
- Local heard fields.
- Activity Intelligence tags.

The iPad client should implement:

- WebSocket consumption of `spots`.
- Local merge/update by `aggregate_key` when provided, otherwise by the same live keys.
- The 15-column table or a mobile equivalent preserving the same fields.
- Filter state compatible with the JSON shown above.
- `GET /api/spots/explain/{callsign}` for detail/explain view.
- `POST /api/spots/filtered-search` for history/filter searches beyond the live cache.
- `GET /api/wavelog-log/entries?limit=5000` only if the mobile UI needs the exact Worked b4 column. It should use the same `CALL-BAND-MODE` key.

Avoid recalculating Wavelog statuses in the client unless you are intentionally porting the whole classifier. The existing backend has several safeguards, especially around DXCC worked-vs-confirmed status and cache-unavailable cases.
