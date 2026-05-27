# DIGITAL Release Architecture

This document freezes the production DIGITAL architecture for FT8 and FT4. It is intended for operators and developers validating the current release shape.

## Supported Path

- Production modes: FT8 and FT4.
- Backend API namespace: `/api/ft8` for historical compatibility. The implementation is mode-aware and shared by FT8 and FT4.
- Core owner: `services/ft8_service.py`.
- Automation scoring and candidate collection: `services/digital_automation.py`.
- TX boundary: `services/ft8_tx.py`.
- QSO logging and persistent dedupe: `services/qso_logging.py`.

FT2, SuperFox, and Fox/Hound automation are non-goals for this frozen release. Do not enable new behavior for those modes without a separate design and test pass.

## Ownership Rules

The backend is authoritative for DIGITAL QSO progression. The frontend may display state, submit decoded candidates, and request engagement, but it must not decide QSO state transitions, directly control PTT, or log completed DIGITAL QSOs independently.

One active QSO attempt is identified by `active_attempt_id`. Pending TX, directed replies, TX callbacks, logging callbacks, aborts, and stale events are checked against that attempt id before they are allowed to advance state.

## Stop TX Semantics

`Abort QSO / Stop TX` means abort the current QSO attempt. It clears pending TX for that attempt, invalidates stale callbacks, and stops active PTT/audio through the backend TX engine. RX and later manual or Auto Call engagements remain available.

## Legacy Route Status

The following legacy routes are deprecated and disabled by default behind `FT8_LEGACY_TX_ROUTES_ENABLED=false`:

- `/api/ft8/transmit`
- `/api/ft8/cq`
- `/api/ft8/reply`
- `/api/ft8/send73`

If the flag is enabled for audited external tooling, legacy CQ is routed through the backend manual-CQ path. Free-form transmit, reply, and send73 remain rejected because they do not carry enough attempt-state context to satisfy the backend-owned QSO invariants.

The active browser path uses `/api/ft8/automation/engage` and `/api/ft8/tx/manual`. These routes go through the backend-owned queue, mode-specific slot timing, late-slot cutoff, and active attempt checks.

## Debug Output

The DIGITAL status snapshot includes `automation_decisions`. The UI shows the latest decisions in the DIGITAL debug strip. Each decision includes the attempt id, mode, active target, state, pending TX message/slot, TX active flag, event, reason, and relevant details.

Backend logs also include DIGITAL automation decisions through the normal Python logger.

## Persistent Logging Dedupe

Persistent QSO dedupe state is stored in:

```text
logs/qso_log_dedupe.json
```

The file is ignored by Git because `/logs/` is ignored. Writes use a temporary file followed by replace. Missing or corrupt JSON is handled as an empty ledger with a warning, not a startup failure.

The stable QSO key includes DX callsign, own callsign, band/frequency, mode, timestamp window, sent report, and received report. This prevents duplicate Wavelog/ADIF processing after refresh, reconnect, backend restart, or Wavelog retry/fallback.

## Smoke Tests

Run the production smoke suite from the project root:

```powershell
python -B -m pytest tests\smoke -q
python -m py_compile services\ft8_service.py backend\api\ft8.py backend\api\spots.py services\qso_logging.py
git diff --check
```

## Receive-Only / Dry-Run Validation

1. Start services without native launcher windows:

   ```powershell
   .\start_all.ps1 -Port 8080 -NoLauncher
   ```

2. Open `http://127.0.0.1:8080/ft8.html`.
3. Leave TX disabled. Confirm RX decode, band/frequency sync, decoded status enrichment, and automation debug decisions.
4. Use Auto Call criteria in receive-only mode only to verify candidate collection and backend decisions. Do not press `Tx Armed` unless RF TX is intentionally being tested.
