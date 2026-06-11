# WSJT-Z OM0RX Source Of Truth

This document tracks the local OM0RX WSJT-Z build and is the reference for any
behavior that differs from upstream `sq9fve/wsjt-z`.

## Build Identity

- Upstream base: `sq9fve/wsjt-z`.
- Local source: `data/build/wsjt-z-om0rx/src`.
- Local executable: `data/build/wsjt-z-om0rx/build-msys/wsjt-z.exe`.
- Launcher: `scripts/wsjtz/run_om0rx_wsjtz.ps1`.
- Enrichment server: `scripts/wsjtz/om0rx_decode_status_server.py` on
  `127.0.0.1:8765`.

## Current OM0RX Changes

1. Decode panes have compact `CS` and `DS` columns.
2. Decode status is enriched from the local OM0RX QSO status cache backed by the
   Wavelog export.
3. Right-clicking a decoded station includes `Prev QSO's for <CALL>`.
4. The previous-QSO popup shows prior QSOs and a band/mode matrix.
5. Active-call display enrichment prefers the current `Call` field when the
   decoded message contains that call, preventing the other side of a QSO from
   being shown as the target.
6. Auto Call candidate ranking now has an OM0RX hunting priority layer.
7. Auto Call has an OM0RX priority-hunt session for ATNO/new-DXCC-band targets.
8. Direct replies addressed to OM0RX take priority over watchdog/Auto Call
   station changes.
9. WSJT-Z logged-QSO bridge uploads are retried from a persisted queue if the
   OM0RX backend is busy or times out.

## Upstream Automation Map

This is the baseline behavior we are preserving unless this document explicitly
records a change.

- `callsignFiltered(...)` runs immediately for every decoded line. It applies
  WSJT-Z filters and picks `m_priorityCall` for Auto Call or Pounce.
- `ZProcess()` runs once per cycle. If Auto Call or Pounce has a priority call
  and TX is not already active, it calls `useNextCall()`, selects Tx1, and starts
  TX.
- `auto_sequence(...)` handles active QSO replies. It only advances a QSO when
  the message is addressed to our call and matches the current DX call or fits
  the existing WSJT-Z tolerance rules.
- `processMessage(...)` chooses the next TX message and advances the QSO state:
  `CALLING -> REPLYING -> REPORT -> ROGER_REPORT -> ROGERS -> SIGNOFF`.
- Double-click handling remains upstream-style: double-click processes the
  clicked decode immediately and may start TX through quick-call behavior.

## Hunter Priority Layer

The hunter priority layer is applied inside `callsignFiltered(...)`, so it does
not wait for additional decodes and does not block on HTTP.

Ranking order:

1. `ATNO` / `ATTNO`: brand-new DXCC, never worked.
2. New call plus new band/mode combinations.
3. New call.
4. New band plus new mode.
5. New band.
6. New mode.
7. Confirmed/worked DXCC new-band/new-mode combinations such as `C/NB+M` or
   `C/NB`.
8. Worked.
9. Confirmed.

Tie breakers still use the existing WSJT-Z Auto Call priority setting:

- `Last decoded`: later decode wins within the same rank.
- `Signal strength`: strongest signal wins within the same rank.
- `Distance`: longest distance wins within the same rank.

Data source behavior:

- If a Wavelog-backed OM0RX CS/DS status is already in the in-memory decode
  status cache, that exact status is used for ranking.
- If the OM0RX status is not cached yet, ranking falls back to WSJT-Z's loaded
  ADIF worked-before data in the same decode pass.
- The fallback is intentional. It preserves the current fast behavior where a
  station can be selected and called directly after a decode instead of waiting
  for the async enrichment request to complete.

Status semantics:

- `NC` means the callsign has no prior QSO in the local Wavelog/QSO status
  cache.
- `NB` means the callsign has been worked before, but not on the current band.
  Example: a station worked on 15m and decoded on 20m must be `NB`, not `NC`.
- `DS` is independent of `CS`: a callsign can be `NB` while the DXCC is already
  `C` if that country is confirmed.

## Priority Hunt Session

This is an OM0RX extension on top of the hunter priority layer.

Trigger:

- The decoded station must pass the normal WSJT-Z filter path first.
- The decoded message must be eligible for Auto Call selection, currently CQ or
  optionally 73 when the upstream `CQonlyIncl73` option allows it.
- The DXCC status must be `ATNO` / `ATTNO`, or a DXCC new-band slot such as
  `W/New Band`, `C/New Band`, or `C/New Band+Mode`.
- Ordinary new calls do not trigger this session unless the DXCC side is also
  ATNO/new-band.

Behavior:

- If WSJT-Z is idle, the target is started immediately in the same Auto Call
  path.
