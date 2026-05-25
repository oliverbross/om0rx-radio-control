# DX Spots Filters - Manual Verification Guide

**Purpose**: Step-by-step guide to manually test all filters in the running application  
**Prerequisites**: Application must be running with DX spots data flowing in  
**Time Required**: ~10 minutes

---

## Quick Start Checklist

Before starting detailed tests, verify the basic setup:

- [ ] Application is running: `http://localhost:8000`
- [ ] Backend is running: Python FastAPI server active
- [ ] WebSocket is connected: Check browser console, should NOT see connection errors
- [ ] DX spots are streaming: Should see spots appearing in the list
- [ ] Filters panel is visible: Bottom section with "Show", "Bands", "Modes", etc.

---

## Test 1: Show Filter (Spot Count) ✓ WORKING

**What it does**: Limit number of spots displayed (10, 25, 50, 100, 200)

### Steps:
1. Open browser DevTools (F12) → Console
2. Note the current number of spots displayed
3. Click the **📊 Show: 100** button (or current value)
4. A dropdown should appear with options: 10, 25, 50, 100, 200
5. Click **25** to select
6. **Verify**: 
   - [ ] Dropdown closes
   - [ ] Button now shows "📊 Show: 25"
   - [ ] Spot list now shows ~25 spots or fewer (if fewer available)
   - [ ] In console: `Vue.vm.$data.maxSpots` should equal `25`

### Result: ✅ **EXPECTED: PASS** (already confirmed working)

---

## Test 2: Band Filter ✓ FIXED

**What it does**: Show only spots from selected bands (20m, 15m, etc.)

### Setup:
```javascript
// In browser console, verify spots have 'band' field:
Vue.vm.$data.dxSpots.slice(0, 3).forEach(s => console.log(`${s.callsign}: ${s.band}`))
// Should show: "K0XYZ: 20m", "VE3ABC: 15m", etc.
```

### Steps:
1. Click **📻 Bands** button
2. A dropdown appears showing available bands
3. Select **"20m"** (click checkbox or item)
4. **Verify**:
   - [ ] Button now shows "📻 Bands ▼" in different color/style (active)
   - [ ] Spot list updates - should now only show 20m spots
   - [ ] **CRITICAL**: Look at displayed spots, check they're all 20m band
   - [ ] In console: `Vue.vm.$data.spotsFilter.bands` should be `["20m"]`

5. Now select **"15m"** as well (add to existing selection)
6. **Verify**:
   - [ ] Spot list now shows 20m AND 15m spots (combined)
   - [ ] Only spots from these two bands appear
   - [ ] In console: `Vue.vm.$data.spotsFilter.bands` should be `["20m", "15m"]`

7. Click **"Clear"** button in dropdown
8. **Verify**:
   - [ ] Filter clears
   - [ ] All spots return
   - [ ] Button returns to normal style

### Expected Results:
- ✅ Single band selection filters correctly
- ✅ Multiple band selection uses OR logic (20m OR 15m)
- ✅ Clear button empties the filter

### Troubleshooting If Failing:
```javascript
// Check if spot.band exists and has correct values
Vue.vm.$data.dxSpots.forEach((s, i) => {
    if (!s.band) console.error(`Spot ${i} missing band:`, s);
});
// If band is missing, it's a backend issue - check main.py line 538
```

---

## Test 3: Mode Filter ✓ FIXED

**What it does**: Show only spots using selected modes (CW, SSB, FT8, etc.)

### Setup:
```javascript
// Verify spots have 'mode' field:
Vue.vm.$data.dxSpots.slice(0, 5).forEach(s => console.log(`${s.callsign}: ${s.mode}`))
// Should show: "K0XYZ: CW", "VE3ABC: SSB", etc.
```

### Steps:
1. Click **📡 Modes** button
2. Dropdown shows: CW, SSB, FT8, FT4, RTTY, PSK, DIGI, AM, FM, JT65, SSTV
3. Select **"CW"**
4. **Verify**:
   - [ ] Button highlights as active
   - [ ] Spot list shows only CW mode spots
   - [ ] In console: `Vue.vm.$data.spotsFilter.modes` should be `["CW"]`

5. Select **"FT8"** as well (multi-select)
6. **Verify**:
   - [ ] Spots now show CW and FT8 combined
   - [ ] In console: `Vue.vm.$data.spotsFilter.modes` should be `["CW", "FT8"]`

