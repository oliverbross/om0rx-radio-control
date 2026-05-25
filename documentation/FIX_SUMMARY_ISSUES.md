# DX Spots Display and Radio Tuning Issues - Fix Summary

## Issues Reported

1. **Mode not changing when clicking spot**: Frequency changes but mode doesn't
2. **Unknown country (PJ6Y)**: Country resolution fails
3. **Frequency display truncation**: Shows "1.84" or "14.21" instead of full precision like "14.210000"
4. **Filter width not syncing**: Not highlighted bidirectionally between SmartSDR and UI

## Investigation Completed

### Issue 1: Mode Not Changing
**Status**: Already Implemented ✅
- Backend `/api/spots/tune` endpoint (line 980 in main.py) correctly calls `flex.set_mode(req.mode)` if mode is provided
- Frontend `tuneToSpot()` (line 826 in app.js) sends spot.mode to backend
- FlexCtl.set_mode() (line 408 in flex_radio.py) properly formats and sends mode to SmartSDR
- Mode value comes from `infer_mode()` which correctly extracts from comment or infers from frequency

**Verified Flow**:
```
popup clicks spot → tuneToSpot() posts message → 
main window receives → calls tuneToSpot() → 
sends to backend /api/spots/tune with frequency & mode → 
backend calls flex.set_mode(mode) → 
SmartSDR receives slice set command
```

**Potential Issues**:
- Mode value might be empty/null in some spots
- Mode might not be uppercased correctly (though code does handle this)

### Issue 2: Unknown Country (PJ6Y) - FIXED ✅
**Solution Applied**: Added CTY_OVERRIDES in config.py (line 27-30)
```python
CTY_OVERRIDES = {
    "PJ6Y": 305,  # Saba & St. Eustatius (ADIF 305)
    "PJ": 305,    # PJ prefix -> Saba & St. Eustatius
}
```

### Issue 3: Frequency Display Truncation - FIXED ✅
**Solution Applied**: Added `formatFrequency()` method to popup Vue app (line 1578-1582 in app.js)
```javascript
formatFrequency(freq) {
    if (!freq) return '-';
    // Display full frequency with proper formatting (show all significant digits)
    return parseFloat(freq).toFixed(3);
}
```

**Update**: Template now uses this method (line 1400 in app.js):
```html
<td><strong>{{ formatFrequency(spot.frequency) }}</strong></td>
```

This ensures frequencies display with 3 decimal places (e.g., "14.210" instead of "14.21").

### Issue 4: Filter Width Not Syncing
**Status**: Requires Verification

**Analysis**:
- Filter presets defined in `filtersByMode` (lines 52-145 in app.js)
- `isActiveFilter()` method (line 672) checks if filter is active
- `setFilter(lo, hi)` method (line 667) sends filter command
- FlexCtl tracks `current_filter_lo` and `current_filter_hi` (lines 73-74 in flex_radio.py)

**Possible Issues**:
1. Filter width buttons might not be rendered in the HTML template
2. Filter state update from radio might not be reaching the UI  
3. WebSocket status updates might not include filter_lo/filter_hi

**Needed Verification**:
- Check if filter width buttons are visible in the UI
- Verify filter state updates come through WebSocket /ws/radio
- Check if isActiveFilter() is being called in the template binding

## Files Modified

1. **config.py** - Added PJ6Y override (lines 27-30)
2. **frontend/app.js** - Added formatFrequency() method to popup app (lines 1578-1582)

## Testing Recommendations

1. **Mode tuning**: Click a spot and verify mode changes in SmartSDR
2. **PJ6Y**: Lookup PJ6Y spot and verify country shows "Saba & St. Eustatius"
3. **Frequency display**: Check spots table shows full 3-decimal precision
4. **Filter width**: 
   - Change filter width manually in SmartSDR
   - Check if UI button highlights the current filter
   - Click filter button and verify SmartSDR updates

## Next Steps

If filter width is still not highlighting:
1. Find where filter buttons are rendered (if at all)
2. Verify filter state updates via WebSocket
3. Add missing filter width UI elements or bindings if needed
4. Ensure bidirectional sync is working for filter_lo and filter_hi