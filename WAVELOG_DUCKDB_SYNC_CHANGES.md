# Wavelog→DuckDB Sync Implementation

## Overview
Successfully replaced the ADIF→DuckDB sync with a new Wavelog DB→DuckDB sync system. The local DuckDB database now serves as a failover/local cache of Wavelog contacts, syncing directly from the Wavelog MySQL database instead of from the local ADIF file.

## Architecture Changes

### Before
```
QSO Logged → Local ADIF File → DuckDB Database
                ↓
         Wavelog (via API)
```

### After
```
QSO Logged → Local ADIF File (still saved)
                ↓
         Wavelog (via API)
                ↓
         Wavelog MySQL DB → DuckDB Database (local failover copy)
```

## What Was Changed

### 1. New Module: `wavelog_duckdb_sync.py`
**Location:** `/wavelog_duckdb_sync.py`

**Features:**
- Direct connection to Wavelog MySQL database
- Smart sync using `last_modified` and `creation_date` timestamps
- Tracks changes efficiently - only syncs new/modified records
- Upsert logic (insert new records, update existing ones)
- Uses `COL_PRIMARY_KEY` from Wavelog as unique identifier
- Maintains complete QSO record with all ADIF fields
- Configurable sync interval

**Key Functions:**
- `WavelogDuckDBSync` class - main sync manager
- `sync()` - performs smart incremental sync
- `get_sync_status()` - returns current sync statistics
- `periodic_wavelog_sync()` - async task for continuous syncing

### 2. Configuration Update: `config.py`
**Added:**
```python
# Wavelog to DuckDB sync interval (seconds)
WAVELOG_SYNC_INTERVAL = 60
```

**Default:** 60 seconds (configurable)

### 3. Backend Changes: `backend/main.py`
**Changed:**
- Import: `from adif_sync` → `from wavelog_duckdb_sync`
- Variable: `adif_sync_manager` → `wavelog_sync_manager`
- Function: `init_adif_sync_manager()` → `init_wavelog_sync_manager()`
- Initialization call updated in `initialize_services()`

### 4. Core Module Updates: `backend/core/__init__.py`
**Changed:**
- Import: `from adif_sync` → `from wavelog_duckdb_sync`
- Global variable: `adif_sync_manager` → `wavelog_sync_manager`
- Function: `periodic_adif_sync()` → `periodic_wavelog_sync()`
- Updated sync status fields to reflect new/updated records
- Removed ADIF file tracking from sync status

### 5. API Updates: `backend/api/server_control.py`
**Changed:**
- Comments updated to reflect Wavelog→DuckDB sync
- Task cancellation logic remains the same (still uses `adif_sync_task` variable name)

## DuckDB Schema Updates

The DuckDB schema has been enhanced to store Wavelog-specific data:

**New Fields:**
- `wavelog_id` - Unique ID from Wavelog (COL_PRIMARY_KEY)
- `submode` - ADIF submode
- `state` - State/province
- `county` - County
- `sig` - Special interest group
- `sig_info` - SIG additional info
- `creation_date` - Record creation timestamp from Wavelog
- `last_modified` - Record modification timestamp from Wavelog
- `time_off` - QSO end time

**Indexes:**
- Primary key on `id`
- Unique index on `wavelog_id`
- Indexes on: `call`, `band`, `mode`, `qso_date`, `time_on`, `last_modified`, `frequency`
- Composite index on `(call, band, mode)`

## Sync Metadata Tracking

The sync system tracks:
- `last_sync_timestamp` - When last sync occurred
- `last_wavelog_modified` - Latest `last_modified` timestamp processed
- `last_wavelog_id` - Latest `COL_PRIMARY_KEY` processed
- `total_records_synced` - Total records in DuckDB
- `last_sync_added` - Records added in last sync
- `last_sync_updated` - Records updated in last sync

## Smart Sync Algorithm

1. **First Run (Initial Sync)**
   - Fetches all records from Wavelog for station
   - Inserts into DuckDB
   - Records latest `last_modified` and `COL_PRIMARY_KEY`

2. **Subsequent Runs (Incremental Sync)**
   - Queries Wavelog for records where:
     - `last_modified > last_sync_timestamp` OR
     - `last_modified = last_sync_timestamp AND COL_PRIMARY_KEY > last_synced_id`
   - For each record:
     - Check if `wavelog_id` exists in DuckDB
     - If exists → UPDATE
     - If not exists → INSERT
   - Update sync metadata

3. **Efficiency**
   - Only fetches changed records (not full table scan)
   - Uses indexed fields for fast queries
   - Batch processing for better performance

## What Remains Unchanged

✅ **QSO Logging Flow:**
- QSOs still saved to local ADIF file (`/logs/qso_log.adif`)
- QSOs still sent to Wavelog via API
- WSJTX integration unchanged

✅ **Local ADIF File:**
- Still maintained for backup purposes
- Can be used for ADIF export
- Not affected by sync changes

