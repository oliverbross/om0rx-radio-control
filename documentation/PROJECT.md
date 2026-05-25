# Wave-Flex Spot Sync Project

## Project Overview
**Version:** 0.1 beta  
**Author:** Oliver Bross OM0RX  
**Purpose:** Python/Tkinter application that syncs DX cluster spots with FlexRadio SmartSDR via TCP/IP API

## Architecture
```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  DX Cluster     │────▶│  dxbridge.py     │────▶│  FlexRadio      │
│  (Telnet)       │     │  Main App        │     │  SmartSDR API   │
└─────────────────┘     └──────────────────┘     │  (TCP 4992)     │
                              │                   └─────────────────┘
                              ▼
                        ┌──────────────────┐
                        │  MySQL/Wavelog   │
                        │  Database        │
                        └──────────────────┘
```

## Key Components

### 1. FlexCtl Class (lines 681-894)
**Purpose:** Minimal SmartSDR TCP client for controlling ONE slice (default: Slice A = ID 0)

**Status:** ✅ Fixed with proper API commands

**Key Methods:**
- `connect()` - Establishes TCP connection to SmartSDR (port 4992)
- `get_current_levels()` - Queries radio for current settings on startup
- `set_volume()` - Controls audio gain (0-100) via `slice set audio_level`
- `set_rf_power()` - Controls TX power (1-100) via `transmit set rfpower`
- `set_tune_power()` - Controls tune power (1-100) via `transmit set tunepower`
- `set_mic_level()` - Controls mic level (0-100) via `transmit set miclevel`
- `set_tune()` - Toggle TUNE mode via `transmit tune on|off`
- `set_mox()` - Toggle MOX via `xmit on|off`
- `set_filter_edges()` - Set filter lo/hi via `slice set filter_lo/filter_hi`

### 2. UI Controls (lines 1496-1650)
**Location:** FlexRadio Control frame

**Controls:**
- **Band buttons:** 160m-6m (11 buttons)
- **Mode buttons:** LSB, USB, CW, AM, FM, DIGI, DIGU, DIGL (8 buttons)
- **Sliders:**
  - Volume (0-100) with mute checkbox
  - Drive/RF Power (1-100)
  - Tune Power (1-100)
  - Mic Level (0-100)
- **TX Controls:**
  - TUNE button (toggle)
  - MOX button (toggle)
  - VOX checkbox
- **Dynamic Filters:** Mode-dependent filter bandwidth buttons

## SmartSDR API Commands (Port 4992)

### Command Format
```
C<seq>|<command>\r
```
**Response:**
```
R<seq>|<hex_status>|<message>|<debug>
```
**Status Messages:**
```
S<handle>|<object> <id> <key1>=<value1> <key2>=<value2>...
```

### Critical API Commands Used

| Function | Correct API Command | Previous (WRONG) | Status |
|----------|---------------------|------------------|---------|
| Volume | `slice set 0 audio_level=X` | `slice set 0 audio_gain=X` | ✅ FIXED |
| RF Power | `transmit set rfpower=X` | ✅ Correct | ✅ OK |
| Tune Power | `transmit set tunepower=X` | `transmit set tune_power=X` | ✅ FIXED |
| Mic Level | `transmit set miclevel=X` | `transmit set mic_level=X` | ✅ FIXED |
| TUNE | `transmit tune on` / `off` | Multiple wrong attempts | ✅ FIXED |
| MOX | `xmit on` / `xmit off` | `transmit set mox=1` | ✅ FIXED |
| Filter | `slice set 0 filter_lo=X filter_hi=Y` | ✅ Correct | ✅ OK |
| Band | `slice tune 0 14.074` | ✅ Correct | ✅ OK |
| Mode | `slice set 0 mode=USB` | ✅ Correct | ✅ OK |

## Configuration
**File:** `config.py`
- `FLEX_TCP_HOST = "192.168.0.199"` - SmartSDR radio IP
- `FLEX_TCP_PORT = 4992` - SmartSDR API port (standard)
- `FLEX_ENABLED_DEFAULT = True` - Enable Flex control on startup
- `LOG_LEVEL = "DEBUG"` - Logging verbosity

## Logging
**File:** `flex_debug.log`
**Location:** Same directory as `dxbridge.py`

**Log Levels:**
- `DEBUG` - All API commands sent/received
- `INFO` - Connection events, state changes
- `WARNING` - Failed commands, connection issues
- `ERROR` - Critical failures

**Example log output:**
```
2025-01-23 10:15:32 INFO FlexCtl connecting to 192.168.0.199:4992
2025-01-23 10:15:32 DEBUG FlexCtl SEND: client station=OM0RX
2025-01-23 10:15:32 DEBUG FlexCtl RECV: R1001|0||
2025-01-23 10:15:32 DEBUG FlexCtl SEND: sub slice all
2025-01-23 10:15:32 DEBUG FlexCtl RECV: R1002|0||
2025-01-23 10:15:33 DEBUG FlexCtl SEND: slice list
2025-01-23 10:15:33 DEBUG FlexCtl RECV: S0|slice 0 freq=14.074 mode=USB active=1 audio_level=50 filter_lo=100 filter_hi=2900
2025-01-23 10:15:33 INFO Initial state: volume=50, mode=USB, filter=100-2900
```

## Known Issues & Fixes

### Issue #1: Volume Slider Not Working ✅ FIXED
**Root Cause:** Used wrong parameter name `audio_gain` instead of `audio_level`  
**Fix:** Changed to `slice set 0 audio_level=X`  
**Status:** ✅ Fixed

