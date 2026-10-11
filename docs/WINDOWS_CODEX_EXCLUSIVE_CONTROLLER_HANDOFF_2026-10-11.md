# Windows Codex handoff: exclusive OM0RX station-controller ownership

Copy the prompt below into Codex on the Windows station machine. Work from the
Git branch and exact commit reported with this document.

## Prompt for Codex on Windows

Implement and validate exclusive controller ownership between the legacy
OM0RX Radio Control Agent and the newer OM0RX Remote Station Agent. Do not
change or weaken any FLEX, Maestro, KPA500, KAT500, interlock, route, or
transmit safety policy.

### Confirmed root cause — 2026-10-11

Two independent Windows agents were running concurrently and competing for
the same station resources:

- Legacy controller: **OM0RX Radio Control Agent**, launched from the HKCU Run
  value `OM0RX Radio Control Agent` and implemented by
  `tools/Om0rxAgent/Om0rxAgent.exe`.
- Remote controller: **OM0RX Remote Station Agent**, launched from the
  scheduled task `OM0RX Remote Station Agent` and implemented by
  `python -m remote_station run`.

While both ran, the station showed FLEX/Maestro interlock errors, conflicting
KPA500/KAT500 band state, HTTP 409 route-command rejection, and RUMlogNG spot
frequency changes that did not persist through OM0RX-xCat. Oliver stopped the
legacy OM0RX Radio Control Agent and the problem immediately disappeared.

This supersedes the earlier theory that the coordinator should accept FLEX
`NOT_READY` for route recovery. Do **not** relax `_fresh_receive_state()`, add
`NOT_READY` to general receive-safe states, or bypass any interlock based on
the earlier handoff.

### Existing partial protection

- `tools/Om0rxAgent/Program.cs` uses the mutex
  `OM0RX.RadioControl.Agent`, but that only prevents a second legacy .NET agent.
- `scripts/remote_agent/run_remote_agent_tray.ps1` protects the tray with
  `Local\OM0RXRemoteStationTray`.
- `scripts/remote_agent/remote_agent_widget.ps1` similarly protects each
  widget instance.
- The Python remote station controller does not currently participate in the
  legacy controller's mutex.

The remote tray and station widget are control surfaces for the Python remote
agent. They must remain usable and must not be mistaken for a competing station
controller.

### Required investigation

1. Fetch the handoff branch and verify its exact SHA before editing. Preserve
   unrelated Windows work and credential-bearing local configuration.
2. Confirm the exact live executable, command line, parent process, startup
   registration, ports, FLEX connection, and COM-port ownership for both
   controller paths. Sanitize all output.
3. Verify that stopping the legacy controller leaves the Python remote agent,
   tray, widget, OM0RX-xCat, RUMlogNG, and station route healthy.
4. Determine whether the legacy agent directly owns station resources or
   starts/manages another backend process. Place the ownership guard at the
   point that actually acquires or supervises FLEX/Elecraft control, not only
   in a cosmetic UI process.
5. Inventory every supported entrypoint that can start either controller:
   scheduled task, HKCU Run entry, Start-menu shortcut, desktop shortcut,
   PowerShell launcher, direct executable, and direct Python invocation.

### Required implementation

Create one shared Windows-wide controller-ownership contract used by both
controller families.

- Use a Windows named kernel mutex with one stable shared name, such as
  `Global\OM0RX.StationController`, from both the .NET controller and Python
  remote controller. Confirm the final name works from the actual scheduled
  task and interactive-user contexts on this machine.
- Acquire the shared mutex before opening any FLEX connection, serial/COM
  device, station-control listener, or supervised legacy backend.
- Hold ownership for the complete controller lifetime. Release it on orderly
  shutdown; rely on Windows abandonment semantics after a crash.
- Preserve the existing per-application mutexes where useful for tray/window
  behavior, but do not treat them as the cross-controller safety boundary.
- If ownership is unavailable, the second controller must fail before touching
  station hardware. It must not retry forever, steal ownership, stop the other
  controller, or start a child backend.
