# Rotor AUTO - Verification Checklist

## Pre-Verification Setup

### Backend Verification
```powershell
# 1. Check rotor_config.json exists and is valid
Get-Content "c:\Projects\om0rx-radio-control\rotor_config.json" | ConvertFrom-Json

# Expected output should show:
# - ROTOR_AUTO_ENABLED: true
# - ROTOR_HOME_GRID: (some grid like JN88TQ)
# - ROTOR_BANDS: {20m: true, 17m: true, ...}
```

### Frontend Verification
```javascript
// 1. Open browser console (F12 → Console tab)
// 2. Copy and paste this to check app state:

console.log('=== App State Check ===');
console.log('Rotor enabled:', this.$root.rotorEnabled);
console.log('Rotor AUTO enabled:', this.$root.rotorAutoEnabled);
console.log('Beaming callsign:', this.$root.currentBeamingCallsign);
console.log('SP bearing:', this.$root.shortPathBearing);
console.log('LP bearing:', this.$root.longPathBearing);
```

## Verification Tests

### Test 1: App Initialization
**What to check:**
1. Refresh browser (Ctrl+F5)
2. Check console for these messages:
   ```
   ✅ Rotor is enabled, loading rotor configuration...
   ✅ Rotor AUTO is ENABLED
   ```

**If you don't see these:**
- Rotor might not be enabled in main config
- Check `config.py` has `ROTOR_ENABLED = True`
- Restart backend: `.\start_webapp.ps1`

---

### Test 2: Click a Spot
**What to do:**
1. Open browser console (F12)
2. Make sure DX spots are loading in the spots panel
3. Click any spot

**What to check in console:**
```
🎯 tuneToSpot called with spot: {callsign: "PJ6Y", ...}
✅ Tuned to PJ6Y on 28.300 MHz
🔍 Rotor status: rotorEnabled=true, rotorAutoEnabled=true, hasGrid=true, hasCoords=false
🤖 AUTO rotor triggered for PJ6Y on 28.300 MHz (Grid: FK87KN)
```

**If you see different output:**
- `hasGrid=false, hasCoords=false` → Spot doesn't have location data (try different cluster)
- `rotorAutoEnabled=false` → AUTO not enabled (click AUTO button)
- `rotorEnabled=false` → Rotor not enabled globally (check config)

---

### Test 3: Wait for AUTO Rotor Command
**What to do:**
1. After clicking spot, wait 2 seconds
2. Watch console

**What to check in console:**
```
⏱️ Rotor AUTO pending: PJ6Y - waiting 2s for cancellation
[After 2 seconds...]
📡 Rotor AUTO response: {ok: true, bearing: 275.0, short_path_bearing: 275.0, long_path_bearing: 95.0, ...}
✅ Beaming display updated: SP=275.0°, LP=95.0°
✅ AUTO rotor moved to 275°: PJ6Y
🤖 Rotor → 275° for PJ6Y
```

**If you don't see these messages:**
- Check network tab (F12 → Network) for `/api/rotor/auto/goto` request
- Check if request returns HTTP 200
- Check response body for any error messages

---

### Test 4: Beaming Display Appearance
**What to look for on screen:**
1. Upper-left corner area (near Azimuth/Director controls)
2. Should see a panel that says:
   ```
   BEAMING FOR: PJ6Y
   SP: 275.0°  [GO]
   LP:  95.0°  [GO]
   ```

**If you don't see it:**
- Check V-if condition in HTML: `v-if="currentBeamingCallsign"`
- Check that `currentBeamingCallsign` is set (see Test 2 console output)
- Look for CSS display issues (hidden, display: none, etc.)
- Try clicking a different spot with a valid grid square

---

### Test 5: Manual GO Buttons
**What to do:**
1. With beaming display showing, click the "GO" button next to SP bearing

**What to check:**
1. Rotor azimuth should change to 275°
2. Console should show:
   ```
   Rotor manually commanded to 275°
   ✅ Rotor moved to 275°
   ```

**If button doesn't work:**
- Check rotor hardware is connected
- Check rotor hardware supports the command
- Check for JavaScript errors in console

---

### Test 6: AUTO Disabled Mode
**What to do:**
1. Click AUTO button to disable it (should turn grey)
2. Click a different spot

**What to check in console:**
```
🔍 Rotor status: rotorEnabled=true, rotorAutoEnabled=false, hasGrid=true, hasCoords=false
📡 Calculating bearing (AUTO disabled): PJ6Y with grid=FK87KN
📡 Bearing API response: {ok: true, bearing: 275.0, short_path_bearing: 275.0, ...}
✅ Bearing calculated for PJ6Y: SP 275.0° / LP 95.0°
```

**Important:** 
- Beaming display should appear IMMEDIATELY (no 2-second delay)
- Rotor should NOT move automatically
- Manual GO buttons should still work

---

### Test 7: Band Filtering
**What to do:**
1. Go to Config → Rotor tab
2. Enable rotor for ONLY 20m (uncheck all others)
3. Click Save
4. Click a 20m spot
5. Then click a 40m spot

