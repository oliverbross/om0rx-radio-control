# Wavelog SQLite Caching System

## Overview
The application now uses a local SQLite database to cache all Wavelog QSO data. This provides:
- **Fast lookups** - Query local database instead of downloading ADIF from Wavelog every time
- **Persistent storage** - Cache survives app restarts
- **Automatic sync** - Background task updates every 5 minutes
- **Complete data** - All Wavelog fields available for application use
- **Cross-app access** - Any module can query the local database

## Architecture

### Files
- **`wavelog_db.py`** - SQLite database layer with schema and CRUD operations
- **`wavelog_sync.py`** - Background sync manager (full sync on startup, delta every 5 minutes)
- **`wavelog_api.py`** - Modified to use local database for recent QSOs queries

### Database Location
```
c:\Projects\om0rx-radio-control\data\wavelog.db
```

### Database Schema

#### QSOs Table
Stores all QSO records from Wavelog with all available fields:

```sql
CREATE TABLE qsos (
    id INTEGER PRIMARY KEY,
    callsign TEXT NOT NULL,
    qso_date TEXT,           -- YYYYMMDD format
    time_on TEXT,            -- HHMMSS format
    time_off TEXT,
    frequency REAL,          -- MHz
    mode TEXT,               -- SSB, CW, etc.
    rst_sent INTEGER,
    rst_rcvd INTEGER,
    name TEXT,               -- Operator name
    qth TEXT,                -- City/Location
    state TEXT,
    country TEXT,
    continent TEXT,
    cq_zone INTEGER,
    itu_zone INTEGER,
    gridsquare TEXT,
    pota_ref TEXT,           -- Parks on the Air
    sota_ref TEXT,           -- Summits on the Air
    iota TEXT,               -- Islands on the Air
    wwff_ref TEXT,           -- World Wide Flora & Fauna
    lotw_qsl_rcvd TEXT,      -- LoTW confirmation (Y/N)
    lotw_qsl_sent TEXT,
    email TEXT,
    ant TEXT,                -- Antenna description
    tx_pwr REAL,             -- TX Power in watts
    prop_mode TEXT,          -- Propagation mode (E, T, A, etc.)
    ant_path TEXT,           -- Antenna path (G, L, H, etc.)
    sat_name TEXT,
    sat_mode TEXT,
    freq_rx REAL,
    mode_rx TEXT,
    comments TEXT,
    qsl_rcvd TEXT,
    qsl_sent TEXT,
    qsl_via TEXT,
    us_county TEXT,
    notes TEXT,
    raw_adif TEXT,           -- Original ADIF record
    synced_at TEXT,          -- ISO timestamp of sync
    updated_at TEXT,         -- ISO timestamp of last update
    UNIQUE(callsign, qso_date, time_on)  -- Prevents duplicates
);
```

**Indexes** for fast queries:
- `idx_callsign` - Lookup by callsign
- `idx_qso_date` - Lookup by date
- `idx_synced_at` - Recent records
- `idx_callsign_date` - Combined callsign + date lookups

#### Sync Status Table
Tracks sync metadata:

```sql
CREATE TABLE sync_status (
    id INTEGER PRIMARY KEY (always 1),
    last_full_sync TEXT,      -- ISO timestamp of last full sync
    last_delta_sync TEXT,     -- ISO timestamp of last delta sync
    total_qsos INTEGER        -- Total records in database
);
```

## Sync Process

### On App Startup
1. Checks if local database exists
2. Creates schema if needed
3. Starts background sync manager
4. **Full sync** - Downloads all QSOs from Wavelog API
   - Calls `/api/get_contacts_adif` endpoint
   - Parses all ADIF records
   - Inserts/updates in local database
   - Time: ~30-60 seconds for ~20,000 QSOs

### Every 5 Minutes (Background)
1. **Delta sync** - Currently re-syncs all records (optimizable)
   - Future: Can use `fetchfromid` parameter for incremental updates
   - Handles both new QSOs and updates to existing records
   - Skipped if sync already in progress

### Conflict Resolution
- Uses `INSERT OR REPLACE` with `UNIQUE(callsign, qso_date, time_on)` constraint
- If a QSO exists with same callsign/date/time, the newer data wins
- `updated_at` timestamp tracks when each record was last synced

## Usage Examples

### Query Recent QSOs for a Callsign
```python
from wavelog_db import get_wavelog_db

db = get_wavelog_db()
qsos = db.get_qsos_by_callsign('N7BHJ', limit=5)

for qso in qsos:
    print(f"{qso['callsign']} on {qso['frequency']} MHz")
    print(f"  LoTW: {qso['lotw_qsl_rcvd']}")
```

