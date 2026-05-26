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
- `settings/rotor_config.json` persists non-secret rotor AUTO settings.

## What Was Fixed During This Review

These were review findings that were low-risk enough to fix immediately:

- Fixed lazy imports that still referenced pre-package root modules such as `utils`, `spots_logger`, `wavelog_api`, and `config`.
- Fixed WSJT-X auto-rotate dependency wiring so it receives the high-level `RotatorService`, not the raw `RotorController`.
- Fixed WSJT-X auto-rotate band conversion from Hz to kHz and made rotor band config support the current boolean settings format.
- Added missing `/api/rotor/auto/bearing` alias used by the frontend.
- Removed duplicate `/api/ft8/config` handlers and moved FT8 config persistence to `config.LOGS_DIR`.
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
- Updated window launchers to respect `BACKEND_HOST` and `BACKEND_PORT` instead of hard-coded `localhost:8000`.

## Review Findings

### P1: CORS Is Wide Open With Credentials Enabled

`backend/core/__init__.py` configures:

- `allow_origins=["*"]`
- `allow_credentials=True`

References:

- `backend/core/__init__.py:67`
- `backend/core/__init__.py:68`

Risk:

- For a radio-control app, broad browser access is not a good default.
- If the API is reachable on the LAN, another page could potentially interact with local control endpoints.

Recommended fix:

- Restrict origins to `http://localhost:8000`, `http://127.0.0.1:8000`, and any explicitly configured local UI origins.
- Keep no-auth endpoints local-only unless deliberate remote access is added later.

### P2: Runtime State Is Spread Across Globals, App State, And Setters

State exists in:

- `backend.core` globals.
- `app.state`.
- `services.radio` globals.
- `services.websocket.websocket_clients`.
- `services.background_tasks` globals.
- module-level singleton services such as FT8, ADIF, Wavelog, WSJT-X, and rotor.

Examples:

- `backend/main.py:281`
- `backend/main.py:285`
- `services/websocket.py:14`
- `services/background_tasks.py:49`
- `services/radio.py:469`

Risk:

- Dependency ownership is unclear.
- Tests must import and mutate globals.
- Registering routes more than once can duplicate handlers.
- Shutdown and reconnect behavior is hard to verify.

Recommended fix:

- Introduce an `AppContext` dataclass or dependency container.
- Put runtime service instances in `app.state.context`.
- Inject dependencies through FastAPI dependencies or service constructors.

### P2: WebSocket Broadcast Lists Are Not Protected

`services/websocket.py` keeps clients in a mutable list and removes disconnected clients while other broadcasts may be iterating:

- `services/websocket.py:14`
- `services/websocket.py:25`
- `services/websocket.py:32`
- `services/websocket.py:44`
- `services/websocket.py:51`

Risk:

- Concurrent broadcasts can mutate the same list.
- A stale client may survive or a client may be removed twice.

Recommended fix:

- Use a `ConnectionManager` class with an `asyncio.Lock`.
- Store clients in a `set`.
- Send from a snapshot and handle disconnect cleanup centrally.

### P2: Shutdown/Restart Endpoints Need A Clear Ownership Model

Shutdown and restart endpoints call `os.kill(os.getpid(), signal.SIGTERM)`:

- `backend/api/server_control.py:113`
- `backend/api/server_control.py:158`
- `backend/api/server_control.py:167`
- `backend/api/server_control.py:212`

Risk:

- Under Uvicorn reload, SIGTERM may target the worker process while the reloader remains.
- Under `start_all.ps1`, the Node bridge and launcher are sibling processes, not children owned by the backend.
- UI restart may not restart the whole app consistently.

Recommended fix:

- Treat process lifecycle as the launcher’s responsibility.
- Backend shutdown endpoint should request shutdown, not own full app restart.
- Build a small local supervisor script/module if restart from UI is required.

### P2: Tests Are Not Yet A Reliable Gate

Current state:

- Python syntax checks pass.
- Node syntax checks pass.
- PowerShell parser checks pass.
- `npm audit --omit=dev` passes.
- Standalone smoke scripts run, but `pytest` is not installed.
- `pyproject.toml` now declares a `dev` optional dependency group for `pytest` and `ruff`.

Observed:

```text
python -m pytest tests\smoke -q
C:\Python314\python.exe: No module named pytest
```

Risk:

- The repository has pytest configuration, but no declared test dependency.
- Some smoke scripts depend on live station state or local data.
- There is no single reliable command for developers to run before changes.

Recommended fix:

- Install dev tooling with `python -m pip install -e .[dev]`.
- Separate pure unit tests from hardware/live integration checks.
- Add a `scripts/maintenance/check_project.ps1` quality gate.

### P2: Frontend Is Functional But Too Large And Untyped

The frontend is mostly static JS with a very large `app-main.js`, direct DOM access, and many direct `fetch()` calls.

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

### P2: Wavelog Sync Is Operational But Needs Hardening

`radio_control/wavelog_duckdb_sync.py` now writes to the correct project data directory. The sync logic is clear, but still has risk areas:

- Initial sync uses `LIMIT/OFFSET`, which can become slow on large tables.
- Sync metadata assumes `last_modified` is reliable and monotonic.
- Database connections are opened per batch and should be reviewed for timeout and error behavior.

References:

- `radio_control/wavelog_duckdb_sync.py:198`
- `radio_control/wavelog_duckdb_sync.py:316`
- `radio_control/wavelog_duckdb_sync.py:505`

Recommended fix:

- Prefer keyset pagination for initial sync.
- Add tests for incremental sync edge cases.
- Add explicit status for failed sync versus no changes.

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
- Node syntax check for bridge and WSJT-X smoke scripts.
- `npm audit --omit=dev`.
- `python -c "import backend.main"`.
- FastAPI route-table duplicate scan.
- `python -m pip install -e . --dry-run`.
- `python scripts\maintenance\check_sync_status.py`.
- `python tests\smoke\test_ft8_files.py`.
- `python tests\smoke\test_qth_data.py`.
- `python tests\smoke\test_config_save.py`.
- `node tests\smoke\test-wsjtx-udp.js` received live WSJT-X packets.

Not passed because tooling is missing:

- `python -m pytest tests\smoke -q`

## Recommended Next Work

Do these before adding new features:

1. Restrict CORS defaults for local radio-control use.
2. Consolidate remaining config persistence files, especially `settings/rotor_config.json` and `logs/ft8_config.json`, under the settings model.
3. Add a controlled process supervisor if UI-triggered whole-app restart remains required.
4. Add a real project quality gate script and declare dev/test dependencies.
5. Introduce an app context/dependency container to reduce module globals.
6. Add endpoint contract tests for all frontend fetch/WebSocket paths.
7. Split the largest frontend modules after backend contracts are stable.

## Development Standards Going Forward

- Do not add new runtime files at the project root unless they are true root-level project metadata.
- Keep station-specific secrets out of Git.
- New backend endpoints should live in `backend/api/` and call service-layer code.
- Shared station/domain logic should live in `radio_control/`.
- Service objects should receive dependencies explicitly where possible.
- Every bug fix should include either a smoke check, a unit test, or a documented manual verification.
- Hardware/live-radio checks should be marked separately from pure tests.
- Avoid adding another global singleton unless there is no practical alternative.
