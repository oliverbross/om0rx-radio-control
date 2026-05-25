# Callsign Slash/Prefix/Suffix Resolution Fix

## Problem
Callsigns with slashes (prefixes and suffixes) were not being resolved from QRZ.com and Wavelog APIs. Examples:
- `IZ4EFP/3` (CALLSIGN/SUFFIX format)
- `OK/OM0RX` (PREFIX/CALLSIGN format)
- `F5JDG/M` (CALLSIGN/SUFFIX format)
- `MW7MWZ/P` (CALLSIGN/SUFFIX format)
- `OM0AAO/QRP` (CALLSIGN/SUFFIX format)
- `PJ4/OM0AAO` (PREFIX/CALLSIGN format)

When these callsigns were entered in the application, lookups would fail because QRZ and Wavelog don't always have these variants registered. The operator data would not be retrieved.

## Solution: Fallback Lookup Strategy

Implemented a multi-tiered fallback strategy that automatically tries different callsign variants when the initial lookup fails.

### How It Works

1. **Original Callsign**: Try the exact callsign as entered (e.g., `IZ4EFP/3`)
2. **First Fallback**: Strip the suffix or prefix:
   - For `CALLSIGN/SUFFIX` (e.g., `IZ4EFP/3`): Try `IZ4EFP`
   - For `PREFIX/CALLSIGN` (e.g., `OK/OM0RX`): Try `OM0RX`
3. **Return Success**: When any variant is found, return immediately
4. **All Failed**: Report failure with list of tried variants

### Example Scenarios

| Input | Variants Tried | Result |
|-------|---|---|
| `IZ4EFP/3` | 1. `IZ4EFP/3`, 2. `IZ4EFP` | Success if either found in QRZ/Wavelog |
| `OK/OM0RX` | 1. `OK/OM0RX`, 2. `OM0RX` | Success if either found (usually OM0RX works) |
| `F5JDG/M` | 1. `F5JDG/M`, 2. `F5JDG` | Success if either found |
| `N0CALL` | 1. `N0CALL` | Direct lookup, no variants |

## Implementation Details

### 1. New Utility Function: `generate_callsign_variants()` (utils.py)

**Location**: `c:\Projects\om0rx-radio-control\utils.py`

Generates a list of callsign variants by intelligently detecting prefix vs. suffix formats:

```python
def generate_callsign_variants(callsign: str) -> list:
    """
    Generate possible callsign variants for lookup fallback.
    
    Handles callsigns with prefixes/suffixes:
    - IZ4EFP/3 -> [IZ4EFP/3, IZ4EFP]
    - OK/OM0RX -> [OK/OM0RX, OM0RX]
    - F5JDG/M -> [F5JDG/M, F5JDG]
    
    Returns:
        List of callsigns in order of priority
    """
```

**Detection Logic**:
- **Suffix Detection**: If second part is ≤3 chars or matches common suffixes (M, P, A, MM, QRP, AM, QRPP)
- **Prefix Detection**: If first part is ≤4 chars, doesn't start with '0', and second part is longer
- **Fallback**: If unclear, try both

### 2. Updated QRZ API (qrz_api.py)

**Location**: `c:\Projects\om0rx-radio-control\qrz_api.py`

**Changes**:
- Added import: `from utils import generate_callsign_variants`
- Refactored `get_profile_picture()` to use fallback strategy:
  - Created internal method `_lookup_profile_internal()` for single lookup
  - Main method now tries variants in sequence
  - Logs which variant succeeded

**Usage**:
```python
result = await qrz_client.get_profile_picture("OK/OM0RX")
# Tries: OK/OM0RX, then OM0RX
# Returns profile data from whichever succeeds
```

### 3. Updated Wavelog API (wavelog_api.py)

**Location**: `c:\Projects\om0rx-radio-control\wavelog_api.py`

**Changes**:
- Added import: `from utils import generate_callsign_variants`
- Updated three lookup methods with fallback strategy:
  1. `private_lookup()` - Logbook lookup with band/mode info
  2. `get_dxcc_status()` - DXCC worked/confirmed status
  3. `get_recent_qsos()` - Recent QSO history
- Each has internal `_*_internal()` method for single lookup
- Main methods try variants in sequence

**Usage**:
```python
result = await wavelog_client.private_lookup("IZ4EFP/3")
# Tries: IZ4EFP/3, then IZ4EFP
# Returns logbook data from whichever succeeds
```

## Testing

All callsign variants were tested:
- ✅ `IZ4EFP/3` → `[IZ4EFP/3, IZ4EFP]`
- ✅ `OK/OM0RX` → `[OK/OM0RX, OM0RX]`
- ✅ `F5JDG/M` → `[F5JDG/M, F5JDG]`
- ✅ `MW7MWZ/P` → `[MW7MWZ/P, MW7MWZ]`
- ✅ `OM0AAO/QRP` → `[OM0AAO/QRP, OM0AAO]`
- ✅ `PJ4/OM0AAO` → `[PJ4/OM0AAO, OM0AAO]`
- ✅ Simple callsigns like `N0CALL` → `[N0CALL]` (unchanged)

## Logging

Enhanced logging shows:
- Initial lookup attempt with original callsign
- Each variant being tried
- Which variant succeeded (if any)
- All tried variants if lookup fails completely

Example logs:
```
🔍 Fetching QRZ profile for callsign: OK/OM0RX
  Trying QRZ lookup for variant: OK/OM0RX
  QRZ lookup failed for variant OK/OM0RX: Callsign not found
  Trying QRZ lookup for variant: OM0RX
✅ QRZ lookup succeeded with variant: OM0RX (requested: OK/OM0RX)
```

## Impact

**User Experience**:
- Callsigns with slashes now resolve in QRZ profile panel
- Wavelog lookups work with portable/mobile suffixes
- Automatic fallback means user sees data even for non-standard variants

**Performance**:
- Minimal: Only attempts fallback if primary lookup fails
- No retry loops, linear progression through variants

**Reliability**:
- Handles all documented callsign formats
- Graceful degradation with detailed error messages
- No breaking changes to existing API

## Files Modified

1. **c:\Projects\om0rx-radio-control\utils.py**
   - Added: `generate_callsign_variants()` function

2. **c:\Projects\om0rx-radio-control\qrz_api.py**
   - Added: `_lookup_profile_internal()` method
   - Modified: `get_profile_picture()` to use fallback
   - Added: Import of `generate_callsign_variants`

3. **c:\Projects\om0rx-radio-control\wavelog_api.py**
   - Added: `_lookup_private_internal()` method
   - Added: `_get_dxcc_internal()` method
   - Added: `_get_recent_qsos_internal()` method
   - Modified: `private_lookup()`, `get_dxcc_status()`, `get_recent_qsos()` to use fallback
   - Added: Import of `generate_callsign_variants`

## Future Enhancements

Possible future improvements:
1. Cache successful lookups to avoid repeated fallbacks
2. Add user-configurable variant patterns
3. Include historical lookup success rates in logs
4. Support for multiple slash separators (rare but possible)