- If another QSO is in progress, WSJT-Z does not interrupt it. The priority
  target is remembered and is started only after the current QSO has cleanly
  returned to the `CALLING` state and the current DX call is logged or cleared.
- The pending target is tried before band-hopper rotation, so a high-value
  decoded target is not skipped by the normal band-hopper countdown.
- While the priority hunt is active, `MainWindow::watchdog()` returns `20`
  minutes. The saved watchdog settings are not rewritten.
- When the priority target is logged, the priority session is cleared and the
  watchdog immediately falls back to the normal configured value, currently the
  operator's usual 2-minute FT8 timer.
- If the priority hunt itself times out, the session is cleared and normal
  operation resumes.

Non-goals:

- It does not change message generation.
- It does not interrupt an active QSO to chase the new target.
- It does not bypass the existing WSJT-Z filters.
- It does not make Wavelog HTTP calls synchronous or delay decoding.

## Reply Priority Guard

This is an OM0RX safety fix for hunting mode.

- When a decoded line is addressed to OM0RX, such as `OM0RX G8NAI -03`, WSJT-Z
  promotes that sender into the active QSO path immediately.
- Any stale `m_priorityCall` or pending OM0RX priority-hunt target is cleared
  for that cycle, so the watchdog/Auto Call path cannot start a different
  station while a reply is waiting.
- While the QSO state is not idle, `ZProcess()` refuses to start another Auto
  Call candidate. Once the QSO returns to `CALLING`/idle or the replied station
  is logged, normal Auto Call resumes.
- This does not change generated messages, filters, double-click behavior, or
  the normal WSJT-Z sequencing states. It only prevents a newly selected station
  from outranking a station that has already replied to us.

## Logged-QSO Bridge Retry

- WSJT-Z still logs locally first and sends the normal UDP `LoggedAdif` packet.
- The bridge forwards that packet to `/api/wsjtx/log-qso` with the existing
  async Wavelog upload payload.
- The backend queues the ADIF text to the local Wavelog outbox first and
  returns immediately. Slower local ADIF/cache/dedupe bookkeeping runs in the
  background so the bridge is not held long enough to hit its upload timeout.
- Upload replay is handled by the existing periodic Wavelog outbox worker. The
  logged-QSO request path does not run Wavelog HTTP replay inline, because that
  can hold the bridge long enough to trigger duplicate retries and stale client
  state.
- If the backend times out or rejects the request, the bridge writes the payload
  to `logs/wsjtx_logged_qso_pending.jsonl` and retries in the background.
- This prevents a valid local WSJT-Z QSO from being lost just because the
  backend or Wavelog path was slow during the first upload attempt.

## Decode Display Deduplication

- WSJT-Z can receive exact duplicate decoded lines from the FT8 decoder path,
  especially around multi-threaded and AP decode passes.
- OM0RX suppresses exact duplicate display rows within the same decode period.
  The key is UTC, mode, and message with trailing AP markers such as `a1` or
  `a9` stripped. SNR, DT, and audio offset are intentionally ignored because
  duplicate decoder passes can report the same decoded message with slightly
  different signal metrics, AP annotations, or a one-bin audio-offset
  difference.
- The dedupe set is cleared when the UTC period changes, when disk WAV decode
  starts, and on the normal FT8 period-boundary reset.
- This is a display/processing guard only for exact duplicates in the same
  period. It does not hide the same station calling again in a later 15-second
  period, and it does not change message generation or QSO sequencing.

## Non-Changes

- The active QSO state machine is unchanged.
- Auto Seq response rules are unchanged.
- TX message generation is unchanged.
- Double-click TX behavior is unchanged.
- Pounce activation semantics are unchanged.
- The enrichment server remains asynchronous from the GUI and is not allowed to
  delay station selection.

## Change Log

### 2026-06-11

- Fixed the backend WSJT-Z launch endpoint so it no longer blocks the FastAPI
  event loop while the PowerShell launcher starts the GUI process. The endpoint
  now starts the launcher with log-file redirection and returns immediately.
- Changed bridge logged-QSO recovery from one queued QSO per retry interval to
  a bounded batch retry. Queued entries caused by backend `ECONNREFUSED`,
  timeout, or socket reset are made due immediately on bridge startup.
- Restored immediate backend Wavelog outbox replay after accepting an async
  WSJT-Z logged-QSO packet. The UDP request still returns quickly; the upload
  is triggered in a background task.
- Replayed the persisted WSJT-Z logged-QSO retry queue from
  `logs/wsjtx_logged_qso_pending.jsonl`. The file had 62 records that were
  captured while the backend was unavailable; after replay the bridge pending
  queue and local Wavelog outbox were both empty.
- Verified the real WSJT UDP `LoggedAdif` path with a duplicate `M0KEE` ADIF.
  The bridge received it, the backend accepted it, Wavelog duplicate handling
  resolved it, and no test QSO remained in Wavelog.
