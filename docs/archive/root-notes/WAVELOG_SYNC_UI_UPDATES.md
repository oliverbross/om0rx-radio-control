# Wavelog Sync UI Updates

## Overview
Updated the sync status modal and UI elements to reflect the new Wavelog→DuckDB sync architecture (replacing the old ADIF→DuckDB sync).

## Changes Made

### 1. Sync Status Modal (`frontend/templates/modal-sync.html`)

#### Title Changed
- **Old:** "📊 ADIF Database Sync Status"
- **New:** "📊 Wavelog→DuckDB Sync Status"

#### Left Column Updates
- **Total Records:** Shows total QSOs synced from Wavelog to DuckDB
- **Added This Sync:** Number of new records added during last sync (green)
- **Updated This Sync:** Number of existing records updated during last sync (orange - NEW field)
- Removed: "Records Skipped" (no longer relevant)

#### Right Column Updates
- **Last Sync:** When the last sync completed
- **Next Sync In:** Countdown to next sync
- **Sync Interval:** Shows "60 seconds" (configurable)
- **Sync Source:** Shows "Wavelog MySQL DB" (was "ADIF File")
- Removed: "File Size" (no longer relevant)

#### Comparison Box - MAJOR UPDATE
- **Background Color:** Changed from white (#f5f5f5) to dark (#2a2a2a) for better readability
- **Text Colors:** Updated to light colors (#fff, #bbb) for dark background
- **Content Changed:**
  - **Old:** "📁 File vs Database Comparison" showing ADIF File QSOs → Database Records
  - **New:** "🔄 Wavelog → DuckDB Sync" showing MySQL (Source) → DuckDB (Cache)
- **Status Indicator:** Shows:
  - "⟳ Syncing..." (orange) when sync is active
  - "✓ In sync" (green) when sync is complete
  - "⏳ Waiting..." (gray) before first sync

#### Footer Section
- **Database Location:** Shows `/data/qso_log.duckdb` path
- Removed: "File Last Modified" (no longer relevant)

### 2. Sync Button Tooltips

Updated in both locations:
- `frontend/templates/controls-row1.html` (line 45)
- `frontend/controls-section.html` (line 31)

#### Tooltip Text
- **While Syncing:** "Wavelog→DuckDB sync in progress..."
- **When Ready:** "Wavelog→DuckDB: X records synced"

## Visual Changes Summary

### Modal Header
```
Old: 📊 ADIF Database Sync Status
New: 📊 Wavelog→DuckDB Sync Status
```

### Comparison Box (The White Box → Dark Box)
```
Old Style:
- background-color: #f5f5f5 (light gray/white)
- color: #666 (dark gray text)
- Title: "📁 File vs Database Comparison"

New Style:
- background-color: #2a2a2a (dark gray)
- color: #fff, #bbb (white/light gray text)
- Title: "🔄 Wavelog → DuckDB Sync"
```

### New Field
- **Updated This Sync:** Shows number of records that were modified in Wavelog and updated in DuckDB (displayed in orange)

## Data Flow Visualization

The modal now clearly shows:
```
Wavelog (MySQL) → DuckDB (Local Cache)
     ↓                    ↓
  Source            X QSOs synced
```

## Benefits

1. **Clarity:** Users now understand the sync is from Wavelog to DuckDB (not ADIF to DuckDB)
2. **Dark Theme:** The comparison box matches the dark UI theme (was jarring white box)
3. **Better Info:** Shows both new records added AND existing records updated
4. **Source Transparency:** Clearly indicates MySQL as the source and DuckDB as local cache
5. **Readability:** Light text on dark background is easier to read in the dark UI

## Files Modified

1. ✅ `frontend/templates/modal-sync.html` - Complete modal redesign
2. ✅ `frontend/templates/controls-row1.html` - Tooltip update
3. ✅ `frontend/controls-section.html` - Tooltip update

## Testing

To test the changes:
1. Start the application
2. Click the "📊 X QSOs" button in the top-right corner
3. Verify:
   - Title shows "Wavelog→DuckDB Sync Status"
   - Dark comparison box is visible and readable
   - "Added This Sync" and "Updated This Sync" fields are present
   - Tooltip on hover shows "Wavelog→DuckDB: X records synced"
   - Status updates in real-time during sync

## Notes

- The sync button icon and text remain the same (📊 X QSOs) for consistency
- ADIF file path configuration remains in Config modal (still used for local backup)
- The local ADIF file is still maintained - this only changes the database sync source