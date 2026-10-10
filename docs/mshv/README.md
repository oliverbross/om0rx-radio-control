# OM0RX MSHV Auto DX runtime

## Adaptive retry and station ignore list — 2026-10-09

`om0rx-adaptive-retry-ignore.patch` is the final maintained patch in the stack.
An all-time new DXCC retains the configured uninterrupted 30-minute lease.
Confirmed DXCCs instead use a bounded automatic attempt, the 60-second
late-reply receive guard, and then a per-call/band/mode retry ladder of 3, 10,
30, and 60 minutes. A successful QSO resets that ladder.

Right-clicking an FT8/FT4 decode now offers **Ignore for Auto DX on this
band/mode**. Entries persist in `settings/database/autodx_ignore.json`, block
local and cluster-driven automatic selection/QSY for only that exact slot, and
can be removed individually or cleared from the Auto DX **Ignore** tab, which
replaces the former SMS tab.

## Late-reply QSY guard — 2026-10-09

`om0rx-late-reply-qsy-guard.patch` precedes the adaptive-retry/ignore patch.
When an unanswered call reaches its attempt budget, AUTO stops but MSHV keeps
the same target, band, and mode in receive-only state until 120 seconds have
elapsed from the actual final transmission. A directed late reply immediately
resumes the existing exchange; only guard expiry permits retry and QSY logic.
Stop/Clear remains immediate and the guard countdown is published in Auto DX
runtime status.

## Operator target lock — 2026-10-09

`om0rx-manual-target-lock.patch` precedes the late-reply QSY guard patch.
A station selected by double-click is an explicit operator command: it takes
priority before hunting visit expiry, refreshes the selected local decode, and
suppresses quiet-band, cluster, timeout, and full-hunting QSY until that manual
attempt finishes or the operator uses Stop/Clear. Automatic history and award
filters cannot silently replace the requested call; same-band and local-decode
safety checks remain in force.

## Native station RF panel — 2026-10-08

`om0rx-station-rf-panel.patch` precedes the operator target lock patch. It also
carries the ATNO minimum-chase and initial operator manual-target priority fix. The
lower-left transmit area now displays live KPA500 state, output watts, SWR,
temperature and fault; KAT500 mode, antenna, SWR and fault; and an emphasized
RF-active state. `KPA ON` requests guarded OPERATE and `KPA OFF` requests
guarded STANDBY through the existing station coordinator. Controls lock during
RF, on device/fault uncertainty, or whenever the coordinator does not authorize
the action. MSHV never opens a second serial/CAT connection to either device.

## Manual decode selection and QSO lifecycle — 2026-10-08

`om0rx-manual-qso-lifecycle-ui.patch` precedes the station RF panel patch. A
decoded row now has a clearly visible single-row highlight, and a
double-click enters MSHV's native selected-decode path to populate the remote
station, generate the exchange, and begin the normal automatic sequence. Auto
DX is notified as well so its target queue and status remain synchronized.

The lower transmit area now gives the seven native MSHV message stages a
labelled QSO lifecycle panel. Its radio buttons select the next stage; the
corresponding `Tx1` through `Tx7` buttons immediately transmit or repeat that
message. This exposes existing native behavior without creating a second QSO
state machine.

## Exchange-only reply guard — 2026-10-08

`om0rx-exchange-only-reply-guard.patch` precedes the manual-QSO lifecycle UI
patch. A directed `RRR`, `RR73`, or `73` is now classified as part of an
existing exchange and can never be admitted by AutoDX as a fresh caller. This
prevents a lost queue/current-target state from restarting the QSO with a
signal report such as `R-11`; native MSHV still receives the decode and can
complete and log the active contact normally.

## Band markers and per-band country exclusions — 2026-10-08

`om0rx-band-markers-country-exclusions.patch` precedes the exchange-only reply
guard. Every real band transition appends a timestamped band separator to
both decode panes, making it clear where reception on each band began.

The native Auto DX settings dialog now accepts country exclusion rules under
eligibility. Use one rule per line, for example `30m: Japan`, `20m: USA`, or
`ALL: Japan`; separate multiple entities with semicolons. Matching is
case/punctuation-insensitive, and `US`/`USA` alias to `United States`. These
rules are fail-closed before scoring, so they apply to local decodes, external
spots, DXpeditions and directed callers without affecting manual operation.

