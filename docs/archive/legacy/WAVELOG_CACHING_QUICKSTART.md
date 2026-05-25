# Wavelog SQLite Caching - Quick Start

## What Changed?

**Before:** ADIF cache in memory (lost on restart) + 30-minute TTL
**After:** Full SQLite database in `/data/wavelog.db` + 5-minute auto-sync

## How It Works

```
┌─────────────────────────────────────────────────────┐
│         FastAPI Backend Starts                      │
│                                                     │
│  1. Creates /data/wavelog.db (if missing)          │
│  2. Starts Wavelog Sync Manager                    │
│  3. FULL SYNC downloads all QSOs from Wavelog      │
│  4. Inserts all records into SQLite                │
│  5. Then DELTA SYNC every 5 minutes                │
└─────────────────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────────────────┐
│      Recent QSOs Feature (Example)                  │
│                                                     │
│  User searches for: N7BHJ                          │
│  1. Query local database (fast!)                   │
│  2. Return last 5 QSOs with all fields            │
│  3. Display LoTW status, country, etc.            │
└─────────────────────────────────────────────────────┘
```

## New Files

1. **`wavelog_db.py`** (76 KB)
   - SQLite database schema and CRUD operations
   - Parses ADIF into structured database records
   - Provides query methods

2. **`wavelog_sync.py`** (8 KB)
   - Background sync manager
   - Runs full sync on startup
   - Runs delta sync every 5 minutes
   - Handles all Wavelog API communication

## Modified Files

1. **`wavelog_api.py`**
   - Now imports and uses local database
   - `_get_recent_qsos_internal()` queries SQLite instead of ADIF
   - Maintains backward compatibility

2. **`backend/main.py`**
   - Added `startup` event handler to initialize sync manager
   - Added `shutdown` event handler to stop sync manager
   - Sync manager runs in background

## Database Location

```
c:\Projects\om0rx-radio-control\data\wavelog.db
c:\Projects\om0rx-radio-control\data\wavelog.db.meta (sync metadata)
```

## Fields Stored

**All ADIF fields** are now in the database:
- Callsign, frequency, mode, date, time
- RST sent/received
- Name, QTH, state, country, continent
- CQ/ITU zones, gridsquare
- POTA, SOTA, IOTA, WWFF
- **LoTW confirmation** (Y/N)
- Email, antenna, TX power
- Propagation mode, satellite info
- QSL status
- And all other ADIF fields

## Sync Schedule

| Event | Timing | What |
|-------|--------|------|
| App Startup | Immediate | Full sync: all QSOs downloaded and stored |
| First Use | ~30-60 seconds | Database ready with all records |
| Every 5 Minutes | Background | Delta sync: check for new/updated QSOs |
| App Shutdown | On exit | Sync manager stopped gracefully |

## Usage in Code

### Example: Get Recent QSOs for a Callsign
```python
from wavelog_db import get_wavelog_db

db = get_wavelog_db()
qsos = db.get_qsos_by_callsign('N7BHJ', limit=5)

for qso in qsos:
    print(f"{qso['callsign']} - {qso['frequency']} MHz")
    print(f"  LoTW: {'✓ Confirmed' if qso['lotw_qsl_rcvd'] == 'Y' else '✗ Not confirmed'}")
```

### Example: Check Sync Status
```python
from wavelog_db import get_wavelog_db

db = get_wavelog_db()
status = db.get_sync_status()

print(f"Total QSOs: {status['total_qsos']}")
print(f"Last sync: {status['last_delta_sync']}")
```

## Testing the Setup

### 1. Start the Backend
```powershell
cd c:\Projects\om0rx-radio-control
.\start_webapp.ps1
```

### 2. Watch the Logs
You should see:
```
🚀 FastAPI backend starting...
📥 Starting initial Wavelog sync...
✅ Full sync complete: 20000 QSOs processed, total in DB: 20000
✅ Wavelog sync manager initialized
```

### 3. Test Database
```powershell
python -c "
from wavelog_db import get_wavelog_db
db = get_wavelog_db()
status = db.get_sync_status()
print(f'QSOs in database: {status[\"total_qsos\"]}')

# Get a sample QSO
qsos = db.get_all_qsos(limit=1)
if qsos:
    qso = qsos[0]
    print(f'Sample: {qso[\"callsign\"]} on {qso[\"frequency\"]} MHz')
"
```

### 4. Test API Endpoint
Open browser and search for a callsign you've worked:
```
http://localhost:8000
Search → Previous QSOs → Enter callsign
```

## Performance Improvements

| Operation | Before | After |
|-----------|--------|-------|
| Get recent QSOs | 5-30 seconds (ADIF download) | < 50ms (database query) |
| Startup time | Instant | +30-60s for initial sync |
| App restart | Cache lost | Cache persists |
| Offline use | ✗ No | ✓ Yes |

## Benefits

✅ **Fast** - Local database queries < 50ms
✅ **Persistent** - Survives app restarts  
✅ **Complete** - All Wavelog fields available
✅ **Automatic** - 5-minute auto-sync in background
✅ **Offline** - Works without Wavelog API
✅ **Accessible** - Any module can query the database

## Troubleshooting

### Issue: Sync seems slow on startup
- Normal! Initial sync takes 30-60 seconds for 20,000 QSOs
- Subsequent syncs are faster (delta only)

### Issue: "No QSOs found" when searching
- Sync might still be in progress (check logs)
- Try again after ~1 minute
- Verify callsign matches exactly (case-insensitive, but spelling matters)

### Issue: LoTW shows N for all records
- Database might have old data
- Wait for next 5-minute sync
- Or restart backend to force full sync

### Issue: Database file huge (> 100MB)
- Normal for large log (19.2MB ADIF → 30-50MB SQLite with indexes)
- Can backup and compress: `7z a wavelog.db.7z wavelog.db`

## Next Steps

1. **Restart backend** to activate sync manager
2. **Wait 1-2 minutes** for initial sync to complete
3. **Test recent QSOs** feature with a callsign you've worked
4. **Check logs** to confirm sync completed

## Files Modified Summary

```
Created:
  wavelog_db.py               (SQLite database layer)
  wavelog_sync.py             (Background sync manager)
  documentation/WAVELOG_SQLITE_CACHING.md
  documentation/WAVELOG_CACHING_QUICKSTART.md

Modified:
  wavelog_api.py              (Use local database for queries)
  backend/main.py             (Add startup/shutdown handlers)
```

## Questions?

Check the full documentation at:
```
documentation/WAVELOG_SQLITE_CACHING.md
```