# Digital engine backend contract

The selected provider is `none`, `wsjtz`, or `mshv_auto_dx`, persisted atomically in
`settings/digital_engine.json`. Existing `/api/wsjtx/` routes remain available.
Missing or invalid selection fails safe to `none` and never enables TX. The
only legacy migration is the Agent's explicit `StartWsjtzWithAgent` preference.

| Endpoint | Meaning |
| --- | --- |
| GET `/api/digital/status` or `/config` | Provider, label, planner owner, capabilities, running PIDs, conflict, bridge health and expiring MSHV telemetry |
| GET `/api/digital/preflight?provider=mshv_auto_dx` | Portable executable and build manifest availability; no launch |
| POST `/api/digital/select` | `{provider}`; stop the previous engine after halt and confirmed radio RX, reset UDP ownership, persist selection |
| POST `/api/digital/start` | Optional `{provider}`; select and launch, then await up to 45 seconds for managed-process, exact bridge-client and fresh-heartbeat confirmation. Returns 202 `starting:true, ready:false` when the exact owned process remains alive but cold-start telemetry is delayed; 503 is reserved for exited/unowned/conflicting startup. |
| POST `/api/digital/stop` | Halt, confirm radio RX, stop digital processes and reset UDP return endpoint |
| POST `/api/digital/restart` | Stop and start selected provider |
| POST `/api/digital/halt-tx` or `/halt` | Provider-independent emergency UDP Halt Tx and Flex MOX off; reports `command_accepted` separately from fresh `idle_confirmed` readback |
| POST `/api/digital/log-qso` | Canonical durable QSO logging, identical to legacy `/api/wsjtx/log-qso` |
| POST `/api/digital/station-ready` | MSHV station interlock described below |
| POST `/api/digital/station-permit/consume` | Bounded authoritative pre-PTT permit consume |
| POST `/api/digital/engine-state` | MSHV state heartbeat described below |
| GET/POST `/api/digital/mshv-settings` | Read or persist stopped-engine native AutoDX policy; POST is rejected while any digital engine is running |
| GET `/api/digital/mshv-history/reconcile-preview` | Read-only list of legacy pending entries exactly backed by the attested canonical Wavelog export |
| POST `/api/digital/mshv-history/reconcile` | Explicit stopped-engine promotion of source-backed entries; requires `{confirm_source_backed:true}` |
| GET `/api/digital/mshv-daily-summaries` | Exact-once daily band/target/QSO summaries from stable native selection IDs and acknowledged QSO event IDs |

`GET /api/digital/status` exposes `station_identity_fresh` separately from
general bridge health. Station authorization uses the exact client ID and a
20-second maximum packet age: the native heartbeat cadence is 15 seconds, with
a five-second scheduling margin. The broader UI health window is never used to
approve a station permit.

Selection/start/stop are serialized with a process lock and OS file lock.
Switching fails closed on unknown radio TX state, an unresponsive old process,
or bridge refusal. All managed WSJT and MSHV processes are enumerated before
launch. An unmanaged operator launch can still physically run a second program;
status reports a conflict and the UDP bridge only accepts the selected provider.
Selecting `none` safely stops either engine, clears UDP ownership, fully disarms
and clears the planner, and prevents the Agent watchdog from starting or repairing
an engine. Starting `none` is an explicit disabled response, never a process launch.

MSHV selection clears and persists retired OM0RX targets, disables auto call/CQ,
and disables the OM0RX planner. Ranking is restored when WSJT-Z is selected;
automatic TX remains off until the operator enables it. Target commands,
planner settings/ticks, ranking/listen selection, and backend Flex dial/mode/TX
commands are guarded while MSHV owns the station. Emergency TX off is allowed.
The browser also disables all OM0RX/WSJT-Z TX, Tune, QSO-engage, band/mode,
offset and automation controls while MSHV owns operation. Its emergency halt
control remains enabled and always calls `/api/digital/halt-tx`.
The same TX/planner controls remain inert when `none` is selected.