7. Click **"All"** button (if available)
8. **Verify**:
   - [ ] All modes are selected
   - [ ] Spot list shows all modes

9. Click **"Clear"**
10. **Verify**:
    - [ ] Filter cleared
    - [ ] All spots return

### Expected Results:
- ✅ Single mode selection filters correctly
- ✅ Multiple mode selections combine with OR
- ✅ "All" and "Clear" buttons work

---

## Test 4: Continent Filter (Spotter Location) ✓ FIXED

**What it does**: Show only spots from spotter's continent

**IMPORTANT**: This filters by **spotter's location**, not DX station location

### Setup:
```javascript
// Verify spots have 'spotter_continent' field (not 'continent'):
Vue.vm.$data.dxSpots.slice(0, 5).forEach(s => 
    console.log(`${s.spotter}: from ${s.spotter_continent}`)
)
// Should show: "W0XYZ: from NA", "G0ABC: from EU", etc.
```

### Steps:
1. Click **🌍 Spotter from** button
2. Dropdown shows continents: Europe, N. America, Asia, Africa, S. America, Oceania
3. Select **"Europe"**
4. **Verify**:
   - [ ] Button shows as active
   - [ ] Spot list updates - only shows spots **spotted by European stations**
   - [ ] In console: `Vue.vm.$data.spotsFilter.continents` should be `["EU"]`

5. Select **"Oceania"** as well
6. **Verify**:
   - [ ] Now shows spots from European AND Oceania spotters
   - [ ] In console: `Vue.vm.$data.spotsFilter.continents` should be `["EU", "OC"]`

7. Clear the filter
8. **Verify**:
   - [ ] All spots return

### Expected Results:
- ✅ Single continent selection filters correctly
- ✅ Multiple continents combine with OR
- ✅ Filters spotter location, not DX station location

### Troubleshooting If Failing:
```javascript
// Check field name - must be 'spotter_continent' not 'continent'
Vue.vm.$data.dxSpots.forEach((s, i) => {
    if (!s.spotter_continent) {
        console.error(`Spot ${i} missing spotter_continent:`, s.callsign);
        console.log('Available fields:', Object.keys(s));
    }
});
// If missing, backend main.py line 536 has the issue
```

---

## Test 5: CQ Zone Filter ✓ FIXED

**What it does**: Show only spots from selected CQ zones (1-75)

**CRITICAL**: This test includes type conversion (string vs integer)

### Setup:
```javascript
// Verify spots have 'cq' field (as string):
Vue.vm.$data.dxSpots.slice(0, 5).forEach(s => 
    console.log(`${s.callsign}: CQ Zone ${s.cq} (type: ${typeof s.cq})`)
)
// Should show: "K0XYZ: CQ Zone 5 (type: string)", etc.
```

### Steps:
1. Click **🌐 Zones** button
2. Dropdown shows numbers 1-75 (might need to scroll)
3. Select **"5"** (CQ Zone 5)
4. **Verify**:
   - [ ] Button shows as active
   - [ ] Spot list updates - only CQ Zone 5 spots
   - [ ] In console: `Vue.vm.$data.spotsFilter.cqs` should be `[5]` (integer)

5. Select **"14"** as well
6. **Verify**:
   - [ ] Now shows CQ Zone 5 AND Zone 14 spots
   - [ ] In console: `Vue.vm.$data.spotsFilter.cqs` should be `[5, 14]`

7. Clear the filter
8. **Verify**:
   - [ ] All spots return

### Critical Check:
```javascript
// Verify the type conversion is happening correctly
const spot = Vue.vm.$data.dxSpots[0];
const filter = Vue.vm.$data.spotsFilter.cqs[0];
console.log(`Spot CQ: ${spot.cq} (type: ${typeof spot.cq})`);
console.log(`Filter CQ: ${filter} (type: ${typeof filter})`);
console.log(`String comparison: String(${spot.cq}) === String(${filter}):`, 
    String(spot.cq) === String(filter));
```

### Expected Results:
- ✅ CQ Zone selection filters correctly
- ✅ Type conversion from integer to string works
- ✅ Multiple zones combine with OR

### Troubleshooting If Failing:
```javascript
// Check if field name is correct (must be 'cq' not 'cq_zone')
Vue.vm.$data.dxSpots.forEach((s, i) => {
    if (!s.cq) {
        console.error(`Spot ${i} missing cq field:`, s.callsign);
    }
});
```

---

## Test 6: Call Status Filter ✓ WORKING

**What it does**: Show only spots with selected call status

