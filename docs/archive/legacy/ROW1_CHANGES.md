# Row 1 Reorganization - Changes Summary

## Changes Applied

### 1. **Button Cleanup**
- ❌ **Removed**: BS, PA, B.M, XVTR, 0 dB (from Panel 2)
- ❌ **Removed**: ☰, 🔇 (between VOX and Break.In)
- ❌ **Removed**: SQL, SPLIT, ○○, ⚙ (after Break.In)
- ✅ **Kept**: ⚡, RX2 | MOX, TUNE, VOX, Break.In

### 2. **Button Renamed**
- Changed **TX** → **MOX** (Manual Override Transmit)

### 3. **Layout Restructure**
- **Top line**: Buttons centered in middle of row
  - `[⚡] [RX2] | [MOX] [TUNE] [VOX] [Break.In]`
- **Bottom line**: All 6 sliders below buttons (same row using flex-wrap)
  - `[Volume] [Monitor] [AGC-T] [Drive] [Tune] [Mic]`
- **UTC Clock**: Absolute positioned to right side (stays on first line)

### 4. **Slider Changes**
- Renamed **Mic.PC** → **Mic**
- Renamed **AGC** → **AGC-T** (AGC Threshold)
- **AGC-T** now controls `rxagc_threshold` parameter (0-100)
- All sliders visible with proper spacing

## New Layout Structure

```
┌────────────────────────────────────────────────────────────────┐
│                                           [●] 12:34:56 UTC     │
│        [⚡] [RX2]  |  [MOX] [TUNE] [VOX] [Break.In]            │
│                                                                 │
│  [Vol 50] [Mon 0] [AGC-T 65] [Drv 21] [Tune 16] [Mic 32]     │
└────────────────────────────────────────────────────────────────┘
```

## Technical Implementation

### Frontend (index.html)
- Used `flex-wrap: wrap` on control-row
- Buttons in centered container (`justify-content: center`)
- Sliders in second row below buttons (`margin-top: 8px`)
- UTC clock absolute positioned (`position: absolute; right: 8px; top: 8px`)

### Frontend (app.js)
- Added `agcThreshold: 65` to `controls` data property
- Added `setAGCThreshold()` method to send command to backend

### Backend (main.py)
- Added `/api/agc_threshold` POST endpoint
- Sends SmartSDR command: `audio client 0 slice {slice_id} rxagc_threshold={value}`
- Broadcasts status update via WebSocket

## SmartSDR API Integration

**AGC Threshold Command:**
```
audio client 0 slice <slice_id> rxagc_threshold=<0-100>
```

This controls the AGC threshold level in SmartSDR, determining how sensitive the AGC reacts to incoming signals.

## Testing Checklist

- [ ] All buttons display correctly (only 6 buttons total)
- [ ] Buttons are centered in row
- [ ] MOX button toggles TX state
- [ ] All 6 sliders are visible and functional
- [ ] AGC-T slider adjusts AGC threshold (test with SmartSDR)
- [ ] UTC clock displays on right side
- [ ] Layout responsive and clean
- [ ] No overlapping elements

## File Changes

1. **frontend/index.html** - Row 1 structure completely reorganized
2. **frontend/app.js** - Added agcThreshold control and setAGCThreshold method
3. **backend/main.py** - Added /api/agc_threshold endpoint