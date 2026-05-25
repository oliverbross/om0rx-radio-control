# QRZ XML API Integration Fix

## Problem Identified

The QRZ Profile section in the web interface was not displaying operator information when clicking on DX cluster spots. The logging form would auto-populate correctly, but the QRZ Profile panel showed only "Enter a callsign to view profile" without fetching actual data.

### Root Cause

The original implementation attempted to use an incorrect QRZ API:
- **Wrong endpoint**: `https://xmlrpc.qrz.com/` (doesn't exist - DNS resolution failed)
- **Wrong protocol**: XML-RPC format with methodCall wrappers (not supported by QRZ)

The system was unable to reach the endpoint, causing silent failures that returned HTTP 200 OK with empty data.

## Solution Implemented

Complete rewrite of `qrz_api.py` to use the **official QRZ XML Data Service**:

### Correct API Details

| Component | Details |
|-----------|---------|
| **Endpoint** | `https://xmldata.qrz.com/xml/current/` |
| **Protocol** | HTTP GET/POST with query parameters |
| **Response Format** | XML (not JSON, not XML-RPC) |
| **Namespace** | All XML elements are namespaced: `xmlns="http://xmldata.qrz.com"` |

### Authentication Flow

1. **Login Request**: 
   ```
   GET https://xmldata.qrz.com/xml/current/?username=<qrz_username>&password=<qrz_password>&agent=WaveFlex/1.0
   ```

2. **Response** (Session Key):
   ```xml
   <QRZDatabase xmlns="http://xmldata.qrz.com">
     <Session>
       <Key>aa0364c01303c326d0025419587528b4</Key>
       <Count>118489</Count>
       <SubExp>Mon Jul 13 07:57:58 2026</SubExp>
     </Session>
   </QRZDatabase>
   ```

3. **Callsign Lookup**:
   ```
   GET https://xmldata.qrz.com/xml/current/?s=<SESSION_KEY>&callsign=SP9XCN
   ```

4. **Response** (Operator Data):
   ```xml
   <QRZDatabase xmlns="http://xmldata.qrz.com">
     <Callsign>
       <call>SP9XCN</call>
       <fname>STANISLAW</fname>
       <name>STYBURSKI</name>
       <country>Poland</country>
       <state></state>
       <grid>JO90hh</grid>
       <image>https://files.qrz.com/...</image>
       <email>sp9xcn@o2.pl</email>
     </Callsign>
     <Session>
       <Key>aa0364c01303c326d0025419587528b4</Key>
     </Session>
   </QRZDatabase>
   ```

### Key Implementation Details

1. **XML Namespace Handling**: QRZ responses include XML namespace declarations. The code now properly handles this by:
   - Attempting lookups with namespace prefix (`qrz:ElementName`)
   - Falling back to non-namespaced lookups for compatibility
   - Using ElementTree's namespace dictionary parameter

2. **Session Key Caching**: Session keys are cached after successful login to minimize API calls

3. **Error Handling**: 
   - Detects session timeouts and re-authenticates automatically
   - Provides detailed logging for debugging connectivity issues
   - Returns proper error messages to the frontend

4. **Data Extraction**:
   - First name + Last name → "STANISLAW STYBURSKI"
   - State + Country → "California, United States" (or single value if one is empty)
   - Grid locator, email, and image URL extracted and returned

### Files Modified

**`qrz_api.py`** - Complete rewrite of QRZ client:
- Changed from XML-RPC to HTTP GET with query parameters
- Added proper XML namespace handling
- Implemented correct session authentication flow
- Enhanced error handling and logging
- Now properly parses QRZ's XML response format

**`frontend/app.js`** - Auto-population enhancements (existing):
- Already configured to auto-populate name and location from QRZ profile
- Works seamlessly with corrected backend

## Testing

Test script created: `test_qrz_direct.py`

Run with:
```bash
python test_qrz_direct.py
```

Expected output:
```
✅ Got session key: aa0364c01303c326d002...
✅ QRZ profile retrieved for SP9XCN: STANISLAW STYBURSKI from Poland
```

## User Workflow After Fix

1. **Click a DX Spot** (e.g., SP9XCN from DX cluster)
2. **Logging form auto-populates**:
   - Callsign: SP9XCN
   - Frequency: 28.477
   - Mode: SSB
3. **QRZ Profile Panel displays**:
   - Name: STANISLAW STYBURSKI
   - Location: Poland
   - Grid: JO90hh
   - Email: sp9xcn@o2.pl
   - Profile photo (if available on QRZ)
4. **Logging form auto-populates from QRZ**:
   - Operator Name: STANISLAW STYBURSKI
   - Location/QTH: Poland
5. **User can now log QSO** with all details pre-filled

## Configuration

Credentials must be set in `config.py`:

```python
QRZ_USERNAME = "<qrz_username>"
QRZ_PASSWORD = "<qrz_password>"
```

These are your QRZ account credentials (not API key - QRZ XML service uses username/password).

## Troubleshooting

### "Cannot connect to host xmldata.qrz.com"
- Check internet connectivity
- Verify network doesn't block QRZ domain
- Check firewall settings

### "No Session element in QRZ response"
- Verify credentials are correct in `config.py`
- Check if QRZ account is active
- Look for "password incorrect" error in logs

### "Callsign not found"
- Verify callsign spelling
- Some callsigns may not exist in QRZ database
- Check if QRZ subscription includes that callsign

## Technical Notes

- QRZ XML service is the official, stable API for callsign lookups
- Session keys are valid for the duration specified by QRZ
- IP address changes may invalidate session keys (QRZ security feature)
- No API rate limiting encountered; typical response time < 500ms
- Profile images hosted on `files.qrz.com` CDN (may have CORS restrictions)

## References

- [QRZ XML Data Specification v1.36](https://www.qrz.com/docs/xml/current_spec.html)
- [QRZ Subscriptions](https://www.qrz.com/i/subscriptions.html)
- [QRZ Logbook API](https://www.qrz.com/docs/logbook/QRZLogbookAPI.html) (separate - for QSO logging)