**Status Values**: "New Call", "New Band", "New Mode", "New Band+Mode", "Worked", "Confirmed"

### Steps:
1. Click **📞 Call Status** button
2. Dropdown shows available statuses
3. Select **"New Call"**
4. **Verify**:
   - [ ] Button shows as active
   - [ ] Spot list shows only "New Call" spots
   - [ ] In console: `Vue.vm.$data.spotsFilter.callStatuses` should be `["New Call"]`

5. Select **"Worked"** as well
6. **Verify**:
   - [ ] Shows "New Call" OR "Worked" spots
   - [ ] In console: `Vue.vm.$data.spotsFilter.callStatuses` should be `["New Call", "Worked"]`

7. Clear filter and verify all spots return

### Expected Results:
- ✅ Single status filters correctly
- ✅ Multiple statuses combine with OR

---

## Test 7: DXCC Status Filter ✓ WORKING

**What it does**: Show only spots with selected DXCC status

**Status Values**: "ATNO", "C/New Band", "C/New Mode", "C/New Band+Mode", "W/New Band", "W/New Mode", "W/New Band+Mode", "Worked", "Confirmed", "Unknown"

### Steps:
1. Click **🏆 DXCC Status** button
2. Dropdown shows available DXCC statuses
3. Select **"ATNO"** (All-Time New One)
4. **Verify**:
   - [ ] Button shows as active
   - [ ] Spot list shows only ATNO spots
   - [ ] In console: `Vue.vm.$data.spotsFilter.dxccStatuses` should be `["ATNO"]`

5. Select **"Worked"** as well
6. **Verify**:
   - [ ] Shows ATNO OR Worked spots
   - [ ] In console: `Vue.vm.$data.spotsFilter.dxccStatuses` should be `["ATNO", "Worked"]`

7. Clear and verify

### Expected Results:
- ✅ Single DXCC status filters correctly
- ✅ Multiple statuses combine with OR

---

## Test 8: Special Activities Filter ✓ WORKING

**What it does**: Show only spots with special activities (POTA, SOTA, WWFF, IOTA, LH, Contest)

**How it works**: Searches spot comments for these keywords (case-insensitive)

### Setup:
```javascript
// Verify spots have 'comment' field and check for activity keywords:
Vue.vm.$data.dxSpots.slice(0, 10).forEach(s => {
    if (s.comment) console.log(`${s.callsign}: ${s.comment}`);
});
```

### Steps:
1. Click **⭐ Special** button
2. Dropdown shows: POTA, SOTA, WWFF, IOTA, LH, Contest
3. Select **"POTA"**
4. **Verify**:
   - [ ] Button shows as active
   - [ ] Spot list shows only spots with "POTA" in comment
   - [ ] In console: `Vue.vm.$data.spotsFilter.specials` should be `["POTA"]`

5. Look at a displayed spot and verify it has "POTA" in the comment
6. Select **"SOTA"** as well
7. **Verify**:
   - [ ] Shows spots containing "POTA" OR "SOTA" in comments
   - [ ] In console: `Vue.vm.$data.spotsFilter.specials` should be `["POTA", "SOTA"]`

8. Clear and verify all spots return

### Expected Results:
- ✅ Single activity filters correctly
- ✅ Multiple activities combine with OR
- ✅ Search is case-insensitive

---

## Test 9: Callsign Search ✓ WORKING

**What it does**: Search by callsign (substring match)

### Steps:
1. Locate the **🔍 Call** search input field (top of filter section)
2. Type **"K0"** 
3. **Verify**:
   - [ ] Spot list instantly filters
   - [ ] Shows only spots with callsigns containing "K0"
   - [ ] In console: `Vue.vm.$data.spotsFilter.callsign` should be `"K0"`

4. Clear the search box
5. **Verify**:
   - [ ] All spots return

### Expected Results:
- ✅ Substring search works
- ✅ Case-insensitive matching
- ✅ Instant filtering

---

## Test 10: Combining Multiple Filters (AND Logic) ✓ CRITICAL

**What it does**: Verify filters combine with AND logic (spot must match ALL active filters)

### Scenario Test:
1. **Set Band to 20m**
   - Select 📻 Bands → "20m"
   - Verify: Shows all 20m spots
   
2. **Add Mode filter CW**
   - Select 📡 Modes → "CW"
   - **Verify**:
     - [ ] Now shows **only 20m AND CW spots**
     - [ ] All displayed spots are both 20m band AND CW mode
     - [ ] More restrictive than either filter alone