## Reliable final exchange — 2026-10-07

`om0rx-repeat-final-exchange.patch` precedes the band-marker/country-exclusion
patch. When the contacted station sends `RRR`, MSHV now keeps transmitting the
selected final `RR73`/`73` exchange until that station answers with `73` or
`RR73`. A repeated `RRR` therefore refreshes the final exchange instead of
ending Auto after its first transmission. The existing TX watchdog still ends
an attempt that never receives confirmation.

## Priority patrol and full FT4 Auto DX — 2026-10-07

`om0rx-priority-patrol-ft4.patch` precedes the final-exchange reliability fix.
Ordinary new-call (`NC`) contacts are now a true fallback: every enabled band
whose local schedule is open must complete a quiet priority patrol first, and
any eligible local, cross-band, or DXpedition opportunity continues to block
the fallback. Accepting any target starts a fresh patrol cycle. Runtime status
exposes the open and checked band sets, cycle completion, pending priority
opportunities, and whether ordinary NC fallback is currently available.

FT4 now uses the same complete Auto DX state machine as FT8: exact-mode history
and duplicate suppression, FT4 dial frequencies, 7.5-second-period scheduling,
mode-matched RBN/PSK Reporter/DX-cluster evidence, DXpedition watch entries,
band switching, target scoring, QSO completion and Wavelog handoff. Switching
mode clears only mode-scoped observations and deferred targets, preventing an
FT8 decode from being chased in FT4. The portable FT4 profile is also migrated
to the same two-decode-list layout and Auto Sequence behavior used by FT8.
The release manifest attests `priority_patrol_fallback_v1`,
`ft4_dual_decode_layout_v1`, and `ft4_autodx_v1`.

## Performance and hunting review — 2026-10-07

The native score-order selector now compares directed callers, all-time-new
DXCCs, new DXCC band slots, unconfirmed DXCCs, and other eligible targets in
that order. Configured scores, rarity, reference awards and preferences rank
targets within a class. The explicit newest-decode selection mode still uses
recency. Cross-band alerts likewise rank ATNOs before band slots before bonus
awards; QSO ownership and local verification remain unchanged. The repeated
decode bonus is capped at ten increments so long-lived calls cannot accumulate
unbounded priority.

Retry-delayed local candidates are removed before ranking. Previously the
selector could repeatedly choose a cooling-down winner and return without
trying another eligible candidate. The final queue admission check remains.
External-only spots no longer undergo a quadratic merge into a local-only
candidate list just to be discarded immediately afterward.

Worked continent/CQ/ITU membership now uses a derived index, invalidated by
history load, acknowledged updates, imports, clears and country-data reload.
`scripts/mshv/benchmark_tracker.ps1` compiles the production tracker and uses a
temporary synthetic history of 300 entities across nine bands. On this host,
48,000 identical membership queries took 16,719,997 microseconds before and
131,441 microseconds after the change (about 127x for this workload). This is
not an end-to-end decoder or GUI speedup claim. Runtime CPU samples before
deployment averaged 0.02 and 0.125 cores, so they did not show sustained CPU
saturation. Decoder sensitivity and station-profile values are preserved.

Regression coverage includes retry starvation in the real planner fixture,
need-class ordering, and cached membership updates after acknowledged QSOs
and history clear. Those source changes are carried in
`om0rx-composable-award-hunting.patch`; the priority-patrol follow-up is in
`om0rx-priority-patrol-ft4.patch`. Both are verified by clean stack replay.

Validation for this pass: 266 selected Python checks passed, along with the
full native `test_mshv.ps1` suite and release attestation. Deployed executable
SHA256: `FDC84A5F53CF74832F512E7101927186BBAB7025DC0D18F4D699B325903B7D06`.
The restarted process selected RW9UDS on 15m, reported TX and a subsequent RX
cycle, retained enabled band switching, and reported healthy history with 221
acknowledged deltas and available DXCC confirmation data. RW9UDS subsequently
completed and uploaded successfully to Wavelog; session counters advanced from
32/32 to 33 logged/33 uploaded with zero upload errors, and the native planner
returned to Listening after completion.

