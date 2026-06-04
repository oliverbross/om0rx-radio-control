# WSJT-Z Automation Porting Map

OM0RX should keep the patched WSJT-X Improved build as the RF/decode/CAT engine
and port the WSJT-Z hunting policy around it. The engine already handles FT8,
FT4, FT2 timing, decoding, message generation, and radio/audio integration. The
OM0RX backend should own Wavelog-aware target choice, operator policy, and
cluster-driven frequency/mode changes.

## Source References

Local WSJT-Z source is available at:

```text
data/research/wsjt-z
```

Primary automation entry points:

- `widgets/mainwindow.cpp:5665` - `auto_sequence(...)`: response handling,
  tail-end handling, and automatic halt when the selected DX replies to someone
  else.
- `widgets/mainwindow.cpp:10787` - `replyToCQ(...)`: UDP Reply flow that
  locates the original decode before calling into the native message processor.
- `widgets/mainwindow.cpp:13021` - `on_cbAutoCall_toggled(...)` and
  `on_cbAutoCQ_toggled(...)`: mode toggles and the UI policy they enforce.
- `widgets/mainwindow.cpp:13093` - `callsignFiltered(...)`: per-decode hunting
  filter and priority-call promotion.
- `widgets/mainwindow.cpp:14315` - `ZProcess(...)`: once-per-cycle automation
  loop, priority target activation, auto-call/auto-CQ switching, and band
  hopping.
- `widgets/mainwindow.cpp:14627` - `setFreeFreq(...)`: busy-slot based TX audio
  frequency choice.
- `widgets/mainwindow.h:725` - priority target, automatic TX frequency, and
  recent-call state members.
- `Configuration.cpp:812`, `Configuration.cpp:2088`, `Configuration.cpp:2284`,
  `Configuration.cpp:2862`: persisted WSJT-Z automation settings.

## Porting Strategy

1. **Keep WSJT-X as the real-time engine**

   Do not reimplement the modem, soundcard path, CAT/PTT, or native
   auto-sequencing. OM0RX should feed targets into the patched
   `OM0RXStartTargetQSO` UDP command and let WSJT-X generate/transmit the native
   messages.

2. **Move target ranking into the backend**

   Translate the intent of `callsignFiltered(...)` into a backend target ranker:

   - ignore invalid calls and `/R` false decodes
   - support CQ-only, CQ-target, and include-73 modes
   - apply minimum dB, continent, prefix, state, and explicit ignore filters
   - use local PostgreSQL Wavelog cache for call/country/grid/zone worked status
   - score by operator priority: new DXCC, new band, new mode, grid, state,
     distance, signal, then recency

   This avoids slow Wavelog API calls in the decode-to-target path and prevents
   UI row churn while enrichment is still being resolved.

3. **Port priority-call activation**

   The backend should maintain a `priorityCall` equivalent from recent decodes.
   When Auto Call is enabled and the current slot permits a safe start, send one
   `start_target_qso` command with:

   - target call/grid
   - current mode
   - current dial frequency
   - decoded RX DF
   - chosen TX DF
   - calculated `txFirst`
   - generated messages enabled
   - Enable Tx armed only when inside the safe WSJT transmit window

4. **Port busy-slot TX DF selection**

   Implement a backend version of `setFreeFreq(...)` using recent decode audio
   offsets. The first pass can choose a clear offset near the operator default.
   Later passes can add narrow/wide ranges and per-mode defaults from settings.

5. **Represent auto-call/auto-CQ as backend state**

   Treat WSJT-Z's `ZProcess(...)` as the model for a backend state machine:

   - auto-call count before switching or band hopping
   - auto-CQ count before returning to hunting
   - watchdog expiry
   - current/last QSO partner suppression
   - optional band hop at mode boundaries

6. **Keep native auto-sequencing in the engine**

   Backend automation should start, halt, or retarget QSOs. Once a QSO is active,
   the patched WSJT-X engine should handle the standard FT message progression.
   If we later need lower-latency behaviour than UDP supervision can provide,
   port the exact WSJT-Z `auto_sequence(...)` safeguards into the C++ patched
   engine.

## Implementation Order

1. Add a local `digital_targets` table or cache view fed from WSJT decodes and
   cluster spots.
2. Add a PostgreSQL-backed Wavelog shadow cache for fast worked/new lookups.
3. Add a target-ranker service with smoke tests built from recorded decodes.
4. Add busy-slot TX DF selection and tests for occupied/clear offsets.
5. Wire Auto Call to the ranker and patched `start_target_qso` command.
6. Add browser and protocol smoke tests proving: decode appears, target is
   ranked, command is emitted once, Enable Tx is not armed outside the safe
   window, and QSO state remains stable while enrichment updates arrive.

## Non-Goals

- Do not reuse port `5002`; that remains available for standalone WSJT-Z.
- Do not drive SmartSDR directly for FT8/FT4/FT2 transmit timing.
- Do not keep querying Wavelog over HTTP in the hot decode path.
- Do not mutate decode rows in-place in a way that moves selectable rows while
  the operator is trying to click.
