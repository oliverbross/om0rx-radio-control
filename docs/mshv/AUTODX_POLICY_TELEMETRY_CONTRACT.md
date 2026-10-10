# AutoDX policy and telemetry contract

The OM0RX backend writes these settings only while every digital engine is
stopped. MSHV remains the sole target planner and the sole owner of native QSY
and PTT sequencing.

## Native settings schema v1

- `Eligibility/FilterMatrixEnabled`
- `Eligibility/FilterNewCall`, `FilterNewDxcc`, `FilterNewContinent`,
  `FilterNewGrid`, `FilterNewCqZone`, `FilterNewItuZone`
- `Eligibility/FilterBandCall`, `FilterBandDxcc`, `FilterBandContinent`,
  `FilterBandGrid`, `FilterBandCqZone`, `FilterBandItuZone`
- `Eligibility/FilterContinents` (comma-separated EU/AF/OC/AS/SA/NA/AN)
- `Eligibility/FilterLotwOnly`, `MinSignal`, `Treat73AsCq`,
  `WatchUnconfirmedDxcc`
- `TargetPriority/PreferNonEurope`, `NonEuropeBoost` (the filter matrix is
  eligibility, not a second set of invented weighting controls)
- `Selection/Order`, exactly `score` or `last`
- `Attempt/CallWindowSeconds`, `MaxConsecutiveWindows`,
  `SameTargetRetrySeconds`, `RecentQsoCooldownSeconds`,
  `EngagedCompletionGraceSeconds`; call window is
  exactly 120 or 240 seconds, consecutive windows are 1 through 20, and
  recent-QSO cooldown is 0 through 86400 seconds (default 3600; 0 disables it);
  completion grace is 15 through 120 seconds rounded upward to a 15-second
  FT8 slot (default 120)
- `BandSwitching/MinimumDwellSeconds`

LoTW-only must remain ineffective until the native runtime can advertise
`lotw_membership_capability=true`. The backend preserves the operator's
preference but labels it inactive when that capability is absent.
Capability is read-only runtime evidence from the actual `lotw-users.txt`
load; a writable INI `Capabilities` section is not trusted. Stopped-engine
settings report availability as unknown. `confirmed_dxcc_data_available` is
handled the same way when supplied by native telemetry.

`AutomationTiming/NormalCallSeconds` is obsolete and is neither written nor
used for parity. The displayed total attempt budget is derived as
`Attempt/CallWindowSeconds * Attempt/MaxConsecutiveWindows`. Runtime parity
normalizes native `automation_timing` attempt/dwell fields, flattened
`eligibility` filter fields, and `target_priority.non_europe_boost` into the
canonical API shape before comparing individual controls.

The canonical grace location is `[Attempt] EngagedCompletionGraceSeconds`.
The backend can read the accidental legacy `[AutoDX]` location, but the next
stopped-engine save migrates it to `[Attempt]` and removes only the legacy key.

## Native telemetry expected

The existing `/api/digital/engine-state` heartbeat accepts the native
`autodx_status` schema-v1 object. Native MSHV reports:

- `selection_id`, `target`, `selection_reason`, `selection_class`,
  `selection_score`
- `attempt` and `budget.{call_window_seconds,max_consecutive_windows,base_total_seconds,engaged_completion_grace_seconds,completion_grace_active,total_seconds,elapsed_seconds,remaining_seconds}`
- `next_retry.{call,utc,remaining_seconds}`
- `band_dwell.{minimum_seconds,elapsed_seconds,remaining_seconds,next_qsy_utc}`
- `active_schedule.{band_index,band,restricted,start,end,open_now}`
- `skipped_reasons`, `last_directed_caller.{call,utc}`
- `audit.{event_counter,last_event}` and
  `dxpedition_catalog.{valid,entries,mtime_utc,expires_utc}`
- `pending_verification.{active,callsign,band_index,band,source,reason,terminal_reason,started_utc,return_band_index}`
- `baseline_patrol.{timer_valid,elapsed_seconds,remaining_seconds,cursor_band_index,band_change_pending}`

Fresh cross-band new-DXCC/new-slot alerts retain their high-priority dwell
override and existing switch cooldown. Within the winning priority class,
native MSHV chooses one eligible band per round-robin turn rather than one
spot per turn. A busy band's distinct calls therefore cannot starve other open
bands. Closed schedules, source/mode failures and per-call|band retry backoff
are filtered before selection and cannot advance the cursor. The cursor moves
only when MSHV commits a verification attempt; calling still requires the
matching local decode and an unverified attempt still returns to its origin.
An in-flight band change, including an origin return or terminal return, owns
the native CAT command slot until completion or failure cleanup. Cross-band
and same-band off-standard evaluation cannot replace it with another band or
dial QSY. The same authoritative transition predicate also defers ordinary
target evaluation, queue admission, directed-caller preemption/resume and slot
analysis output. Decode evidence and verification timestamps are retained for
normal, exactly-once reconsideration after cleanup. The independent history
safety deadline still runs; no CAT timeout grace is added.

Baseline patrol uses an independent deadline and cursor. Alert verification
outbound and origin-return transitions do not reset either. Patrol advances
round-robin over every enabled schedule-open band, resumes after excursions,
and is re-anchored only by a committed patrol move or a proven manual/external
band change, including one observed while AutoDX is disabled. Local target
evaluation precedes external interruption. When the baseline deadline is due,
lower-class new-band-slot alerts wait (including same-band off-standard
frequency alerts) without losing their cached evidence; urgent all-time-new
DXCC alerts may still interrupt.

Standard FT8 decode admission is fail-closed: CQ must be the leading protocol
token and non-CQ messages require resolved TO and FROM calls. FROM is the sole
transmitter identity. An ambiguous line with only its destination resolved is
not local-hearing evidence and cannot verify or queue an external target.
Resolved angle-bracket and portable sender calls remain supported.

Wavelog authority is supplied separately by the backend history-status API;
it is not fabricated inside native AutoDX telemetry.

Status telemetry is observational. It must not call `StopAuto`, change the
AutoDX checkbox, clear a native target, authorize TX, or alter station-gate
decisions. `selection_id` must be stable for one native selection so daily
summary counting is exactly once.

Runtime parity reports `match` only for schema v1 and these canonical fields.
