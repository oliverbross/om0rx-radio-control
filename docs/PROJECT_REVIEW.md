# OM0RX Radio Control Project Review

Date: 2026-05-26
Branch reviewed: `codex/project-cleanup`

This document is the baseline technical review for the project after the cleanup and architecture
polish passes. It describes how the project is currently structured, how it starts, where important
runtime state lives, what was fixed during review, and what should be improved before adding new
features.

## Current Project Shape

OM0RX Radio Control is a local station-control application for a FlexRadio-based station. It combines:

- A FastAPI backend in `backend/`.
- A service layer in `services/`.
- Core radio, cluster, logging, Wavelog, QRZ, CTY, and ADIF logic in `radio_control/`.
- A browser-based frontend in `frontend/`.
- A Node.js bridge in `bridge/` for SDC Skimmer TCP traffic and WSJT-X UDP traffic.
- Runtime data in `data/`, logs in `logs/`, tracked non-secret settings in `settings/`, and local secrets in ignored `config_local.py` or `settings/local_secrets.json`.

The primary user entry point is:

```powershell
.\start_all.ps1
```

That script starts:

1. `bridge/sdc-bridge-server.js`
2. `uvicorn backend.main:app`
3. `scripts/launch/launch_windows.py`

## Runtime Architecture

```mermaid
flowchart LR
    Start["start_all.ps1"] --> Bridge["Node bridge: SDC TCP + WSJT-X UDP"]
    Start --> Backend["FastAPI backend.main:app"]
    Start --> Launcher["window launcher"]
    Backend --> Core["backend.core app/state"]
    Backend --> API["backend.api routers"]
    Backend --> Services["services layer"]
    Services --> Radio["FlexRadio control"]
    Services --> Rotor["Rotator service"]
    Services --> Wavelog["Wavelog API + MySQL sync"]
    Services --> QRZ["QRZ lookup"]
    Services --> ADIF["Local ADIF backup"]
    Backend --> Frontend["frontend static files"]
    Bridge --> Frontend
    Backend --> Frontend
```

Important ownership boundaries:

- `backend/main.py` orchestrates startup, dependency creation, route registration, and shutdown.
- `backend/core/__init__.py` owns the FastAPI app object, shared runtime state declarations, validation handling, and rotor settings bootstrap only.
- `services/` contains backend service behavior, but some services still use module-level globals.
- `radio_control/config.py` centralizes defaults and project-relative paths, then layers `config_local.py`, JSON runtime settings, ignored local secrets, and environment overrides.
- `settings/app_settings.json` persists non-secret runtime settings, including rotor AUTO and FT8 settings.

## What Was Fixed During This Review

These were review findings that were low-risk enough to fix immediately:

- Fixed lazy imports that still referenced pre-package root modules such as `utils`, `spots_logger`, `wavelog_api`, and `config`.
- Fixed WSJT-X auto-rotate dependency wiring so it receives the high-level `RotatorService`, not the raw `RotorController`.
- Fixed WSJT-X auto-rotate band conversion from Hz to kHz and made rotor band config support the current boolean settings format.
- Added missing `/api/rotor/auto/bearing` alias used by the frontend.
- Removed duplicate `/api/ft8/config` handlers and moved FT8 config persistence into the shared settings model.
- Fixed `WavelogDuckDBSync` and legacy `ADIFSyncManager` default DuckDB paths to use `config.DATA_DIR`.
- Fixed WSJT-X parser frequency values to return JavaScript numbers instead of BigInt values.
- Fixed `tests/smoke/test_ft8_files.py` to look at the real root `frontend/` directory.
- Aligned Python package metadata version with the app/package version: `2.0.0`.
- Removed deprecated route handlers, startup handlers, duplicate Pydantic models, and copied background workers from `backend/core/__init__.py`.
- Moved Wavelog periodic background task startup to import directly from `radio_control/wavelog_duckdb_sync.py`.
- Removed the remaining duplicate `GET /api/sync-status` registration and made the route report from the active Wavelog sync manager.
- Replaced `/api/config` source-code writes with JSON-backed runtime settings in `settings/app_settings.json` and ignored `settings/local_secrets.json`.
- Updated legacy config helpers to use the same JSON settings store instead of editing `radio_control/config.py`.
- Hardened launch scripts to bind the backend to `127.0.0.1` by default and make Uvicorn reload a development-mode opt-in.
- Updated window launchers to respect `BACKEND_HOST` and `BACKEND_PORT` instead of hard-coded localhost URLs.
- Restricted default CORS origins to local UI origins and added `CORS_ALLOWED_ORIGINS` for explicit overrides.
- Consolidated rotor AUTO and FT8 config persistence into `settings/app_settings.json`, with legacy JSON read fallback only.
- Added a lifecycle-aware startup supervisor: backend restart/shutdown endpoints now write an ignored runtime request file and exit, while `start_all.ps1` or `scripts/start/start_services_only.ps1` owns restarting sibling bridge/backend processes.
- Added `scripts/maintenance/check_project.ps1` as the fast local quality gate and exposed it through `npm run check`.
- Introduced `backend.core.context.AppContext` as the explicit runtime context and wired backend startup, health/status, Wavelog sync status, server-control cleanup, and WebSocket ownership through it.
- Removed remaining active-tree legacy product strings from maintained code and tightened the quality-gate stale-reference scan.
- Added frontend/backend endpoint contract smoke checks and restored the missing spots database stats/special endpoints used by the frontend.
- Replaced direct WebSocket client list mutation with a `ConnectionManager` that broadcasts from snapshots, cleans stale clients centrally, and is exposed through `AppContext`.
- Moved background task dependencies into a configured `BackgroundTaskService` that reads from `AppContext` instead of copied module globals.
- Moved radio endpoint dependencies into an explicit `RadioControlState` instead of raw module-level `flex` and broadcaster globals.
- Moved live station diagnostics out of `tests/smoke/` into `tests/live/`, leaving `tests/smoke/` as the safe local test subset.
- Added `docs/TESTING.md` to document default checks, safe smoke tests, and live diagnostics.
- Hardened Wavelog initial sync to use keyset pagination and report the last sync failure in status responses.
- Removed the unused legacy `services/spots.py` duplicate now that active spots endpoints live in `backend/api/spots.py` and cluster spot processing lives in `services/background_tasks.py`.

