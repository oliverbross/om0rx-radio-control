# "Worked b4" Feature - Diagnostic Guide

## Quick Status Check

The "Worked b4" feature should show a checkmark (✓) with the date (DD/MM/YYYY) in the "Worked b4" column for any DX spot that matches a previous QSO from your log.

### How to Test It Right Now

#### Step 1: Open Browser Console
1. In your browser, press **F12**
2. Go to the **Console** tab
3. You should see several log messages starting with ✅ and 🔍

#### Step 2: Check for Success Message
Look for this message in the console:
```
✅ Loaded 1250 worked band/mode combinations from 2847 total QSOs
📝 Sample keys: VE3KZE-20M-CW, K3LR-40M-SSB, ...
```

**If you see this**: ✅ Data is loading correctly

**If you see "Loaded 0"**: ⚠️ Either your QSO log is empty, or there's a backend issue

#### Step 3: Check For Warnings
Look for these warning messages (these are NORMAL if you have old QSOs):
```
⚠️  QSO without BAND: VE3KZE CW - will try to derive from frequency
⚠️  Skipped 45 QSOs due to missing CALL/BAND/MODE
```

**What this means**: Some QSOs in your log don't have BAND fields (they were logged before this feature). The system tries to derive the band from frequency, but this may not always work perfectly.

---

## If "Worked b4" Shows Nothing

### Check 1: Is Your QSO Log File Present?
```
File location: c:\Projects\om0rx-radio-control\logs\qso_log.adif
Expected size: 1+ MB (yours appears to be 39MB)
```

✅ **How to verify**:
1. Open your file explorer
2. Navigate to: `c:\Projects\om0rx-radio-control\logs\`
3. Look for `qso_log.adif`
4. File should be large (39+ MB)

❌ **If file is missing or empty**: You have no QSO history to match against

### Check 2: Is the Backend API Working?
1. In browser console, run this command:
```javascript
fetch('/api/adif/all').then(r => r.json()).then(d => {
  console.log('Status:', d.success);
  console.log('QSO Count:', d.count);
  console.log('Sample QSOs:', d.data?.slice(0, 3));
});
```

2. You should see output like:
```
Status: true
QSO Count: 2847
Sample QSOs: [
  {call: "VE3KZE", band: "20m", mode: "CW", qso_date: "20251028", ...},
  ...
]
```

✅ **Good**: QSOs have `band` field with values like "20m"

❌ **Bad**: QSOs missing `band` field → **See Fix Below**

### Check 3: Is the Data Loaded in Frontend?
In the browser console, run:
```javascript
// Check Vue app's workedCallsigns data
console.log('Worked callsigns loaded:', Object.keys(app._instance.data.workedCallsigns).length);
console.log('Sample keys:', Object.keys(app._instance.data.workedCallsigns).slice(0, 5));
```

✅ **Should show**: Sample keys like `VE3KZE-20M-CW`, `K3LR-40M-SSB`

❌ **Shows 0 keys**: Data not being loaded

### Check 4: Does a Specific Spot Have Band Information?
Click on a DX spot in the table, then in console:
```javascript
// Check if last tuned spot had band
console.log('Tuning form data:', {
  callsign: app._instance.data.loggingForm.callsign,
  band: app._instance.data.loggingForm.band,
  frequency: app._instance.data.loggingForm.frequency,
  mode: app._instance.data.loggingForm.mode
});
```

✅ **Should show**: `band: "20m"` (not empty!)

❌ **Shows empty band**: Spot may not have band information

---

## Common Issues & Fixes

### Issue 1: "Loaded 0 worked band/mode combinations"

**Cause**: Backend is not returning QSOs from your ADIF file

**Fix**:
1. Verify `/logs/qso_log.adif` exists and is not empty
2. Restart backend: `python backend/main.py`
3. Wait 5 seconds for startup
4. Refresh browser page

### Issue 2: "Skipped many QSOs due to missing BAND"

**Cause**: Old QSOs don't have BAND field written to ADIF

**Fix** - Option A (One-time regeneration):
1. Delete old ADIF log: `c:\Projects\om0rx-radio-control\logs\qso_log.adif`
2. Re-export your QSOs from your log application (if you have another copy)
3. New QSOs will have BAND field

**Fix** - Option B (Use frequency-derived band):
The system automatically tries to derive band from frequency for old QSOs, but it only works if FREQ field exists.

**Fix** - Option C (Manual cleanup):
Edit `qso_log.adif` with a text editor and add BAND fields:
- Find: `<MODE:3>CW <FREQ:9>14.074000`
- Replace with: `<MODE:3>CW <FREQ:9>14.074000 <BAND:3>20m`

### Issue 3: Worked spot shows but date is wrong

**Cause**: ADIF date format issue or duplicate entries

**Fix**:
1. Check ADIF file format - dates should be YYYYMMDD (e.g., 20251028)
2. Remove duplicate QSO entries
3. Restart backend

### Issue 4: Band doesn't populate when clicking a spot

**Cause**: Spot object doesn't have band field

**Check**:
1. Click a DX spot
2. In console, run:
```javascript
console.log('Current spot band:', app._instance.data.loggingForm.band);
```

**If empty**: Band field not being set by tuneToSpot()

**Fix**: Check that spot data from backend includes `band` field:
```javascript
// In console, check what the API returns
fetch(`/api/spots/recent?limit=1`).then(r => r.json()).then(d => 
  console.log('Spot fields:', Object.keys(d.data[0]))
);
```

Should include: `callsign`, `band`, `mode`, `frequency_mhz`

---

## Data Flow Verification

### Expected Flow for "Worked b4" to Work:

```
1. ✅ QSO is logged with band information
   ↓
