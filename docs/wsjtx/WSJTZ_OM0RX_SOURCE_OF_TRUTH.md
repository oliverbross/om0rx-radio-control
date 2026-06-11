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
10. WSJT-Z accepts backend planner target commands over the WSJT UDP protocol
    as OM0RX message type `17`. The command payload is JSON and is handled by
    `MainWindow::remote_start_target_qso`, which prepares the DX call/grid,
    mode, Rx/Tx audio frequencies, Tx-first, Hold Tx Freq, selected Tx message,
    and only arms Enable Tx when the backend explicitly sends `enableTx=true`.
    Backend commands can mark `priorityHunt=true`; WSJT-Z then uses the same
    OM0RX 20-minute priority watchdog that decoded ATNO/new-band targets use.
11. The WSJT-Z launcher forces `PromptToLog=false`, `AutoLog=true`,
    `AcceptUDPRequests=true`, `UDPServer=224.0.0.1`, and `UDPServerPort=2237`
    inside the WSJT-Z `[Configuration]` INI section before startup. The
    `[Configuration]` section is the one WSJT-Z actually reads for UDP command
    acceptance.
12. The backend planner decision log records why targets were selected, held,
    or rejected, including candidate ordering and rejected candidate examples.
13. The local Wavelog/QSO status cache is authoritative over stale cluster or
    decode payload status when deciding whether a DXCC or bandslot still needs
    hunting.
14. The browser WSJT Planner panel exposes a `Why not TX?` table, a priority
    score trace, and a compact automation event log for live troubleshooting.
15. OM0RX WSJT-Z appends an optional QSO-state heartbeat field to its UDP
    Status message. The bridge reads it when present and safely derives a state
    for stock clients when it is absent.
16. Replay fixtures under `tests/fixtures/wsjtz_replays` capture real
    decode/QSO cycles so regressions like "finished QSO, then direct caller was
    not answered" can be replayed by tests.
17. The backend planner has a browser-visible dry-run mode. In dry-run the UI
    shows what would be prepared or QSYed, but no WSJT bridge command is sent.

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

## Cluster DXCC/Bandslot Hunt

This is the source-of-truth behavior for backend-driven cross-band hunting.

Example flow:

- WSJT-Z is automating on 40m FT8 and is already working `OM0AAO`.
- The OM0RX cluster/planner sees `VK8RX` on 20m FT8 from Australia.
- If Wavelog shows that the VK DXCC is all-time new, worked but not confirmed,
  or needed on 20m/FT8, the backend queues it as a DXCC hunt prospect.
- Ordinary new calls are not enough for this cross-band hunt. They can still be
  displayed and enriched, but they must not pull WSJT-Z away from the current
  band by themselves.

Execution rules:

- Active QSOs are never interrupted. If `OM0AAO` is in progress, the backend
  holds the `VK8RX` prospect until WSJT-Z has returned to an idle/calling state
  or the current QSO has logged/cleared.
- After the active QSO finishes, the backend sends WSJT-Z a listen-only target
  command for the prospect band/mode/frequency. The command does not enable TX
  and does not generate messages yet; it only QSYs and listens.
- If the prospect is decoded locally, the normal decoded-station path marks it
  heard. The next backend tick sends an armed target command with
  `priorityHunt=true`, `enableTx=true`, and a 20-minute priority watchdog.
- While the station continues to be heard but is not worked, the system keeps
  trying within that priority hunt window. A one-sided attempt must not switch
  to an unrelated station if the hunted DXCC replies to OM0RX.
- If the prospect is not heard for 5 minutes after the listen-only QSY, the
  backend sends a return-to-origin listen-only command and normal automation
  resumes on the original band/frequency/mode.
- If the QSO is logged, the backend marks the target complete, WSJT-Z clears
  the priority watchdog, the backend returns WSJT-Z to the original
  band/frequency/mode, and normal automation resumes.
- If the same DXCC/bandslot appears later in the cluster and Wavelog still does
  not show it confirmed for that band/mode, the same hunt cycle can repeat.

DXCC status rules:

- `ATNO` / `ATTNO`: always highest-priority hunt.
- `Worked` DXCC: still hunt, because worked-but-not-confirmed DXCC is not good
  enough for this autonomous goal.
- `W/New Band`, `C/New Band`, `W/New Band+Mode`, or `C/New Band+Mode`: hunt
  because the DXCC slot is still needed on that band/mode.
- Plain `Confirmed`, with no new band/mode slot, is not hunted by the
  cross-band DXCC hunter.
- New calls, new grids, and reference-only needs are not cross-band DXCC hunt
  triggers unless the DXCC status above also says the DXCC or DXCC band/mode
  slot is needed.

Wavelog authority rules:

- The planner enriches every incoming cluster/decode payload from the local
  `qso_status_store` when that cache is available.
- Wavelog/QSO-cache call status replaces stale incoming call status. Example:
  if a spot says `NC` but Wavelog shows the call exists on another band, the
  planner treats it as worked/new-band rather than new-call.
- Wavelog/QSO-cache DXCC status replaces stale incoming DXCC status. Example:
  if a spot still says `ATNO` but the local Wavelog mirror says the DXCC is
  confirmed and there is no new band/mode slot, the planner rejects it as not a
  DXCC hunt target.
- Worked-but-not-confirmed remains huntable. Only Wavelog-backed plain
  `Confirmed` with no new band/mode slot is a hard stop for cross-band DXCC
  hunting.

