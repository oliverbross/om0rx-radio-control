# OM0RX Remote Station Agent

The remote-station agent runs independently of the full OM0RX Radio Control
application. It is the sole process that owns the FLEX-8400 TCP connection and
the KPA500/KAT500 serial endpoints. OM0RX-xCat is the macOS client and continues
to present a local CAT endpoint to RUMlog.

```text
RUMlog -> OM0RX-xCat (127.0.0.1:15002)
                    |
                    | HTTPS/WebSocket over Tailscale
                    v
           OM0RX Remote Station Agent
                    |
                    +-- FLEX-8400 TCP 4992
                    +-- KPA500 COM17 / 38400
                    +-- KAT500 COM15 / 38400
```

## Safety and ownership

- Never run this agent and the full OM0RX application against the same serial
  endpoints at the same time.
- The agent starts by requesting FLEX receive, KPA500 standby, and exact device
  readback. Transmit remains locked when that recovery cannot be proven.
- PTT on, PA operate, tuner actions, frequency changes, and split changes pass
  through the existing station coordinator.
- `station.commissioned` defaults to `false`. Change it only after the physical
  route, key-interrupt path, antennas, and drive table have been checked.
- The API requires a random bearer token even inside the private tailnet.

## Windows setup

Install Python 3.11 or newer. From PowerShell in the project directory:

```powershell
python -m pip install -r requirements-remote-agent.txt
.\scripts\remote_agent\init_remote_agent.ps1
python -m remote_station check
```

Open the generated path printed by `init`, set the FLEX LAN address, confirm
`flex.station_name` matches the active GUI station (currently `Maestro`), and
review every band. The default clean profile uses the current VSPE endpoints
COM17 and COM15 at 38,400 baud. The file is deliberately separate from the full
OM0RX application. Open it in Notepad at any time with:

```powershell
.\scripts\remote_agent\edit_remote_agent_config.ps1
```

Run interactively for the first receive-only validation:

```powershell
.\scripts\remote_agent\run_remote_agent.ps1 -LogLevel info
```

Install it at Windows login only after that pass succeeds:

```powershell
.\scripts\remote_agent\install_remote_agent_startup.ps1
```

The hidden scheduled task writes a rotating diagnostic log beside the
configuration at `%APPDATA%\OM0RX Remote Station\agent.log`.

### Windows tray controller

Install the separate interactive tray controller for the signed-in Windows
user:

```powershell
.\scripts\remote_agent\install_remote_agent_tray_startup.ps1
```

The tray starts at login and shows sanitized FLEX, KPA500, KAT500, route, and
alarm details. Double-click the icon or choose **Show details**. Its menu can
start, stop, or restart the `OM0RX Remote Station Agent` scheduled task, open
the agent log, and quit only the tray. Stop and restart require confirmation.

Choose **Settings** to manage the entire independent agent without editing
JSON or using PowerShell:

- loopback API port and masked bearer credential;
- FLEX address, port, slice, GUI station name, and antenna-policy enforcement;
- KPA500/KAT500 enable switches, serial ports, and baud rates;
- per-band FLEX antenna, KAT output, PA eligibility, PA drive, barefoot power,
  digital PA eligibility, and digital drive;
- radio-follow behavior, the digital PA default, tuner power/SWR/timeout, and
  the commissioning interlock.

Saving creates `agent.json.bak`, validates the complete candidate profile with
the Python agent, and atomically replaces the active JSON only after validation
passes. **Save** never restarts the service. **Save and restart agent** requires
another confirmation. Enabling commissioning additionally requires typing
`COMMISSION`; it does not key PTT or bypass live safety checks.

The details window and **Station control** menu also provide Standby, Operate,
Tune, and Cancel. Operate and Tune remain disabled while the running agent is
uncommissioned, request confirmation, and always use the authenticated command
endpoint and coordinator preflight. The tray intentionally does not provide a
raw PTT button; PTT/CW and radio commands come from the authenticated macOS
client and remain guarded by the same coordinator.