The integration reconstructs the GPL MSHV Auto DX fork at commit
`d960ae22de78940c6be9d95bd4817d233d02ee39` from
https://github.com/kd9taw/mshv-auto-dx-chaser. Generated source/build/runtime
are under `data/build/mshv-auto-dx` and are not repository source files.
`om0rx-integration.patch` is the maintained station-safety/protocol base,
`om0rx-autodx-phase1.patch` is the active AutoDX runtime configuration layer,
`om0rx-wavelog-history-phase2.patch` supplies history authority, and
`om0rx-autodx-quiet-qsy-fix.patch` supplies the reviewed quiet-band QSY and
failed-handoff cleanup. `om0rx-autodx-native-policy.patch` is the final native
selection, retry, dwell and structured-audit layer. `om0rx-ui-persistence.patch`
adds screen-safe main-window geometry/maximized-state restoration and preserves
the operator's waterfall visibility preference. `om0rx-ui-layout-persistence.patch`
extends that state to the TX panel and DXCC Chaser window and makes the settings
rewrite atomic. `om0rx-recent-qso-cooldown.patch` replaces the former fixed
five-minute post-log blacklist with a persisted, live-configurable propagation
guard. `om0rx-permanent-slot-dedupe.patch` makes Wavelog's exact callsign,
band and mode history authoritative for automatic, manual and directed-caller
selection: a worked slot is never called again, while a new band or mode remains
eligible. It also adds the default-on all-band option that permits a new DXCC
band slot to override a continent exclusion.
`om0rx-compact-status-combinations.patch` keeps the native CS/DS columns aligned
with the main Spots vocabulary, including combinations such as `NB/C`, `NM/C`,
`NB/W`, and `NB+NM/C` instead of collapsing confirmed countries to plain `C`.
`om0rx-us-states-chase.patch` adds Wavelog-authoritative Worked All States
automation and fixes the QSO-side decode table to classify the remote station
rather than the local transmitter. By default it seeks three distinct worked
calls per state on each 160--10 metre HF band (excluding 6 metres), continues
until at least one is confirmed, prefers known LoTW users, and still rejects an
exact callsign/band/mode duplicate. FT8 and FT4 count together toward the
distinct-call quota, while exact duplicate protection remains mode-specific.
`om0rx-cluster-chase-scheduler.patch` adds a globally ranked, observable
cross-band cluster queue for ATNOs, DXCC band slots, active DXpeditions, needed
US states, and unconfirmed continents/WAZ/ITU zones. Needed award targets may
override the ordinary continent filter, but never exact call/band/mode history.
An active QSO is protected to completion, multiple independent spotters and
feed families increase confidence, and off-standard reports are converted to
a configurable receive-audio dial hypothesis that must be verified by a local
FT8 decode before MSHV calls.
`om0rx-us-state-dxcc-guard.patch` ensures US-state chasing only admits Alaska,
Hawaii, and United States DXCC records, rejecting foreign two-letter regions.
`om0rx-composable-award-hunting.patch` adds additive POTA/SOTA/WWFF reference
correlation, campaign multipliers, zone/continent scoring, live band-productivity
adaptation, pileup audio rotation and revisit timing, a bounded directed-caller
inbox, and outcome telemetry. Award settings and the activation sidecar are
polled every two seconds. Sidecar-only changes atomically replace the award
index without restarting spot transports, including during an exchange; INI
changes are deferred until active QSO/CAT ownership releases. Spot transports
restart only when their own source configuration changes. Reference gaps
are admitted only from a schema-1 `award_hunting.json` sidecar that declares
authoritative history, after a local decode, and never override exact
callsign/band/mode history.
Selected references remain structured through `ScoredTarget` and the active
QSO. MSHV persists the program-specific values in its reserved log columns and
emits every selected reference as `POTA_REF`, `SOTA_REF`, or `WWFF_REF` in the
saved/broadcast ADIF record. A single unambiguous reference additionally emits
`SIG`/`SIG_INFO`; multi-program contacts retain separate standard fields.

