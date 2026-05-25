# Callsign Auto-Lookup Feature Implementation

## Problem
When typing a callsign in the logging form, the application was not automatically:
- Checking QRZ database
- Pulling previous QSOs from Wavelog
- Pulling from local log
- Filling in all details automatically

This auto-lookup functionality only worked when clicking on a DX spot, not when manually typing a callsign.

## Solution
Enhanced the callsign field event handlers to trigger the same lookups that occur when clicking on a DX spot.

### Changes Made

#### 1. **frontend/js/app-main.js** - Enhanced `onCallsignChange()` method
**Before:** Only called `loadDXCCStatus()` with 500ms debounce
**After:** Now calls BOTH:
- `loadQRZProfile()` - Loads QRZ data with Wavelog profile lookup
- `loadDXCCStatus()` - Loads DXCC status and triggers `loadPreviousQSOs()`

```javascript
// Old: Only DXCC lookup
this.dxccLookupTimer = setTimeout(() => {
    this.loadDXCCStatus();
}, 500);

// New: Full lookup suite
this.dxccLookupTimer = setTimeout(() => {
    this.loadQRZProfile();      // Load QRZ profile with Wavelog lookup
    this.loadDXCCStatus();      // Load DXCC status (which calls loadPreviousQSOs)
}, 500);
```

#### 2. **frontend/js/app-main.js** - Enhanced `autoPopulateForm()` method
**Before:** Only updated frequency, mode, band, RST, and time (no lookups)
**After:** 
- Checks for matching DX spot
- Updates frequency/mode from spot or radio status
- Derives band from frequency
- Auto-populates RST
- **NOW: Calls `loadQRZProfile()` and `loadDXCCStatus()`**

#### 3. **frontend/templates/logging-panel.html** - Enhanced callsign input field
**Before:** `@blur="autoPopulateForm" @input="onCallsignChange"`
**After:** `@blur="autoPopulateForm" @input="onCallsignChange" @keydown.enter="autoPopulateForm"`

Added explicit Enter key handler to ensure immediate lookup when user presses Enter.

### Trigger Points for Auto-Lookup

| Trigger | Handler | Behavior |
|---------|---------|----------|
| **Typing** | `@input="onCallsignChange"` | 500ms debounced lookup (QRZ + DXCC + PrevQSOs) |
| **Tab** | `@blur="autoPopulateForm"` | Immediate lookup (QRZ + DXCC + PrevQSOs) + frequency/mode/RST |
| **Enter** | `@keydown.enter="autoPopulateForm"` | Immediate lookup (QRZ + DXCC + PrevQSOs) + frequency/mode/RST |

## What Gets Filled In

When a callsign is entered (typing, Tab, or Enter), the following data is automatically populated:

### From QRZ Profile (`loadQRZProfile`):
- Name
- Location/QTH
- Country
- State
- Continent
- CQ Zone
- ITU Zone
- Gridsquare
- Email

### From Wavelog (`loadWavelogProfile`):
- Gridsquare (if not in QRZ)
- Continent (if not in QRZ)
- CQ Zone (if not in QRZ)
- ITU Zone (if not in QRZ)
- State (if not in QRZ)
- US County
- Operator Name
- QSL Manager

### From DXCC Status (`loadDXCCStatus`):
- Call Status (New Call/New Band/etc)
- DXCC Status (ATNO/Worked/Confirmed/etc)
- Band-specific worked information

### Previous QSOs (`loadPreviousQSOs`):
- List of last 5 QSOs with this callsign (displayed in UI)

## Behavior Notes

1. **Minimum Length**: Lookups only trigger if callsign is 3+ characters
2. **Debounce on Typing**: 500ms debounce prevents excessive API calls while typing
3. **Immediate on Blur/Enter**: Tab and Enter keys trigger immediate lookups for responsiveness
4. **DX Spot Preference**: If callsign matches a DX spot, spot's frequency and mode are used
5. **Rotor Auto**: If enabled, rotor auto-positioning is triggered when QRZ grid is available

## Testing Instructions

1. **Type in Callsign Field**:
   - Start typing a callsign (e.g., "N0CALL")
   - After 500ms, you should see QRZ data appear in the form
   - Previous QSOs should appear in the QRZ Profile section

2. **Press Tab**:
   - Enter a complete callsign
   - Press Tab
   - Lookup should happen immediately (visible in form fields)

3. **Press Enter**:
   - Enter a complete callsign
   - Press Enter
   - Lookup should happen immediately and form should populate

4. **Compare with Spot Click**:
   - Click on a DX spot
   - Type the same callsign manually
   - Both should populate the same fields automatically

## Files Modified
- `/frontend/js/app-main.js` - Enhanced event handlers
- `/frontend/templates/logging-panel.html` - Added @keydown.enter event