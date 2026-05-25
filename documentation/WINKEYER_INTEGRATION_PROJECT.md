# Winkeyer Integration Project

**Project Status**: Planning Phase  
**Created**: 2024-12-19  
**Version**: 1.0  
**Objective**: Integrate Winkeyer CW keyer control into the main Wave-Flex-Spots UI

---

## Project Overview

Add a dedicated Winkeyer control widget to the main application UI (Row 3, left side, between rotor controls and frequency display). The widget will provide:
- Serial port connection management
- WPM (Words Per Minute) speed adjustment with slider
- 4 programmable memory buttons (M1-M4) for CW macros
- Visual connection status indicator
- Configuration UI in the Config modal

---

## Requirements Summary

### Functional Requirements
1. **Connection Control**
   - Connect button that opens serial port to Winkeyer device
   - Green "Connected" status indicator when connected
   - Automatic reconnection handling
   - Graceful disconnection

2. **Speed Control**
   - Display current WPM value (5-50 range)
   - Click on speed number to show WPM slider
   - Slider to adjust speed from 5-50 WPM
   - Real-time speed updates sent to Winkeyer
   - Physical Winkeyer potentiometer continues to work (receives feedback)

3. **Memory Buttons (M1-M4)**
   - 4 memory buttons for sending CW macros
   - User-definable macro text
   - Configuration saved in config.py
   - Send macro to Winkeyer when clicked

4. **Configuration Management**
   - Settings modal (alongside WSJT-X settings)
   - Port selection (COM port input)
   - Memory definitions (M1-M4 text fields)
   - Enable/disable Winkeyer integration
   - Baud rate setting (default: 1200)

5. **Physical Button Support**
   - Keep physical Winkeyer buttons functional
   - Serial API properly maps to device capabilities
   - No interference with hardware controls

### Non-Functional Requirements
- Use existing Web Serial API (from /winkeyer reference implementation)
- Modular design - separate JS file for Winkeyer logic
- Persistent configuration in config.py
- Error handling and logging
- Clean UI styling matching existing design

---

## Technical Architecture

### Files to Modify

#### 1. **config.py** - Add Winkeyer configuration
```
WINKEYER_ENABLED = True
WINKEYER_PORT = "COM3"
WINKEYER_BAUDRATE = 1200
WINKEYER_DEFAULT_WPM = 20
WINKEYER_MEMORIES = {
    "M1": "CQ DE OM0RX",
    "M2": "UR RST 599",
    "M3": "QSL TU DE OM0RX",
    "M4": "MNI TU",
}
```

#### 2. **frontend/index.html** - Add Winkeyer widget to Row 3
- Position: Left side, between rotor controls and frequency
- Layout: Vertical stacked (title, connect button, speed display, memory buttons)
- Integrate into existing Row 3 structure

#### 3. **frontend/js/winkeyer-ui.js** - New file
- Winkeyer UI controller for the main app
- Handles:
  - Connection/disconnection
  - WPM slider popup and updates
  - Memory button clicks
  - Status display
  - Config modal handling

#### 4. **frontend/js/winkeyer-client.js** - New file (extract from /winkeyer)
- Simplified WinKeyerClient class
- Serial port communication
- Command protocol (already in /winkeyer/js/winkeyer.js)
- Reusable for main app

#### 5. **frontend/main-styles.css** - Add Winkeyer styles
- Widget container styling
- Connection status indicator colors
- Button styling for M1-M4
- Speed display and slider popup
- Responsive sizing

#### 6. **frontend/index.html** - Update Config modal
- Add Winkeyer settings tab/section
- Port selection dropdown
- Baud rate input
- Memory definitions (M1-M4 text areas)
- Enable/disable toggle

#### 7. **backend/main.py** - Add Winkeyer endpoints (optional for future)
- GET /config/winkeyer - Read current config
- POST /config/winkeyer - Save config
- WebSocket messages for config updates

---

## Implementation Phases

### Phase 1: Core Setup (Files Created)
- [ ] Copy WinKeyerClient from /winkeyer/js/winkeyer.js → frontend/js/winkeyer-client.js
- [ ] Create frontend/js/winkeyer-ui.js with UI state management
- [ ] Update config.py with Winkeyer settings
- [ ] Add Winkeyer HTML widget to index.html Row 3
- [ ] Add CSS styling to main-styles.css

### Phase 2: Frontend Integration
- [ ] Implement connect/disconnect button logic
- [ ] Implement WPM slider popup and updates
- [ ] Implement M1-M4 memory button send
- [ ] Add visual status indicator
- [ ] Test serial communication

### Phase 3: Configuration UI
- [ ] Add Winkeyer settings section to Config modal
- [ ] Port selection and validation
- [ ] Memory text input fields
- [ ] Save/load config from config.py
- [ ] Enable/disable toggle

### Phase 4: Testing & Polish
- [ ] Test connection to actual Winkeyer device
- [ ] Test macro sending
- [ ] Test physical buttons still work
- [ ] Test config persistence
- [ ] Error handling and recovery

### Phase 5: Backend Integration (Optional)
- [ ] Add config endpoints to main.py
- [ ] WebSocket broadcast config changes
- [ ] Persistence to config.py file

---

## UI Layout

### Row 3 Current Layout
```
[Rotor Controls] ... [Frequency Display] ... [RIT/XIT on right]
```

### Row 3 New Layout
```
[Rotor] [WINKEYER] ... [Frequency Display] ... [RIT/XIT]
        ┌─────────────┐
        │  WinKeyer   │
        │ [Connect🔌] │
        │  Speed: 20  │
        │ [M1][M2][M3][M4]
        └─────────────┘
```

