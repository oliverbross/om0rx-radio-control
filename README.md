# OM0RX Radio Control

Self-contained local control app for a FlexRadio station. The app combines a FastAPI backend, a browser-based frontend, a Node.js bridge for SDC/WSJT-X traffic, Wavelog/QRZ lookup and logging services, rotor controls, and FT8 support.

## Start

### Independent remote-station agent

For the dedicated Windows-to-macOS FLEX/KPA500/KAT500 bridge, use the
independent remote-station agent. It starts only the hardware and guarded
station services, has a separate configuration, and does not require the full
OM0RX Radio Control application to be running. See
[`docs/REMOTE_STATION_AGENT.md`](docs/REMOTE_STATION_AGENT.md).
Install its smaller dependency set with `requirements-remote-agent.txt`.
Cross-machine diagnosis and acceptance evidence is coordinated through
[`docs/REMOTE_STATION_HANDOFF.md`](docs/REMOTE_STATION_HANDOFF.md). Keep that
record free of credentials and update it whenever Windows or macOS changes the
remote-station implementation or its verified state.

The independent remote-station tray includes its own complete Settings window
for FLEX/KPA500/KAT500 connections, per-band antenna and RF policy, tuning
limits, credentials, and commissioning. It also exposes guarded station
Standby/Operate/Tune/Cancel controls, so normal operation does not require
PowerShell or direct JSON editing.

### Windows tray agent

The preferred Windows entry point is the OM0RX tray agent. It runs in the hidden-icons area, starts the local runtime, monitors the backend, bridge, Docker/Postgres, WSJT/SDC processes, WebSocket bridge ports, and exposes manual Start/Stop/Restart/Repair controls.

Build it:

```powershell
.\scripts\agent\build_agent.ps1
```

Run it:

```powershell
.\scripts\agent\run_agent.ps1 -Port 8080
```

Start it detached so PowerShell can be closed:

```powershell
.\scripts\agent\start_agent.ps1 -Port 8080
```

Create Desktop and Start Menu shortcuts:

```powershell
.\scripts\agent\install_agent_shortcuts.ps1 -Port 8080
```

Install it for Windows user login:

```powershell
.\scripts\agent\install_agent_startup.ps1 -Port 8080
```

Remove the Windows startup entry:

```powershell
.\scripts\agent\uninstall_agent_startup.ps1
```

The tray icon changes color by status. Double-click it to open the status window, or right-click it for Start All, Stop All, Restart All, Repair, Open Web UI, Logs, Settings, Auto Restart, and Start with Windows.

Agent settings can also start OM0RX WSJT-Z after the backend/bridge are healthy and optionally enable Auto Call through the backend FT8 TX controls.

When `Remember app window positions` is enabled, native launcher windows persist their last size and position in `settings/window_layout.json`.

The Windows executable and shortcuts use a generated OM0RX radio icon from `tools/Om0rxAgent/assets/om0rx-agent.ico`.

The agent stores its settings under `%APPDATA%\OM0RX Radio Control\Agent\agent-settings.json` and writes its own log to `logs/om0rx-agent.log`.

### PowerShell supervisor

Run the full local application from the project root:

```powershell
.\start_all.ps1
```

That script starts the Node bridge, FastAPI backend, and desktop/browser launcher using paths relative to this repository. It binds the backend to `127.0.0.1:8080` by default and does not use Uvicorn reload unless development mode is requested:

```powershell
.\start_all.ps1 -AppEnv development -Reload
```

The backend only allows browser origins for the local UI by default. For deliberate remote access, set `CORS_ALLOWED_ORIGINS` to a comma-separated list or JSON array in the environment, `config_local.py`, or the settings store.

`start_all.ps1` is also the local lifecycle supervisor. UI restart requests are written to an ignored runtime request file under `logs/` and handled by the launcher script, so the backend no longer tries to restart sibling processes by itself. Restart and shutdown controls are disabled while Uvicorn reload mode is active.

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

`config_local.py` is intentionally ignored by Git. Keep station-specific credentials, API keys, database passwords, and local bootstrap overrides there or in environment variables. The web configuration dialog persists non-secret runtime settings to `settings/app_settings.json` and secret-bearing values to ignored `settings/local_secrets.json`. Runtime settings override `config_local.py`; environment variables override both.

Rotor AUTO, FT8, and Elecraft KPA500/KAT500 settings are part of `settings/app_settings.json`. Older `settings/rotor_config.json` and `logs/ft8_config.json` files are treated as legacy fallback inputs only. See `docs/ELECRAFT_INTEGRATION.md` for the recommended VSPE shared-port topology and first-run procedure.

## Project Layout

```text
backend/          FastAPI app, route modules, backend helpers
bridge/           Node.js SDC and WSJT-X bridge
frontend/         Browser UI assets
radio_control/    Core Python package for station, radio, logging, and integration logic
services/         Backend service modules used by FastAPI routes
settings/         Tracked non-secret runtime settings
scripts/launch/   Desktop/browser launcher helpers
scripts/start/    Alternate service startup scripts
scripts/maintenance/ Maintenance and database utility scripts
tests/smoke/      Lightweight smoke checks
docs/             Current docs, references, and archived notes
vendor/           Vendored/reference source used for local development
data/             Tracked static data plus ignored runtime databases
logs/             Ignored runtime logs
```

## Main Runtime Pieces

- `start_all.ps1` is the primary entry point.
- `backend/main.py` runs the FastAPI application.
- `bridge/sdc-bridge-server.js` handles SDC/WSJT-X bridge traffic.
- `radio_control/config.py` contains defaults and loads overrides from `config_local.py`, `settings/app_settings.json`, ignored `settings/local_secrets.json`, and environment variables.
- `frontend/index.html` is the main browser UI.
- `docs/FRONTEND.md` documents the no-build frontend module pattern and script-order contract.

## Quality Gate

Run the fast local project check before committing:

```powershell
.\scripts\maintenance\check_project.ps1
```

The default gate runs syntax checks, backend import checks, duplicate route scanning, safe smoke checks, stale project-reference scanning, and Git whitespace checks. Optional live or network checks are explicit:

```powershell
.\scripts\maintenance\check_project.ps1 -IncludeLive
.\scripts\maintenance\check_project.ps1 -IncludeNpmAudit
```

## Cleanup Notes

Legacy implementation notes, historical troubleshooting files, and one-off diagnostics are archived under `docs/archive/`. They are kept out of the project root and active test tree so the maintained code is easier to navigate while still preserving useful context.

## Project Review

See `docs/PROJECT_REVIEW.md` for the current architecture review, verified checks, fixed review findings, and recommended next cleanup work before new feature development.