2. ✅ Band is written to /logs/qso_log.adif
   ↓
3. ✅ User loads index.html
   ↓
4. ✅ Frontend calls loadWorkedCallsigns()
   ↓
5. ✅ Fetches /api/adif/all from backend
   ↓
6. ✅ Backend reads ADIF file and parses BAND field
   ↓
7. ✅ Returns QSOs with BAND in JSON
   ↓
8. ✅ Frontend builds map: "CALL-BAND-MODE" → date
   ↓
9. ✅ When rendering spots, calls getWorkedDate(callsign, band, mode)
   ↓
10. ✅ Returns checkmark with date if found
```

### How to Trace Each Step:

**Step 1-2: QSO Logged**
```
Check: c:\Projects\om0rx-radio-control\logs\qso_log.adif
Should contain: <BAND:3>20m
```

**Step 4-8: Frontend Loading**
```
Console: Check for "✅ Loaded X worked" message
```

**Step 9-10: Spot Rendering**
```
Click a spot, check console:
- getWorkedDate('VE3KZE', '20m', 'CW') → Should return '✓ 28/10/2025'
- Or empty string if not found
```

---

## Browser Console Commands Reference

### See all console messages
```javascript
// Copy/paste this to see formatted output
console.group('=== Worked b4 Status ===');
console.log('QSOs loaded:', Object.keys(app._instance.data.workedCallsigns).length);
console.log('Sample key:', Object.keys(app._instance.data.workedCallsigns)[0]);
const testKey = Object.keys(app._instance.data.workedCallsigns)[0];
console.log('Test result:', app._instance.data.getWorkedDate(...testKey.split('-')));
console.groupEnd();
```

### Check if a specific callsign was worked
```javascript
// Example: Find if VE3KZE on 20m CW was worked
const result = app._instance.data.getWorkedDate('VE3KZE', '20m', 'CW');
console.log('VE3KZE/20m/CW worked on:', result || 'NOT FOUND');
```

### See all worked callsigns for a specific call
```javascript
// Find all band/mode combinations for a callsign
const call = 'VE3KZE';
const keys = Object.keys(app._instance.data.workedCallsigns).filter(k => 
  k.startsWith(call.toUpperCase() + '-')
);
console.log(`${call} worked on:`, keys);
```

---

## Performance Check

If the feature is slow or causing lag:

1. Check how many QSOs are loaded:
```javascript
console.log('QSO count:', Object.keys(app._instance.data.workedCallsigns).length);
```

**Should be**: < 100,000 (most operators have 1,000-10,000)

2. If very high (100,000+), performance may be impacted:
   - Limit ADIF load: `app._instance.data.loadWorkedCallsigns()` with limit parameter
   - Archive old QSOs to separate file

---

## Still Not Working?

### Enable Debug Logging
Add this to browser console:
```javascript
// Monkey-patch getWorkedDate to log calls
const original = app._instance.data.getWorkedDate;
app._instance.data.getWorkedDate = function(call, band, mode) {
  const result = original.call(this, call, band, mode);
  if (result) {
    console.log(`✓ ${call} on ${band}/${mode}: ${result}`);
  }
  return result;
};
```

Now when you scroll the spots table, you'll see every match in the console.

### Restart Everything
Sometimes browser cache causes issues:
1. Press **Ctrl+Shift+Delete** (Clear browsing data)
2. Click: Clear all time, History + Cache
3. Close browser
4. Restart backend: `python backend/main.py`
5. Open browser to http://localhost:8000
6. Reload: **Ctrl+F5** (hard refresh)

---

## Contact Support

If you're still having issues, run this diagnostic command and share the output:

```javascript
fetch('/api/adif/all').then(r => r.json()).then(d => {
  const diagnostic = {
    qso_count: d.count,
    sample_qso: d.data?.[0],
    has_band: !!d.data?.[0]?.band,
    loaded_count: Object.keys(app._instance.data.workedCallsigns).length,
    test_lookup: app._instance.data.getWorkedDate(d.data?.[0]?.call, d.data?.[0]?.band, d.data?.[0]?.mode)
  };
  console.log(JSON.stringify(diagnostic, null, 2));
  // Copy output and send
});
```

This will show:
- How many QSOs are in your log
- Sample QSO structure
- Whether BAND field exists
- Whether frontend loaded them
- Whether lookup works

---

**Status**: DIAGNOSTIC READY ✅
**Use this to identify exactly where the issue is**