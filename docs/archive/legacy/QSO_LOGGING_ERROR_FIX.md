# QSO Logging Error Handling Fix

## Issue Reported
**Error**: `500 (Internal Server Error)` when submitting QSO data
**Error Message**: `SyntaxError: Unexpected token 'I', "Internal S"... is not valid JSON`

### Root Cause
When the backend returned a 500 error, it was responding with HTML content (FastAPI error page), not JSON. The frontend code was trying to parse this HTML as JSON, which caused a JSON parsing error that masked the actual backend error.

---

## Solution Implemented

### Frontend Improvements (`frontend/js/app-main.js`)

#### 1. **Proper HTTP Status Code Checking** (Line 655)
```javascript
if (!response.ok) {
    // Now checks HTTP status code BEFORE attempting JSON parsing
}
```
- Checks if response status is 200-299 before attempting to parse response body
- Gracefully handles error responses with appropriate error messages

#### 2. **Comprehensive Error Response Parsing** (Lines 656-678)
The fix implements a three-tier error parsing strategy:

**Tier 1: Try JSON parsing** (Line 658)
- Attempts to parse error response as JSON
- Extracts `data.detail` or `data.message` from backend
- Logs full error object for debugging

**Tier 2: Fallback to text** (Line 664)
- If JSON parsing fails, reads response as plain text
- Includes error text in user-facing message (if < 200 chars)
- Logs response text to console for debugging

**Tier 3: Last resort** (Line 674)
- If even text parsing fails, shows generic error message
- User is directed to check browser console

#### 3. **Detailed Console Logging** (Lines 641, 660, 665, 674)
Added logging markers to help users troubleshoot:
```javascript
console.log('📤 Sending QSO data to backend:', JSON.stringify(qsoData, null, 2));
console.error('📍 Backend error details:', data);
console.error('📍 Server error response:', errorText);
console.error('📍 Could not parse error response:', e);
```

---

## What the User Will See Now

### Before (Broken)
```
500 (Internal Server Error)
QSO submission error: SyntaxError: Unexpected token 'I'...
```

### After (Fixed)
If backend returns JSON error:
```
❌ [Actual error message from backend, e.g., "Connection timeout", "Invalid API key"]
```

If backend returns HTML/text error:
```
❌ 500: [Error details from response text, if available]
```

If nothing can be parsed:
```
❌ Server error 500 - Check console for details
```

---

## Troubleshooting Steps for Users

If you still see a 500 error:

1. **Check Browser Console** (F12 → Console tab)
   - Look for messages starting with `📤`, `📍`
   - These will show the exact data being sent and server response

2. **Check Server Logs**
   - Backend logs show: `📝 QSO Log Request - ...` with full details
   - Check for error messages with `❌` prefix

3. **Verify QSO Data** (from console)
   - Callsign should be uppercase and non-empty
   - Frequency should be a valid float (MHz)
   - Mode should be valid (SSB, CW, etc.)
   - RST values should be 1-999

4. **Check Backend Services**
   - Is Wavelog API accessible?
   - Are Wavelog credentials correct in `config.py`?
   - Is the local ADIF log path writable?

---

## Technical Details

### Request/Response Flow

**Request (Frontend → Backend)**:
```json
{
  "callsign": "W1ABC",
  "frequency": 14.250,
  "mode": "SSB",
  "rst_sent": 59,
  "rst_received": 59,
  "date": "2025-01-18",
  "time_off": "20:30:00",
  ...other optional fields
}
```

**Success Response (Backend → Frontend)**:
```json
{
  "success": true,
  "message": "QSO logged successfully",
  "wavelog": {...},
  "adif_saved": true
}
```

**Error Response (Backend → Frontend)**:
```json
{
  "detail": "Error message describing what went wrong"
}
```

### Error Handling in Backend (`backend/main.py:1386-1427`)

The backend's `log_qso()` function:
1. Validates QSO data via Pydantic `QSORequest` model
2. Initializes `WavelogClient` and `ADIFHandler` if needed
3. Calls `wavelog_client.log_qso(qso_dict)` to submit to Wavelog API
4. Saves backup to local ADIF file
5. Returns success/failure response
6. Catches any exception and logs it with full traceback

---

## Files Modified
- `frontend/js/app-main.js` - Lines 641-678 (error handling in `submitQSO()`)

## Related Files
- `backend/main.py` - Line 1386-1427 (`/api/qso/log` endpoint)
- `wavelog_api.py` - Line 283-352 (Wavelog API integration)
- `adif_handler.py` - Line 103-130 (Local ADIF backup)

---

## Next Steps

If the 500 error persists after this fix:

1. Run the browser console and capture the exact error message
2. Check backend logs for the full exception traceback
3. Verify Wavelog API credentials and connectivity
4. Ensure all required Python dependencies are installed
5. Check file permissions on the ADIF log directory

The detailed error messages should now make it much easier to identify the root cause!