**What to check:**

**For 20m spot:**
```
🤖 AUTO rotor triggered for ... on 14.XXX MHz
[After 2 sec...]
✅ AUTO rotor moved to XXX°
🤖 Rotor → XXX° for ...
```
Rotor should move ✅

**For 40m spot:**
```
🤖 AUTO rotor triggered for ... on 7.XXX MHz
[After 2 sec...]
ℹ️ Rotor AUTO not executed: Rotor not enabled for band 40m
⚠️ AUTO rotor: Rotor not enabled for band 40m
```
Rotor should NOT move ✅
But beaming display should STILL show with manual GO buttons ✅

---

### Test 8: Error Conditions

**Scenario A: Spot with NO location data**
```
🔍 Rotor status: ... hasGrid=false, hasCoords=false
ℹ️ Rotor data insufficient: rotorEnabled=true, hasGrid=false, hasCoords=false
```
Result: No beaming display, no rotor movement ✅

**Scenario B: Band disabled**
```
⚠️ AUTO rotor: Rotor not enabled for band 40m
```
Result: Beaming shows, rotor doesn't move ✅

**Scenario C: No coordinates at all**
```
📡 Bearing API response: {ok: false, error: "Insufficient data to calculate bearing"}
⚠️ Could not calculate bearing: Insufficient data to calculate bearing
```
Result: No beaming display ✅

---

## Console Message Reference

### ✅ SUCCESS Messages (All Good)
```
✅ Rotor is enabled, loading rotor configuration...
✅ Rotor AUTO is ENABLED
✅ Tuned to [callsign] on [frequency] MHz
✅ Bearing calculated for [callsign]: SP XXX° / LP XXX°
✅ AUTO rotor moved to XXX°: [callsign]
✅ Beaming display updated: SP=XXX°, LP=YYY°
```

### 🤖 INFO Messages (Actions in Progress)
```
🤖 AUTO rotor triggered for [callsign]...
🤖 Rotor → XXX° for [callsign]
⏱️ Rotor AUTO pending: [callsign] - waiting 2s
```

### 📡 DATA Messages (Calculations)
```
📡 Bearing calculated for [callsign]: SP XXX° / LP XXX°
📡 Rotor AUTO response: {...}
📡 Bearing API response: {...}
```

### ⚠️ WARNING Messages (Issues)
```
⚠️ Rotor is not enabled in configuration
⚠️ rotorAutoGoto called but not enabled: rotorAutoEnabled=false
⚠️ AUTO rotor: Rotor not enabled for band 40m
⚠️ Could not calculate bearing: [reason]
⚠️ Bearing API error: [error]
```

### ❌ ERROR Messages (Problems)
```
❌ Rotor AUTO error: [error message]
❌ Failed to tune to spot: [error]
```

---

## Expected Bearings Calculation

**For any location:**
- Short Path bearing = 0-360° (true bearing from your QTH)
- Long Path bearing = (SP + 180) mod 360

**Example:**
- If SP = 275°, then LP = (275 + 180) mod 360 = 95° ✓

**Verification:**
- Open console and click a spot
- Check: `SP=XXX°, LP=YYY°`
- Verify: `YYY = (XXX + 180) mod 360`

---

## Quick Diagnostic Commands

Run these in browser console after clicking a spot:

```javascript
// Check if AUTO is enabled
console.log('AUTO enabled:', this.$root.rotorAutoEnabled);

// Check current beaming state  
console.log('Callsign:', this.$root.currentBeamingCallsign);
console.log('SP:', this.$root.shortPathBearing);
console.log('LP:', this.$root.longPathBearing);

// Manually verify bearing math
const sp = this.$root.shortPathBearing;
const lp = this.$root.longPathBearing;
console.log('LP should be (SP + 180) % 360 = ' + sp + ' = ' + ((sp + 180) % 360));
console.log('Match:', lp === ((sp + 180) % 360));
```

---

## If Tests Fail

### Immediate Actions
1. **Refresh browser**: Ctrl+Shift+R (hard refresh)
2. **Restart backend**: `.\start_webapp.ps1`
3. **Check logs**: `Get-Content -Tail 50 c:\Projects\om0rx-radio-control\logs\flex_debug.log`

### Information to Collect
1. Screenshot of console messages (F12 → Console)
2. Content of rotor_config.json
3. Grid square being used for home location
4. Grid square of the DX spot being clicked
5. Which band the spot is on
6. Whether AUTO button is enabled/disabled

### Then Report With:
- Console screenshot (showing all messages from click to result)
- rotor_config.json content
- The exact spot clicked (callsign, band, frequency)
- What you expected to happen vs what actually happened

---

## Test Completion

✅ **All tests pass if you see:**
1. Console shows AUTO rotor messages
2. Beaming display appears in UI within 2 seconds
3. Rotor moves to bearing
4. SP/LP GO buttons work
5. Band filtering works correctly
6. Error conditions handled gracefully

If all above are working, the Rotor AUTO implementation is functioning correctly! 🎉