Campaign profiles apply fixed DXCC/state/zone/grid/reference percentages:
`balanced` 100/100/100/100/100, `dxcc-challenge` 175/75/100/75/75,
`five-band-dxcc` 200/50/75/50/50, `worked-all-states` 75/200/75/75/50,
`waz` and `itu-zones` 75/50/200/50/50, `grids` 75/50/50/200/50, and
`references` 75/50/50/50/200. `custom` preserves the five explicit values.
All score weights are bounded to 0..100000 and campaign percentages to 0..500;
activation and propagation windows are 60..86400 seconds, pileup offsets are
1..16 unique values in -2400..2400 Hz, revisit delay is 0..86400 seconds, and
the directed inbox is 1..100 entries aged 15..3600 seconds. Outcome learning
reads at most the newest 2 MiB of JSONL telemetry, adjusts an already eligible
base call by +75 per completion or -25 per miss, and clamps the cumulative
adjustment to -250..+500; it can never create eligibility.
The patches are required,
clean-replayed in order, and
attested as one aggregate source diff.

## Build and test

```powershell
./scripts/mshv/build_mshv.ps1
./scripts/mshv/test_mshv.ps1
```

The default toolchain is the existing JTSDK64 Qt 5.15 MinGW installation.
OmniRig is omitted because ActiveQt is unavailable and native FlexRadio network
CAT supplies the required interface. Build failures stop packaging. The runtime
is `data/build/mshv-auto-dx/runtime/MSHV_OM0RX.exe`; settings, tracker and logs are
portable beside the executable. QSQLITE is explicitly deployed under
`sqldrivers/qsqlite.dll`. GPL and third-party notices, source pin, patch and
SHA256 build manifest accompany the executable. The manifest inventories every
immutable staged file except itself and declares the narrow mutable operator
state patterns separately, so package completeness remains auditable after use. When redistributing a binary,
provide the pinned corresponding source and patch, and Qt/library source or
offers as their licenses require; an upstream link alone is not a complete
corresponding-source distribution.

`assert_source.ps1` refuses any tracked delta outside the exact maintained
patch or any untracked source file. Build records source-patch and EXE hashes;
package verifies them before writing `om0rx-build.json`. The manifest contains
provider, version, interlock capabilities, exact UDP ID
`MSHV-OM0RX-AUTO-DX`, pinned commit, and executable/country/mapping/source hashes.
The `target_priority_v1` capability attests that the packaged executable reads
the stopped-engine OM0RX priority contract rather than the fork's hard-coded
legacy weights. `autodx_runtime_config_v1` additionally attests that active
`AutoDxerCore` loads its stopped-engine runtime policy at startup without
opening the dialog: FT8-only mode gating, the explicit cross-band switch,
enabled bands, ATNO/scarce thresholds, scorer/grid/min-SNR values and external
spot-source configuration. Desired enable preference and effective mode-gated
state remain separate and are reported by engine heartbeat telemetry. RBN,
PSKReporter and cluster records must carry explicit FT8 mode evidence before
they enter the cache or can request a same/cross-band QSY; FT4 and untyped
frequency-proximity guesses fail closed. Zero DXCC or band-slot priority weight
also disables that dimension's alert/QSY path. Source
setters remain inert until the core starts, so loading settings alone does not
open RBN, PSKReporter or cluster connections.
`test_clean_patch.ps1` reconstructs a fresh pinned clone and verifies the patch
and protocol identity without launching the application.

Build cleans generated objects before compilation. Packaging constructs a new
runtime directory, hashes the complete immutable staged inventory, classifies
preserved operator settings/logs as mutable, then swaps directories. The
previous complete runtime is retained under `runtime-previous-*` for recovery;
stale DLLs cannot silently carry into the new installation.

The Phase 1 remediation candidate was verified with these exact bounded commands:

```powershell
python -m pytest tests/test_mshv_autodx_phase1.py tests/test_mshv_package_transaction.py tests/smoke/test_digital_engine.py tests/smoke/test_frontend_contracts.py -q
python -m pytest tests/smoke -q
node --test tests/digital-engine-ui.test.cjs
```

The final local results were 107 focused Python tests, 699 smoke tests and 15
Node UI tests. The independent review subset used 103 focused tests; the four
additional local cases are the runtime-package transaction tests. The exact
single-job clean-build transcript is archived beside the generated build state
as `data/build/mshv-auto-dx/phase1-native-build-remediation.log`; hashes in
`compiled-source.json` and the packaged `om0rx-build.json` remain the authority.

