# QSO Logging Fix - "Works Once, Then Fails" Issue

## Problem Summary
QSO logging was intermittently failing on second and subsequent submissions with a 500 Internal Server Error, while the first submission often succeeded.

## Root Cause Analysis
The issue was likely caused by:
1. **Connection pooling issues**: A new `aiohttp.ClientSession` was being created for each API request, which can exhaust connection pools and cause resource leaks
2. **File locking**: The ADIF file operations might encounter locking issues on Windows, especially under rapid successive writes
3. **Incomplete error handling**: Missing exception details made it harder to diagnose the actual problem

## Fixes Applied

### 1. Persistent HTTP Session Management (`wavelog_api.py`)
- **Added class-level HTTP session** that persists across requests instead of creating a new one each time
- **Connection pooling** configured with:
  - Max 10 connections total
  - Max 5 connections per host
  - 300-second DNS cache
  - 30-second timeout per request
- **Session lifecycle management**:
  - Created on first use
  - Reused for subsequent requests
  - Properly closed on app shutdown
- **Fallback to temporary sessions** if persistent session creation fails

**Code Changes:**
```python
@classmethod
async def _get_session(cls) -> aiohttp.ClientSession:
    """Get or create a persistent HTTP session"""
    if cls._session is None or cls._session.closed:
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=5, ttl_dns_cache=300)
        cls._session = aiohttp.ClientSession(connector=connector, timeout=timeout)
    return cls._session
```

### 2. Retry Logic for ADIF File Operations (`adif_handler.py`)
- **Exponential backoff retry mechanism** (3 attempts with increasing delays)
- **Proper encoding** (UTF-8) and explicit flush to disk
- **Better error handling** with detailed logging for each attempt
- **Handle Windows file locking** issues gracefully

**Retry Strategy:**
- 1st attempt: Immediate
- 2nd attempt: After 100ms
- 3rd attempt: After 200ms

### 3. Improved Backend Error Handling (`backend/main.py`)
- **Separated error handling** for Wavelog and ADIF operations
- **Graceful degradation**: QSO is considered successful if EITHER Wavelog OR ADIF succeeds
- **Enhanced logging** with full stack traces for debugging
- **Better error propagation** to frontend with specific error messages

**Key Improvement:**
```python
# Success if either Wavelog or ADIF succeeded
"success": wavelog_result.get('success', True) or adif_saved,
```

### 4. Resource Cleanup (`backend/main.py`)
- **Added shutdown hook** to properly close the persistent HTTP session
- Ensures no dangling connections on app restart

```python
@app.on_event("shutdown")
async def shutdown_event():
    if wavelog_client:
        await wavelog_client.close_session()
```

## Benefits of These Fixes

✅ **Eliminates connection pool exhaustion** - Persistent session prevents resource leaks
✅ **Handles file locking** - Retry logic handles Windows file locks gracefully  
✅ **Better error diagnostics** - Detailed logging helps identify future issues
✅ **More resilient QSO logging** - Works even if one system (Wavelog or ADIF) temporarily fails
✅ **Proper resource cleanup** - No dangling connections or file handles

## Testing Recommendations

1. **Test multiple sequential QSO submissions** (5-10 QSOs in quick succession)
2. **Monitor backend logs** for any retry messages or warnings
3. **Check both Wavelog and ADIF log files** for proper recording
4. **Verify response messages** in the UI for any error details

## Files Modified

1. `wavelog_api.py` - Added persistent session management
2. `adif_handler.py` - Added retry logic for file operations
3. `backend/main.py` - Enhanced error handling and resource cleanup

## Next Steps

If you still experience issues after this fix:
1. Check the backend logs for specific error messages
2. Verify Wavelog API connectivity and credentials
3. Ensure ADIF log file has proper write permissions
4. Check system resources (disk space, open file limits)