- Verified live service state after restart: FlexRadio status endpoint
  connected, WSJT-Z bridge client `WSJT-X - OM0RX-WSJT-Z` fresh, Wavelog outbox
  empty, and cluster source stats showing fresh cluster and RBL spots.
- Fixed `/api/service-health` Wavelog reporting so the dashboard uses a short
  bounded sync-status refresh instead of showing `0 QSOs` from an empty startup
  cache while the real local Wavelog mirror is already initialized.

### 2026-06-10

- Added this document as the source of truth for OM0RX WSJT-Z behavior.
- Added immediate hunter priority ranking to Auto Call candidate selection.
- Preserved upstream sequencing and TX message logic.
- Added priority-hunt sessions for ATNO/new-DXCC-band targets with a temporary
  20-minute watchdog until the target is logged or the hunt times out.
- Recorded `NC`/`NB` status semantics after investigating `KB9ELS` and
  `CA6SNT`; both are correctly `NB/C` because both calls already exist in the
  log on other bands.
- Fixed live CS/DS callsign selection for third-party reply/RR73 decodes. The
  live columns now follow the same target callsign WSJT-Z uses for row
  interaction: CQ caller for CQ lines, the second decoded callsign when it is
  not our call, and the first decoded callsign for replies addressed to OM0RX.
  This prevents rows such as `K5VGS PY5DC RR73` from showing `K5VGS` status
  (`NC`) while the modal/right-click action is correctly focused on `PY5DC`
  (`NB` on 20m).
- Replayed the missed `G8NAI` 40m FT8 QSO from the local WSJT-Z ADIF/log into
  Wavelog after the bridge had received it but the backend upload timed out.
- Added persisted bridge retries for future WSJT-Z logged-QSO uploads that time
  out while the backend is busy.
- Changed `/api/wsjtx/log-qso` async upload handling to enqueue the ADIF before
  returning and move local ADIF/cache/dedupe bookkeeping into a background
  worker. This keeps logged-QSO handoff fast enough for the bridge timeout.
- Added an immediate backend outbox replay trigger after accepted WSJT-Z logged
  QSOs, so Wavelog upload happens right away without blocking the bridge.
- Replayed all seven 2026-06-10 local WSJT-Z ADIF records through Wavelog:
  `TA5CUK`, `PY5CV`, `G8NAI`, `W4SFX`, `9X5KM`, `R2026DR`, and `M0LEX`.
  Wavelog returned duplicate for all seven, confirming they are present and
  leaving the local Wavelog outbox empty.
- Added a reply-priority guard so a received reply to OM0RX clears stale
  watchdog/Auto Call candidates and prevents starting a different station until
  the reply QSO is handled or the QSO state returns to idle.
- Fixed the reply-priority guard so it no longer returns early from
  `ZProcess()` while TX/auto-sequence is active. The guard now clears competing
  Auto Call candidates but lets the active reply sequencing continue.
- Tightened decode display deduplication to ignore audio-offset differences
  within the same UTC period. Rows such as the same callsign/message at 670 Hz
  and 671 Hz are now one displayed decode, not two.
- Tightened decode display deduplication again to treat AP-suffixed variants
  such as `EA1CQ AA4HV R-07 a9` and `EA1CQ AA4HV R-07` as the same displayed
  decode within the same UTC period.
- Added decode display deduplication for exact repeated decoder lines within
  one period, rebuilt WSJT-Z, killed the old process, replaced `wsjt-z.exe`,
  and relaunched the `OM0RX-WSJT-Z` profile.
- Fixed the async Wavelog duplicate retry path. If a repeated logged-QSO
  request matches an existing dedupe entry that does not have
  `wavelog_success=true`, the backend now re-queues the ADIF and triggers an
  immediate outbox replay instead of ignoring it.
- Replayed `N4MTB` 40m FT8 from the local WSJT-Z ADIF. Wavelog returned a
  duplicate for `2026-06-10 02:14:15 N4MTB 40m`, confirming the contact is
  present remotely.
- Removed the visible browser UI launch buttons for the abandoned built-in
  `DIGITAL` window and patched WSJT-X launch experiment. The current native
  WSJT-Z launcher button, source/build, UDP bridge, enrichment, QSO-history
  popup, and Wavelog logging endpoints remain in place.
- Removed the old built-in Digital service health pill so the browser status
  strip no longer advertises the failed Digital path.
- Clarified bridge status behavior: `WSJT no client` means the Node bridge is
  running but has not received a fresh WSJT-Z UDP packet since it started. It
  does not by itself mean Wavelog logging is disabled; logged-QSO upload uses
  the same UDP bridge when packets arrive.
