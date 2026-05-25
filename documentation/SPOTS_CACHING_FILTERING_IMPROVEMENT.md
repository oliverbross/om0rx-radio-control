# DX Spots Filtering Improvement - Database-Backed Search

## Overview
**Feature**: Enhanced DX spots filtering that searches across all historical spots in the database instead of just the cached recent spots.

**Problem Addressed**: Previously, the spots display cached only the last 100 spots in memory. When users applied filters (e.g., searching for "9u" callsigns), they could only see matches within those 100 cached spots. Historical spots matching the criteria were lost once they aged out of the cache.

**Solution**: Now maintains two-tier spot access:
1. **Display**: Shows the last X spots (default 100) from cache for fast, real-time updates
2. **Filtering**: Queries the persistent DuckDB database when any filter is applied, allowing searches across ALL historical spots

## Architecture

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│ INCOMING DX SPOTS FROM CLUSTER                                      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ├─► In-Memory Cache (dxSpots array)
                           │   - Last 100 spots
                           │   - Real-time WebSocket updates
                           │   - Used for live display
                           │
                           └─► DuckDB Database (spots.duckdb)
                               - ALL spots (persistent)
                               - Indexed for fast queries
                               - Used for filtered searches

┌─────────────────────────────────────────────────────────────────────┐
│ USER APPLIES FILTERS (band, mode, callsign, etc.)                   │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ├─► No Filters Active
                           │   └─► Use cache-based filtering (fast)
                           │       Display results from memory
                           │
                           └─► Filters Active
                               └─► Query database via /api/spots/filtered-search
                                   └─► Return up to maxSpots results
                                       matching ALL criteria
