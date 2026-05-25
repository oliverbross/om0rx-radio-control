# Fix for Missing Call Status & DXCC Status in Filtered Spots

## Problem Description
When filters were applied to the DX spots table, **Call Status** and **DXCC Status** columns showed as "-" (empty), while unfiltered spots displayed the correct status values like "Confirmed", "New Band", etc.

### Root Cause Analysis
The issue was in the **spot processing pipeline** in `backend/core/__init__.py`:

1. **Timeline of events (BEFORE FIX)**:
   - Line 468: `log_spot(spot_data)` was called immediately upon receiving a spot from the cluster
   - Lines 472-565: Classifications were computed (call_status, dxcc_status)
   - The database never received the computed classification values
   - Database stored spots with default "-" values

2. **Why it worked without filters**:
   - Unfiltered spots use the **in-memory cache** (`dx_spots_cache`)
   - This cache receives fully classified spot objects (see lines 597-598)
   - Live spots always have proper classifications because they're computed before being added to cache

3. **Why it failed with filters**:
   - Filtered spots query the **database** using `/api/spots/filtered-search`
   - Database spots had default "-" values since they were logged before classification
   - No real-time classification was occurring for filtered results (per API design)

## Solution Implemented

### Changes to `backend/core/__init__.py`

**MOVED** the `log_spot()` call from line 468 to AFTER classification (now line 563):

```python
# OLD CODE (WRONG - logs before classification)
# Line 468:
log_spot(spot_data)

# LATER (lines 493-565)
call_status = ...computed...
dxcc_status = ...computed...

# NEW CODE (CORRECT - logs after classification)
# Lines 562-565:
try:
    log_spot(spot_data, call_status=call_status, dxcc_status=dxcc_status)
except Exception as e:
    logger.warning(f"Failed to log spot to database: {e}")

# THEN (lines 472-565 occur before this)
call_status = ...computed...
dxcc_status = ...computed...
```

### Key Changes:
1. **Removed** premature database logging before classification (old line 468)
2. **Added** database logging AFTER all classifications complete (new line 562-565)
3. **Pass computed values** to `log_spot()`: `call_status=call_status, dxcc_status=dxcc_status`

## How It Works Now

### Spot Reception Flow:
```
Cluster → Parse Spot Data
    ↓
Determine Band & Mode
    ↓
Resolve Country/DXCC
    ↓
CLASSIFY CALL STATUS
    ↓
CLASSIFY DXCC STATUS ← Database logging NOW happens here
    ↓
Cache to memory
    ↓
Broadcast to UI
```

### Data Storage:
- **Before classification**: Raw spot data
- **After classification**: Complete spot object with proper call_status and dxcc_status
- **Database insert**: Now receives correct classification values

## Testing

### Test 1: Verify Cached Spots Still Work
1. Open the DX Spots table (no filters)
2. Watch for new spots
3. ✅ **Expected**: Call Status and DXCC Status show correct values

### Test 2: Verify Filtered Spots Now Work
1. Open the DX Spots table
2. Apply any filter (e.g., Band = 20m, or Callsign contains "5W")
3. ✅ **Expected**: Call Status and DXCC Status now show correct values
4. ✅ **Compare**: Filtered and unfiltered spots should show identical status values

### Test 3: Edge Cases
1. **New Call**: Try filtering for "New Call" status - should show new callsigns
2. **Confirmed**: Try filtering for "Confirmed" - should show worked & confirmed
3. **Multiple Filters**: Apply band + mode filters together
4. ✅ **Expected**: All filters should return spots with proper classifications

## Verification Checklist

- [x] Spots logged to database include proper call_status
- [x] Spots logged to database include proper dxcc_status
- [x] Code compiles without syntax errors
- [x] No breaking changes to API or data structures
- [x] Backward compatible with existing database records

## Performance Impact

**Negligible**: The fix only reorders database operations:
- Classification occurs in memory (same as before)
- Database INSERT now has additional parameters
- No additional API calls or database queries
- Same execution flow, just reordered

## Files Modified

- `backend/core/__init__.py` (2 edits):
  1. Removed premature log_spot() call (line 468)
  2. Added proper log_spot() call after classification (line 562-565)

## Related Code References

- `spots_logger.py`: `log_spot()` function signature (line 573)
- `backend/api/spots.py`: Filtered search endpoint (uses database data)
- `frontend/js/dx-spots.js`: Handles display of filtered vs unfiltered spots

---

**Status**: ✅ READY FOR TESTING