### Query All QSOs
```python
all_qsos = db.get_all_qsos(limit=1000)
```

### Get Sync Status
```python
status = db.get_sync_status()
print(f"Total QSOs: {status['total_qsos']}")
print(f"Last sync: {status['last_delta_sync']}")
```

### Get Recently Updated QSOs
```python
# QSOs modified in last 24 hours
recent = db.get_recent_qsos(hours=24)
```

## Performance

### Initial Load
- **First sync**: ~30-60 seconds (depends on Wavelog API speed)
- **Database size**: ~20-50 MB for 20,000 QSOs with all fields
- **Startup time**: Database initialization takes < 1 second

### Ongoing Queries
- **Local database lookups**: < 10ms (depends on index)
- **By callsign**: < 5ms with indexed query
- **No API calls**: Eliminates Wavelog API latency

### Storage
- ADIF cache files: ~19.2 MB (compressed ADIF export)
- SQLite database: ~30-50 MB (with indexes)
- Total /data folder: ~50-70 MB for ~20,000 QSOs

## Configuration

All config comes from `config.py`:
```python
WAVELOG_API_URL = "https://wavelog.local/index.php"
WAVELOG_API_KEY = "<wavelog_api_key>"
WAVELOG_STATION_ID = "1"
```

## Monitoring

### Check Database Status
```bash
cd c:\Projects\om0rx-radio-control
python -c "
from wavelog_db import get_wavelog_db
db = get_wavelog_db()
status = db.get_sync_status()
print(f'Total QSOs: {status[\"total_qsos\"]}')
print(f'Last sync: {status[\"last_delta_sync\"]}')
"
```

### Check Sync Manager Logs
The sync manager logs to the main application logger:
```
INFO: 📥 Starting initial Wavelog sync...
INFO: ✅ Full sync complete: 20000 QSOs processed, total in DB: 20000
DEBUG: 🔄 Starting delta Wavelog sync...
INFO: ✅ Delta sync complete: 20000 QSOs processed, total in DB: 20000
```

## Benefits

1. **No Wavelog API Dependency** - Works offline with cached data
2. **Fast Queries** - Local database is orders of magnitude faster
3. **Complete Data** - All Wavelog fields stored locally
4. **Cross-Module Access** - Any part of app can query database
5. **Real-time Updates** - Automatic 5-minute sync for new/updated QSOs
6. **Persistent Cache** - Survives app restarts

## Migration from Old Caching

The old system used:
- In-memory ADIF cache (lost on restart)
- Disk ADIF file cache (30-minute TTL)

The new system:
- ✅ Persistent SQLite database
- ✅ Structured data (not raw ADIF)
- ✅ Indexes for fast queries
- ✅ Automatic background sync
- ✅ Available to entire application

## Future Optimizations

1. **Incremental Sync** - Use `fetchfromid` parameter for delta sync
2. **Selective Sync** - Only sync records modified in last 24 hours
3. **Compression** - Compress ADIF field in database
4. **Cleanup** - Archive old QSOs to separate table
5. **Replication** - Sync to multiple databases/instances

## Troubleshooting

### Database Locked
If you see "database is locked" errors:
1. Ensure no other processes accessing `/data/wavelog.db`
2. Restart the FastAPI backend
3. Check Windows file locks: `Get-ChildItem -LiteralPath c:\Projects\om0rx-radio-control\data -Force`

### Sync Not Running
Check logs for startup errors:
```
ERROR: ❌ Failed to start Wavelog sync
```
- Verify Wavelog API credentials in `config.py`
- Check network connectivity to Wavelog server
- Check `/logs/` folder for detailed error messages

### Stale Data
If QSOs aren't updating:
1. Check last sync timestamp: `status['last_delta_sync']`
2. If > 5 minutes old, sync may have failed
3. Check logs for sync errors
4. Manually trigger full sync: `await sync_manager.full_sync()`

## Database Backup

To backup your Wavelog cache:
```powershell
Copy-Item c:\Projects\om0rx-radio-control\data\wavelog.db -Destination c:\Projects\om0rx-radio-control\data\wavelog.db.backup
```

To restore:
```powershell
Copy-Item c:\Projects\om0rx-radio-control\data\wavelog.db.backup -Destination c:\Projects\om0rx-radio-control\data\wavelog.db -Force
```

To clear and re-sync:
```powershell
Remove-Item c:\Projects\om0rx-radio-control\data\wavelog.db
# App will rebuild on next startup
```