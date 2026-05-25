# Wavelog→DuckDB Sync Fix - Multiple Issues Resolved

## 🐛 CRITICAL BUG FIX: Schema Issue (2025-01-05)

**Error Symptoms:**
```
❌ Error upserting record: Constraint Error: NOT NULL constraint failed: qso_records.id
```

**Root Cause:** The `qso_records` table was created without a DEFAULT value for the `id` column. The sequence `seq_qso_id` was created but never connected to the table, causing INSERT statements to fail.

**Fix Applied:** Changed line 68 in `wavelog_duckdb_sync.py`:
```sql
-- BEFORE (broken):
id INTEGER PRIMARY KEY,

-- AFTER (fixed):
id INTEGER PRIMARY KEY DEFAULT nextval('seq_qso_id'),
```

**Action Required:** The existing database must be deleted and recreated with the fixed schema.

### Quick Fix for Schema Issue
Run this script (backend must be stopped):
```powershell
.\fix_duckdb_schema.ps1
```

Or manually delete the database:
```powershell
Remove-Item "c:\Projects\om0rx-radio-control\data\qso_log.duckdb" -Force
```

Then restart the backend to recreate with the correct schema.

---

## Original Problem: Initial Sync Hanging
The initial sync was hanging indefinitely because it tried to fetch ALL QSOs from Wavelog in a single query. For databases with thousands of QSOs, this caused:
- Memory exhaustion
- Query timeouts
- The sync to appear "stuck" at 0 records

## Solution
Implemented **batched sync** that:
1. Fetches records in chunks of 1000 at a time
2. Processes and commits each batch separately
3. Shows progress updates in the logs
4. Handles large databases efficiently

## What Was Changed

### 1. `wavelog_duckdb_sync.py`
- Modified `_fetch_changed_records()` to support LIMIT/OFFSET pagination
- Rewrote `sync()` method to use batched fetching for initial sync
- Added `reset_sync()` method to force a fresh sync if needed
- Added better progress logging

### 2. `backend/api/wavelog_log.py`
- Added `/api/wavelog-log/reset-sync` endpoint to reset sync via API

### 3. New Script: `reset_wavelog_sync.py`
- Command-line tool to reset the sync
- Options to keep or clear existing data

## How to Fix the Stuck Sync

### Option 1: Using the Reset Script (Recommended)
```powershell
python reset_wavelog_sync.py
```

Follow the prompts:
- Option 1: Reset metadata only (keeps existing data)
- Option 2: Reset metadata AND clear all data (fresh start)

### Option 2: Using the API Endpoint
```powershell
# Reset without clearing data
Invoke-RestMethod -Uri "http://localhost:8000/api/wavelog-log/reset-sync" -Method POST

# Reset and clear all data
Invoke-RestMethod -Uri "http://localhost:8000/api/wavelog-log/reset-sync?clear_data=true" -Method POST
```

### Option 3: Manual Database Reset
```powershell
# Delete the DuckDB database file to start fresh
Remove-Item "c:\Projects\om0rx-radio-control\data\qso_log.duckdb" -Force
```

## Restart the Backend

After resetting, restart the backend to trigger a fresh sync:

```powershell
# Stop the current backend (Ctrl+C in the terminal running it)

# Start it again
.\start_webapp.ps1
```

## Expected Behavior After Fix

1. **Initial Sync**: 
   - Processes 1000 records per batch
   - Shows progress in logs: `"✅ Batch 1: +1000 new | Total: 1000 QSOs synced"`
   - Continues until all records are synced
   - Takes minutes instead of hours

2. **Incremental Sync**:
   - Runs every 60 seconds
   - Only fetches changed records (very fast)
   - Silent when no changes detected

## Monitoring Progress

Watch the logs for progress updates:

```powershell
Get-Content "c:\Projects\om0rx-radio-control\logs\flex_debug.log" -Tail 50 -Wait
```

Look for these messages:
```
🔄 Starting INITIAL sync (batched: 1000 records per batch)
📥 Fetched 1000 records from Wavelog database (offset: 0)
✅ Batch 1: +1000 new, ~0 updated | Total: 1000 QSOs synced
📥 Fetched 1000 records from Wavelog database (offset: 1000)
✅ Batch 2: +1000 new, ~0 updated | Total: 2000 QSOs synced
...
✅ Wavelog sync complete: 5432 added, 0 updated, total: 5432
```

## Configuration

You can adjust the batch size in `config.py`:

```python
# Batch size for initial sync (default: 1000)
WAVELOG_SYNC_BATCH_SIZE = 1000

# Sync interval in seconds (default: 60)
WAVELOG_SYNC_INTERVAL = 60
```

## Troubleshooting

### Sync still appears stuck
1. Check the logs for errors
2. Verify database credentials in `config.py`
3. Test database connection manually:
   ```python
   python -c "from wavelog_duckdb_sync import get_wavelog_sync; s = get_wavelog_sync(); print(s.get_sync_status())"
   ```

### "No records fetched" message
- Check that `WAVELOG_STATION_ID` in `config.py` matches your Wavelog station ID
- Verify you have QSOs in Wavelog for that station

### Slow sync performance
- Increase batch size: `WAVELOG_SYNC_BATCH_SIZE = 2000`
- Check network latency to Wavelog database
- Verify database indexes are present

## Technical Details

### Batch Processing Flow
```
Initial Sync:
  Loop:
    1. Fetch batch of 1000 records (LIMIT 1000 OFFSET n)
    2. Process each record (convert + upsert)
    3. Commit batch to DuckDB
    4. Log progress
    5. If batch < 1000, done; else increment offset and repeat

Incremental Sync:
  1. Fetch only records with last_modified > last_sync_timestamp
  2. Process and commit (single batch, usually very small)
  3. Update metadata
```

### Database Schema
- `qso_records`: Main QSO data table
- `sync_metadata`: Tracks last sync state (timestamp, last ID, counts)

### Performance
- **Before**: Hours or hanging for 10k+ QSOs
- **After**: ~2-5 minutes for 10k QSOs (depends on network/DB speed)

## Support

If issues persist:
1. Check logs: `c:\Projects\om0rx-radio-control\logs\flex_debug.log`
2. Verify config: `c:\Projects\om0rx-radio-control\config.py`
3. Test connection: Run `reset_wavelog_sync.py` to see detailed status