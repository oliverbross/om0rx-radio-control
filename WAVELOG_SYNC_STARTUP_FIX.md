# Wavelog→DuckDB Sync Startup Fix

## Problem
The Wavelog→DuckDB sync task was not running even though it was configured (60 second interval). The modal showed:
- **Last Sync: Never**
- **Total Records: 0**
- **Next Sync In: 0s**

No sync activity was logged in `flex_debug.log`.

## Root Cause
**Global Variable Namespace Conflict** - Python modules have separate global namespaces!

1. `backend/main.py` initialized `wavelog_sync_manager` in its own namespace
2. `backend/core/__init__.py` has `periodic_wavelog_sync()` which declares `global wavelog_sync_manager`
3. These are **different variables** in different module namespaces
4. When `periodic_wavelog_sync()` ran, it checked `if wavelog_sync_manager:` which was always `None` in its namespace
5. Result: The sync code never executed!

## Solution
**Set the global variable in BOTH namespaces** by explicitly setting `backend.core.wavelog_sync_manager`:

```python
def init_wavelog_sync_manager():
    """Initialize Wavelog→DuckDB sync manager"""
    global wavelog_sync_manager, adif_sync_task
    import backend.core
    try:
        wavelog_sync_manager = init_wavelog_sync()
        # CRITICAL: Also set in backend.core namespace (used by periodic_wavelog_sync)
        backend.core.wavelog_sync_manager = wavelog_sync_manager
        logging.info("✅ Wavelog→DuckDB sync initialized")
        return True
    except Exception as e:
        logging.error(f"❌ Wavelog→DuckDB sync initialization failed: {e}")
        return False
```

## Changes Made
- **File:** `backend/main.py` (line 228-232)
- **Added:** Import `backend.core` and explicitly set `backend.core.wavelog_sync_manager`
- **Removed:** Duplicate task start code (was starting task twice)

## What Should Happen Now
After restarting the application:

1. **Startup logs** should show:
   ```
   ✅ Wavelog→DuckDB sync initialized
   🔄 Starting periodic Wavelog→DuckDB sync task (60 second interval)
   ⏳ Running initial Wavelog→DuckDB sync in background...
   ✅ Wavelog sync: +X new, ~Y updated, total: Z
   ```

2. **Modal** should show:
   - **Last Sync:** Recent timestamp
   - **Total Records:** Number from Wavelog database
   - **Added This Sync:** Count of new records
   - **Updated This Sync:** Count of modified records
   - **Next Sync In:** Countdown from 60 seconds

3. **Logs** should show sync every 60 seconds:
   ```
   ✅ Wavelog sync: +0 new, ~0 updated, total: 1234
   ```

## Testing Steps
1. **Restart the application**: `.\start_webapp.ps1`
2. **Check startup logs** for sync initialization messages
3. **Open the sync modal** (click "📊 X QSOs" button)
4. **Verify:**
   - "Last Sync" shows a recent time
   - "Total Records" > 0
   - "Next Sync In" counts down from 60
5. **Wait 60 seconds** and check if sync runs again
6. **Check logs** with: `Get-Content logs\flex_debug.log -Tail 50 | Select-String "Wavelog"`

## Important Notes
- **Sync Status** (`sync_status` dict) is already shared properly via `backend.core` import
- **Background Tasks** start the sync task via `services/background_tasks.py`
- **Sync Function** is defined in `backend/core/__init__.py` at line 713
- **Sync Manager** is initialized from `wavelog_duckdb_sync.py`

## Related Files
- `backend/main.py` - Application initialization
- `backend/core/__init__.py` - Core module with periodic_wavelog_sync
- `services/background_tasks.py` - Background task management
- `wavelog_duckdb_sync.py` - Sync manager implementation
- `config.py` - WAVELOG_SYNC_INTERVAL = 60

---
**Date:** 2025-11-04  
**Issue:** Wavelog sync not running (namespace conflict)  
**Status:** ✅ Fixed