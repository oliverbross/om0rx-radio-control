# Rotor SP/LP Bearing Display Feature

## Overview
Added a new visual panel next to the rotor controls that displays **Short Path (SP)** and **Long Path (LP)** bearing information for the currently beamed spot/callsign. Users can now manually click GO buttons to rotate the antenna to either SP or LP direction.

## What Was Added

### 1. New Data Properties in Frontend (app.js)
- `currentBeamingCallsign` - The callsign currently being beamed to
- `shortPathBearing` - Short path bearing in degrees (0-359)
- `longPathBearing` - Long path bearing in degrees (0-359, calculated as SP + 180°)
- `lastBeamingTime` - Timestamp of when beaming started

### 2. Backend Integration Update
The existing `/api/rotor/auto/goto` endpoint now returns bearing data that is captured by the frontend:
```json
{
  "ok": true,
  "bearing": 251.5,
  "band": "20m",
  "callsign": "WP3PJ",
  "message": "Rotor moving to 251.5°"
}
```

### 3. New Frontend Functions (app.js)

#### `rotorGotoShortPath()`
- Manually tune rotor to short path bearing
- Sets `rotorAzimuth` to `shortPathBearing` and calls `rotorGoto()`

#### `rotorGotoLongPath()`
- Manually tune rotor to long path bearing
- Sets `rotorAzimuth` to `longPathBearing` (SP + 180°) and calls `rotorGoto()`

### 4. Updated `rotorAutoGoto()` Function
Enhanced to capture and display bearing information:
```javascript
// After successful AUTO rotor move:
this.currentBeamingCallsign = callsign;
this.shortPathBearing = Math.round(data.bearing * 10) / 10;
this.longPathBearing = (this.shortPathBearing + 180) % 360;
this.lastBeamingTime = new Date();
```

### 5. New HTML Panel (radio-control.html)
Added beaming display panel below the rotor controls with:
- "Spot beaming for: [CALLSIGN]" header
- SP: [bearing]° with GO button
- LP: [bearing]° with GO button
- Only visible when a spot is currently being beamed to and rotor is enabled

### 6. CSS Styling (radio-control.html)
New styles for the beaming display:
- `.beaming-display` - Main container with blue left border accent
- `.beaming-title` - Section label ("Spot beaming for:")
- `.beaming-callsign` - Callsign display (blue, monospace font)
- `.beaming-row` - SP/LP row layout
- `.beaming-label` - "SP" or "LP" label
- `.beaming-degrees` - Bearing value display
- `.beaming-go-btn` - Manual GO button with hover/active states

## How It Works

### Scenario 1: AUTO Rotor Enabled
1. User clicks a spot in the Spots panel or types callsign in Log QSO
2. Frontend calls `rotorAutoGoto()` with spot data
3. Backend calculates bearing and moves rotor
4. Frontend receives bearing response and:
   - Displays callsign in beaming panel
   - Shows SP bearing (as received from backend)
   - Calculates LP bearing (SP + 180°)
   - Shows both with GO buttons
5. User can optionally click GO next to LP to switch to long path

### Scenario 2: AUTO Rotor Disabled
1. System still displays spot/callsign and bearing info if a spot was recently looked up
2. User can manually click GO on SP or LP to rotate antenna
3. Bearing calculations are always available

## Visual Layout

```
┌─────────────────────────────────────────────────────────────┐
│ OM0RX Flex / Radio Control                    Time 14:35 UTC │
└─────────────────────────────────────────────────────────────┘

┌──────────────────┐  ┌──────────────────────────┐
│ AZ: 251°         │  │ Spot beaming for:        │  
│ [GO] [AUTO]      │  │ WP3PJ                    │  <-- New Panel
│                  │  │ SP: 251.5° [GO]          │
│ [Director  ] N S │  │ LP: 71.5° [GO]           │
│ E W              │  │                          │
└──────────────────┘  └──────────────────────────┘

        ┌──────────────────┐
        │   28.050 MHz     │
        │ NB NR ANF APF    │
        └──────────────────┘
```

## Benefits

1. **Quick Manual Override** - If AUTO decides differently or is disabled, user can easily switch between SP/LP with one click
2. **Visual Feedback** - Always see what spot is currently being tracked
3. **No Manual Math** - LP is automatically calculated (180° opposite)
4. **Clean Integration** - Fits naturally in the rotor control area
5. **Works with Configuration** - Respects rotor enabled/disabled and AUTO enabled/disabled states

## Technical Details

### Long Path Calculation
```javascript
longPathBearing = (shortPathBearing + 180) % 360
// Examples:
// SP: 251° → LP: 71° (251 + 180 = 431, 431 % 360 = 71)
// SP: 45° → LP: 225° (45 + 180 = 225)
// SP: 0° → LP: 180°
```

### Bearing Precision
- Short Path: Rounded to 1 decimal place from backend calculation
- Long Path: Calculated as SP + 180°, inherits SP precision
- Display: Shows 1 decimal place in UI

### Data Flow
```
DX Cluster Spot
     ↓
Backend: process_dx_spot()
     ↓ (extract lat/lon/gridsquare)
/api/rotor/auto/goto
     ↓ (calculate bearing)
Frontend: rotorAutoGoto()
     ↓ (receive bearing response)
Update: currentBeamingCallsign, shortPathBearing, longPathBearing
     ↓
Display SP/LP panel with GO buttons
```

## Files Modified

1. **frontend/app.js**
   - Added data properties (lines 319-323)
   - Updated `rotorAutoGoto()` to capture bearings (lines 2232-2236)
   - Added `rotorGotoShortPath()` function (lines 2252-2260)
   - Added `rotorGotoLongPath()` function (lines 2262-2270)

2. **frontend/radio-control.html**
   - Added CSS styles for beaming display (lines 400-467)
   - Added HTML panel (lines 723-741)

## Testing Checklist

- [ ] Rotor AUTO enabled in config
- [ ] Click on a DX spot → beaming panel should appear with callsign and bearings
- [ ] SP and LP bearings should differ by ~180°
- [ ] Click SP GO button → rotor moves to SP bearing
- [ ] Click LP GO button → rotor moves to LP bearing (180° opposite)
- [ ] Type callsign in Log QSO → beaming panel updates with new callsign
- [ ] Rotor AUTO disabled → beaming panel still shows last tracked spot
- [ ] Rotor disabled in config → beaming panel hidden even if data available

## Future Enhancements

- [ ] Add magnetic declination adjustment for each location
- [ ] Show band name next to bearings
- [ ] Add elevation angle display (requires antenna height info)
- [ ] Save last 5 beamed spots for quick re-access
- [ ] Add audio alert when rotor reaches target bearing