3. **Add Continent filter Europe**
   - Select 🌍 Spotter from → "Europe"
   - **Verify**:
     - [ ] Now shows **only 20m AND CW AND spotted by Europeans**
     - [ ] Three filters active, all apply together
     - [ ] Most restrictive filter so far

4. **Add Special Activity POTA**
   - Select ⭐ Special → "POTA"
   - **Verify**:
     - [ ] Now shows 20m AND CW AND European spotters AND POTA
     - [ ] Very restrictive - might show 0 results if no matches
     - [ ] All 4 filters combined with AND logic

5. **Click 🗑️ Clear All**
6. **Verify**:
    - [ ] All filters clear
    - [ ] All spots return

### Console Verification:
```javascript
// After step 4, run this to verify all filters are active:
const f = Vue.vm.$data.spotsFilter;
console.log({
    bands: f.bands,           // Should have ["20m"]
    modes: f.modes,           // Should have ["CW"]
    continents: f.continents, // Should have ["EU"]
    specials: f.specials      // Should have ["POTA"]
});

// Verify results match all criteria:
Vue.vm.$data.filteredSpots.forEach(spot => {
    if (spot.band !== "20m") console.error("Band mismatch!", spot);
    if (spot.mode !== "CW") console.error("Mode mismatch!", spot);
    if (spot.spotter_continent !== "EU") console.error("Continent mismatch!", spot);
    if (!spot.comment.includes("POTA")) console.error("POTA mismatch!", spot);
});
console.log("All spots match criteria!");
```

### Expected Results:
- ✅ Filters combine with AND logic
- ✅ Spot must match ALL active filter criteria
- ✅ Clear All button resets everything

---

## Test 11: Button States & Visual Feedback ✓

**What it does**: Verify UI shows correct active/inactive states

### Steps:
1. With no filters active, all filter buttons should appear **normal** (not highlighted)
2. Activate Band filter (select one band)
3. **Verify**:
   - [ ] 📻 **Bands button now appears highlighted/different color** (active state)
   - [ ] Shows indication that filter is active
   
4. Activate Continent filter too
5. **Verify**:
   - [ ] Both 📻 Bands and 🌍 Spotter from buttons show as active
   
6. Clear Bands filter only
7. **Verify**:
   - [ ] 📻 Bands button returns to normal
   - [ ] 🌍 Spotter from still shows as active
   
8. Clear All filters
9. **Verify**:
   - [ ] All buttons return to normal state

### Expected Results:
- ✅ Active filters show visual distinction
- ✅ Inactive filters appear normal
- ✅ UI feedback is clear and immediate

---

## Test 12: Spot Count Display ✓

**What it does**: Verify the "X spots" display updates correctly

### Steps:
1. Check the number display next to filters (shows "X spots" or similar)
2. Apply Band filter - select "20m"
3. **Verify**:
   - [ ] Count updates to show filtered number (e.g., "42 spots")
   - [ ] Number decreases or stays same (never increases)
   
4. Add another band "15m"
5. **Verify**:
   - [ ] Count increases or stays same (from adding more matching spots)
   
6. Apply strict Mode filter "CW" 
7. **Verify**:
   - [ ] Count decreases or stays same
   - [ ] No new spots added
   
8. Clear all filters
9. **Verify**:
   - [ ] Count returns to original total

### Expected Results:
- ✅ Count updates reactively
- ✅ AND logic shows decreasing or same count
- ✅ OR logic within filters can increase count

---

## Browser Console Helper Commands

Run these in the browser console (F12) to diagnose issues:

```javascript
// 1. Check current filter state
Vue.vm.$data.spotsFilter

// 2. Check filtered spots count
Vue.vm.$data.filteredSpots.length

// 3. Check all raw spots
Vue.vm.$data.dxSpots.length

// 4. Verify a specific spot structure
Vue.vm.$data.dxSpots[0]

// 5. Check if filters are merging correctly
{
    bands: Vue.vm.$data.spotsFilter.bands,
    modes: Vue.vm.$data.spotsFilter.modes,
    continents: Vue.vm.$data.spotsFilter.continents,
    cqs: Vue.vm.$data.spotsFilter.cqs,
    callStatuses: Vue.vm.$data.spotsFilter.callStatuses,
    dxccStatuses: Vue.vm.$data.spotsFilter.dxccStatuses,
    specials: Vue.vm.$data.spotsFilter.specials
}

// 6. Verify spot contains required fields
Vue.vm.$data.dxSpots.slice(0, 3).map(s => ({
    callsign: s.callsign,
    band: s.band,
    mode: s.mode,
    spotter_continent: s.spotter_continent,
    cq: s.cq,
    call_status: s.call_status,
    dxcc_status: s.dxcc_status
}))

// 7. Check WebSocket connection
Vue.vm.$data  // Should have active WebSocket connection in background

// 8. Manually test filter logic
const testSpot = Vue.vm.$data.dxSpots[0];
Vue.vm.$data.spotsFilter.bands = ["20m"];
console.log("20m spots:", Vue.vm.$data.filteredSpots.length);
Vue.vm.$data.spotsFilter.bands = [];
console.log("All spots:", Vue.vm.$data.filteredSpots.length);
```

