# DX Spots Filtering - Testing & Verification Guide

## Quick Start Testing

### 1. Browser Console Debug Mode

Open your browser's Developer Console (F12) and you'll see real-time logs like:

```
🔔 Spots filter changed, triggering search...
🔍 Searching database for spots...
✅ Filtered search returned 42 spots
📊 Using 42 spots from database search
```

### 2. Basic Test Cases

#### Test 1: No Filters (Default Behavior)
1. Open the web app
2. Check the Spots section
3. **Expected**: See last 100 spots from cache
4. **Console**: Should NOT show "Searching database" messages
5. **Verify**: Spots update in real-time as new ones arrive via WebSocket

#### Test 2: Apply Callsign Filter
1. In the search box, type a callsign prefix (e.g., "9u")
2. **Expected**: Search executes automatically
3. **Console** should show:
   ```
   🔔 Spots filter changed, triggering search...
   🔍 Searching database for spots...
   ✅ Filtered search returned X spots
   📊 Using X spots from database search
   ```
4. **Verify**: Results include ALL spots matching the criteria, not just cached ones

#### Test 3: Apply Multiple Filters
1. Select "20m" in bands filter
2. Select "CW" in modes filter  
3. Enter "N" in callsign search
4. **Expected**: Database query combines all conditions with AND logic
5. **Verify**: Results show ONLY 20m CW spots from N callsigns

#### Test 4: Change Display Limit
1. Apply some filters
2. Change "Show" dropdown from 100 to 200
3. **Expected**: Search re-executes with new limit
4. **Console** should show:
   ```
   🔄 maxSpots changed to 200, refetching...
   ```
5. **Verify**: Results update to new limit

#### Test 5: Clear Filters
1. With filters active, click "Clear Filters"
2. **Expected**: Reverts to cached display immediately
3. **Console** should show filter cleared
4. **Verify**: Back to showing last N spots

## Database Verification

### Check Database Contents

If you have DuckDB CLI available:

```bash
duckdb c:/Projects/om0rx-radio-control/data/spots.duckdb

# In DuckDB prompt:
.header on
.mode column
SELECT COUNT(*) as total_spots FROM spots;
SELECT band, COUNT(*) as count FROM spots GROUP BY band ORDER BY band;
SELECT mode, COUNT(*) as count FROM spots GROUP BY mode ORDER BY count DESC;
```

### Verify Database is Being Updated

1. Note the current spot count in console:
   ```
   Get recent spots: N spots in cache
   ```

2. Let the app run for a few minutes

3. Run the query again:
   ```
   SELECT COUNT(*) FROM spots;
   ```

4. **Verify**: Count increases as new spots are received

## API Endpoint Testing

### Test the API Directly

Using curl or Postman:

```bash
curl -X POST http://localhost:8000/api/spots/filtered-search \
  -H "Content-Type: application/json" \
  -d '{
    "limit": 50,
    "callsign": "9U",
    "bands": ["20m", "40m"],
    "modes": ["SSB"]
  }'
```

**Expected Response**:
```json
{
  "ok": true,
  "spots": [
    {
      "received_at": "2024-11-02T08:33:55Z",
      "frequency_khz": 24935000,
      "band": "20m",
      "mode": "SSB",
      "callsign": "9U1RX",
      "country": "BURUNDI",
      "cq": 36,
      "comment": "Strong signal",
      "special_tags": null
    }
  ],
  "count": 1
}
```

## Performance Testing

### Measure Response Times

1. Open DevTools Network tab (F12 → Network)
2. Apply a filter that will search the database
3. Look for POST request to `/api/spots/filtered-search`
4. **Expected**: Response time < 500ms for typical filters
5. **If slower**: Database might need optimization or spot count is very large

### Monitor Database Performance

```sql
-- Count total spots in database
SELECT COUNT(*) as total_spots FROM spots;

-- Count spots by band
SELECT band, COUNT(*) as count FROM spots GROUP BY band;

-- Check index usage
-- (Database will automatically use indexes for WHERE clauses)

-- Find slowest queries (if logging enabled)
-- Look at backend logs for any slow query warnings
```

## Common Issues & Troubleshooting

### Issue: Search Returns No Results

**Possible Causes**:
1. Database is empty (no spots received yet)
2. Filter criteria too specific (no spots match)
3. Database connection error

**Solution**:
```javascript
// In browser console, check:
console.log('Has active filters:', this.hasActiveFilters());
console.log('Search results:', this.filteredSearchResults);
console.log('Last search filter:', this.lastSearchFilter);
```

### Issue: Search Taking Too Long

**Possible Causes**:
1. Database has many spots (thousands)
2. Filter query is complex
3. Browser/server connection slow

