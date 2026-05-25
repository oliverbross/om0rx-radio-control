# Rotor AUTO Complete Implementation Guide

## Overview
This document describes the complete implementation of the Rotor AUTO beaming display system across the modular JavaScript architecture.

## Architecture

### Files Involved
1. **Frontend**:
   - `frontend/index.html` - Beaming display HTML UI elements
   - `frontend/js/app-main.js` - Main Vue app with rotor AUTO state initialization
   - `frontend/js/radio-controls.js` - Rotor AUTO methods and bearing calculations
   - `frontend/js/dx-spots.js` - Spot tuning logic that triggers rotor AUTO

2. **Backend**:
   - `backend/main.py` - Rotor AUTO API endpoints
   - `rotor_config.json` - Rotor configuration persistence

## System Flow

### 1. Initialization (App Startup)
```
App Start
  ↓
initializeApp()
  ↓
loadConfig()  // Load main config (ROTOR_ENABLED, etc.)
  ↓
If rotorEnabled:
  ↓
  loadRotorStatus()      // Check rotor hardware status
  loadRotorAutoConfig()  // Load AUTO settings from backend
  ↓
  Backend reloads rotor_config.json
  ↓
  Frontend receives:
    - auto_enabled (true/false)
    - home_grid (e.g., "JN88TQ")
    - home_lat (e.g., 48.17)
    - home_lon (e.g., 17.08)
    - bands (dict of band: enabled pairs)
```

### 2. User Clicks a Spot
```
User clicks DX spot
  ↓
tuneToSpot(spot)
  ↓
Collects spot data:
  - callsign
  - frequency (MHz)
  - gridsquare (optional)
  - latitude/longitude (optional)
  ↓
Logs status: "🎯 Tuning to [callsign]..."
  ↓
Tunes radio to frequency
  ↓
Populates logging form with spot data
  ↓
Checks rotor status:
  if (rotorAutoEnabled && rotorEnabled):
    ↓
    Calls rotorAutoGoto(callsign, freq_khz, grid, lat, lon)
    ↓
    Waits 2 seconds (for user cancellation)
    ↓
    Sends to backend: /api/rotor/auto/goto
    ↓
    Backend checks:
      - AUTO enabled?
      - Band enabled for rotor?
      - Can calculate bearing? (grid or lat/lon)
    ↓
    If all checks pass:
      - Calculates bearing using Vincenty algorithm
      - Moves rotor to bearing
      - Returns: {ok: true, bearing, short_path_bearing, long_path_bearing}
    ↓
    Frontend receives response:
      - Updates beaming display with SP/LP bearings
      - Shows status: "🤖 Rotor → XXX° for [callsign]"
  
  elif (rotorEnabled && hasGridOrCoords):
    ↓
    Even if AUTO disabled, calculate bearings for manual rotor control
    ↓
    Sends to backend: /api/rotor/auto/bearing
    ↓
    Backend calculates bearing
    ↓
    Returns: {ok: true, bearing, short_path_bearing, long_path_bearing}
    ↓
    Frontend updates beaming display immediately
```

## Frontend State Properties

### In `app-main.js` data():
```javascript
// Rotor AUTO Control
rotorAutoEnabled: false,        // Whether AUTO mode is enabled
rotorAutoTimer: null,           // Timeout for 2-second delay
rotorAutoPending: null,         // Info about pending AUTO action

// Rotor AUTO Configuration
rotorHomeGrid: 'JN88TQ',        // Home grid square
rotorHomeLat: 48.17,            // Home latitude
rotorHomeLon: 17.08,            // Home longitude
rotorBands: {                   // Which bands have rotor enabled
    "160m": false,
    "80m": false,
    ...
    "20m": true,
    "17m": true,
    ...
}

// Beaming Display
currentBeamingCallsign: null,   // Callsign being tracked
shortPathBearing: null,         // SP bearing in degrees (0-360)
longPathBearing: null,          // LP bearing in degrees (0-360)
lastBeamingTime: null,          // When beaming was last updated
```

## Frontend Methods

### In `radio-controls.js`:

#### `loadRotorAutoConfig()`
- Fetches `/api/rotor/auto/status`
- Sets the rotor AUTO state properties from server response
- Called at app initialization and periodically

#### `saveRotorAutoConfig()`
- Sends `/api/rotor/auto/config` POST request
- Persists rotor AUTO settings to backend (which saves to rotor_config.json)
- Called when user changes AUTO settings