GET/POST `/api/digital/mshv-settings` exposes the active native Auto DX runtime
configuration. Writes are accepted only when every digital engine is stopped,
are backed up and applied by `AutoDxerCore` on the next MSHV start without
requiring the native settings dialog. Phase 1 includes callsign/grid, FT8-only
mode policy, the explicit cross-band switch, enabled bands (160–10m excluding
60m), ATNO chase type, scarce threshold, RBN/PSKReporter/DX-cluster source
settings and servers, US-only filters, grid/min-SNR and all target weights. New
DXCC, new band slot, new grid and a station explicitly calling OM0RX are
eligible categories. CQ and SNR are ranking bonuses only; they never make a
random/common already-worked call eligible. New-grid chasing remains enabled
with a nonzero weight. Responses distinguish saved `desired` policy from the
live `effective` native heartbeat status.
`runtime_parity.status` is `match`, `drift`, or `unknown` and checks every
operator-visible Phase 1 knob (identity/grid, weights and eligibility, SNR,
bands/modes, ATNO/scarce, cross-band gate, and complete source/server policy)
against native telemetry. External spots require explicit FT8 mode evidence;
FT4 and untyped/nonstandard-frequency cluster spots cannot initiate QSY.
Managed MSHV process starts preserve the native persisted Auto DX preference.
MSHV remains the sole planner: `auto_dx_enabled` and
`auto_dx_saved_preference` report the portable runtime's `AutoDx/Enabled`
value, while `auto_dx_startup_forced_off=false` confirms that OM0RX did not
rewrite it during launch. A stopped-engine settings write may set `enabled`
explicitly; the next managed start honors that native preference.

Windows process ownership scans use an exact-column WMIC snapshot where that
component is available, protected by a short single-flight cache. Lifecycle
operations force a fresh scan. Newer Windows systems without WMIC retain a
CIM fallback with a longer cache so ordinary browser/Agent status polling does
not spawn a multi-second PowerShell scan on every request.

The Node bridge accepts the exact MSHV client ID `MSHV-OM0RX-AUTO-DX`, pins one live UDP
client endpoint, resets it on lifecycle requests, and attaches `provider` and
`planner_owner` to existing WSJT websocket events. Standard type 5/12 logged
events are paired per call/mode/frequency, preferring ADIF with a 1.5 second
provisional receipt fallback. Provisional type 5 is saved durably and never
submitted to Wavelog until authoritative ADIF arrives. Late type 12 always upgrades
the receipt. Pending receipts are visible at `/api/digital/logging/provisional`.
Interleaved QSOs cannot cancel each other. The existing durable retry
queue and backend dedupe/outbox handle restarts and network outages.

## Station interlock

The request contract is exact, correlated and two-phase:

`{provider:"mshv_auto_dx", request_id, phase:"prepare"|"final", frequency_hz, band, mode:"DIGU", prepare_nonce?}`.

The response echoes `request_id` and `phase`. `prepare` applies target-band
antenna/accessory policy while the radio is still on the old dial and returns
`ready:true`, `prepared:true`, `transmit_ready:false` and a short-lived opaque
`prepare_nonce`; it never grants TX. Native MSHV then performs CAT QSY and waits
until it observes the exact target dial. `final` must present that nonce. It is
accepted once only when provider, managed PID/process identity, exact bridge
client/endpoint, frequency, band, mode, antenna route and accessory policy still
match. Final performs a new, non-mutating Flex and accessory hardware readback
and returns `transmit_ready:true` plus a short-lived opaque `permit_nonce` only
when the observed dial, DIGU mode, RX state, antenna routing and enabled
Elecraft state all match. An old-band background poll cannot undo the prepared
target routing. Missing, replayed, expired or mismatched nonces and stale
readback fail closed. No frequency or PTT command is sent by this endpoint.
Unhandled device or transport errors also return `ready:false` with a
`failure_stage`; the authorization audit records that stage, exception type,
and detail. This distinguishes process/client loss, standby failure, route
preparation, accessory refresh, combined readback, and nonce/permit issuance
without weakening the fail-closed response.