```

### Database Schema

Located at: `/data/spots.duckdb`

```sql
CREATE TABLE spots (
    -- Timestamps
    received_at TIMESTAMP WITH TIME ZONE NOT NULL,
    date_utc DATE NOT NULL,
    time_utc TIME NOT NULL,
    
    -- Core spot data
    frequency_khz DOUBLE NOT NULL,
    callsign VARCHAR NOT NULL,
    spotter VARCHAR NOT NULL,
    comment VARCHAR,
    
    -- Derived fields
    band VARCHAR NOT NULL,
    mode VARCHAR NOT NULL,
    
    -- Geographic information
    country VARCHAR,
    zone_cq INTEGER,
    zone_itu INTEGER,
    continent VARCHAR,
    
    -- Special event tags
    special_tags VARCHAR,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for efficient filtering
CREATE INDEX idx_spot_band ON spots(band);
CREATE INDEX idx_spot_mode ON spots(mode);
CREATE INDEX idx_spot_callsign ON spots(callsign);
CREATE INDEX idx_spot_zone_cq ON spots(zone_cq);
CREATE INDEX idx_spot_continent ON spots(continent);
CREATE INDEX idx_spot_special_tags ON spots(special_tags);
```

## Implementation Details

### Backend Changes

#### 1. New API Endpoint: `/api/spots/filtered-search` (POST)

**Location**: `backend/api/spots.py`

**Request Model**:
```json
{
    "limit": 100,
    "callsign": "9u",
    "bands": ["20m", "40m"],
    "modes": ["SSB", "CW"],
    "zones_cq": [14, 15],
    "continents": ["EU"],
    "special_tags": ["POTA", "SOTA"]
}
```

**Response**:
```json
{
    "ok": true,
    "spots": [
        {
            "received_at": "2024-11-02T08:33:55Z",
            "frequency_khz": 24935000,
            "band": "12m",
            "mode": "SSB",
            "callsign": "9U1RX",
            "country": "BURUNDI",
            "cq": 36,
            "comment": "Strong signal",
            "special_tags": null
        },
        // ... more spots
    ],
    "count": 42
}
```

#### 2. New Method: `SpotsLogger.get_filtered_spots()`

**Location**: `spots_logger.py`

**Features**:
- Comprehensive filtering by: callsign, bands, modes, CQ zones, continents, special tags
- Case-insensitive partial callsign matching
- Special tags support comma-separated search (e.g., "POTA" in "POTA, WWFF")
- Respects the `limit` parameter to bound result set size
- Returns results ordered by most recent first

**Parameters**:
```python
def get_filtered_spots(
    limit: int = 100,
    callsign: Optional[str] = None,
    bands: Optional[List[str]] = None,
    modes: Optional[List[str]] = None,
    zones_cq: Optional[List[int]] = None,
    continents: Optional[List[str]] = None,
    special_tags_filter: Optional[List[str]] = None
) -> List[Dict]
```

### Frontend Changes

#### 1. New Data Properties (dx-spots.js)

```javascript
dxSpotsData: {
    // ... existing properties ...
    
    // Filtered search from database
    filteredSearchResults: [],      // Results from database query
    isSearchingSpots: false,        // Search in progress indicator
    lastSearchFilter: null,         // Last filter criteria (for change detection)
}
```

#### 2. New Methods (dx-spots.js)

##### `performFilteredSearch()`
- Triggered when any filter changes
- Builds filter criteria from `spotsFilter` object
- Calls `/api/spots/filtered-search` endpoint
- Updates `filteredSearchResults` with response
- Includes debounce to avoid rapid consecutive calls

##### `hasActiveFilters()`
- Helper to check if any filter is currently active
- Returns boolean indicating whether to use database search

#### 3. Updated Computed Property: `filteredSpots()` (dx-spots.js)

**Logic**:
```
if (filters active AND we have database results) {
    use database results
    apply local-only filters (DXCC status, worked b4)
    return limited by maxSpots
} else {
    use cache-based filtering (original logic)
}
```

**Filter Application**:
- **Database-applied filters** (efficient at data source):
  - Callsign (partial match)
  - Band
  - Mode
  - CQ Zone
  - Continent
  - Special tags

- **Local-applied filters** (applied to results):
  - DXCC Status (requires real-time classification)
  - Worked B4 (requires local QSO lookup)

#### 4. New Watchers (app-main.js)

##### `spotsFilter` Watcher
```javascript
spotsFilter: {
    handler(newFilter) {
        // Debounced search trigger on filter change
    },
    deep: true  // Watch nested filter properties
}
```

##### `maxSpots` Watcher
```javascript
maxSpots() {
    // Refetch results if filters active and limit changed
}
```

## Usage

### For Users

1. **Default Behavior** (no filters):
   - Display shows the last 100 spots from cache
   - Updates in real-time as new spots arrive
   - Fast and responsive

2. **With Filters Applied** (any filter active):
   - Search triggers automatically when filter changes
   - Results queried from full spot history in database
   - Limited to current "Show" setting (10, 25, 50, 100, 200)
   - Example: Search for "9u" to find ALL 9U spots ever received, not just recent ones

3. **Changing Display Limit**:
   - If filters active, re-queries database with new limit
   - Updates results to match new limit

### Example Scenarios

#### Scenario 1: Search for a Specific Callsign
- User enters "N1MM" in the callsign filter
- All spots ever received from N1MM are fetched from database
- Limited to current "Show" setting
- Includes spots from hours ago, not just the cached recent ones

#### Scenario 2: Find All 40m CW Spots
- User selects "40m" in bands and "CW" in modes
- Database returns all matching historical spots
- Perfect for analyzing band conditions and modes worked

#### Scenario 3: Search for Special Event Stations
- User selects "POTA" in special activities filter
- Database returns all POTA stations ever spotted
- Allows retroactive discovery of special event activations

## Performance Considerations

### Database Indexes
The following indexes are created for efficient filtering:
- `idx_spot_band` - Band filtering
- `idx_spot_mode` - Mode filtering
- `idx_spot_callsign` - Callsign searches
- `idx_spot_zone_cq` - CQ zone filtering
- `idx_spot_continent` - Continent filtering
- `idx_spot_special_tags` - Special event tag filtering
- `idx_spot_band_mode` - Combined band+mode queries

### Query Optimization
- All filter conditions are combined with AND logic at the database level
- Indexes are used for fast lookups
- LIMIT clause stops query after finding enough results
- Results ordered by received_at DESC (most recent first)

### Cache Strategy
- Live spots still update via WebSocket using cache
- Database search doesn't impact real-time display responsiveness
- Debounce (300ms) prevents excessive queries during rapid filter changes

## Limitations & Notes

1. **Continent Filter**: Currently filters by DX station's continent (from cty.dat), not spotter's continent
2. **DXCC Status Filter**: Applied locally after database search (not in database query)
3. **Worked B4 Filter**: Requires local QSO lookup (not in database query)
4. **Maximum Results**: Limited by the `limit` parameter sent to API (typically 100-200 spots)

## Future Enhancements

1. Add DXCC classification data to spots table for faster filtering
2. Store spotter continent in database for accurate "Spotter from" filtering
3. Add worked QSO data to spots table for faster worked b4 filtering
4. Add pagination support for very large result sets
5. Add export/analysis views of historical spot data

## Testing

### Manual Testing Checklist

- [ ] No filters: Display shows last 100 cached spots
- [ ] Apply callsign filter: Database search executes, results appear
- [ ] Apply band filter: Database search filters by selected bands
- [ ] Apply mode filter: Database search filters by selected modes
- [ ] Apply CQ zone filter: Database search filters by zones
- [ ] Apply multiple filters: All conditions combined with AND
- [ ] Change maxSpots: Results refetch with new limit
- [ ] Clear filters: Goes back to cache-based display
- [ ] Worked B4 filter with database results: Local filtering applied
- [ ] Real-time spots still arrive: Cache updates independently

### Debug Console Messages

When activated, look for these log messages:
```
✅ Filtered search returned 42 spots
🔍 Searching database for spots...
📊 Using 42 spots from database search
ℹ️ No filters active, using cache
🔄 maxSpots changed to 200, refetching...
```

## Code Files Modified

1. **Backend**:
   - `spots_logger.py` - Added `get_filtered_spots()` method
   - `backend/api/spots.py` - Added `/api/spots/filtered-search` endpoint

2. **Frontend**:
   - `frontend/js/dx-spots.js` - Added filtered search methods and updated computed property
   - `frontend/js/app-main.js` - Added watchers for filter and maxSpots changes

## Files Created

- `documentation/SPOTS_CACHING_FILTERING_IMPROVEMENT.md` (this file)

---

**Last Updated**: 2024-11-02
**Status**: Implementation Complete