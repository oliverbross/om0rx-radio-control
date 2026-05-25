# OM0RX Radio Control

Self-contained local control app for a FlexRadio station. The app combines a FastAPI backend, a browser-based frontend, a Node.js bridge for SDC/WSJT-X traffic, Wavelog/QRZ lookup and logging services, rotor controls, and FT8 support.

## Start

Run the full local application from the project root:

```powershell
.\start_all.ps1
```

That script starts the Node bridge, FastAPI backend, and desktop/browser launcher using paths relative to this repository. It should not depend on any older checkout.

## Setup

Install Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

Install Node dependencies:

```powershell
npm install
```

Create local configuration from the example:

```powershell
Copy-Item config_local.example.py config_local.py
```

`config_local.py` is intentionally ignored by Git. Keep station-specific credentials, API keys, database passwords, radio IPs, and local overrides there or in environment variables.

## Project Layout

```text
backend/          FastAPI app, route modules, backend helpers
bridge/           Node.js SDC and WSJT-X bridge
frontend/         Browser UI assets
services/         Backend service modules used by FastAPI routes
scripts/launch/   Desktop/browser launcher helpers
scripts/start/    Alternate service startup scripts
scripts/maintenance/ Maintenance and database utility scripts
tests/smoke/      Lightweight smoke checks
tests/diagnostics/ Historical diagnostic scripts
docs/             Current docs, references, and archived notes
vendor/           Vendored/reference source used for local development
data/             Tracked static data plus ignored runtime databases
logs/             Ignored runtime logs
```

## Main Runtime Pieces

- `start_all.ps1` is the primary entry point.
- `backend/main.py` runs the FastAPI application.
- `bridge/sdc-bridge-server.js` handles SDC/WSJT-X bridge traffic.
- `config.py` contains defaults and loads overrides from environment variables or `config_local.py`.
- `frontend/index.html` is the main browser UI.

## Cleanup Notes

Legacy implementation notes and historical troubleshooting files are archived under `docs/archive/`. They are kept out of the project root so the active code is easier to navigate while still preserving useful context.
