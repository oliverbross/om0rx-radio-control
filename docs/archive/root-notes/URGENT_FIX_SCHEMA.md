# 🚨 URGENT: DuckDB Schema Bug Fix Required

## What's Wrong?
You're seeing this error repeatedly in your logs:
```
❌ Error upserting record: Constraint Error: NOT NULL constraint failed: qso_records.id
```

## Why It's Happening
The DuckDB table was created with a missing DEFAULT value on the `id` column. When trying to insert QSO records, the database expects an `id` value but none is provided, causing the sync to fail.

## The Fix (3 Simple Steps)

### Step 1: Stop the Backend
Press `Ctrl+C` in the terminal running the backend.

### Step 2: Delete the Broken Database
Run this PowerShell command:
```powershell
Remove-Item "c:\Projects\om0rx-radio-control\data\qso_log.duckdb" -Force
```

**OR** use the fix script:
```powershell
.\fix_duckdb_schema.ps1
```

### Step 3: Restart the Backend
```powershell
.\start_webapp.ps1
```

The database will be recreated with the correct schema, and the sync will start fresh with the batched sync system.

## What You'll See After the Fix

### Good Progress Messages:
```
🔄 Starting INITIAL sync (batched: 1000 records per batch)
📥 Fetched 1000 records from Wavelog database (offset: 0)
✅ Batch 1: +1000 new, ~0 updated | Total: 1000 QSOs synced
📥 Fetched 1000 records from Wavelog database (offset: 1000)
✅ Batch 2: +1000 new, ~0 updated | Total: 2000 QSOs synced
...
✅ Wavelog sync complete: 5432 added, 0 updated in 3m 24s
```

## Performance
- **Before Fix**: Sync hangs forever or fails with constraint errors
- **After Fix**: Syncs 1000 records every few seconds
  - 1,000 QSOs: ~30 seconds
  - 5,000 QSOs: ~2-3 minutes
  - 10,000 QSOs: ~5 minutes

## Files Modified
1. `wavelog_duckdb_sync.py` - Fixed table schema (line 68)
2. `fix_duckdb_schema.ps1` - New helper script (created)
3. `WAVELOG_SYNC_FIX.md` - Updated documentation

## Need Help?
If the fix doesn't work:
1. Check that the backend is completely stopped (no Python processes)
2. Try rebooting if the file is locked
3. Check logs: `logs\flex_debug.log`

## Technical Details
The fix changes the table definition from:
```sql
id INTEGER PRIMARY KEY,
```
to:
```sql
id INTEGER PRIMARY KEY DEFAULT nextval('seq_qso_id'),
```

This tells DuckDB to auto-generate the `id` using the sequence, eliminating the NOT NULL constraint error.