**Solution**:
1. Reduce the "Show" limit
2. Use more specific filters
3. Check network latency in DevTools

### Issue: Spots Not Updating in Real-Time

**Possible Causes**:
1. WebSocket connection lost
2. Cluster connection problem
3. Browser tab not focused

**Solution**:
1. Check WebSocket status in Network tab
2. Check console for connection errors
3. Refocus browser tab

### Issue: Searched Results Show Different Fields

**Possible Causes**:
1. Database has different fields than cache
2. Field mapping issue between backend and frontend

**Solution**:
- Database results should have these fields:
  - `received_at`, `date_utc`, `time_utc`
  - `frequency_khz`, `band`, `mode`
  - `callsign`, `spotter`, `country`, `cq`, `zone_itu`
  - `continent`, `special_tags`, `comment`

## Backend Log Checking

### Enable Debug Logging

The backend logs filtered search requests. Check:
```
c:/Projects/om0rx-radio-control/logs/server.log
```

Look for messages like:
```
DEBUG: Filtered search request: callsign=9U, bands=['20m'], limit=100
DEBUG: ✓ Filtered query returned 42 spots with filters...
```

### Increase Log Level

In `backend/main.py` or `backend/core.py`, set:
```python
logging.basicConfig(level=logging.DEBUG)
```

## Stress Testing

### Test with Large Filter Results

1. Apply a broad filter (e.g., just "SSB" mode)
2. Check if 100+ results load without issues
3. **Expected**: UI remains responsive
4. **Verify**: No JavaScript errors in console

### Test Rapid Filter Changes

1. Apply a filter
2. Immediately change it (before first search completes)
3. Apply another filter
4. Clear filters
5. Apply new filter
6. **Expected**: Debounce prevents excessive queries
7. **Verify**: Console shows debounced timing

### Test Large Database

If database has 10,000+ spots:
1. Apply a specific filter
2. Measure response time (should still be fast due to indexes)
3. Check database CPU usage
4. **Expected**: < 1 second for filtered queries with indexes

## Verification Checklist

- [ ] No filters: Display shows cache (last 100 spots)
- [ ] Apply filter: Database search executes
- [ ] Multiple filters: All conditions combined with AND
- [ ] Change "Show" limit: Results refetch with new limit
- [ ] Clear filters: Reverts to cache display
- [ ] Real-time spots: Still arrive independently of search
- [ ] Console messages: Debug logs appear as expected
- [ ] Response time: API responds in reasonable time
- [ ] No JavaScript errors: Browser console is clean
- [ ] Database has spots: DuckDB database is being populated

## Debug Logging

### Enhanced Debugging in Browser Console

```javascript
// Check filter state
console.log('Current filters:', app.spotsFilter);

// Check search results
console.log('Search results:', app.filteredSearchResults);

// Check active filters check
console.log('Has active filters:', app.hasActiveFilters());

// Check last search criteria
console.log('Last search filter:', app.lastSearchFilter);

// Check spot counts
console.log('Cache spots:', app.dxSpots.length);
console.log('Filtered spots:', app.filteredSpots.length);

// Manually trigger search
app.performFilteredSearch();
```

## Expected Behavior Summary

| Scenario | Expected Behavior |
|----------|-------------------|
| App opens | Shows last 100 cached spots, no DB queries |
| User types in search | DB query executes, results appear |
| User selects band | DB query executes with filter |
| User changes Show limit | DB query re-executes with new limit |
| User clears filters | Reverts to cache, no DB query |
| Real-time spot arrives | Appears in cache instantly |
| Multiple filters applied | All combined with AND logic in query |
| Fast filter changes | Debounce prevents excessive queries |
| Old matches found | Results include spots aged out of cache |

## Performance Metrics

Acceptable performance thresholds:
- API response time: < 500ms
- Database query time: < 300ms (with indexes)
- Frontend search trigger: < 50ms (after debounce)
- UI responsiveness: No freezing during search
- Memory usage: < 50MB additional for search results

## Next Steps If Issues Found

1. **Check browser console** for JavaScript errors
2. **Check backend logs** for API errors
3. **Verify database connection** - can you connect with DuckDB CLI?
4. **Test API directly** with curl/Postman
5. **Check network** - is API responding?
6. **Restart backend** - clear any stale connections
7. **Clear browser cache** - reload JavaScript
8. **Review implementation** - compare with documentation

---

**Test Completed**: ___________  
**Tester**: ___________  
**Results**: ✅ All tests passed / ⚠️ Issues found (describe below)  

**Notes**:
```




```

**Status**: Ready for production ✅ / Needs fixes ⚠️