`settings/database/cty.dat` comes from this application's country data;
`dxcc_numbers.dat` is generated from `data/cty.csv`. The patch rebuilds DXCC
number mappings without collisions and updates every alias and exact-call
lookup. Entities absent from the official mapping use separate 10000+ fallback
IDs rather than colliding with official ADIF IDs. The tracker database is
`settings/database/worked.db` (upstream documentation calls it `autodx.db`).

## Station contract

The supervisor passes `OM0RX_API_BASE` (default `http://127.0.0.1:8080`) and
`OM0RX_CONTROL_TOKEN`; tokens are never printed or stored in runtime INI files.
Only localhost endpoints are allowed. Automatic band or nonstandard dial
requests use two fail-closed calls to `POST /api/digital/station-ready`.
Before CAT QSY, native MSHV sends:

```json
{"provider":"mshv_auto_dx","request_id":"UUID","phase":"prepare","frequency_hz":14074000,"band":"20m"}
```

`X-OM0RX-Control-Token` carries the configured token. Prepare must return HTTP
2xx with matching `request_id` and `phase`, plus `ready:true`, `prepared:true`,
`transmit_ready:false`, and an opaque `prepare_nonce`. The native client uses one
75-second request deadline, leaving margin beyond the backend's bounded accessory path.
MSHV then issues CAT QSY and waits for exact CAT frequency observation. Its
`phase:final` request carries the prepare nonce. The backend accepts that nonce
once only and only while its provider, managed PID/process identity, bridge
client/endpoint, frequency, band, DIGU mode, antenna route, KPA policy and KAT
antenna still match. Final returns a short-lived opaque `permit_nonce`.

Immediately before hardware output, the lowest shared CAT/RTS/DTR PTT-on edge
must receive a successful response from the bounded
`POST /api/digital/station-permit/consume` endpoint. The backend revalidates
the authorization epoch, exact process/client binding, current frequency,
mode, Flex antennas, fresh idle/interlock proof, and fresh enabled-accessory
readback, then atomically consumes the nonce. A 1.5-second native timeout or
any rejection prevents hardware output and retires the ambiguous local nonce.
This also protects manual, Tune/Test and direct paths. During RX a new two-phase
permit is prefetched without changing the upstream Auto button, AutoDX desired
state, target, queue or QSO sequence. A missing, late, expired or mismatched
permit skips only that TX slot and requests a replacement; it does not stop
Auto or disable AutoDX. Explicit Stop, Halt and QSY invalidate authorization,
and stale replies cannot overwrite a newer route request. Band confirmation
still requires the exact CAT-observed frequency.

The native/server authorization generation also orders asynchronous revoke and
prepare traffic. A server prepare atomically retires older permits; a matching
late revoke notification is idempotent, while a newer Stop/QSY generation wins.
Every requested PTT edge has its own monotonic native sequence. After the
consume POST returns, the actual `HvRigControl::SetPtt_p` hardware path rechecks
that the sequence, generation, exact dial and requested-TX state are unchanged.
Re-entrant RX/Stop/QSY/frequency events therefore prevent a late success from
reaching CAT, RTS or DTR.

Every two seconds `POST /api/digital/engine-state` supplies provider, state,
enabled, target_call, frequency_hz and UTC timestamp. Standard WSJT UDP status
remains authoritative for actual TX. The backend expires this heartbeat after
six seconds and halts enabled automation. This heartbeat is telemetry and does
not schedule targets; MSHV owns the planner.

Managed launch preserves `[AutoDx] Enabled` from the portable native runtime.
OM0RX records the persisted preference for status reporting but does not
rewrite or disarm it, so native Auto DX ownership survives a managed restart.
The stopped-engine `/api/digital/mshv-settings` editor may set `enabled`
explicitly; no OM0RX/WSJT-Z planner is armed for MSHV operation.

Station identity freshness is stricter than operator-facing bridge health.
Authorization accepts only the exact managed process/client and a packet age
under 20 seconds, derived from the native 15-second heartbeat plus scheduling
margin. A bridge loss between prepare and final is audited by exact failure
stage and cannot issue a permit.

The native target scorer reads `[TargetPriority]` values from portable
`settings/autodx.ini`: `NewDxcc`, `NewBandSlot`, `NewGrid`, `CallingMe`, `Cq`,
and `SnrPerDb`. OM0RX exposes those through the stopped-engine-only
`/api/digital/mshv-settings` editor. New grid is clamped to a positive weight;
CQ and SNR are bonuses only after a new-category or calling-me eligibility
match, so they cannot cause random/common already-worked stations to be chased.
DXCC, band-slot, grid and calling-me dimensions combine independently; a new
grid remains eligible whether or not the call is also a new band slot. The
default weights are 10000, 1000, 500, 400, 200, and 10 respectively.

