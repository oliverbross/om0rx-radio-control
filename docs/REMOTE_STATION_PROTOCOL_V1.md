# Remote Station Protocol v1

This is the integration contract between OM0RX-xCat on macOS and the
independent Windows station agent. The transport is HTTPS and WebSocket over
Tailscale Serve. Every endpoint requires the bearer token in the
`Authorization` header.

## Command envelope

Send commands to `POST /api/v1/commands`:

```json
{
  "request_id": "xcat-7b5a1fc8-73a2-4b9f-a709-524b78dbf46a",
  "command": "set_frequency_hz",
  "arguments": {"frequency_hz": 14074000}
}
```

`request_id` is 8–128 ASCII letters, digits, dots, underscores, colons, or
hyphens. A retry must reuse the same ID and identical command content. A reused
ID with different content is rejected.

Successful responses contain `success`, `request_id`, `result`, `state`, and
`replayed`. Errors contain `success: false` plus a stable error `code` and a
human-readable `message`.

## Commands

| Command | Arguments | Notes |
| --- | --- | --- |
| `set_frequency_hz` | `frequency_hz: integer`, optional `vfo: A or B` | Ham-band frequencies only; guarded route change; VFO defaults to A. |
| `set_mode` | `mode: string`, optional `vfo: A or B` | Guarded route change; VFO defaults to A. |
| `set_ptt` | `enabled: boolean` | PTT-on is atomic with station preflight; PTT-off remains available for recovery. |
| `set_rit` | `enabled: boolean`, `offset_hz: integer`, optional `vfo` | Offset range −9999…9999 Hz. |
| `set_xit` | `enabled: boolean`, `offset_hz: integer`, optional `vfo` | Guarded because it changes the transmit route. |
| `set_receive_vfo` | `vfo: A or B` | Maps RUMlog `FR` to SmartSDR slice `active=1`. |
| `set_split` | `enabled: boolean`, optional `tx_frequency_hz: integer` | Maps RUMlog `FT` to slice A/B `tx=1`; version 1 permits same-band split only. |
| `set_rf_power` | `watts: integer` | Must exactly match the active PA/barefoot policy. |
| `set_cw_speed` | `words_per_minute: integer` | Range 5…100 WPM. |
| `send_cw` | `text: string` | 1…128 printable ASCII characters; atomic TX preflight. |
| `clear_cw` | none | Clears CWX and explicitly returns the radio to receive. |
| `station_standby` | none | Requests KPA standby and safe receive state. |
| `station_operate` | none | Requires commissioning and exact readback. |
| `station_tune` | none | Runs the guarded KAT tune transaction. |
| `station_cancel` | none | Cancels tuning and restores safe state. |

## State stream

Connect to `WS /api/v1/stream` with the bearer header. The agent sends:

```json
{"type": "state", "state": {"protocol_version": 1, "revision": 42}}
```

whenever the monotonic revision changes, and:

```json
{"type": "heartbeat", "revision": 42}
```

after 15 seconds without a state change. `GET /api/v1/state` returns the same
state for initial connection and recovery after a WebSocket interruption.

`state.radio.vfos` contains the station's SmartSDR slice A/B records.
`state.radio.active_receive` is the slice selected by RUMlog `FR`, while
`state.radio.transmit` is the slice selected by `FT`. The top-level
`state.radio.frequency` and `mode` remain the transmitter-routing authority for
the KPA/KAT safety coordinator.

Clients must treat the following as transmit-inhibiting conditions:

- `radio.connected` is not `true`;
- `radio.known` is not `true`;
- `radio.stale` is not `false`;
- `station.commissioned` is not `true`;
- the station snapshot reports blockers or an active alarm.

The Windows agent is authoritative for enforcement. OM0RX-xCat should display
the same conditions, but it must not implement a separate check-then-transmit
sequence or send route/PTT writes directly to SmartLink when agent mode is
enabled.
