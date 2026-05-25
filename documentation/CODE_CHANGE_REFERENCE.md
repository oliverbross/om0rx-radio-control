# Code Change Reference - Duplicate Sync Fix

## Quick Diff

### File: `backend/main.py`

**Location**: Lines 842-849 in the `startup_event()` function

#### BEFORE (with bug):
```python
842    # Start background tasks
843    asyncio.create_task(poll_radio_status())
844    asyncio.create_task(poll_dx_spots())
845    asyncio.create_task(monitor_cluster_status())
846    
847    # Start periodic ADIF sync
848    if adif_sync_manager:
849        adif_sync_task = asyncio.create_task(periodic_adif_sync())
```

#### AFTER (bug fixed):
```python
842    # Start background tasks
843    asyncio.create_task(poll_radio_status())
844    asyncio.create_task(poll_dx_spots())
845    asyncio.create_task(monitor_cluster_status())
846    
847    # NOTE: periodic_adif_sync() already started on line 779, don't create duplicate task!
```

## What Changed

- **Removed**: Lines 848-849 (the redundant periodic_adif_sync() task creation)
- **Added**: Comment explaining why it's removed

## Why This Works

The sync task is already created on line 779:

```python
779    adif_sync_task = asyncio.create_task(periodic_adif_sync())
780    logger.info("✅ ADIF periodic sync task started (runs first immediately, then every 30 seconds)")
```

Creating it twice (line 779 AND line 849) caused:
1. Two concurrent async tasks running the same sync function
2. Race condition where both check for duplicates
3. Both insert the same new records
4. Result: **Duplicates in database**

Removing the second creation (lines 848-849) ensures:
1. Only ONE sync task runs
2. No race conditions
3. No duplicate inserts
4. Database stays clean ✅

## Testing the Fix

To verify the fix is applied:

```bash
# Check that periodic_adif_sync() is only created once
grep -n "asyncio.create_task(periodic_adif_sync" backend/main.py

# Expected output:
# 779:        adif_sync_task = asyncio.create_task(periodic_adif_sync())

# Should show ONLY line 779, not line 849
```

Or in PowerShell:
```powershell
Select-String -Path "backend/main.py" -Pattern "asyncio.create_task\(periodic_adif_sync" | Select-Object LineNumber

# Expected: Only line 779
```

## Related Code

### Sync Task Creation (Line 779):
```python
adif_sync_manager = init_adif_sync()
logger.info("✅ ADIF DuckDB sync initialized")

# ✅ Correct: Create the periodic sync task
adif_sync_task = asyncio.create_task(periodic_adif_sync())
logger.info("✅ ADIF periodic sync task started (runs first immediately, then every 30 seconds)")
```

### Periodic Sync Function (Lines 688-710):
```python
async def periodic_adif_sync():
    """
    Periodic ADIF sync task
    Runs immediately on first call, then every 30 seconds to check for ADIF file changes
    """
    import asyncio
    
    first_run = True
    while True:
        try:
            # Do immediate first sync, then wait 30 seconds between subsequent syncs
            if not first_run:
                await asyncio.sleep(30)
            first_run = False
            
            if _sync_instance is not None:
                result = _sync_instance.sync()
                if result['synced']:
                    logger.info(f"✅ ADIF sync: {result['records_synced']} records synced, "
                               f"total: {result.get('total_records', 0)}")
        except Exception as e:
            logger.error(f"Error in ADIF sync task: {e}")
            await asyncio.sleep(5)  # Wait 5 seconds before retrying
```

## Impact

- **Lines Changed**: 3 lines (2 removed, 1 added as comment)
- **Breaking Changes**: None (only removes buggy code)
- **Backwards Compatibility**: 100% (no API changes)
- **Performance Impact**: None (actually improves by preventing race conditions)

## Database Cleanup

After deploying this code fix, run the database cleanup:

```bash
python fix_duckdb_duplicates.py
```

This removes the 12 existing duplicate records:
- Before: 41,686 records (with duplicates)
- After: 41,674 records (duplicates removed)

## Verification

After the fix is applied and deployed:

1. **Code is deployed** ✅
   - Check that backend/main.py has the comment on line 847

2. **Application restarts** ✅
   - Run: `python backend/main.py`
   - Check logs for single "ADIF periodic sync task started" message

3. **Database is cleaned** ✅
   - Run: `python fix_duckdb_duplicates.py`
   - Verify: 41,674 total records, 0 duplicates

4. **Test functionality** ✅
   - Click "Prev QSO's" button
   - Check that modal loads correctly
   - Verify no performance issues

## Git Commit Message (if applicable)

```
fix: remove duplicate periodic_adif_sync() task creation

- Removed redundant asyncio.create_task(periodic_adif_sync()) call on line 849
- This was creating two concurrent sync tasks causing race conditions
- Race condition led to duplicate QSO records in database (12 duplicates found)
- Now only one sync task runs (created on line 779)
- Database cleanup removes 12 existing duplicates

Fixes: Duplicate QSO records in DuckDB
```

---

**Summary**: This is a minimal 1-line fix (removing 2 lines, adding 1 comment) that eliminates a critical race condition in the ADIF sync system.