The final native policy also reads the following portable `autodx.ini` keys.
The filter names intentionally match the WSJT-Z automation schema while the
MSHV core remains the only selection/QSY/PTT owner:

- `[Eligibility] FilterMatrixEnabled=false`; all-time `FilterNewCall`,
  `FilterNewDxcc`, and `FilterNewGrid` default true while
  `FilterNewContinent`, `FilterNewCqZone`, and `FilterNewItuZone` default
  false. On-band `FilterBandCall` and `FilterBandGrid` default true; the other
  four on-band dimensions default false. These switches take effect only when
  the matrix is enabled.
- `FilterContinents=EU,AF,OC,AS,SA,NA,AN`, `FilterLotwOnly=false`,
  `MinSignal=-20`, `Treat73AsCq=false`, and `WatchUnconfirmedDxcc=true`.
  LoTW or confirmation filtering is applied only when the corresponding
  `settings/database/lotw-users.txt` or `confirmed-dxcc.txt` data exists.
  Native `autodx_config` reports read-only `lotw_membership_capability` and
  `confirmed_dxcc_data_available` booleans from successful opens of those
  files. Writable `[Capabilities]` INI text cannot assert either capability.
- `[TargetPriority] PreferNonEurope=true`, `NonEuropeBoost=7500`, and
  `DxpeditionBoost=12000`. A fresh schema-1
  `settings/database/dxpedition_watch.json` may add the DXpedition boost to an
  otherwise eligible native target. It never creates a target, and the final
  local-decode requirement remains mandatory. Non-Europe and DXpedition
  boosts are applied only after a positive base eligibility score; neither can
  bypass fail-closed history, pending-Wavelog inhibition, minimum signal,
  continent/LoTW restrictions, or filter-matrix blockers.
- `[Selection] Order=score`; `last` instead selects the most recently decoded
  eligible station. `[Attempt] CallWindowSeconds=120` accepts only 120 or 240,
  `MaxConsecutiveWindows=1` is clamped to 1..20, and
  `SameTargetRetrySeconds=1800`. `RecentQsoCooldownSeconds=3600` suppresses a
  just-completed station for 0..86400 seconds (0 disables the cooldown).
  `ATNOMinimumCallMinutes=30` is adjustable from 1..180 minutes and keeps an
  all-time-new DXCC target active for at least that period while matching local
  decodes remain fresh. An operator double-click immediately replaces an
  unanswered automatic target and bypasses its retry delay; only a QSO that
  has already received a reply remains non-preemptible.
  `EngagedCompletionGraceSeconds=60` is clamped
  to 15..120 seconds and rounded upward to a 15-second FT8 slot; after a reply,
  the absolute target deadline is the normal attempt budget plus this grace.
  The published configuration/status schema is
  version 1; there is no configurable eligibility-class order or per-filter
  weight map.
- `[BandSwitching] MinimumDwellSeconds=180`. A directed caller, a schedule
  closure, or a materially higher-priority rare/new target may override dwell;
  routine quiet-band rotation may not.

Native `AUTODX-AUDIT` records use schema `om0rx.autodx.audit.v1` and include
selection class/reason/score, attempt and budget, stop/retry/preemption and QSY
reasons. The lowest native rig layer also records attempted PTT rising/falling
edges. These are observational events and add no TX permit/readback gate.

