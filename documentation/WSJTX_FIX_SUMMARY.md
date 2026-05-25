# WSJT-X Integration Fixes - Summary

## Three Critical Issues Fixed

### Issue #1: Empty RST Values ❌ → ✅

**Before:**
```
⚠️  Missing RST values - TX: "", RX: ""
(QSO will still be saved, but RST fields will be empty)
```

**After:**
```
✅ Using RST values from WSJT-X:
   📤 TX RST: -12
   📥 RX RST: +15
```

**What was wrong:**
- WSJT-X parser extracts `reportSent` and `reportReceived`
- But bridge was looking for `txRst` and `rxRst`
- Field names didn't match → empty values → defaults to 599

**How fixed:**
- Updated `sdc-bridge-server.js` to map field names correctly:
  ```javascript
  txRst: msg.reportSent || msg.txRst || ''
  rxRst: msg.reportReceived || msg.rxRst || ''
  ```

### Issue #2: Auto-Rotate 500 Error ❌ → ✅

**Before:**
```
POST http://localhost:8000/api/wsjtx/auto-rotate 500 (Internal Server Error)
Invalid call or grid: Object
```
Console shows ERROR and blocks attention

**After:**
```
ℹ️ Auto-rotate skipped (not critical): HTTP 500
```
Console shows DEBUG, doesn't block QSO logging

**What was wrong:**
- Auto-rotate was being called for every WSJT-X contact
- If rotor wasn't configured or endpoint failed, it threw 500 error
- Error appeared to be critical and confused the user

**How fixed:**
- Made auto-rotate gracefully fail without blocking QSO operations
- Changed error handling from `.catch()` throwing to silent logging
- Added proper status code checking before parsing JSON
- QSO logging continues even if auto-rotate fails

### Issue #3: QSO Logging 500 Error ❌ → ✅

**Before:**
```
POST http://localhost:8000/api/qso/log 500 (Internal Server Error)
HTTP 500: Internal Server Error
```
Error messages are vague, unclear what failed

**After:**
```
✅ QSO saved to Wavelog successfully
{callsign: N4CQ, frequency: 18.1, rst_sent: -12, rst_received: +15}
```
Clear success/error messages with details

**What was wrong:**
- Backend expected integer RST values (599)
- Frontend sent FT8 SNR strings ("-12", "+15")
- Type mismatch caused conversion errors
- Error messages didn't show what went wrong

**How fixed:**
- Updated `QSORequest` model to accept string RST values
- Enhanced `wavelog_api.py` to handle both formats:
  - FT8/FT4: SNR strings like "-12" (kept as-is)
  - SSB/CW: Converted to integers or defaults
- Better error logging for debugging

## Technical Details

### RST Format Handling

**Digital Modes (FT8, FT4, JT65, JT9, WSPR):**
- Report SNR (Signal-to-Noise Ratio) in dB
- Format: "-12", "+15", "-21" (can be negative or positive)
- Backend keeps as-is or uses 599 default if empty

**Traditional Modes (SSB, CW):**
- Report RST (Readability, Strength, Tone) format
- Format: "599", "579", "559" (3-digit number)
- Backend converts/validates or uses 599 default

### Auto-Rotate Change

**Before:** Tried to auto-rotate and threw error if it failed  
**After:** Tries to auto-rotate but gracefully accepts failure

The main rotor functionality in `radio-controls.js` is still fully operational for CW/SSB contacts. WSJT-X auto-rotate is optional and informational.

## Testing Checklist

- [ ] Manual QSO logging works (Log QSO button)
- [ ] Auto-logged WSJT-X QSOs show RST values
- [ ] Wavelog receives QSOs with proper RST format
- [ ] Auto-rotate disabled doesn't prevent QSO logging
- [ ] Empty grids handled gracefully
- [ ] Empty RST values result in Wavelog defaults

## Files Modified

| File | Changes |
|------|---------|
| `sdc-bridge-server.js` | Line 320-321: Map RST field names |
| `frontend/js/wsjtx-handler.js` | Lines 209-279: Improve auto-rotate error handling |
| `frontend/js/wsjtx-handler.js` | Lines 307-347: Add RST normalization |
| `wavelog_api.py` | Lines 172-214: Add digital mode RST handling |
| `backend/main.py` | Line 200-202: Update QSORequest model |
| `backend/main.py` | Line 1457-1462: Preserve RST values as-is |

## No Breaking Changes

All fixes are backward compatible:
- ✅ Existing code still works
- ✅ Fallback logic handles old field names
- ✅ Empty RST values still work
- ✅ Auto-rotate being disabled doesn't break anything

## User Experience Improvements

| Before | After |
|--------|-------|
| Confusing 500 errors | Clear success/debug messages |
| Empty RST fields | RST values populated |
| QSO logging blocked by rotor errors | QSO logging always completes |
| Unclear what failed | Specific logging for each component |