The bearer token is masked by default and is never written to the tray status
or agent log. Regenerating it is explicit because every client credential must
then be updated.

Both **Settings** and **Show station widget** launch as ordinary Windows GUI
windows with the PowerShell host console hidden.

### Desktop station widget

The tray starts a compact station widget automatically. Close it when it is not
needed and choose **Show station widget** from the tray to open it again. The
widget can be moved and resized, remembers its screen position, and is always
on top by default. Right-click it to toggle always-on-top, reset its position,
or close it.

The widget updates from the authenticated read-only state endpoint and shows:

- current FLEX frequency, mode, RX/TX state, interlock, and VFO A/B;
- configured FLEX RF drive;
- prominent transmit power and live/last SWR;
- KPA500 operate/standby, band, measured output, temperature, voltage,
  current, SWR, and fault;
- KAT500 mode, band, antenna, tuning state, forward/reflected ADC, SWR, and
  fault;
- route, amplifier/barefoot policy, active drive, alarm count, and
  commissioning state.

When the amplifier is operating, **TX POWER** uses the KPA500 measured output.
For barefoot transmission the available telemetry contains the FLEX requested
drive rather than a calibrated antenna-output wattmeter, so the widget labels
that value `~N W SET` instead of presenting it as measured power. SWR is marked
`LIVE` only when the hardware reports a live/valid sample; otherwise the last
available KAT500 sample is labelled `LAST`.

Remove only the tray startup task with:

```powershell
.\scripts\remote_agent\uninstall_remote_agent_tray_startup.ps1
```

## Tailscale transport

The agent listens only on `127.0.0.1:8840`. In an Administrator PowerShell,
publish it privately to the tailnet with Tailscale Serve:

```powershell
.\scripts\remote_agent\configure_tailscale_serve.ps1
```

Do not enable Tailscale Funnel and do not forward the agent port on the public
router. Configure OM0RX-xCat with the HTTPS URL reported by `tailscale serve`
and copy the `server.control_token` value into the macOS Keychain-backed agent
credential field.

## API contract

All HTTP and WebSocket connections use an `Authorization: Bearer <token>`
header. Tokens in URLs or query strings are rejected so they cannot leak into
browser history, proxy logs, or screenshots.

- `GET /api/v1/health` — connectivity and safety-latch summary.
- `GET /api/v1/config` — redacted station policy; never returns the token.
- `GET /api/v1/state` — complete FLEX, KPA500, KAT500, route, and alarm state.
- `POST /api/v1/commands` — idempotent command envelope.
- `WS /api/v1/stream` — state-change stream plus 15-second heartbeat.

Every command requires a unique `request_id`. Retrying the same command with
the same ID returns the recorded result; reusing an ID for different content is
rejected.

The version-1 command set covers RUMlog VFO A/B, receive/transmit VFO selection,
mode, PTT, RIT/XIT, same-band split, CW speed/text/clear, guarded RF power, and
station standby/operate/tune/cancel. Route-changing and transmit commands are
executed inside the station coordinator, not as separate "check then send"
operations.

`GET /api/v1/state` is the authoritative status feed for the macOS menu-bar
widget. It includes the FLEX state, KPA500/KAT500 readback, current route,
commissioning latch, alarms, supported commands, and a monotonic revision.
The exact request/response contract is documented in
[`REMOTE_STATION_PROTOCOL_V1.md`](REMOTE_STATION_PROTOCOL_V1.md).

## Commissioning order

1. Leave `station.commissioned` set to `false`, start the agent, and verify
   FLEX, KPA500, and KAT500 readback over Tailscale.
2. Confirm each band's FLEX antenna, KAT output, PA eligibility, PA drive, and
   barefoot drive against the physical station.
3. Exercise standby and receive-only band changes while physically observing
   the equipment.
4. Verify the KAT amplifier key-interrupt path and emergency receive recovery.
5. Set `station.commissioned` to `true`, restart the agent, and test into a
   dummy load before enabling remote antenna operation.
