# OM0RX WSJT-X Full Automation Structure

This document tracks the implementation structure derived from `om0rx_wsjtx_full_automation_codex.md`.

## Ownership

- `services/digital_automation.py` owns target scoring, queueing, lifecycle state, active-QSO state, retry/backoff, dry-run decisions, and replay tests.
- `services/wsjtx.py` owns WSJT-X command construction, automation policy normalization, bridge command handoff, and dry-run bridge avoidance.
- `backend/api/ft8.py` exposes automation queue, replay, and WSJT-X prepare endpoints.
- `radio_control/digital_target_store.py` and `radio_control/postgres_store.py` persist backend automation targets across restarts.
- `frontend/templates/dx-spots.html`, `frontend/dx-spots-section.html`, and `frontend/js/dx-spots.js` expose queue state and decision logs in the main app planner panel.

## Implemented Contract

- Structured target model: target ID, command ID, lifecycle, active state, skip/completion reason, direct-caller flag, timestamps, attempts, backoff, need reasons, and reference items.
- Formal lifecycle names: `candidate`, `queued`, `selected`, `command_sent`, `active`, `in_progress`, `completed`, `logged`, `failed`, `backoff`, `expired`, `skipped`, `ignored`.
- Formal active-QSO names: `idle`, `candidate_selected`, `command_sent`, `waiting_for_tx`, `calling`, `reply_received`, `report_sent`, `rr73_seen`, `logged`, `completed`, `failed`, `aborted`.
- Multiple incoming callers addressed to OM0RX are queued as independent targets and prioritized ahead of normal hunt candidates.
- Every select, skip, queue, dry-run, transition, backoff, promote, and completion decision is written to a bounded decision log.
- WSJT-X commands include idempotent `targetId` and `commandId`.
- Dry-run mode performs queue/ranking/command planning without sending a bridge command.
- Replay endpoint can feed decode/status/log events into the backend without radio TX.
- PostgreSQL persistence stores queued/backoff target state for restart recovery.
- Reference hunting model carries POTA/SOTA/IOTA/WWFF/county/state/province data through scoring, filters, persistence, and WSJT target payloads.
- Backend manual override detection releases the active automation target when WSJT-X reports a conflicting DX Call, band, frequency, mode, tune, or explicit operator action.

## Remaining Native-UI Work

- Add the same queue and decision-log visibility directly inside the OM0RX WSJT-X Qt window.
- Add native WSJT-X controls for reference-hunting filters once the backend reference model is enabled in operator settings.
- Extend native WSJT-X status reporting if more operator actions need to be surfaced to the backend.

## Acceptance Tests

- Multiple direct callers queue without overwriting each other.
- The next caller is selected after the active target is completed.
- Avoid-logged targets are skipped unless an enabled need remains.
- Command IDs are stable per target attempt.
- Dry-run prepare does not send a bridge command.
- Replay harness drives decode/select/attempt/logged flows.
- Reference targets are carried but gated by the reference hunting filter.
- WSJT-X status events advance active-QSO state or abandon active automation on manual override.