Only selected MSHV and a valid amateur band (60m excluded) are accepted. API
control-token protection applies; the launcher inherits `OM0RX_CONTROL_TOKEN`
and `OM0RX_API_BASE` without including secrets in arguments or logs. A final
permit is consumed once through `POST /api/digital/station-permit/consume`
before the lowest shared native CAT/RTS/DTR PTT-on edge. That bounded endpoint
rechecks the authorization epoch, exact process/client binding, live Flex
frequency/mode/antennas and independent idle/interlock proof, plus cached-fresh
enabled-accessory readback. Only its atomic `permit-consumed` result allows the
hardware call; timeout, replay, revocation or drift fails closed. This includes
manual, Tune/Test and direct paths. RX-time renewal is non-mutating:
authorization failure skips only the current TX slot while upstream Auto,
AutoDX, queue and target state remain intact. Halt/stop, route/process/client
change and expiry invalidate authorization.

Consuming the preparation also captures its server authorization epoch and
native generation.  Permit insertion reuses those exact values; it never
adopts the epoch that happens to be current after the slow final hardware
checks.  Under the lifecycle lock it refreshes and matches the selected
provider, managed process identity and bridge client immediately before
insertion.  Halt, provider/client/process change, authorization clear or a
newer native generation during that interval therefore leaves
`ready:false`, `transmit_ready:false` and cannot mint a permit.

When the Windows lifecycle supervisor is active, every telemetry, readiness,
and permit operation also validates the atomic runtime-owner manifest. The
check covers the exact supervisor/backend/bridge PID, executable path, process
creation identity, and actual IPv4 listener owner for the backend port plus
bridge ports 8091 and 8092. A missing listener, additional listener owner, PID
reuse, or listener-query failure revokes authorization and fails closed.

Lifecycle cleanup is limited to the application-owned backend and bridge
listeners (the configured backend port/8080, 8091, and 8092). TCP 12166 belongs
to the external SDC service and UDP 2237 is a client input; neither is stopped
by the launcher. If the backend disappears, the supervisor sends a bounded,
authenticated `halt_tx` directly to the bridge first, checks bridge/backend
idle evidence when available, and only then stops the exact attested bridge.

Native requests also carry a monotonically increasing authorization generation.
Starting a new `prepare` atomically retires every prior preparation and permit
on the server. Because the native invalidation audit is asynchronous, a delayed
audit for the same generation is idempotent and cannot revoke the preparation
that already superseded it; a newer Stop/QSY generation still revokes it. The
lowest PTT path separately sequences every requested TX/RX edge and, after a
successful consume response, rechecks that sequence, generation, dial frequency
and requested-TX state before touching CAT/RTS/DTR. Thus a late 2xx cannot key
the radio after RX, Stop, QSY or a frequency change was processed while the
bounded network wait was active.

KPA500 behavior is an explicit durable operator policy. In DIGU, DIGL, RTTY,
and every other non-voice/non-CW radio mode, `DIGITAL_KPA_POLICY` is the master
switch and `STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS` selects the bands on which
the PA may operate. `STATION_DIGITAL_AMPLIFIER_DRIVE_W` selects the
mode-specific PA drive. Digital bands without PA permission continue to use
their standard barefoot drive. CW, SSB, FM, and AM continue
to use `STATION_AMPLIFIER_ALLOWED_BANDS`, `STATION_AMPLIFIER_DRIVE_W`, and
`STATION_BAREFOOT_DRIVE_W`. The shared effective result is exposed as
`station_policy.kpa500`. The exact effective mode and drive are bound into the
one-use PTT permit and re-read from FLEX immediately before permit consumption.
`standby` readiness requires the configured
amplifier to remain connected and powered, on the requested band, with a
healthy fault code, `operate=false`, and zero output power/current. It fails
closed if the amplifier enters operate, reports a fault, shows TX output, or the
FLEX drive differs from the permit.

Manual Prepare/Operate while MSHV owns CAT/PTT uses a short station-control
lease. The lease atomically revokes preparations and permits, inhibits new
authorizations, and requires two independent receive proofs before any relay or
amplifier write. Releasing the lease lets MSHV prepare normally for a later slot.