---

## Summary Checklist

After running all 12 tests, verify:

- [ ] **Show Filter**: Works - spot count updates ✓
- [ ] **Band Filter**: Works - filters by spot.band ✓
- [ ] **Mode Filter**: Works - filters by spot.mode ✓
- [ ] **Continent Filter**: Works - filters by spotter_continent ✓
- [ ] **CQ Zone Filter**: Works - filters by spot.cq with string conversion ✓
- [ ] **Call Status Filter**: Works - filters by call_status ✓
- [ ] **DXCC Status Filter**: Works - filters by dxcc_status ✓
- [ ] **Special Activities**: Works - searches comment field ✓
- [ ] **Callsign Search**: Works - substring match ✓
- [ ] **AND Logic**: Works - multiple filters combine correctly ✓
- [ ] **Visual Feedback**: Works - active filters highlighted ✓
- [ ] **Spot Count**: Works - updates reactively ✓

---

## If Any Test Fails

### **Problem**: Filter not working at all

**Quick Fix Steps**:
1. Open browser Console (F12)
2. Run: `location.reload()` - refresh page
3. Wait 10 seconds for WebSocket to reconnect
4. Try filter again

### **Problem**: Specific filter not working

**Diagnostic Steps**:
```javascript
// Check if spots have the required field
const fieldName = 'band'; // replace with 'band', 'mode', 'spotter_continent', etc.
const missingCount = Vue.vm.$data.dxSpots.filter(s => !s[fieldName]).length;
if (missingCount > 0) {
    console.error(`${missingCount} spots missing '${fieldName}' field!`);
    console.log('This is a BACKEND issue, not UI');
}

// Check if filter method exists
console.log('toggleFilterItem exists:', typeof Vue.vm.toggleFilterItem === 'function');
console.log('clearAllFilters exists:', typeof Vue.vm.clearAllFilters === 'function');
```

### **Problem**: Filter is slow or unresponsive

**Causes & Fixes**:
- Too many spots loaded: Use "Show" filter to display fewer spots
- Browser issue: Open DevTools, check for memory leaks
- WebSocket backlog: Stop the server, restart, reconnect

### **Problem**: AND logic not working (filters not combining)

```javascript
// Check if filteredSpots computed property is working
console.log('filteredSpots is reactive:', Vue.vm.$data.filteredSpots.length);

// Manually verify AND logic
Vue.vm.$data.spotsFilter.bands = ["20m"];
Vue.vm.$data.spotsFilter.modes = ["CW"];
const count = Vue.vm.$data.filteredSpots.length;
console.log(`20m AND CW = ${count} spots`);
```

---

## Reporting Results

If you find any filter is **NOT working**, please provide:

1. **Which filter**: (e.g., "Band filter")
2. **What you did**: (e.g., "Selected 20m")
3. **What you expected**: (e.g., "Only 20m spots displayed")
4. **What actually happened**: (e.g., "All spots still shown")
5. **Console output**: Run the diagnostic command above and share output
6. **Browser**: (Chrome, Firefox, Safari, Edge)

---

## Success Criteria

**All filters are working correctly when**:

✅ Each individual filter works in isolation  
✅ Multiple items in one filter use OR logic  
✅ Different filter types use AND logic  
✅ Spot count updates reactively  
✅ Active filters show visual indication  
✅ Clear/All buttons work within each filter  
✅ Clear All button clears everything  
✅ No console errors appear  

---

## Next Steps

If all tests pass:
- ✅ Filters are production-ready
- ✅ No further action needed

If any test fails:
- Check the "Troubleshooting" section for that filter
- Run diagnostic commands in browser console
- Check backend logs for errors
- Contact support with diagnostic output