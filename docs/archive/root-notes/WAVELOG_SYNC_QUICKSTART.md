# Wavelog→DuckDB Sync - Quick Start Guide

## What Changed?

Your DuckDB database (`/data/qso_log.duckdb`) now syncs from **Wavelog database** instead of from the local ADIF file.

### Important Notes
- ✅ QSOs still save to local ADIF file (`/logs/qso_log.adif`)
- ✅ QSOs still sent to Wavelog via API
- ✅ Everything else works exactly the same
- 🆕 DuckDB is now a local copy of your Wavelog contacts (failover)

## Testing Steps

### 1. Start the Application
```powershell
.\start_webapp.ps1
```

### 2. Check Startup Logs
Look for these messages:
```
✅ Wavelog→DuckDB sync initialized
✅ Wavelog→DuckDB periodic sync task started (interval: 60s)
⏳ Running initial Wavelog→DuckDB sync in background...
✅ Wavelog sync: +100 new, ~0 updated, total: 100
```

The first sync will fetch all your existing Wavelog contacts.

### 3. Verify Data in DuckDB

Open PowerShell and test:

```powershell
python -c "import duckdb; conn = duckdb.connect('data/qso_log.duckdb'); print('Total QSOs:', conn.execute('SELECT COUNT(*) FROM qso_records').fetchone()[0]); print('Latest 3:', conn.execute('SELECT call, mode, band, time_on FROM qso_records ORDER BY time_on DESC LIMIT 3').fetchall()); conn.close()"
```

Expected output:
```
Total QSOs: 190
Latest 3: [('MM0ALM', 'SSB', '160m', datetime...), ...]
```

### 4. Test Incremental Sync

**Add a new QSO in Wavelog:**
1. Log a contact directly in Wavelog (via web interface or API)
2. Wait 60 seconds (or your configured interval)
3. Check logs for: `✅ Wavelog sync: +1 new, ~0 updated, total: 191`

**Or trigger manual sync:**
```powershell
python -c "from wavelog_duckdb_sync import get_wavelog_sync; result = get_wavelog_sync().sync(); print(result)"
```

### 5. Test Update Detection

**Edit an existing QSO in Wavelog:**
1. Modify a contact in Wavelog (change name, grid, etc.)
2. Wait for next sync
3. Check logs for: `✅ Wavelog sync: +0 new, ~1 updated, total: 191`

### 6. Verify Failover

**Simulate Wavelog being offline:**
```powershell
# Query your local DuckDB even when Wavelog is unreachable
python -c "import duckdb; conn = duckdb.connect('data/qso_log.duckdb'); print(conn.execute('SELECT COUNT(*) FROM qso_records WHERE call LIKE \"9U%\"').fetchone()); conn.close()"
```

This proves your local DuckDB works independently!

## Configuration

### Change Sync Interval

Edit `config.py`:
```python
WAVELOG_SYNC_INTERVAL = 120  # Change to 2 minutes
```

Then restart the application.

### View Sync Status

```python
from wavelog_duckdb_sync import get_wavelog_sync

sync = get_wavelog_sync()
status = sync.get_sync_status()
print(f"Total records: {status['total_records']}")
print(f"Last sync: {status['last_sync']}")
print(f"Added last sync: {status['last_sync_added']}")
print(f"Updated last sync: {status['last_sync_updated']}")
```

## Monitoring

### Check Sync is Running
```powershell
# Windows: Look for running process
Get-Process python | Where-Object {$_.MainWindowTitle -like "*uvicorn*"}
```

### Watch Logs in Real-Time
```powershell
Get-Content logs\flex_debug.log -Wait -Tail 20 | Select-String "Wavelog sync"
```

### Check Sync Metadata
```powershell
python -c "import duckdb; conn = duckdb.connect('data/qso_log.duckdb'); print(conn.execute('SELECT * FROM sync_metadata').fetchall()); conn.close()"
```

Expected output:
```
[(1, datetime(...), datetime(...), 79645, 190, 0, 1)]
```

Fields: `id, last_sync_timestamp, last_wavelog_modified, last_wavelog_id, total_records_synced, last_sync_added, last_sync_updated`

## Common Issues

### ❌ "Failed to connect to Wavelog database"

**Solution:**
- Verify network connection to `wavelog.online:3306`
- Check firewall settings
- Verify credentials in `config.py`

```powershell
Test-NetConnection -ComputerName wavelog.online -Port 3306
```

### ❌ "No changes detected in Wavelog"