### Winkeyer Widget Structure
```
┌─────────────────────────┐
│     🔑 WINKEYER         │
├─────────────────────────┤
│ [●Connected] [Disconnect]
│ Speed: 20 WPM           │ ← Clickable to show slider
│ ┌──────────────────────┐│
│ │ ◀────●────▶ 5 -- 50 ││ ← Slider popup (initially hidden)
│ └──────────────────────┘│
├─────────────────────────┤
│ [M1]    [M2]           │
│ CQ DE   RST 599        │
├─────────────────────────┤
│ [M3]    [M4]           │
│ QSL TU  MNI TU         │
└─────────────────────────┘
```

---

## Configuration Modal - Winkeyer Section

```
┌─────────────────────────────┐
│ ⚙️ Configuration             │
├─────────────────────────────┤
│ Tabs: [General] [WSJT-X] [WinKeyer]
│
│ WinKeyer Settings:
│ ├─ Enable: [✓] Enable WinKeyer
│ ├─ Port: [COM3      ▼]
│ ├─ Baudrate: [1200]
│ ├─ Default WPM: [20]
│ └─ Memories:
│    ├─ M1: [CQ DE OM0RX        ]
│    ├─ M2: [UR RST 599         ]
│    ├─ M3: [QSL TU DE OM0RX    ]
│    └─ M4: [MNI TU             ]
│
│ [Save] [Cancel]
└─────────────────────────────┘
```

---

## Serial Protocol Reference

From existing `/winkeyer/js/winkeyer.js`:

### Key Commands
- `0x00, 0x02` → Admin Open (initialize)
- `0x00, 0x01` → Reset
- `0x02, WPM` → Set WPM (WPM = 5-99)
- `0x0E, MODE` → Set Mode (Iambic A/B, Ultimatic, Bug)
- ASCII characters sent for CW text

### Responses
- Status bytes: `0xC0-0xFF` → Device status
- Pot data: `0x80-0xBF` → Physical potentiometer
- Extended: `0xE0` followed by 4 bytes → Extended status

---

## Dependencies & Browser APIs

- **Web Serial API**: For serial port communication
  - Available in Chrome/Edge 90+, Brave, Opera
  - Requires secure context (HTTPS or localhost)
  - User must grant permission
  
- **WebSockets**: Already in use for radio control (not needed for Winkeyer initially)

---

## Error Handling Strategy

### Connection Errors
- Port not available → Show error dialog
- Permission denied → Prompt user to grant permission
- Device not responding → Show timeout error
- Auto-reconnect disabled (user must manually connect)

### Serial Communication
- Send failures → Log and show status indicator
- Receive timeout → Mark as disconnected
- Invalid WPM values → Clamp to 5-50 range

---

## Testing Plan

### Unit Tests
- [ ] WPM validation (5-50 range)
- [ ] Command byte generation
- [ ] Config persistence

### Integration Tests
- [ ] Connection workflow
- [ ] Macro sending
- [ ] Physical button feedback (potentiometer)
- [ ] Config modal save/load

### Device Tests
- [ ] Real Winkeyer connection
- [ ] Speed control responsiveness
- [ ] Macro transmission accuracy
- [ ] Physical buttons still work

---

## Known Limitations & Future Enhancements

### Phase 1 (Current)
- Only basic macro support (simple text)
- No CW character timing visualization
- No sidetone audio (hardware feature)
- Manual connection required

### Future Enhancements (Phase 2+)
- Advanced CW mode selection
- Sidetone control
- CW speed profiling
- Macro editor UI improvements
- Auto-connect on startup
- Connection persistence
- CW prosign support

---

## File Change Summary

| File | Type | Action |
|------|------|--------|
| config.py | Config | Modify - Add Winkeyer settings |
| frontend/index.html | HTML | Modify - Add widget + config section |
| frontend/main-styles.css | CSS | Modify - Add Winkeyer styles |
| frontend/js/winkeyer-client.js | JS | Create - WinKeyerClient class |
| frontend/js/winkeyer-ui.js | JS | Create - UI controller |
| backend/main.py | Python | Modify (optional) - Add endpoints |

---

## Timeline Estimate

- **Phase 1 (Core Setup)**: 1-2 hours
- **Phase 2 (Frontend)**: 2-3 hours  
- **Phase 3 (Config UI)**: 1-2 hours
- **Phase 4 (Testing)**: 1-2 hours
- **Total**: 5-9 hours

---

## Success Criteria

- ✅ Winkeyer widget visible in Row 3 (left side)
- ✅ Connect button successfully opens serial port
- ✅ Status shows "Connected" in green when active
- ✅ WPM slider works and updates device speed
- ✅ M1-M4 buttons send correct macros to device
- ✅ Physical Winkeyer controls still responsive
- ✅ Configuration persists between sessions
- ✅ No errors or crashes during operation
- ✅ UI integrates seamlessly with existing design

---

## References

- Reference implementation: `/winkeyer/index.html` and `/winkeyer/js/winkeyer.js`
- Existing serial implementation: Not used (new feature)
- Web Serial API docs: https://developer.chrome.com/articles/serial/

---

## Notes

- User confirmed serial port connection (COM ports like COM3)
- WPM range: 5-50 (standard for Winkeyer)
- Memories persist in config.py
- Physical buttons should remain functional
- Layout: Standalone box on Row 3 (not inline)