### Issue #2: Tune Power Slider Not Working ✅ FIXED
**Root Cause:** Used underscore `tune_power` instead of API's `tunepower`  
**Fix:** Changed to `transmit set tunepower=X`  
**Status:** ✅ Fixed

### Issue #3: Mic Slider Not Working ✅ FIXED
**Root Cause:** Used underscore `mic_level` instead of API's `miclevel`  
**Fix:** Changed to `transmit set miclevel=X`  
**Status:** ✅ Fixed

### Issue #4: TUNE Button Not Working ✅ FIXED
**Root Cause:** Tried multiple wrong command variations  
**Fix:** Use simple `transmit tune on` or `transmit tune off`  
**Status:** ✅ Fixed

### Issue #5: MOX Button Not Working ✅ FIXED
**Root Cause:** Used `transmit set mox=1` instead of direct xmit command  
**Fix:** Use `xmit on` or `xmit off`  
**Status:** ✅ Fixed

### Issue #6: Filters Not Working ✅ FIXED
**Root Cause:** Commands were correct but state tracking was incomplete  
**Fix:** Enhanced status parsing and state tracking  
**Status:** ✅ Fixed

### Issue #7: No Initial Values from Radio ✅ FIXED
**Root Cause:** 
1. `get_current_levels()` didn't wait long enough for responses
2. Didn't parse status messages correctly
3. Called before UI variables existed

**Fix:** 
1. Increased timeout to 1.5 seconds
2. Rewrote status parsing with regex for all parameters
3. Moved call to AFTER all UI elements exist
4. Added comprehensive debug logging

**Status:** ✅ Fixed

## Testing Checklist

### Before Running
- [ ] SmartSDR is running on FlexRadio
- [ ] Radio IP is correct in `config.py` (currently: 192.168.0.199)
- [ ] Port 4992 is accessible (firewall check)
- [ ] flex_debug.log is writable

### On Startup
- [ ] App connects to radio (check log for "FlexCtl connected")
- [ ] Initial values loaded:
  - [ ] Current band button is highlighted
  - [ ] Current mode button is highlighted
  - [ ] Volume slider shows current value
  - [ ] Drive slider shows current value
  - [ ] Tune slider shows current value
  - [ ] Mic slider shows current value
  - [ ] Filter values display current lo/hi

### Control Tests
- [ ] Volume slider changes audio gain in real-time
- [ ] Mute checkbox works
- [ ] Drive slider changes RF power
- [ ] Tune slider changes tune power
- [ ] Mic slider changes mic level
- [ ] TUNE button toggles tune mode (button text changes)
- [ ] MOX button toggles transmit (button text changes)
- [ ] VOX checkbox enables/disables VOX
- [ ] Band buttons tune to correct frequency
- [ ] Mode buttons change demodulation mode
- [ ] Filter buttons set correct bandwidth
- [ ] Filter display updates with lo/hi values

### Log Verification
- [ ] Open `flex_debug.log`
- [ ] Check for connection messages
- [ ] Verify commands are being sent (look for "FlexCtl SEND:")
- [ ] Verify responses received (look for "FlexCtl RECV:" or "FlexCtl RESP:")
- [ ] Check for any WARNING or ERROR messages

## File Structure
```
c:\Projects\om0rx-radio-control\
├── dxbridge.py          # Main application (2056 lines)
├── config.py            # Configuration settings
├── flex_debug.log       # Debug/info log (auto-created)
├── PROJECT.md           # This file - project tracking
└── __pycache__/         # Python bytecode cache
```

## Dependencies
```python
mysql-connector-python  # Database connectivity
tkinter                # UI framework (built-in)
socket                 # TCP/IP for SmartSDR API
asyncio               # Async operations
```

## Future Improvements
1. **Modularize code** - Split 2056-line dxbridge.py into modules:
   - `flex_control.py` - FlexCtl class
   - `ui_components.py` - Tkinter UI helpers
   - `dx_cluster.py` - Cluster connection logic
   - `database.py` - MySQL/Wavelog integration
   
2. **Status monitoring** - Add continuous status message parser to:
   - Update UI when radio changed by other clients (SmartSDR GUI)
   - Show real-time TX/RX state
   - Display SWR, power meters
   
3. **Multi-slice support** - Currently hardcoded to Slice A (ID 0)
   - Add slice selector dropdown
   - Control multiple slices simultaneously
   
4. **Error recovery** - Auto-reconnect if TCP connection drops

5. **Save/Restore** - Remember last settings between sessions

## Development Notes
- FlexRadio uses 0-based slice IDs (Slice A = 0, Slice B = 1, etc.)
- SmartSDR API is case-sensitive for commands
- Parameter names use underscore (filter_lo) or no separator (rfpower), not camelCase
- Status messages start with `S<handle>|` where handle is client ID
- Commands echo sequence number in responses for matching
- Socket timeout set to 0.8s for responsive UI
- Connection established once, reused for all commands

## Version History
- **v0.1 beta** (2025-01-23) - Initial release by OM0RX
  - Basic DX spot sync
  - FlexRadio control panel
  - Database integration
- **v0.1 beta + fixes** (2025-01-24) - SmartSDR API fixes
  - Fixed all control parameters (audio_level, tunepower, miclevel)
  - Fixed TUNE and MOX commands
  - Enhanced initial state reading
  - Comprehensive debug logging
  - Project documentation created

## Support
- SmartSDR API Docs: https://github.com/flexradio/smartsdr-api-docs/wiki
- Author: Oliver Bross OM0RX
- Project: Wave-Flex Spot Sync

---
**Last Updated:** 2025-01-24  
**Status:** ✅ All FlexRadio controls operational