**This is normal!** It means:
- All Wavelog records are already in DuckDB
- No new/modified contacts since last sync
- Sync is working perfectly, just nothing to do

### ❌ Duplicate Records

Should not happen due to unique constraint on `wavelog_id`. If it does:

```powershell
# Clear DuckDB and re-sync
Remove-Item data\qso_log.duckdb
# Restart application - will perform full initial sync
```

### ❌ Slow Sync

If syncing 1000+ records:
- Initial sync may take 1-2 minutes (normal)
- Subsequent syncs are fast (only changes)
- Consider increasing `WAVELOG_SYNC_INTERVAL` to reduce frequency

## Performance Tips

### Optimize for Large Logs
```python
# In config.py
WAVELOG_SYNC_INTERVAL = 300  # 5 minutes for 10,000+ QSOs
```

### Monitor Database Size
```powershell
Get-Item data\qso_log.duckdb | Select-Object Name, Length, LastWriteTime
```

### Vacuum DuckDB (if needed)
```powershell
python -c "import duckdb; conn = duckdb.connect('data/qso_log.duckdb'); conn.execute('VACUUM'); conn.close()"
```

## What to Expect

### Initial Sync
- Duration: ~5-30 seconds depending on QSO count
- Log message: `✅ Wavelog sync: +N new, ~0 updated`
- All your Wavelog contacts copied to DuckDB

### Regular Syncs (every 60s)
- Usually: `No changes detected in Wavelog` (silent)
- If new QSO: `✅ Wavelog sync: +1 new, ~0 updated`
- If edited QSO: `✅ Wavelog sync: +0 new, ~1 updated`

### During Active Operating
- QSO logged → Saves to ADIF → Sends to Wavelog → Next sync picks it up
- Typical delay: < 60 seconds for QSO to appear in DuckDB
- No action needed - fully automatic!

## Troubleshooting Commands

### Check DuckDB Schema
```powershell
python -c "import duckdb; conn = duckdb.connect('data/qso_log.duckdb'); print(conn.execute('DESCRIBE qso_records').fetchall()); conn.close()"
```

### Check Latest Records
```powershell
python -c "import duckdb; conn = duckdb.connect('data/qso_log.duckdb'); print(conn.execute('SELECT wavelog_id, call, time_on, last_modified FROM qso_records ORDER BY last_modified DESC LIMIT 5').fetchall()); conn.close()"
```

### Force Full Re-sync
```powershell
# Option 1: Delete DuckDB and restart (cleanest)
Remove-Item data\qso_log.duckdb
.\start_webapp.ps1

# Option 2: Clear sync metadata to trigger full sync
python -c "import duckdb; conn = duckdb.connect('data/qso_log.duckdb'); conn.execute('DELETE FROM sync_metadata'); conn.commit(); conn.close()"
# Then restart application
```

### Test Wavelog Connection
```powershell
python -c "import pymysql; import config; conn = pymysql.connect(host=config.DB_HOST, port=config.DB_PORT, user=config.DB_USER, password=<qrz_password> database=config.DB_NAME); print('✅ Connected to Wavelog database'); cursor = conn.cursor(); cursor.execute('SELECT COUNT(*) FROM TABLE_HRD_CONTACTS_V01 WHERE station_id = %s', (config.WAVELOG_STATION_ID,)); print('Total QSOs in Wavelog:', cursor.fetchone()[0]); conn.close()"
```

## Success Indicators

✅ **Working Correctly:**
- Log shows: `✅ Wavelog→DuckDB sync initialized`
- Initial sync completes: `✅ Wavelog sync: +N new...`
- DuckDB file exists: `data/qso_log.duckdb`
- Record count matches Wavelog
- New QSOs appear after sync interval
- No error messages in logs

❌ **Something Wrong:**
- Repeated connection errors
- Sync never completes
- DuckDB record count = 0
- Error messages in logs
- Check firewall, credentials, network

## Next Steps

Once sync is working:
1. ✅ Monitor for 24 hours to ensure stability
2. ✅ Log a few QSOs and verify they sync
3. ✅ Test the log viewer in the UI
4. ✅ Enjoy your local Wavelog failover! 🎉

## Need Help?

Check:
1. `logs/flex_debug.log` - Main application log
2. Console output - Real-time messages
3. This guide - Common solutions above

## Summary

**Before:** ADIF file → DuckDB (30s sync)  
**After:** Wavelog DB → DuckDB (60s smart sync)  

**Result:** Local failover copy of all Wavelog contacts with automatic updates! 🚀