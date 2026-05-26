# OM0RX Radio Control Repository Information

## Project Overview

OM0RX Radio Control is a self-contained local control app for a FlexRadio station.
It combines a FastAPI backend, browser frontend, Node.js bridge for SDC/WSJT-X
traffic, Wavelog/QRZ integrations, rotor controls, and FT8 support.

## Technology Stack

- Frontend: static HTML, Vue.js 3 from CDN, and vanilla JavaScript modules
- Backend: Python FastAPI with WebSocket support
- Bridge: Node.js WebSocket/TCP/UDP bridge in `bridge/`
- Radio interface: FlexRadio SmartSDR helpers in `radio_control/`
- Runtime data: `data/`, `logs/`, and `settings/`

## Project Structure

```text
om0rx-radio-control/
├── backend/          FastAPI app and route modules
├── bridge/           Node.js SDC and WSJT-X bridge
├── frontend/         Browser UI assets
├── radio_control/    Core station, radio, logging, and integration logic
├── services/         Backend service modules
├── settings/         Tracked non-secret runtime settings
├── scripts/          Launch, startup, and maintenance scripts
├── tests/smoke/      Lightweight smoke checks
├── docs/             Current docs and archived notes
├── data/             Static data plus ignored runtime databases
└── logs/             Ignored runtime logs
```

## Development Guidelines

1. Keep the project self-contained under `C:\Projects\om0rx-radio-control`.
2. Use `.\start_all.ps1` as the primary local entry point.
3. Keep station-specific secrets in ignored `config_local.py` or `settings/local_secrets.json`.
4. Persist non-secret runtime settings in `settings/app_settings.json`.
5. Put maintained documentation in `docs/`, not the project root.
6. Put smoke checks in `tests/smoke/`.
7. Do not add new root-level runtime files unless they are true project metadata.

## Important Files

- `start_all.ps1`: primary local supervisor and launcher
- `backend/main.py`: FastAPI application entry point
- `backend/api/`: API routers
- `bridge/sdc-bridge-server.js`: SDC/WSJT-X bridge
- `radio_control/config.py`: defaults plus layered overrides
- `settings/app_settings.json`: tracked non-secret runtime settings
- `docs/PROJECT_REVIEW.md`: current architecture review and next work

## Testing

- Python syntax check: compile maintained Python directories.
- Smoke checks: run targeted scripts in `tests/smoke/`.
- PowerShell parser check: parse tracked `.ps1` files before startup script changes.
- Start application: `.\start_all.ps1`.
