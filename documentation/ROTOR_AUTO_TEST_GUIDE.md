# 🎯 ROTOR AUTO TEST GUIDE

## Problem Fixed
✅ **AUTO mode was enabled but rotor was NOT turning** when clicking spots or logging QSOs

## Solution Applied
Added AUTO rotor trigger calls in:
1. **tuneToSpot()** - When clicking a DX spot
2. **submitQSO()** - When manually logging a QSO

---

## Quick Test (3 minutes)

### Prerequisites
- ✅ Backend started: `.\start_webapp.ps1`
- ✅ Application loaded: http://localhost:8000
- ✅ Rotor connected and working
- ✅ DX Cluster connected (getting spots)

### Test Steps

#### Test 1: AUTO via Spot Click

1. **Enable AUTO in Configuration:**
   - Click ⚙️ Configuration icon
   - Select "Rotor" tab
   - ✓ Check "Enable Rotor AUTO (auto-turn to spots/stations)"
   - Select your gridsquare (JN88TQ or yours)
   - ✓ Check desired bands (20m, 17m, 15m, 12m, 10m, etc.)
   - Click "Save Configuration"

2. **Open Browser DevTools (F12):**
   - Click Console tab
   - You should see AUTO config loaded messages

3. **Click a Spot in Spots panel:**
   - Spots panel on right side
   - Click any spot (e.g., "IS0GQX 3.5 CW")
   - Watch console for these messages in order:
     ```
     🎯 Tuning to IS0GQX on 3.5 MHz (CW)...
     ✅ Tuned to IS0GQX on 3.5 MHz
     🤖 AUTO rotor triggered for IS0GQX on 3.5 MHz
     ⏱️  Rotor AUTO pending: IS0GQX - waiting 2s for cancellation
     ✅ AUTO rotor moved to 215°: IS0GQX
     🤖 Rotor → 215° for IS0GQX (success notification)
     ```

4. **Check Rotor Movement:**
   - Look at rotor bearing in Radio Control section
   - Should show new bearing (e.g., 215°)
   - If rotor is physically connected, it should turn

5. **Test Cancellation (optional):**
   - During the 2-second delay, click another spot
   - Rotor should move to NEW bearing instead
   - Confirms cancellation logic works

#### Test 2: AUTO via Manual QSO Log

1. **Enter Callsign in Logging Panel:**
   - Log QSO section
   - Type callsign: "ZL3B" (or any other)
   - Tab/click to next field
   - System auto-loads QRZ data (gridsquare, lat/lon)

2. **Complete QSO Form:**
   - Frequency: 7.045
   - Mode: CW (or SSB, etc.)
   - RST Sent: 599
   - RST Rcvd: 599
   - Any other desired fields

3. **Click "Log QSO":**
   - Watch console for:
     ```
     🤖 AUTO rotor triggered for manual QSO: ZL3B on 7.045 MHz
     ⏱️  Rotor AUTO pending: ZL3B - waiting 2s for cancellation
     ✅ AUTO rotor moved to 342°: ZL3B
     🤖 Rotor → 342° for ZL3B
     ```

4. **Verify Rotor Movement:**
   - Rotor should turn to new bearing
   - Success notification should appear

---

## Expected Results

### ✅ AUTO Should Work (Rotor Turns)
- [ ] Click spot → Rotor turns to bearing
- [ ] Log QSO → Rotor turns to bearing
- [ ] 2-second delay allows cancellation
- [ ] Console shows all steps
- [ ] Bearing matches expected direction

### ✅ AUTO Should NOT Work (Rotor Stays)
- [ ] AUTO disabled in config → No rotor movement
- [ ] Band not enabled for rotor → No rotor movement
- [ ] Rotor not connected → Error message in console
- [ ] Invalid frequency → No rotor movement

### ✅ Bearings Should Be Accurate
- Examples from JN88TQ (Slovakia):
  - **IS0GQX (Italy):** 215-216° (Southwest)
  - **RZ9L (Russia):** 54-56° (Northeast)
  - **VE3... (Canada):** 300-310° (Northwest)

---

## Debugging

### If Rotor Doesn't Turn:

**Check 1: Is AUTO enabled?**
```javascript
// In console, type:
console.log(app.$data.rotorAutoEnabled);
// Should return: true
```

**Check 2: Is Rotor enabled?**
```javascript
console.log(app.$data.rotorEnabled);
// Should return: true
```

**Check 3: What's the error message?**
- Open F12 Console
- Look for any red "❌" error messages
- Rotor connection? Band enabled? Gridsquare available?

**Check 4: Is frequency being passed correctly?**
```javascript
// In console when clicking a spot, type:
console.log('Rotor auto enabled:', app.$data.rotorAutoEnabled);
console.log('Rotor enabled:', app.$data.rotorEnabled);
// Look for debug logs in console
```

**Check 5: Backend working?**
- Open http://localhost:8000/api/rotor/auto/status
- Should show AUTO config:
  ```json
  {
    "ok": true,
    "auto_enabled": true,
    "home_grid": "JN88TQ",
    "bands": {"20m": true, "17m": true, ...}
  }
  ```

### Common Issues

| Issue | Solution |
|-------|----------|
| Rotor doesn't move | Check AUTO enabled in config, band enabled, rotor connected |
| Wrong bearing | Check home gridsquare is correct, QRZ data loaded |
| No console messages | Hard refresh (Ctrl+Shift+R), check backend is running |
| 2s delay too long | Can change ROTOR_AUTO_DELAY_SEC in config.py (default: 2.0) |
| Rotor gets stuck | Click another spot to cancel, or wait 2s and try again |

---

## Success Indicators

✅ **You know it's working when:**

1. **Console shows "🤖 AUTO rotor triggered"** when clicking spot
2. **Rotor bearing changes** in Radio Control section
3. **Success message** "🤖 Rotor → XXX°" appears
4. **2-second delay works** - can cancel by clicking another spot
5. **Bearings are accurate** - match WSJT-X or other ham radio software

---

## Next Steps

Once verified working:

1. **Test with different spots** - European, Asian, American
2. **Verify bearings** - Use WSJT-X or online bearing calculators
3. **Test band disabling** - Disable band in config, verify rotor doesn't move
4. **Test AUTO disabling** - Disable AUTO, verify rotor doesn't move
5. **Long-term operation** - Leave running and verify stability

---

## Files Modified

| File | Change |
|------|--------|
| `frontend/app.js` | Added AUTO rotor trigger in tuneToSpot() and submitQSO() |

---

## Revert if Needed

If you need to revert the change:

```powershell
# Go back to original app.js (if you have version control)
git checkout frontend/app.js

# Or manually remove the sections between:
# "// === TRIGGER ROTOR AUTO IF ENABLED ===" 
# comments in both functions
```

---

**Test Status:** Ready to test! 🚀