✅ **Wavelog API Integration:**
- All API calls remain functional
- QSO submission unchanged
- Lookup functionality unchanged

✅ **Frontend:**
- No changes required
- Log viewer still works
- All UI functionality intact

## Benefits

1. **Failover Capability**
   - Local DuckDB has complete copy of Wavelog contacts
   - Works even when Wavelog is unreachable
   - No internet dependency for local queries

2. **Performance**
   - Fast local queries on DuckDB
   - No API rate limits for local operations
   - Indexed for optimal search performance

3. **Reliability**
   - Smart sync ensures data consistency
   - Handles updates to existing contacts
   - Tracks sync status for monitoring

4. **Flexibility**
   - Configurable sync interval
   - Can adjust based on needs
   - Independent from ADIF file

## Configuration

### Sync Interval
Edit `config.py`:
```python
WAVELOG_SYNC_INTERVAL = 60  # seconds
```

### Wavelog Connection
Already configured in `config.py`:
```python
DB_HOST = "wavelog.online"
DB_PORT = 3306
DB_NAME = "om0rx"
DB_USER = "<db_user>"
DB_PASS = "<db_password>"
WAVELOG_STATION_ID = "1"
```

## Monitoring

### Sync Status
The sync status can be monitored via:
```python
from wavelog_duckdb_sync import get_wavelog_sync

sync = get_wavelog_sync()
status = sync.get_sync_status()
```

**Returns:**
```python
{
    'initialized': True,
    'last_sync': datetime,
    'last_wavelog_modified': datetime,
    'last_wavelog_id': int,
    'total_records': int,
    'last_sync_added': int,
    'last_sync_updated': int
}
```

### Logs
Look for these log messages:
- `✅ Wavelog→DuckDB Sync initialized`
- `✅ Wavelog sync: +X new, ~Y updated, total: Z`
- `❌ Wavelog sync failed: ...` (on errors)

## Testing

### Verify Sync is Running
1. Start the application
2. Check logs for: `✅ Wavelog→DuckDB periodic sync task started`
3. Initial sync should run immediately
4. Subsequent syncs every 60 seconds (or configured interval)

### Verify Data
```python
import duckdb
conn = duckdb.connect('data/qso_log.duckdb')
print(conn.execute("SELECT COUNT(*) FROM qso_records").fetchone())
print(conn.execute("SELECT * FROM qso_records ORDER BY time_on DESC LIMIT 5").fetchall())
print(conn.execute("SELECT * FROM sync_metadata WHERE id = 1").fetchone())
conn.close()
```

### Force Manual Sync
```python
from wavelog_duckdb_sync import get_wavelog_sync

sync = get_wavelog_sync()
result = sync.sync()
print(result)
```

## Troubleshooting

### Sync Not Working
- Check Wavelog database credentials in `config.py`
- Verify network connectivity to `wavelog.online:3306`
- Check logs for error messages
- Verify `WAVELOG_STATION_ID` is correct

### Duplicate Records
- Should not happen due to `wavelog_id UNIQUE` constraint
- If occurs, check sync metadata integrity
- May need to clear DuckDB and re-sync

### Performance Issues
- Increase `WAVELOG_SYNC_INTERVAL` if too frequent
- Check DuckDB indexes are created
- Monitor Wavelog database load

## Migration Notes

### From Old System
The system will automatically:
1. Create new DuckDB schema on first run
2. Perform initial sync from Wavelog
3. Populate all historical records

### Data Preservation
- Old DuckDB data (if any) will be preserved
- New records will be added based on `wavelog_id`
- Duplicates prevented by unique constraint

### Rollback
If needed to revert to old ADIF sync:
1. Restore imports in `backend/main.py` and `backend/core/__init__.py`
2. Change `wavelog_duckdb_sync` back to `adif_sync`
3. Update function names back to `init_adif_sync`, `periodic_adif_sync`
4. Restart application

## Files Modified

1. **NEW:** `wavelog_duckdb_sync.py` - Complete new sync module
2. **MODIFIED:** `config.py` - Added `WAVELOG_SYNC_INTERVAL`
3. **MODIFIED:** `backend/main.py` - Updated imports and initialization
4. **MODIFIED:** `backend/core/__init__.py` - Updated imports, globals, and sync function
5. **MODIFIED:** `backend/api/server_control.py` - Updated comments

## Files NOT Modified

- `adif_sync.py` - Still exists but not used
- `adif_handler.py` - Still used for ADIF file operations
- `wavelog_api.py` - Still used for API operations
- `services/qso_logging.py` - Unchanged
- `services/wavelog_log.py` - Unchanged
- All frontend files - Unchanged

## Completion Status

✅ Wavelog→DuckDB sync module created  
✅ Configuration added  
✅ Backend initialization updated  
✅ Core module updated  
✅ API comments updated  
✅ Smart sync with change tracking implemented  
✅ DuckDB schema enhanced  
✅ Failover capability established  
✅ Documentation created  

**Status:** Ready for testing! 🚀