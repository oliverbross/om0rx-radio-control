# Remove the remote agent's startup recovery latch

The installed macOS xLog 1.5.6 (source `58a1ca9a`) displayed the remote
agent's rejection: “Station controls remain locked until safe startup recovery
is confirmed”. This text originates in `StationCoordinator._require_recovered`,
not in the Mac app's startup or logbook recovery.

An authenticated, read-only state observation on 4 November 2026 at 09:17 UTC
confirmed FLEX connected, known, fresh, station-bound, MOX off and READY. The
station was commissioned, outside maintenance, but its coordinator remained in
`recovery_required`; only Standby was advertised. KPA500 was serial-connected
without a confirmed status response (`operate` unknown). The agent's retained
error reported that startup could not confirm receive and amplifier standby.
No radio or amplifier command was sent during this investigation.

The runtime initialized the coordinator with `recovery_required=True`, attempted
recovery once, then kept serving the API after failure without retrying recovery.
A transient or unavailable startup device response therefore latched normal
station commands off for the entire agent process.

The remote runtime now starts its coordinator with the normal default and starts
polling without a forced receive/standby transaction. Startup no longer imposes
this separate recovery requirement. Individual transactions continue to use
their existing current device-state checks; this change does not assert that an
amplifier with missing telemetry is ready to operate.

Validation: 170 tests passed across the remote agent, station coordinator and
station alarms suites. The new startup regression uses the real coordinator's
command-admission gate with missing amplifier readback and verifies polling
starts without invoking startup recovery or sending hardware writes.

The change is based on agent branch `codex/latency-route-polling` at `d3b5509`.
The original Mac agent checkout's unique local commit `67d2902` and untracked
build artifacts were left intact; development used a separate worktree.

Deployment is pending on Windows. The live HTTPS endpoint is reachable, but
SSH was unavailable and the connected Desktop Commander inventory provided no
online Windows device. The Mac application was not replaced, and its logbook,
settings and drafts were not modified. Apply this change to the actual owning
Windows checkout after checking its running source and local changes, then
restart the existing agent using its established launcher. Preserve `agent.json`
and verify the new state no longer advertises startup recovery. An agent update,
rather than a Mac application rebuild, is required for this server rejection.
