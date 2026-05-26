# Testing

The project keeps safe local checks separate from station-specific diagnostics.

## Default Project Gate

Run the standard gate before committing backend, frontend, script, or config changes:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\maintenance\check_project.ps1
```

This runs syntax checks, backend import checks, duplicate route checks, safe smoke scripts, the
stale project reference scan, and `git diff --check`.

## Safe Smoke Tests

Safe tests live in `tests/smoke/`. They must not require live radio hardware, MySQL, audio devices,
WSJT-X traffic, network access, or writes to station logs.

When `pytest` is installed, the safe subset is:

```powershell
python -m pytest tests\smoke -q
```

## Live Diagnostics

Live diagnostics live in `tests/live/`. They may require local station services, audio devices,
Wavelog database access, WSJT-X UDP packets, or real runtime files.

Run them intentionally, either one by one or through:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\maintenance\check_project.ps1 -IncludeLive
```