## Review Findings

### P2: Runtime State Still Has Some Legacy Compatibility Surface

State exists in:

- `backend.core.context.AppContext`.
- legacy `backend.core` compatibility globals.
- legacy `app.state.*` attributes synchronized from the context.
- module-level singleton services such as FT8, ADIF, Wavelog, WSJT-X, and rotor.

Examples:

- `backend/main.py:68`
- `backend/main.py:307`
- `services/ft8_service.py`
- `services/wsjtx.py`

Risk:

- Dependency ownership is clearer at the app boundary, but some services still expose process-wide singletons.
- Some tests still import and mutate process-global state.
- Registering routes more than once can duplicate handlers.
- Shutdown and reconnect behavior is hard to verify.

Recommended fix:

- Continue moving service dependencies onto `AppContext`.
- Replace service-level global setters with constructor or FastAPI dependency injection where practical.
- Keep legacy `app.state.*` compatibility only while routers migrate.

### P2: Frontend Is Functional But Too Large And Untyped

The frontend is mostly static JS with a very large `app-main.js`, direct DOM access, and many direct `fetch()` calls.

Current progress:

- `solar-data.js` owns Vue solar state, refresh, and HF condition formatting.
- `wavelog-stats.js` owns Vue Wavelog dashboard statistics state, loading, and mode consolidation.
- `docs/FRONTEND.md` now documents the active no-build module pattern and script-order contract.

Risk:

- API contract changes are easy to miss.
- UI state and transport code are tightly coupled.
- There is no lint/type check/build gate.

Recommended fix:

- Keep the current no-build app for now, but split frontend code by domain:
  - API client module
  - WebSocket client module
  - radio controls
  - rotor controls
  - logging
  - FT8
  - modals
- Add lightweight contract tests for fetch endpoints used by the frontend.

### P3: Wavelog Sync Still Needs Deeper Integration Coverage

`radio_control/wavelog_duckdb_sync.py` now writes to the correct project data directory,
uses keyset pagination for initial sync, and reports last sync failures. Remaining risk areas:

- Sync metadata assumes `last_modified` is reliable and monotonic.
- Database connections are opened per batch and should be reviewed for timeout and error behavior.

References:

- `radio_control/wavelog_duckdb_sync.py:198`
- `radio_control/wavelog_duckdb_sync.py:316`
- `radio_control/wavelog_duckdb_sync.py:505`

Recommended follow-up:

- Add tests for incremental sync edge cases.
- Review Wavelog MySQL connection timeouts and retry behavior.

### P3: Dependency And Metadata Management Is Duplicated

Dependencies are listed in both `requirements.txt` and `pyproject.toml`.

Risk:

- Versions can drift.
- Developers may install a different set depending on which file they use.

Recommended fix:

- Choose `pyproject.toml` as the source of truth.
- Keep `requirements.txt` generated or clearly documented as a compatibility install path.
- Add dev dependencies separately.

## Verification Performed

Passed:

- Python syntax check across maintained Python files.
- PowerShell parser check across tracked `.ps1` files.
- Bash syntax check for `scripts/start/start_webapp.sh`.
- Node syntax check for bridge scripts and live WSJT-X diagnostics.
- `npm audit --omit=dev`.
- `python -c "import backend.main"`.
- FastAPI route-table duplicate scan.
- `python -m pip install -e . --dry-run`.
- `python scripts\maintenance\check_sync_status.py`.
- `python tests\smoke\test_ft8_files.py`.
- `python tests\live\test_qth_data.py`.
- `python tests\smoke\test_config_save.py`.
- `python tests\smoke\test_app_context.py`.
- `python tests\smoke\test_lifecycle_contract.py`.
- `python tests\smoke\test_frontend_contracts.py`.
- `python tests\smoke\test_service_dependency_state.py`.
- `python tests\smoke\test_wavelog_sync_pagination.py`.
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\maintenance\check_project.ps1`.
- `node tests\live\test-wsjtx-udp.js` received live WSJT-X packets.

Not run by default because they need local station resources:

- MySQL-backed Wavelog diagnostics.
- Audio-device FT8 diagnostics.
- Live WSJT-X packet checks.

## Recommended Next Work

Do these before adding new features:

1. Split the largest frontend modules now that backend contracts are covered.
2. Continue extracting cohesive `app-main.js` domains, starting with configuration, QRZ/DXCC lookup, and previous-QSO state.
3. Add a frontend lint/type-check strategy appropriate for the no-build app.
4. Add deeper Wavelog incremental sync tests and review MySQL timeout/retry behavior.
5. Decide whether `requirements.txt` remains a compatibility file or becomes generated from `pyproject.toml`.

## Development Standards Going Forward

- Do not add new runtime files at the project root unless they are true root-level project metadata.
- Keep station-specific secrets out of Git.
- New backend endpoints should live in `backend/api/` and call service-layer code.
- Shared station/domain logic should live in `radio_control/`.
- Service objects should receive dependencies explicitly where possible.
- Every bug fix should include either a smoke check, a unit test, or a documented manual verification.
- Hardware/live-radio checks should be marked separately from pure tests.
- Avoid adding another global singleton unless there is no practical alternative.
