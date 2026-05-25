# Spots Timestamp Fix

## Issues Fixed

### 1. ✅ FIXED: All spots showing "9:25:26" on index.html
**Problem:** The `formatSpotTime()` function was receiving Unix timestamps in seconds but JavaScript's `Date` constructor expects milliseconds. This caused incorrect time display.

**Solution:** Modified `frontend/js/app-main.js` line 649 to multiply by 1000:
```javascript
const date = new Date(timestamp * 1000);  // Convert seconds to milliseconds
```

This fix applies to the real-time spots displayed in the main index.html interface.

---

### 2. ⚠️ INVESTIGATING: No new spots since 30/10/2025 on spots-database.html
**Problem:** The spots-database.html page shows no new spots after a certain date. This could be due to:
- Cluster disconnected and not reconnecting
- Database not being updated with new spots
- Stale data cached in the database

**Solution:** Added a debug endpoint to diagnose the issue

---

## How to Verify the Fixes

### Step 1: Restart the Backend
```powershell
# Stop the current backend process
# Then restart it:
python c:\Projects\om0rx-radio-control\backend\main.py
```

### Step 2: Check Spots on index.html
1. Open http://localhost:8000 in your browser
2. Look at the DX Spots table - the timestamps should now show the correct UTC time (different for each spot, not all "9:25:26")
3. New spots arriving should show current times

### Step 3: Check Cluster Connection Status
Open this URL in your browser to see detailed status:
```
http://localhost:8000/api/debug/spots-status
```

This will show:
```json
{
  "cluster": {
    "connected": true/false,
    "status": "connected/disconnected"
  },
  "cache": {
    "count": 100,           // Real-time spots in memory
    "latest": { ... }       // Most recent spot received
  },
  "database": {
    "count": 5000,          // All spots ever logged
    "latest": { ... }       // Most recent spot in database
  }
}
```

**What to look for:**
- **`cluster.connected: false`** - Cluster is disconnected, need to check cluster connection settings
- **`cache.count: 0`** - No recent spots received
- **`database.latest` is old** - New spots aren't being logged to database

### Step 4: Troubleshooting

**If cluster is disconnected:**
1. Check config.py for correct CLUSTER_HOST and CLUSTER_PORT
2. Check network connectivity to the cluster
3. Verify CLUSTER_USER and CLUSTER_PASS are correct

**If cache shows spots but database doesn't:**
1. Check database file exists: `c:\Projects\om0rx-radio-control\data\spots.duckdb`
2. Check file permissions
3. Look for errors in the backend logs about database writes

**If both cache and database are empty:**
1. Cluster is not receiving any spots
2. Check cluster connection and ask on cluster for `/sh/dx` to see if any spots exist

---

## Technical Details

### Backend Changes:
- Added `/api/debug/spots-status` endpoint in `backend/main.py`

### Frontend Changes:
- Fixed `formatSpotTime()` in `frontend/js/app-main.js` to properly convert Unix timestamps

### Data Flow:
```
DX Cluster 
  ↓
cluster_client receives spot
  ↓
process_cluster_spot() 
  ├→ log_spot() [saves to database]
  ├→ broadcast_spots() [sends to index.html WebSocket]
  └→ add_spot() [sends to radio]
  
index.html: Real-time WebSocket updates (now with correct timestamps)
spots-database.html: Fetches from database every 10 seconds
```

---

## Spot Timestamp Fields

The backend sends three time-related fields for each spot:

1. **timestamp** (Unix seconds) - Used for real-time calculations
2. **time** (HH:MM:SS string) - Pre-formatted for display
3. In database: **received_at** (ISO string) - Persistent record

Frontend should use:
- `formatSpotTime(spot.timestamp)` for index.html
- Parse `spot.received_at` for spots-database.html

---

## Monitor Logs

Check backend logs for any spot-related errors:
```
grep -i "spot\|error\|cluster" logs/flex_debug.log | tail -50
```

Or on Windows:
```powershell
Get-Content c:\Projects\om0rx-radio-control\logs\flex_debug.log -Tail 100 | Select-String "spot|error|cluster"
```