## Planner Decision Log

This is the operational log used to explain why the backend automation did or
did not prepare a target for WSJT-Z.

- Every planner tick records one decision: `selected`, `hold`, or `idle`.
- Every queued or rejected candidate carries a single score trace. Current
  headline scores are: `reply-to-us=99999`, `ATNO=10000`,
  `DXCC worked-not-confirmed=9000`, `DXCC new band=8000`,
  non-EU `New Call=7500`, `New Band=6500`, references `6000`, grid `5000`,
  new mode `3500`, and plain new call `2000`.
- Decisions include the active target, hold reason, current station state,
  rejected reason counts, and candidate count.
- Selected decisions include the top candidate ordering so we can verify that
  ATTNO/ATNO, new DXCC, worked-but-unconfirmed DXCC, and DXCC bandslot targets
  outrank lower-value options without delaying the decode-to-call path.
- Hold and idle decisions include rejected candidate examples. Each example
  records call, band, mode, score, state, source, direct-caller flag, CS/DS
  status, and need reasons.
- The frontend WSJT Planner panel shows the decision summary and rejected
  examples directly, so debugging should start from the UI before digging into
  backend logs.
- The `Why not TX?` table explains each visible decode or target with operator
  language such as `blocked: Europe filter`, `blocked: active QSO with <CALL>`,
  `blocked: DXCC already confirmed`, `waiting: target not heard`, or
  `selected: ATNO`.
- The `Priority score trace` table shows the sorted candidate list for the
  current cycle, including score label, eligibility, and blocker reasons.
- The `Automation event log` table shows recent planner events in the browser:
  time, event, station, reason, and action/state.
- This log is explanatory only. It must not add wait-for-more-decodes behavior
  or slow the existing immediate WSJT-Z automation path.

## QSO State Heartbeat

- OM0RX WSJT-Z sends a direct QSO-state heartbeat as an optional trailing field
  in the normal UDP Status packet.
- Supported states are `idle`, `calling`, `in_qso`, `waiting_rrr`,
  `waiting_73`, `logged`, and `blocked`.
- The backend planner trusts this field when it is present. It should no longer
  infer critical QSO ownership only from selected fields, UDP command history,
  or timers.
- The bridge remains backward-compatible: when the optional field is missing,
  it derives a coarse state from Status fields (`watchdogTimeout`,
  `transmitting`, `txEnabled`, and `dxCall`).

## Replay Tests

- Replay tests must use the same controller path as live automation:
  ingest decode/spot, select target, record attempt, process WSJT status, and
  mark logged/completed.
- The `ha0aa_pa3dri_direct_reply.json` fixture records the bug class where a
  QSO completes and the next decoded line is addressed directly to `OM0RX`.
  The expected result is that the direct caller gets `reply-to-us=99999` and is
  selected immediately.
- New recurring screenshots/log sequences should become replay fixtures before
  changing the priority rules again.

## Dry-Run Planner Mode

- Dry-run is controlled by backend automation setting `dryRun` / `dry_run` and
  is visible as a `Dry run` toggle in the browser WSJT Planner panel.
- When enabled, preparing the best target returns `dry-run` / `would-*`
  decisions and does not call the WSJT bridge command endpoint.
- Dry-run examples should read like: `Would prepare VK8RX; no WSJT command
  sent`, `would-send-spot-listen-qsy`, or `would-return-wsjtz-to-origin`.
- Dry-run is for planner validation before unattended operation. It must not
  bypass filters, change priority scores, or alter the normal live execution
  rules when disabled.

## Reply Priority Guard

This is an OM0RX safety fix for hunting mode.

- When a decoded line is addressed to OM0RX, such as `OM0RX G8NAI -03`, WSJT-Z
  promotes that sender into the active QSO path immediately.
- If automation/Auto Seq is active, TX is not running, and the QSO state is
  idle or already in a finished `ROGERS`/`SIGNOFF` state, the direct reply is
  processed and TX is armed immediately from the decode path. This covers the
  case where a previous QSO has just finished and the next station calls OM0RX
  before the operator clicks anything.
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

- Added the backend-driven Cluster DXCC/Bandslot Hunt contract. Cross-band
  cluster hunting is now limited to ATNO/ATTNO, worked-but-unconfirmed DXCC,
  and DXCC band/mode slot needs. Ordinary new calls no longer pull WSJT-Z away
  from the current band. The backend records the original band/frequency/mode,
  QSYs listen-only to the prospect, arms WSJT-Z with `priorityHunt=true` only
  after the station is locally decoded, uses the existing 20-minute priority
  watchdog for the attempt, and queues a return-to-origin command after the
  QSO logs or after 5 minutes without hearing the prospect.
- Fixed direct replies after a completed QSO. When a station calls OM0RX while
  WSJT-Z is idle in automation mode, the decode path now starts the reply
  immediately instead of merely blocking other Auto Call candidates and waiting
  for an operator double-click.
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
- Added richer planner decision logging. The backend now records candidate
  counts, top candidate order, rejected reason counts, and concrete rejected
  examples; the frontend WSJT Planner panel displays the same summary.
- Made the Wavelog/QSO status cache authoritative for planner hunt decisions.
  Stale incoming `NC`/`ATNO` payloads are overridden by local cache truth, and
  Wavelog-backed plain `Confirmed` DXCC with no new band/mode slot is rejected
  from cross-band hunting.

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