Every ordinary MSHV engine-state JSON POST also carries `autodx_status`
schema version 1. It exposes a UUID `selection_id` that is stable through queue
reinsertion and directed-caller suspension/resume, the selected target and
reason/class/score, attempt budget and remaining time, retry deadline, band
dwell and next-QSY time, active schedule, recent skip reasons, last directed
caller, audit counter/last event, and DXpedition catalog validity/expiry.
The `budget` object additionally reports `base_total_seconds`, configured
`engaged_completion_grace_seconds`, and whether that grace is active. Native
configuration telemetry exposes the same grace under `automation_timing`.
It also exposes the active cross-band `pending_verification` callsign, band,
external evidence source, selection reason, terminal reason, start time and
origin band; the object is cleared with the canonical verification lifecycle.
Eligible fresh cross-band alerts are selected fairly by band within the best
available priority class. The cursor advances only on a committed verification,
so multiple distinct calls on a busy lowest-index band cannot starve later open
bands; schedule exclusions and per-call|band retry deferrals are applied first.
While any native band change or saved-origin return is awaiting CAT outcome,
cross-band and same-band off-standard alerts cannot issue or overwrite a CAT
band/dial command. Ordinary selection, queue admission, slot reservation/TX
frequency output, directed-caller preemption and verification timeout aging
are held by the same native transition predicate. Decode evidence remains in
cache and is reconsidered normally after completion/failure cleanup. History's
independent safety deadline and the existing CAT acknowledgement timeout are
unchanged.
Baseline patrol has a separate deadline and band cursor from alert
verification. Verification outbound/return QSYs neither restart that deadline
nor move its cursor; after an excursion, patrol resumes round-robin across all
enabled bands whose schedules are open. A genuinely manual/external band
change anchors patrol to the observed band even while AutoDX is disabled; a
later enable grants a fresh interval from that anchor.
Locally decoded eligible targets are evaluated before network alerts. Once
patrol is due, lower-class new-band-slot alerts (including same-band
off-standard-frequency evidence) yield to patrol without being discarded,
while an urgent all-time-new DXCC alert may still interrupt.
The native logged-QSO callback terminal-clears matching selection and queue
ownership regardless of a stale legacy AUTO/QSO flag, discards suspended chase
state after a successful directed-caller QSO, and publishes an empty target in
`Listening` state. Unrelated/manual log events do not interrupt an active QSO.
The aggregate configured attempt budget remains terminal for unanswered
targets. A positively parsed response addressed to this station activates the
slot-aligned completion grace, with an absolute cap at normal budget plus the
configured grace. Cap expiry disables AUTO, clears queue and selection
ownership, and applies the same-target revisit delay even when a legacy
engaged flag remains asserted.

Native FT8 sender parsing is fail-closed. CQ is recognized only as the leading
protocol token. Standard messages require resolved `<TO> <FROM>` fields, and
only `FROM` is admitted as locally heard. A sole recognizable destination with
an unresolved/hashed sender cannot satisfy verification, scoring, or the final
queue guard. Resolved angle-bracket calls and portable calls remain supported.

At startup, native AutoDX keeps a one-time idle reconciliation armed until both
the persisted legacy target editor and WSJT-compatible UDP Status cache have
finished hydrating. It clears an exact call/grid pair only when a valid, recent
`settings/database/autodx_status_owner.json` marker proves native AutoDX wrote
that target. Equal caches without provenance, an active exchange, a divergent
manual/foreign pair, and malformed, future-dated or older-than-24-hour markers
are preserved. Ownership-marker replacement uses `QSaveFile` atomic commit and
the marker is retired after authoritative clear or foreign replacement.
Status-field deduplication also compares the actual UDP cache, so a locally
cached empty value cannot suppress this authoritative empty-target update.
This reconciliation mutates status fields only and has no AUTO, PTT, CAT,
queue, selection, or QSY side effects.

`settings/database/dxpedition_watch.json` is checked every five seconds using
its replacement mtime/size fingerprint and is reparsed after atomic replacement.
Missing, malformed, non-schema-1, future-dated or expired catalogs clear all
catalog boosts and leave ordinary AutoDX selection unchanged. A valid active
catalog alias only boosts a target that MSHV decoded locally and found eligible.
It does not initiate QSY. Off-standard QSY requires a fresh explicit-FT8 RBN or
native DX-cluster spot and still waits for a matching local decode before call;
spot identity includes call, band and a 100-Hz frequency bucket so simultaneous
same-call/same-band frequencies do not collapse together.

This hook guards AUTO and Auto DX QSY. Manual Tune/TX buttons remain operator
controls and must still obey the backend's radio safety policy. Production
cross-band qualification must test actual CAT acknowledgement and station
accessory readiness before unattended use.

## Explicit historical migration

Export canonical history first using `scripts/digital/export_history.py`. Then:

```powershell
python scripts/mshv/import_history.py --runtime data/build/mshv-auto-dx/runtime --adif data/migration/mshv/canonical.adi
python scripts/mshv/import_history.py --runtime data/build/mshv-auto-dx/runtime --adif data/migration/mshv/canonical.adi --apply
```

The first command is a dry-run report. Apply is an explicit administrative
action and is never invoked by ordinary launch. It refuses the exact packaged
MSHV executable process (unrelated MSHV installations do not match), acquires
`.history-import.lock`, verifies existing ADIF is already in Wavelog, stages a
fresh native log and SQLite tracker using an offline executable mode, checks
SQLite integrity, and backs up originals under `history-backups`. Identical
canonical history is idempotent. An existing native log without an ADIF mirror
must be exported before migration, preventing silent loss. Native log default
is raised from 50000 to 150000 QSOs; offline importer permits up to 500000.
Historical tracker import supports FT8, FT4 and MFSK/SUBMODE=FT4; unspecified
modes are not silently classified as FT8.

Input must have an adjacent `canonical.adi.report.json` from the canonical
Wavelog exporter, explicitly qualified using `--qualify-migration` after count
review. Source provenance, station, eligibility, policy, exact source record
counts and the exact ADIF SHA256 are verified. WSJT ADIF is audit-only and is
never imported; WSJT-only, raw-union, forensic candidate and any other
ineligible report is rejected.
SQLite WAL/SHM/journal sidecars also block migration until the existing store
has been cleanly closed/recovered.

Before replacing any file, migration verifies every native call/date/time/
band/mode identity and its total count, and exact SQLite call/band/mode coverage
against canonical Wavelog history. Output store hashes and verified counts are
recorded in the marker. The recovery journal is valid before backup work and
records whether originals are untouched (`preparing`) or replacement began
(`committing`). A backup failure preserves originals and removes the lock.

If interrupted mid-commit, the lock remains as a recovery journal. Stop the
packaged runtime and run
`python scripts/mshv/import_history.py --runtime data/build/mshv-auto-dx/runtime --recover`.
Recovery validates the journal/runtime identity and every backup SHA256 before
atomically restoring originals (and removing targets that did not originally
exist). A second interruption during rollback is idempotently recoverable.
Launcher and native startup refuse normal execution while this journal exists.
On an ordinary exception the same recovery path restores originals
automatically. The original canonical ADIF and WSJT profile are never modified.

## Qualification status

Native build, offline fixture imports and local fake HTTP gate tests validate
software only. No live SmartSDR settings are altered by build/test scripts and
tests never key the radio. Receive-only, dummy-load, logging-outage, emergency
halt, crash, cross-band and extended live soak gates remain operator tests.

## Current operator-configuration readiness

The packaged runtime was subsequently qualified in a supervised receive-only
session. These persisted operator values are separate from build/package
attestation and must be preserved when the runtime is rebuilt or replaced.

| Item | Current state |
| --- | --- |
| Callsign/grid | Persisted and observed as `OM0RX` / `JN88`. |
| Auto DX operating mode | Search-and-pounce is enforced in the integrated AutoDxer core; CQ-on-free-slot is disabled. Auto DX/Auto/Tune remain off at receive-only startup. |
| US spotters filter | Persisted off; worldwide sources are allowed. The separate US-only grid filter is also explicit in the OM0RX priority editor. |
| Flex CAT | Native FlexRadio 6xxx network CAT is persisted at `127.0.0.1:5002`; receive frequency/mode readback was observed without PTT. |
| DAX audio | DAX RX 1 capture was selected and receive decodes were observed. The TX endpoint was identified/configured for the staged QSO profile but no completed on-air QSO qualification has yet validated the full TX/audio chain. |
| UDP bridge | Implemented: exact client ID `MSHV-OM0RX-AUTO-DX`, loopback host `127.0.0.1`, supervised `OM0RX_UDP_PORT` (currently application port 2237), ADIF logging and decode/status forwarding. |
| Engine selector | Backend/frontend switching among None, WSJT-Z and MSHV is implemented. Missing/invalid state defaults to None. The supervised receive-only session selected `mshv_auto_dx`; no WSJT-Z process was run concurrently. |

Do not claim unattended RF readiness until the DAX TX/PTT chain, one-QSO logging,
emergency halt under TX, and extended station soak have been verified with the
live SmartSDR station. Receive-only success is not transmit qualification.
