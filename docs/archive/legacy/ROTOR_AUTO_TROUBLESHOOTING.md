# Rotor AUTO Troubleshooting Guide

## Quick Checks

### "Beaming display is not showing"

**Step 1: Check the console for errors**
- Open browser Developer Tools (F12)
- Go to Console tab
- Look for red error messages

**Step 2: Check that you're actually clicking a spot**
- Spots should be visible in the DX Spots section
- When you click a spot, you should see messages like:
  - `🎯 tuneToSpot called with spot: ...`
  - `🔍 Rotor status: rotorEnabled=true, rotorAutoEnabled=...`

**Step 3: Verify the spot has location data**
Check the console for messages like:
```
🔍 Rotor status: rotorEnabled=true, rotorAutoEnabled=true, hasGrid=true, hasCoords=false
```

If both `hasGrid=false` and `hasCoords=false`, the beaming can't be calculated. This spot doesn't have location information.

**Solution**: 
- Switch to a different DX cluster (some provide grid squares, others don't)
- Or enable AUTO for a cluster that includes grid squares in spot data

### "Rotor is NOT automatically turning"

**Step 1: Check that AUTO is actually enabled**
- In the UI, look for the "AUTO" button at the top
- It should show green/active if AUTO is enabled
- Check the console: look for `✅ Rotor AUTO is ENABLED` on app startup

If AUTO is disabled:
- Click the AUTO button to enable it
- Verify it shows as enabled

**Step 2: Check rotor_config.json**
- File location: `c:\Projects\om0rx-radio-control\rotor_config.json`
- Should contain: `"ROTOR_AUTO_ENABLED": true`

If false or missing:
```json
{
    "ROTOR_AUTO_ENABLED": true  // Must be true
}
```

**Step 3: Check that AUTO is actually being triggered**
- Click a spot
- Check console for: `🤖 AUTO rotor triggered for ...`

If you DON'T see this message:
- Either AUTO is disabled (see Step 1)
- Or rotor is not enabled (see "Rotor not working" section)

**Step 4: Wait 2 seconds after clicking**
- AUTO rotor has a 2-second delay before sending the command
- Look for: `⏱️ Rotor AUTO pending: ...`
- Then after 2 seconds: `📡 Rotor AUTO response: ...`

If rotor doesn't move after that:
- Check band is enabled for that frequency
- Check rotor hardware connection

### "Bearing calculations are wrong"

**Step 1: Verify home grid square**
- In rotor config tab, check ROTOR_HOME_GRID
- Must be a valid grid like JN88TQ
- Wrong grid = wrong bearing calculation

**Step 2: Verify spotted station's location**
- Check console: `short_path_bearing: 275.0, long_path_bearing: 95.0`
- If LP bearing is just (SP + 180), calculation is correct
- Example: 275 + 180 = 455, mod 360 = 95 ✓

**Step 3: Check that gridsquare is from QRZ**
- When clicking a spot, if it has a gridsquare, that's used for bearing
- Console shows: `source: "gridsquare"`
- If source is "coordinates", lat/lon were used instead

### "The AUTO button doesn't work"

**Step 1: Check rotor is enabled**
- AUTO only works if rotor is enabled globally
- If rotor not connected, you'll see alert: "Rotator not enabled"

**Step 2: Check the console**
- Click AUTO button
- Look for: `🤖 Rotor AUTO ENABLED` or `DISABLED`
- Look for save message: `✅ Rotor AUTO config saved`

If you see error messages:
- Check server is running: visit http://localhost:8000 in browser
- Check no firewall issues
- Check browser console for network errors

**Step 3: Verify rotor_config.json was updated**
- After toggling AUTO, file should update within 2 seconds
- Check: `"ROTOR_AUTO_ENABLED": true` or `false`

If file doesn't update:
- Check file permissions
- Check backend has write access to project directory
- Restart backend: `.\start_webapp.ps1`

### "Manual GO buttons (SP/LP) don't work"

**Step 1: Verify bearings are shown**
- Must see `SP: XXX°` with GO button
- Must see `LP: YYY°` with GO button

If not showing:
- Click a spot with valid location first
- See "Beaming display is not showing" section

**Step 2: Click the GO button**
- Check console: `Rotor manually commanded to ...°`
- Check rotor azimuth dial moves

If button click doesn't work:
- Open browser console
- Check for JavaScript errors
- Try refreshing browser

### "Rotor settings won't save"

**Step 1: Try in rotor configuration tab**
- Set ROTOR_HOME_GRID
- Click Save
- Check console: `✅ Rotor AUTO config saved`

If you see error:
- Check server is running
- Check network connection
- Try again in 30 seconds

**Step 2: Verify settings in rotor_config.json**
- File should update after successful save
- Check file timestamp changed

If file doesn't update:
- Backend might have crashed
- Restart: `.\start_webapp.ps1`

### "Band filtering not working"

**Step 1: Check which bands are enabled**
- Go to rotor config tab
- Look at ROTOR_BANDS section
- 20m, 17m, 15m, etc. should show checkboxes

**Step 2: Enable/disable bands**
- Check desired bands
- Uncheck undesired bands
- Click Save

**Step 3: Test**
- Click a spot on enabled band → rotor should move
- Click a spot on disabled band → rotor shouldn't move, but beaming shows

If rotor moves on disabled band:
- Refresh browser
- Check rotor_config.json file has correct bands
- Restart backend

### "Beaming display shows wrong callsign"

This can happen if:
1. You have multiple spots selected (UI issue)
2. You manually entered a different callsign
3. OLD state is persisting

**Solutions**:
- Click on the spot whose bearing you want (not others)
- Or manually clear the callsign field and re-enter
- Or reload the browser page

### General Debugging Tips

**1. Always check browser console (F12 → Console)**
- This is where all the debug messages go
- Filter by the rotor symbols: 🤖, 📡, ⏱️, ✅, ⚠️, ❌
- Timestamps help identify when things happened

**2. Check the logs**
- Backend logs: `c:\Projects\om0rx-radio-control\logs\flex_debug.log`
- Look for rotor-related messages with timestamps

**3. Verify file changes**
```powershell
# Check rotor config file
Get-Content c:\Projects\om0rx-radio-control\rotor_config.json | ConvertFrom-Json | Format-List

# Check file timestamp
Get-Item c:\Projects\om0rx-radio-control\rotor_config.json | Select-Object LastWriteTime
```

**4. Restart components**
```powershell
# Restart just the rotor config (reload from JSON)
# (no specific restart needed, happens automatically)

# Restart backend
.\start_webapp.ps1

# Reload frontend browser
# Press Ctrl+Shift+R for hard refresh (clears cache)
```

**5. Check network in browser**
- F12 → Network tab
- Click a spot
- Look for `/api/rotor/auto/goto` request
- Check Response tab for bearing data

### Still Not Working?

**Capture for support:**
1. Open browser console (F12)
2. Clear it
3. Perform the action that doesn't work
4. Take screenshot of all console messages
5. Provide details:
   - What spot did you click?
   - What grid square is your station?
   - What frequency/band?
   - What does rotor_config.json currently show?
   - Any error messages?

## Known Issues and Workarounds

### Issue: AUTO triggers too fast / need to cancel
**Workaround**: There's a 2-second delay built in. Click a different spot quickly to cancel.

### Issue: Band name mismatch (e.g., "10m" vs "10M")
**Status**: Backend normalizes to lowercase (10m, 20m, etc.)
**Action**: No user action needed, handled automatically

### Issue: Bearing shows but rotor doesn't move
**Likely**: Band is disabled for rotor
**Solution**: Enable band in rotor configuration and try again

### Issue: Nothing happens when clicking spots
**Most likely**: Rotor is not enabled in main config
**Check**: `config.py` file has `ROTOR_ENABLED = True`

### Issue: Beaming display cleared after entering manual callsign
**Expected behavior**: When you manually type a callsign (not clicking a spot), bearings clear until calculated
**Action**: Either click a spot or wait for bearing calculation to update

## Performance

- Bearing calculation: <100ms (usually <50ms)
- AUTO delay: 2 seconds (configurable in code)
- Display update: Real-time via Vue reactivity (<10ms)
- Network latency: Depends on server (usually <100ms)

**Total time from clicking spot to rotor moving:**
- AUTO enabled: 2-2.2 seconds
- AUTO disabled: 0.1-0.3 seconds