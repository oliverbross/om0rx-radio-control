# OM0RX WSJT-X Engine Patch

This directory contains the local WSJT-X Improved patch used to turn the
proven WSJT engine into an automation target for OM0RX Radio Control.

See `WSJTZ_AUTOMATION_PORTING.md` for the WSJT-Z automation source map and the
planned backend porting strategy.

## Patch

- `om0rx-start-target-qso.patch`

Apply it from the root of the WSJT-X Improved source tree:

```powershell
git apply --unidiff-zero C:\Projects\om0rx-radio-control\docs\wsjtx\om0rx-start-target-qso.patch
```

The patch adds UDP message type `17` (`OM0RXStartTargetQSO`). The payload is a
UTF-8 JSON object, wrapped by the normal WSJT-X UDP binary header. It does not
change existing WSJT-X UDP behavior; standard `Reply` remains limited to prior
CQ/QRZ decodes.

On Windows, the patch also makes OmniRig support optional. This lets the engine
build in the JTSDK/MSYS2 toolchain without requiring a local OmniRig COM
installation. The OM0RX build scripts keep OmniRig disabled and use Hamlib/CAT
for rig control.

## Windows Build

The expected Windows toolchain is JTSDK64 Tools with MSYS2 packages for Qt5,
Boost, FFTW, Hamlib, and Fortran support. From the OM0RX project root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\wsjtx\prepare_om0rx_wsjtx.ps1 -Force
powershell -ExecutionPolicy Bypass -File scripts\wsjtx\build_om0rx_wsjtx.ps1 -InstallMissingDependencies
```

The resulting engine is written to:

```text
data\build\wsjtx-improved-om0rx\build-msys\wsjtx.exe
data\build\wsjtx-improved-om0rx\build-msys\jt9.exe
```

To start the patched engine in a separate test configuration:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\wsjtx\run_om0rx_wsjtx.ps1 -TestMode
```

The launcher verifies both executables are present, refuses duplicate starts for
the same profile, clears stale test-profile lock files when no matching instance
is running, and writes startup logs to
`logs\wsjt-x-om0rx-auto-test.out.log` and
`logs\wsjt-x-om0rx-auto-test.err.log`.

In the patched WSJT-X settings, enable UDP request handling before sending
automation target commands from OM0RX Radio Control.

## WSJT-Z Enrichment Build

The WSJT-Z side-by-side build uses upstream `sq9fve/wsjt-z` plus the local
`om0rx-wsjtz-enrichment.patch`. It adds OM0RX Wavelog enrichment display,
compact `CS` and `DS` columns in the RX/TX decode panes, a right-click previous
QSO popup, and the OM0RX hunter priority layer for Auto Call candidate ranking.
Use `docs/wsjtx/WSJTZ_OM0RX_SOURCE_OF_TRUTH.md` as the source of truth for the
current behavior and any differences from upstream WSJT-Z.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\wsjtz\prepare_om0rx_wsjtz.ps1 -Force
powershell -ExecutionPolicy Bypass -File scripts\wsjtz\build_om0rx_wsjtz.ps1 -InstallMissingDependencies
```

The resulting side-by-side engine is written to:

```text
data\build\wsjt-z-om0rx\build-msys\wsjt-z.exe
data\build\wsjt-z-om0rx\build-msys\jt9.exe
```

To start WSJT-Z outside the web UI:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\wsjtz\run_om0rx_wsjtz.ps1
```

## Target Payload

The app sends:

```json
{
  "version": 1,
  "target": {
    "call": "E51ABC",
    "grid": "BG08",
    "mode": "FT8",
    "dialFrequency": 14074000,
    "rxDf": 1240,
    "txDf": 1500,
    "trPeriod": 15,
    "holdTxFreq": true,
    "enableTx": true
  }
}
```

Supported fields:

- `call` / `dxCall`
- `grid` / `dxGrid`
- `mode`
- `dialFrequency` in Hz
- `rxDf`
- `txDf`
- `trPeriod`
- `frequencyTolerance`
- `submode`
- `fastMode`
- `generateMessages`
- `holdTxFreq`
- `txFirst`
- `txMessageNumber`
- `enableTx`

The patched engine maps these into native WSJT-X controls, generates messages,
selects the requested TX message, and arms Enable Tx through the normal UI state
machine.