Heartbeat: `{provider, state, enabled, desired_enabled, autodx_config,
autodx_status, target_call, frequency_hz, timestamp}`. `autodx_config` contains the native
mode gate, cross-band gate, enabled bands, ATNO/scarce policy, callsign/grid,
scoring weights/eligibility, SNR/grid policy, and applied source/server status;
absent fields make runtime parity unknown rather than being inferred.
`autodx_status` is observational and reports target, selection reason/class/score,
attempt budget/retry, band dwell/next QSY, active schedule, recent skip reasons,
last directed caller, and Wavelog state. See
`docs/mshv/AUTODX_POLICY_TELEMETRY_CONTRACT.md` for the canonical schema-v1 native contract.
The backend expires telemetry after six seconds and requests Halt Tx plus MOX
off if an enabled session stops reporting. Standard WSJT status remains the TX
observation authority. Hardware acceptance tests and a station soak test are
required before claiming qualified unattended RF operation; automated tests use
test doubles and never connect to or transmit with the station.

MSHV runtime: `data/build/mshv-auto-dx/runtime/MSHV_OM0RX.exe`, configurable with
`OM0RX_MSHV_RUNTIME`. Build metadata is read from `om0rx-build.json` if present.
MSHV portable settings/native log/tracker stay private to that runtime. Historical
ADIF reconciliation uses the migration tooling rather than sharing writable logs.

## Canonical history snapshot

Run `python scripts/digital/export_history.py --postgres --output data/migration/mshv/canonical.adi`.
The PostgreSQL mirror is read in a read-only repeatable snapshot, scoped to
`--station-id` (configured Wavelog station ID). Wavelog is the sole source of the
production FT8/FT4 ADIF. Optional `--adif` files are diagnostic only and never
contribute a record or field to production. `--station OM0RX` scopes records
to the station; logs with no station callsign inherit that explicit station.
The exporter never changes source logs, refreshes live caches, or writes to a
database. It fails visibly if a requested database/source is unavailable.

Output and adjacent `.adi.report.json` include deterministic normalized records,
SHA256, source totals, duplicates merged, rejected records, counts by mode/band,
and FT8/FT4 totals. Invalid identity records are counted, not invented. Truncated
ADIF aborts before output replacement. Review any rejected-record count before
import. Eligibility defaults false until `--qualify-migration` is supplied after
count/dedupe review. Native MSHV import/backup tooling is under `scripts/mshv/`.

Optional forensic ADIF comparison emits complete CSV/JSON with raw/normalized
fields, Wavelog primary IDs, exact/likely/ambiguous/absent classifications, mode
denominators, and mapping cardinality. Near matches use absolute UTC time within
180 seconds, including midnight, and 5 kHz frequency tolerance. Portable/base
calls and band/frequency inconsistencies remain lower-confidence diagnostics;
they cannot become import candidates. Repeated near contacts remain ambiguous.
The separate candidate ADIF is explicitly `not-for-mshv` and ineligible for
MSHV migration. `scripts/digital/import_reviewed_wavelog.py` dry-runs by default,
rechecks against the current mirror, and requires `--apply --reviewed-sha256`
before any canonical backend submission. The 2026-10-04 explicitly authorized
repair imported 50 freshly rechecked FT8/FT4 records through the Wavelog API;
its durable journal and post-verification evidence are under
`artifacts/mshv-forensics-20261004/wavelog-import-50/`. That repair is
independent of native MSHV history migration. After separate explicit
authorization, the final qualified Wavelog-only snapshot (39,135 FT8/FT4
records) was imported through the offline MSHV migration tool. Native-log
identity coverage, normalized tracker coverage, output hashes, backup creation,
and an idempotent second apply were verified; interactive MSHV and radio control
were never started.
Canonical band/frequency mismatches are always reported. Migration eligibility
is blocked by mismatches within the FT8/FT4 snapshot actually being imported;
unrelated all-mode inconsistencies remain visible for operator review.
