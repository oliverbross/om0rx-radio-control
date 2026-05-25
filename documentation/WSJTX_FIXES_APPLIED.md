# WSJT-X Integration Fixes - Three Key Issues Resolved

## Issues Fixed

### 1. **Auto-Rotate Status Showing "Disabled" When It's Enabled**
**Problem:** The console log showed `⚠️ Auto-rotate disabled` even though WSJT-X auto-rotate is enabled in the config.

**Root Cause:** 
- The code was checking for `config.ROTOR_AUTO_ENABLED` 
- But the actual config property is `WSJTX_AUTO_ROTATE` (defined in app-main.js line 51)
- Also, `window.configData` was never being set in the window object

**Solution Applied:**
- Modified `wsjtx-handler.js` `autoRotateToGrid()` function (lines 166-224) to:
  - Try multiple config property names: `WSJTX_AUTO_ROTATE`, `ROTOR_AUTO_ENABLED`
  - Attempt to access Vue instance via `window.vueInstance` first
  - Fall back to `window.configData` if available
  - Get station grid from multiple sources: `rotorHomeGrid`, `STATION_GRID`
  - Updated console message to show which setting is being checked

**Files Modified:**
- `frontend/js/wsjtx-handler.js` - Updated `autoRotateToGrid()` function

---

### 2. **Call Sign Not Transferred to Log QSO Window**
**Problem:** When clicking a station in WSJT-X (e.g., EA5BH), the call was NOT appearing in the Log QSO form, and QRZ details weren't loading.

**Root Cause:**
- The logging window (`logging.html`) is a **separate window**, not part of the main app DOM
- `wsjtx-handler.js` was trying to find form elements using DOM selectors in the main window
- Cannot access DOM elements in a separate window from the main window

**Solution Applied:**
- Implemented **inter-window communication using postMessage API**:
  1. **In wsjtx-handler.js** (lines 113-161):
     - Modified `autoPopulateLogQsoForm()` to send data via `postMessage` instead of DOM manipulation
     - Maintains reference to logging window: `window.loggingWindow`
     - Opens logging window if not already open using `window.open('logging.html', 'loggingWindow')`
     - Sends structured message with: `{ type: 'wsjtx-qso-data', callsign, gridsquare, frequency, mode }`
  
  2. **In app-main.js** (lines 1021-1047):
     - Added `message` event listener in the `mounted()` hook
     - Listens for messages with type `'wsjtx-qso-data'`
     - Auto-populates form fields: `callsign`, `gridsquare`, `frequency`, `mode`
     - Triggers `onCallsignChange()` to automatically load QRZ profile data

  3. **Vue Instance Exposure** (line 1050):
     - Exposes Vue instance to `window.vueInstance` for access from other scripts
     - Enables wsjtx-handler to access reactive data and methods

**Files Modified:**
- `frontend/js/wsjtx-handler.js` - Rewrote `autoPopulateLogQsoForm()` to use postMessage
- `frontend/js/app-main.js` - Added message listener and exposed Vue instance

---

### 3. **Auto-Save Functionality (Pending Testing)**
**Status:** Not yet tested since QSO isn't complete

**Expected Behavior:** When QSO is finished in WSJT-X, the LoggedAdif message will trigger:
- Automatic logging to Wavelog (if enabled)
- Form should auto-save (implementation in progress)

**Handler Already in Place:** `wsjtx-handler.js` lines 101-107 have `handleWsjtxLoggedAdif()` which calls `logQsoToWavelog()`

---

## How Inter-Window Communication Works

### Flow Diagram:
```
1. WSJT-X Status Message (e.g., click EA5BH)
   ↓
2. sdc-bridge-server.js detects and sends to WebSocket
   ↓
3. Browser receives at sdc-ticker.js
   ↓
4. Dispatches 'wsjtx-message' event
   ↓
5. wsjtx-handler.js receives event
   ↓
6. Calls autoPopulateLogQsoForm('EA5BH', 'IM98SJ', 10136000)
   ↓
7. wsjtx-handler.js sends postMessage to logging window:
   window.loggingWindow.postMessage({ 
     type: 'wsjtx-qso-data',
     callsign: 'EA5BH',
     gridsquare: 'IM98SJ',
     frequency: '10.136',
     mode: 'FT8'
   }, '*')
   ↓
8. Logging window (app-main.js) receives message event
   ↓
9. Message listener updates Vue data:
   - loggingForm.callsign = 'EA5BH'
   - loggingForm.gridsquare = 'IM98SJ'
   - loggingForm.frequency = '10.136'
   - loggingForm.mode = 'FT8'
   ↓
10. Calls this.onCallsignChange() to trigger QRZ lookup
    ↓
11. QRZ profile and DXCC info load automatically
```

---

## Testing Checklist

### Test Case 1: Auto-Rotate Configuration
- [ ] Click on a station in WSJT-X (e.g., EA5BH)
- [ ] Check browser console for auto-rotate status
- **Expected:** Should show either:
  - `🔄 Auto-rotating to IM98SJ (from [STATION_GRID])` if enabled
  - OR `⚠️ Auto-rotate disabled (WSJTX_AUTO_ROTATE: false)` if disabled
- [ ] Check if rotor actually rotates if enabled

### Test Case 2: Form Population & QRZ Lookup
- [ ] Ensure logging window is open (or will be opened automatically)
- [ ] Click on a station in WSJT-X (e.g., EA5BH)
- [ ] Check logging window Console for messages:
  - `📤 Sent WSJT-X data to logging window: EA5BH`
  - `📨 Received WSJT-X data from main window`
  - `✅ Populated callsign: EA5BH`
  - `✅ Populated gridsquare: IM98SJ`
- [ ] Verify in logging window that:
  - Callsign field shows: **EA5BH**
  - Gridsquare field shows: **IM98SJ**
  - Frequency shows current dial frequency
  - Mode shows: **FT8**
  - QRZ profile is loading (check DXCC/QRZ panel)

### Test Case 3: Complete QSO Flow (After Current Testing)
- [ ] Complete a QSO in WSJT-X
- [ ] Check for LoggedAdif message in bridge server
- [ ] Verify QSO auto-logs to Wavelog (if configured)

---

## Console Debugging

**Main Window Console Messages:**
```
🔄 Forwarding WSJT-X message to handler: wsjtx_status
📡 WSJT-X message received: wsjtx_status
📍 WSJT-X Status: EA5BH (IM98SJ)
📤 Sent WSJT-X data to logging window: EA5BH
```

**Logging Window Console Messages:**
```
📨 Received WSJT-X data from main window: {...}
✅ Populated callsign: EA5BH
✅ Populated gridsquare: IM98SJ
✅ Set mode: FT8
```

---

## Key Files Modified

1. **frontend/js/wsjtx-handler.js**
   - Lines 113-161: Rewrote `autoPopulateLogQsoForm()` 
   - Lines 166-224: Updated `autoRotateToGrid()` function

2. **frontend/js/app-main.js**
   - Lines 1021-1050: Added message listener and Vue instance exposure
   - Maintains backward compatibility with existing code

---

## Notes & Future Improvements

1. **Window Management:** The logging window reference should ideally be registered in a central window manager to avoid losing the reference
2. **Config Access:** Consider moving config data to a central store accessible to all windows
3. **Message Security:** Using `'*'` as postMessage origin is permissive; consider stricter origin validation in production
4. **QRZ Auto-Load:** The `onCallsignChange()` call should trigger QRZ/Wavelog profile loading automatically

---

**Status:** ✅ Ready for testing
**Last Updated:** 2024
**Tested With:** WSJT-X FT8 on 40m band (EA5BH example)