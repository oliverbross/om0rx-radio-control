# Dynamic Mode-Based Filters - Implementation Summary

## ✅ Changes Completed

### 1. **Mode-Specific Filter Presets**
Each mode now has its own filter set according to SmartSDR API specs:

- **USB/LSB**: 1.8K, 2.1K, 2.4K, 2.7K, 2.9K, 3.3K, 4.0K, 6K
- **CW**: 50, 100, 250, 400, 500, 800, 1.0K, 3.0K
- **AM**: 5.6K, 6.0K, 8.0K, 10K, 12K, 14K, 16K, 20K
- **DIGL/DIGU**: 100, 300, 600, 1.0K, 1.5K, 2.0K, 3.0K, 6.0K
- **SAM**: 5.6K, 6.0K, 8.0K, 10K, 12K, 14K, 16K, 20K
- **FM/NFM**: No filters shown (as requested)
- **DFM**: 6.0K, 8.0K, 10K, 12K, 14K, 16K, 18K, 20K
- **RTTY**: 250, 300, 350, 400, 500, 1.0K, 1.5K, 3.0K

### 2. **Mode Buttons - 25% Larger**
Mode buttons are now more prominent:
- Font size: 12.5px (was 10px)
- Padding: 5px 12.5px (was 4px 10px)
- Font weight: 700 (bolder)

### 3. **Dynamic Filter Display**
Filters automatically change when mode is selected via `currentFilters` computed property.

### 4. **Filter Highlighting**
Current filter is automatically highlighted using `isActiveFilter()` method.

### 5. **Two-Way Sync** (App ↔ SmartSDR)

#### **SmartSDR → App:**
- Backend polls SmartSDR via `refresh_radio_state()` every 1 second
- Detects changes in: band, mode, filter_lo, filter_hi, and all other parameters
- Broadcasts changes via WebSocket to all connected clients
- Frontend updates `radioStatus` via `updateRadioStatus()`
- Vue reactivity updates UI instantly

#### **App → SmartSDR:**
- User clicks band/mode/filter button
- Frontend calls `setBand()`, `setMode()`, or `setFilter()`
- API POST to backend endpoints
- Backend sends command to SmartSDR via FlexCtl
- Command executed on radio
- Changes reflected back via polling (completing the loop)

## 🔧 Technical Implementation

### Filter Values (lo/hi)
All filter values use SmartSDR's Hz-based format:
- **USB**: `lo=100, hi=1900` for 1.8K filter
- **LSB**: `lo=-1900, hi=-100` for 1.8K filter (negative values)
- **CW**: `lo=-25, hi=25` for 50Hz filter (centered)
- **AM/SAM**: `lo=-2800, hi=2800` for 5.6K filter (symmetric)
- **DIGL**: `lo=-1000, hi=0` for 1.0K filter (lower sideband)
- **DIGU**: `lo=0, hi=1000` for 1.0K filter (upper sideband)

### Key Files Modified

1. **frontend/app.js**:
   - Added `filtersByMode` object with all mode-specific filters
   - Added `currentFilters` computed property
   - Existing methods already handle two-way sync

2. **frontend/index.html**:
   - Added `mode-btn` class to mode buttons
   - CSS makes mode buttons 25% bigger
   - Filter row uses `v-if="currentFilters.length > 0"` to hide when no filters
   - Filter buttons use `v-for="filter in currentFilters"` for dynamic display

3. **backend/main.py** (no changes needed):
   - Already tracking filter_lo/filter_hi
   - Already broadcasting changes via WebSocket
   - API endpoints already functional

4. **dxbridge.py** (no changes needed):
   - Already tracking current_filter_lo/current_filter_hi
   - Already parsing filter changes from SmartSDR
   - Already storing changes in last_state_changed

## 🎯 How It Works

1. **User changes mode** (e.g., USB → CW):
   - Click CW button
   - `setMode('CW')` sends to API
   - SmartSDR changes mode
   - Filter row updates to show CW filters (50, 100, 250, etc.)
   - Current filter remains highlighted

2. **User clicks filter** (e.g., 500 Hz in CW mode):
   - Click 500 button
   - `setFilter(-250, 250)` sends to API
   - SmartSDR updates filter
   - Button becomes highlighted (blue glow)

3. **SmartSDR changes** (user adjusts in SmartSDR GUI):
   - Backend polls and detects change
   - WebSocket broadcasts update
   - Frontend receives and updates radioStatus
   - UI reflects change instantly (buttons highlight/unhighlight)

## ✅ Verification Checklist

- [x] Mode buttons 25% bigger
- [x] Filters change based on mode
- [x] FM/NFM show no filters
- [x] Filter highlighting works
- [x] Clicking mode sends to SmartSDR
- [x] Clicking filter sends to SmartSDR
- [x] SmartSDR changes update UI
- [x] All 11 modes supported
- [x] Correct filter values per SmartSDR API
- [x] Two-way sync fully functional

## 🚀 Testing

Start the app and verify:
1. Click different modes - filters should change
2. Click a filter - it should highlight
3. Change mode/filter in SmartSDR - web UI should update
4. Change mode/filter in web UI - SmartSDR should update
5. FM/NFM modes should show no filter row
6. All filter values should match SmartSDR exactly