#### `toggleRotorAuto()`
- Toggles `rotorAutoEnabled` boolean
- Calls `saveRotorAutoConfig()` to persist

#### `rotorAutoGoto(callsign, frequency_khz, gridsquare, latitude, longitude)`
- Main AUTO rotor method
- Implements 2-second delay for user cancellation
- Sends `/api/rotor/auto/goto` POST request
- Handles response:
  - Updates beaming display with short_path_bearing and long_path_bearing
  - Shows status message
  - Handles errors (band disabled, insufficient data, etc.)

#### `rotorGotoShortPath()`
- Sets rotor azimuth to shortPathBearing
- Calls `rotorGoto()` to send command

#### `rotorGotoLongPath()`
- Sets rotor azimuth to longPathBearing
- Calls `rotorGoto()` to send command

### In `dx-spots.js`:

#### `tuneToSpot(spot)`
- Triggered when user clicks a DX spot
- Logs status and tunes radio
- Populates logging form
- **CRITICAL**: Decides between AUTO vs bearing-only:
  1. If AUTO enabled + rotor enabled: calls `rotorAutoGoto()`
  2. Else if rotor enabled + has grid/coords: calls `/api/rotor/auto/bearing`
  3. Else: no rotor action (but beaming display may show previous callsign)

## Backend API Endpoints

### `/api/rotor/auto/status` (GET)
**Returns**: Current rotor AUTO configuration
```json
{
    "ok": true,
    "auto_enabled": true,
    "home_grid": "JN88TQ",
    "home_lat": 48.17,
    "home_lon": 17.08,
    "bands": {"20m": true, "17m": true, ...},
    "delay_sec": 2.0
}
```

### `/api/rotor/auto/config` (POST)
**Request**:
```json
{
    "home_grid": "JN88TQ",
    "home_lat": 48.17,
    "home_lon": 17.08,
    "bands": {"20m": true, "17m": true, ...},
    "auto_enabled": true
}
```
**Action**: Saves config to rotor_config.json and updates config object

### `/api/rotor/auto/bearing` (POST)
**Purpose**: Calculate bearing to a station WITHOUT moving rotor
**Request**:
```json
{
    "callsign": "PJ6Y",
    "frequency_khz": 28300.0,
    "gridsquare": "FK87KN",
    "latitude": null,
    "longitude": null
}
```
**Response**:
```json
{
    "ok": true,
    "bearing": 275.0,
    "short_path_bearing": 275.0,
    "long_path_bearing": 95.0,
    "band": "10m",
    "band_enabled": true,
    "callsign": "PJ6Y",
    "source": "gridsquare"
}
```

### `/api/rotor/auto/goto` (POST)
**Purpose**: Calculate bearing AND move rotor to it
**Request**: Same as `/bearing`
**Response**: Same as `/bearing` plus rotor movement

## Beaming Display HTML
Located in `frontend/index.html` (lines 1455-1480):
```html
<div class="beaming-display" v-if="currentBeamingCallsign" style="margin-top: 0;">
    <div style="display: flex; gap: 6px; align-items: center; margin-bottom: 4px;">
        <span class="beaming-title">Beaming for:</span>
        <span class="beaming-callsign">{{ currentBeamingCallsign }}</span>
    </div>
    
    <!-- Short Path Row -->
    <div class="beaming-row" v-if="shortPathBearing !== null">
        <span class="beaming-label">SP:</span>
        <span class="beaming-degrees">{{ shortPathBearing.toFixed(1) }}°</span>
        <button @click="rotorGotoShortPath" class="beaming-go-btn">GO</button>
    </div>
    
    <!-- Long Path Row -->
    <div class="beaming-row" v-if="longPathBearing !== null">
        <span class="beaming-label">LP:</span>
        <span class="beaming-degrees">{{ longPathBearing.toFixed(1) }}°</span>
        <button @click="rotorGotoLongPath" class="beaming-go-btn">GO</button>
    </div>
</div>
```

The display shows ONLY when:
1. `currentBeamingCallsign` is not null (user has selected a callsign)
2. `shortPathBearing` and `longPathBearing` are set from bearing calculation

## Configuration Persistence