- Return a distinct non-zero exit code and log a concise actionable message:
  another OM0RX station controller is active, which controller requested
  ownership, and how to inspect/stop the intended startup entry.
- Maintain a small atomic owner-information record containing only safe
  diagnostics such as controller family, PID, executable path, UTC start time,
  and launch source. The named mutex remains authoritative; stale metadata
  must never block startup by itself. Do not store credentials or full command
  lines containing secrets.
- Surface the conflict in the appropriate tray/settings UI and Windows Event
  Log or existing sanitized log. Avoid repeated dialogs from scheduled-task
  restart loops.
- Retain independent single-instance behavior for the remote tray and widget;
  those processes must not acquire the controller mutex.
- Retain existing port-binding and COM/FLEX connection failures as secondary
  safeguards and diagnostics.

### Startup and migration behavior

Make the installation/startup scripts detect the conflicting startup paths:

- HKCU Run value: `OM0RX Radio Control Agent`
- Scheduled task: `OM0RX Remote Station Agent`
- Remote tray task: `OM0RX Remote Station Tray` — this is allowed and should
  not be disabled merely because the remote controller is active.

The installer must not silently leave both controllers configured to start.
Provide an explicit, reversible migration path to select the Python Remote
Station Agent as the station owner and disable the legacy controller's HKCU
Run entry. Do not remove shortcuts, settings, or application data unless the
operator explicitly requests removal. If automatic migration cannot be made
safely, fail installation with exact instructions instead of creating a
dual-controller boot configuration.

The live Windows machine currently intends the Python **OM0RX Remote Station
Agent** to be the active controller. Inspect current state before modifying it;
do not assume the legacy process is still running merely because its startup
entry exists.

### Regression coverage

Add automated coverage for at least:

1. Legacy controller starts first; Python remote controller refuses before any
   station resource is opened.
2. Python remote controller starts first; legacy controller refuses and does
   not start its supervised backend.
3. A second copy of either controller refuses cleanly.
4. Tray and widget can run with the Python controller without competing for
   controller ownership.
5. Normal shutdown releases ownership and permits the other controller to
   start.
6. Crash/abandoned-mutex recovery permits a later clean start and reports the
   prior abandonment without bypassing startup validation.
7. Stale owner metadata alone does not block startup.
8. Concurrent launch races result in exactly one controller owner.
9. The losing scheduled task does not enter a noisy restart/dialog loop.
10. Installer/migration detection distinguishes the legacy HKCU Run entry,
    remote controller task, and allowed tray task.

Run the complete maintained Python smoke suite, focused remote-agent/tray
tests, the .NET agent test/build workflow, relevant PowerShell contract/parser
tests, Node tests where applicable, Ruff `F,E9`, Python compile checks, and Git
whitespace checks. Report exact pass/fail counts.

### Live acceptance boundary

Do not perform a transmit test. Do not issue PTT-on, TUNE, CWX, Operate, or any
command that can produce RF. Keep KPA500 in verified standby.

With the intended Python Remote Station Agent running:

- Attempt to start the legacy controller and prove it refuses before opening
  FLEX, COM ports, or its managed backend.
- Confirm the Python agent remains healthy and its PID/start time is unchanged.
- Confirm the remote tray and widget remain usable.
- Confirm FLEX remains bound to Maestro, MOX remains false, KPA500 remains in
  standby, KAT500 is readable, and the route remains confirmed.
- Confirm OM0RX-xCat remains connected and RUMlogNG retains receive-only CAT
  readback.
- Stop no active controller unless Oliver explicitly authorizes that live
  lifecycle action. Prepare the exact acceptance commands first if such an
  action is needed.

### Deliverables

- Commit the fix and tests on a `codex/` branch.
- Add a dated result and exact live/offline evidence to
  `docs/REMOTE_STATION_HANDOFF.md`.
- Never commit tokens, passwords, private keys, or local configuration.
- Push the branch and report the exact branch name and commit SHA to Oliver.
- Clearly separate offline test proof from live Windows acceptance.

