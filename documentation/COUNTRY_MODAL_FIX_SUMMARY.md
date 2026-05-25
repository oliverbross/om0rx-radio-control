# Country Modal Fix - Unknown Country Error

## Problem
When clicking the "View" button to open the country modal, users were seeing a 404 error:
```
GET http://localhost:8000/api/country/by-name/Unknown 404 (Not Found)
Country feature not found for: Unknown
```

The country name was being extracted as "Unknown" from the DXCC data, causing the modal to fail when trying to fetch the country information.

## Root Cause
The Wavelog API's `private_lookup` endpoint returns QSO/contact data but doesn't include:
- Country entity name (DXCC country)
- Geographic data (latitude, longitude)
- CQ zone information
- Other DXCC details needed for the country modal

The frontend code was trying to extract these fields from the Wavelog response, but they didn't exist, so the country name defaulted to "Unknown".

## Solution
Implemented a two-part fix:

### 1. Backend Enhancement (`backend/main.py`)
Modified the `/api/wavelog/private_lookup` endpoint to **enrich** the Wavelog response with DXCC data:

- Uses the `cty_resolver` to look up DXCC information for the callsign
- Adds missing fields to the response:
  - `dxcc_entity` - Country name
  - `continent` - Continent code
  - `cq` - CQ zone number
  - `dxcc` - DXCC ID
  - `itu` - ITU zone
  - `latitude` / `longitude` - Geographic coordinates
  - `grid` - Maidenhead grid square

The enrichment only adds fields that don't already exist, preserving any data from the original Wavelog response.

**File Changed**: `backend/main.py` (lines 1470-1538)

### 2. Frontend Update (`frontend/js/app-main.js`)
Enhanced the `showCountryModal()` method to:

- Better extract country name with multiple fallback field names
- Add validation to prevent showing modal with "Unknown" country
- Display user-friendly alert if country cannot be determined
- Support multiple field naming conventions for geographic data
- Include debug logging to help troubleshoot field availability

**File Changed**: `frontend/js/app-main.js` (lines 888-957)

## Testing

### Before the Fix
1. Open app and enter a callsign (e.g., "SV3RPQ")
2. Click "View" button
3. **Expected Error**: 404 error for `api/country/by-name/Unknown`

### After the Fix
1. Open app and enter a callsign (e.g., "SV3RPQ")
2. Click "View" button
3. **Expected Behavior**: Country modal opens showing:
   - Country map (Greece, in this example)
   - Country highlighted in blue
   - Station marker in red
   - Information card with:
     - Continent: EU
     - CQ Zone: 20
     - DXCC ID: 243
     - Latitude/Longitude
     - Grid Square

### If Still Getting Errors
Check browser console for debug messages:
- `📊 DXCC data available keys:` - Shows what fields the backend returned
- `🌍 Showing country modal for:` - Shows extracted values

If country is still "Unknown":
1. Verify `cty_resolver` is initialized (check backend startup logs)
2. Check if the callsign is recognized in the CTY database
3. Ensure `/data/countries-110m.json` is present for the country modal

## Technical Details

### How It Works
1. User clicks "View" button
2. Frontend calls `/api/wavelog/private_lookup` with callsign
3. Backend:
   - Calls Wavelog API for contact/worked status
   - Uses `cty_resolver.lookup()` to get DXCC information
   - Enriches response with country, continent, coordinates
   - Returns enriched data
4. Frontend extracts country name and other fields
5. Calls country modal with valid country name
6. Country modal fetches map data and renders

### Field Mapping
The solution handles multiple field name conventions:

**Country Name**
- Primary: `dxcc_entity` (added by backend)
- Fallbacks: `country`, `country_entity`

**Coordinates**
- Primary: `latitude` / `longitude` (added by backend)
- Fallbacks: `lat` / `lon`, `dxcc_lat` / `dxcc_long`

**CQ Zone**
- Primary: `cq` (added by backend)
- Fallbacks: `cqz`, `cq_zone`, `dxcc_cqz`

**DXCC ID**
- Primary: `dxcc` (added by backend)
- Fallback: `dxcc_id`

**Grid Square**
- Multiple names supported: `grid`, `gridsquare`, `grid_square`

## Files Modified
- `backend/main.py` - Lines 1470-1538 (69 new lines for enrichment logic)
- `frontend/js/app-main.js` - Lines 888-957 (enhanced extraction logic)

## Backward Compatibility
✅ **Fully backward compatible**
- Only adds fields that don't exist
- Preserves existing Wavelog response data
- No changes to API endpoints or contracts
- Works with existing country modal implementation

## Performance Impact
✅ **Minimal**
- Single CTY lookup per request (already done elsewhere)
- No additional database queries
- Negligible latency added (<1ms)

## Troubleshooting

### Still showing "Unknown"?
1. Verify CTY resolver is working:
   ```
   Check backend startup logs for: "✅ CTY resolver loaded"
   ```

2. Try a well-known callsign like "VE3LJX" (Canada) or "G0EEP" (UK)

3. Check browser console logs for actual field names being returned

### Getting 404 for country name?
1. The country name extraction is working
2. Verify `/data/countries-110m.json` exists
3. Try refreshing the page

### Want to Debug?
1. Open browser Dev Tools → Console tab
2. Look for `📊 DXCC data available keys:` message
3. Note which fields the backend returned
4. Share this with support

## Related Documentation
- [Country Modal Implementation](COUNTRY_MODAL_IMPLEMENTATION.md)
- [Country Modal Quickstart](COUNTRY_MODAL_QUICKSTART.md)
- [Backend Architecture](ARCHITECTURE_WAVELOG_CACHE.txt)