### rotor_config.json
Located at project root, stores:
```json
{
    "ROTOR_HOME_GRID": "JN88TQ",
    "ROTOR_HOME_LAT": 48.17,
    "ROTOR_HOME_LON": 17.08,
    "ROTOR_BANDS": {
        "160m": false, "80m": false, ..., "20m": true, ...
    },
    "ROTOR_AUTO_ENABLED": true
}
```

**Lifecycle**:
1. Backend loads at startup: `_load_rotor_config()`
2. Every rotor AUTO API call reloads this file: `_load_rotor_config()`
3. User saves settings via UI: `saveRotorAutoConfig()` → API POST → backend saves JSON
4. Next API call reloads updated values

## Bearing Calculation

### Algorithm
Uses Vincenty's algorithm for accuracy:
1. Converts gridsquare to lat/lon (if gridsquare provided)
2. Calculates great-circle distance between home and station
3. Calculates bearing using Vincenty initial bearing formula
4. Returns bearing: 0° = North, 90° = East, 180° = South, 270° = West

### Short Path vs Long Path
- **Short Path**: bearing (0-360°)
- **Long Path**: (bearing + 180°) % 360

### Preferences
1. Use gridsquare if available (more accurate, from QRZ)
2. Fall back to latitude/longitude if provided
3. Return error if neither available

## Error Handling

### When Beaming Display Won't Show
1. **Spot has no location data**: Rotor can't calculate bearing
   - Solution: Ensure spot has gridsquare or coordinates
2. **Band not enabled for rotor**: `ROTOR_BANDS[band]` is false
   - Solution: Enable band in rotor configuration
3. **AUTO mode not enabled**: Backend or config says `ROTOR_AUTO_ENABLED: false`
   - Solution: Toggle AUTO button or check rotor_config.json
4. **Rotor hardware not connected**: Backend can't move rotor
   - Solution: Check rotor connection in config, but bearings should still calculate

### Logging
Comprehensive console logging for debugging:
- `🔍 Rotor status: ...` - When spot clicked, shows all rotor flags
- `🤖 AUTO rotor triggered for ...` - AUTO method called
- `⏱️ Rotor AUTO pending: ...` - Waiting before sending
- `📡 Bearing calculated for ...` - Bearing received
- `✅ Beaming display updated: SP=XX°, LP=YY°` - Display updated
- `⚠️` - Warning/error conditions

## Testing Checklist

### Basic Functionality
- [ ] Click a spot with grid square → beaming display appears in 2 seconds
- [ ] Beaming display shows callsign and bearings
- [ ] SP GO button moves rotor to short path
- [ ] LP GO button moves rotor to long path

### AUTO Disabled
- [ ] Toggle AUTO off
- [ ] Click a spot with grid → beaming display appears immediately (no 2-sec delay)
- [ ] Rotor should NOT move automatically

### AUTO Enabled
- [ ] Toggle AUTO on
- [ ] Click a spot → rotor should move within 2 seconds
- [ ] Beaming display should show new bearings

### Band Filtering
- [ ] Enable rotor for 20m only
- [ ] Click 20m spot → rotor moves
- [ ] Click 40m spot → rotor doesn't move, but bearings still show

### Error Conditions
- [ ] Click spot with NO grid/coords → no beaming display, no rotor movement
- [ ] Disconnect rotor hardware → bearings still calculate, rotor doesn't move
- [ ] Disable AUTO in config → rotor doesn't move, but bearings still calculate

## Recent Changes (Modular Refactor)

### What Was Added
1. Enhanced `/api/rotor/auto/bearing` to return `short_path_bearing` and `long_path_bearing` fields for consistency
2. Updated frontend to handle new response format
3. Added comprehensive logging throughout the flow
4. Enhanced callsign watcher to update beaming display

### What Stays The Same
1. Core bearing calculation algorithm
2. 2-second AUTO delay mechanism
3. Band filtering logic
4. Configuration persistence to rotor_config.json
5. Manual rotor GO buttons (SP/LP)

## Known Limitations
1. Bearing calculation takes gridsquare over lat/lon - if both provided, lat/lon ignored
2. No real-time bearing updates - only when spot clicked or callsign entered
3. Rotor can only move to one band at a time
4. Band toggling requires UI interaction (no auto-band-switching)

## Future Enhancements
1. Real-time bearing updates as frequency changes
2. Rotor preset buttons for common bearings
3. Rotor status display (current azimuth, moving, errors)
4. Automatic band switching based on frequency
5. Custom rotor speed/acceleration settings