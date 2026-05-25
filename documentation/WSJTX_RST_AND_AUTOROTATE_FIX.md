# WSJT-X RST Values and Auto-Rotate Fixes

## Issues Fixed

### 1. Empty RST Values in WSJT-X Auto-Logging
**Problem:** When WSJT-X QSOs were automatically logged, RST (signal report) fields were empty.

**Root Cause:** 
- WSJT-X parser correctly extracts `reportSent` and `reportReceived` from ADIF
- But the SDC bridge was looking for `txRst` and `rxRst` fields (field name mismatch)
- Result: RST values were never passed to the frontend

**Fix Applied:** 
- Updated `sdc-bridge-server.js` line 320-321 to map:
  - `msg.reportSent` → `txRst`
  - `msg.reportReceived` → `rxRst`
- Added fallback to handle both field names for backward compatibility

### 2. Auto-Rotate 500 Error
**Problem:** Frontend logging shows `POST http://localhost:8000/api/wsjtx/auto-rotate 500 (Internal Server Error)`

**Root Cause:**
- Auto-rotate was called for every WSJT-X contact
- Rotor might not be initialized or grid validation failed
- Error crashed the entire operation

**Fix Applied:**
- Made auto-rotate gracefully fail without blocking QSO logging
- Changed error handling in `wsjtx-handler.js` to use `console.debug` for non-critical failures
- Added check for `ROTOR_AUTO_ENABLED` in addition to `WSJTX_AUTO_ROTATE`
- Error responses (HTTP 4xx/5xx) are now handled gracefully

**Note:** The main rotor functionality in `radio-controls.js` handles CW/SSB auto-rotation and works correctly. The WSJT-X handler now calls it informally without blocking the user experience.

### 3. RST Format Support for Digital Modes
**Problem:** Backend was trying to convert FT8 SNR values (like "-12", "+15") to standard RST integers, causing conversion errors.

**Root Cause:**
- FT8/FT4 modes report signal quality as SNR (Signal-to-Noise Ratio) strings
- SSB/CW modes use standard RST format (3-digit numbers like 599)
- Code didn't distinguish between these formats

**Fix Applied:**
- Updated `wavelog_api.py` to handle both formats:
  - **Digital modes (FT8, FT4, JT65, JT9, WSPR):** Accept SNR values as strings or convert to 599 default
  - **SSB/CW modes:** Parse as integers, defaulting to 599 if empty
- Updated `QSORequest` model to accept RST as optional strings
- Frontend now normalizes RST values (removes leading "R" or "S" prefix)
- Backend has robust error handling with proper logging

## RST Value Flow

### WSJT-X → Frontend → Backend → Wavelog

```
WSJT-X LoggedAdif Message
├─ reportSent: "-12"  (SNR in dB)
├─ reportReceived: "+15"
└─ dialFrequency: 18102000 Hz

↓ sdc-bridge-server.js (mapping)

SDC Bridge Message
├─ txRst: "-12"
├─ rxRst: "+15"
└─ dialFrequency: 18102000

↓ wsjtx-handler.js (normalization)

Frontend Request
├─ rst_sent: "-12"  (remove "R" prefix if present)
├─ rst_received: "+15"
└─ mode: "FT8"

↓ POST /api/qso/log

Backend → wavelog_api.py
├─ For FT8 mode: Keep SNR strings as-is or use 599 default
├─ For SSB mode: Convert to integers
└─ Build ADIF with proper format

↓ Wavelog API

ADIF String
<rst_sent:-12>-12 or <rst_sent:3>599
<rst_rcvd:3>599 or <rst_rcvd:2>+15
```

## Configuration

### Enable/Disable Auto-Rotate for WSJT-X
In `config.py`:
```python
WSJTX_AUTO_ROTATE = True        # Enable WSJT-X auto-rotate attempts
ROTOR_AUTO_ENABLED = True       # Rotor auto mode must be enabled
ROTOR_HOME_LAT = 40.0           # Your station latitude
ROTOR_HOME_LON = -74.0          # Your station longitude
```

### Enable/Disable WSJT-X Auto-Logging
In `config.py`:
```python
WSJTX_ENABLED = True            # Enable WSJT-X integration
WSJTX_AUTO_LOG = True           # Auto-log QSOs to Wavelog
WAVELOG_ENABLED = True          # Must enable Wavelog integration
```

## Testing & Verification

### 1. Check RST Values Are Captured
1. Open browser DevTools (F12)
2. Go to Console tab
3. Log a WSJT-X contact
4. Look for: `✅ Using RST values from WSJT-X:`
   - Should show TX RST and RX RST values
   - If empty, check sdc-bridge-server.js mapping

### 2. Verify Auto-Rotate Doesn't Block QSO Logging
1. With rotor disabled, log a WSJT-X contact
2. Should see: `ℹ️ Auto-rotate skipped (not critical)`
3. QSO should still log successfully to Wavelog

### 3. Check Wavelog Receipt
1. After QSO logs, check Wavelog logbook
2. RST fields should be populated with:
   - For FT8: SNR values (e.g., "-12", "+15") or defaults if empty
   - For SSB: Standard RST (e.g., "599", "579")

## Logging Details

### Frontend Console Messages
- `✅ Using RST values from WSJT-X:` - RST values successfully captured
- `ℹ️ RST values empty - TX: "", RX: ""` - Normal for some QSOs
- `ℹ️ Auto-rotate skipped (not critical)` - Rotor disabled or invalid grid
- `✅ QSO saved to Wavelog successfully` - QSO logged successfully

### Backend Logs
- `📝 QSO Log Request - Callsign: N4CQ, RST_sent: -12, RST_rcvd: +15`
- `✅ QSO processed: N4CQ ... (Wavelog: True, ADIF: True)`
- Error logs if Wavelog API fails (will still save to local ADIF)

## Files Modified

1. **sdc-bridge-server.js** - Fixed RST field mapping (reportSent → txRst)
2. **frontend/js/wsjtx-handler.js** - Improved auto-rotate error handling and RST normalization
3. **wavelog_api.py** - Enhanced RST format handling for digital vs. SSB/CW modes
4. **backend/main.py** - Updated QSORequest model to accept string RST values

## Backward Compatibility

All changes are backward compatible:
- Fallback logic handles both old and new field names
- Empty RST values are handled gracefully
- Both integer and string RST formats are supported
- Auto-rotate failures don't block QSO logging

## Related Issues

- Grid validation for auto-rotate now handles empty grids gracefully
- Empty RST values no longer cause conversion errors
- QSO logging succeeds even if auto-rotate fails
- Wavelog defaults (599) are used when RST is empty or invalid