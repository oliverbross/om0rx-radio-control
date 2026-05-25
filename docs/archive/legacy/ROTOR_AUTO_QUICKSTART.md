# Rotor AUTO - Quick Start Guide

## 30-Second Setup

### Step 1: Configure Your Home Location
Edit `config.py`:
```python
ROTOR_HOME_GRID = "JN88TQ"  # Your Maidenhead grid square
ROTOR_HOME_LAT = 48.17      # Auto-calculated from grid
ROTOR_HOME_LON = 17.08      # Auto-calculated from grid
```

### Step 2: Select Your Rotor Bands
In `config.py`, set which bands have your rotator antenna:
```python
ROTOR_BANDS = {
    "20m": True,   # ← Rotor antenna on these bands
    "17m": True,
    "15m": True,
    "10m": True,
    "40m": False,  # ← No rotor here
}
```

### Step 3: Enable AUTO Mode
In the web UI:
- Click the **"AUTO"** button in the rotor control section
- Button shows green when active
- Or set in `config.py`: `ROTOR_AUTO_ENABLED = True`

## Usage

### Auto-Rotate to Spots
1. **Click a spot** from the cluster list
2. **Radio tunes** to frequency
3. **Rotor waits 2 seconds** (you can cancel)
4. **Rotor auto-turns** to station's bearing

### Auto-Rotate to Manual Callsigns
1. **Type or paste callsign** in the log form
2. **Wait 1 second** after typing stops
3. **QRZ lookup** gets gridsquare
4. **Rotor waits 2 seconds** (you can cancel)
5. **Rotor auto-turns** toward station

### Cancel AUTO Action
- Click **"Cancel AUTO"** button during the 2-second countdown
- Or just wait and nothing happens if AUTO disabled

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Rotor not moving | Check: Rotor enabled? Band in config? Grid square from QRZ? |
| Wrong direction | Verify ROTOR_HOME_GRID is correct |
| Too slow | Network/QRZ delay - normal, can take 3-5 seconds |
| AUTO button doesn't appear | Rotor must be enabled in config first |

## API Endpoints (Advanced)

### Check Bearing (No Rotor Move)
```bash
curl -X POST http://localhost:8000/api/rotor/auto/bearing \
  -H "Content-Type: application/json" \
  -d '{"callsign":"W5XYZ","frequency_khz":14200,"gridsquare":"CN87"}'
```

### Get AUTO Configuration
```bash
curl http://localhost:8000/api/rotor/auto/status
```

### Update AUTO Configuration
```bash
curl -X POST http://localhost:8000/api/rotor/auto/config \
  -H "Content-Type: application/json" \
  -d '{
    "home_grid":"JN88TQ",
    "home_lat":48.17,
    "home_lon":17.08,
    "bands":{"20m":true,"10m":true},
    "auto_enabled":true
  }'
```

## Examples

### Example 1: Austria → Seattle
```
Home: JN88TQ (Austria)
Station: CN87 (Seattle)
Bearing: 205.5° (South-Southwest)
```

### Example 2: Germany → Japan
```
Home: JO73AA (Germany)
Station: QN03 (Sapporo, Japan)
Bearing: 55° (Northeast)
```

## Features

✅ Automatic bearing calculation  
✅ Grid square ↔ Coordinate conversion  
✅ QRZ integration for gridsquares  
✅ 2-second cancellation delay  
✅ Band-aware (rotor skipped if band not configured)  
✅ Manual frequency tracking  
✅ RESTful API for integrations  

## Keyboard Shortcuts (When available)

- **A** = Toggle AUTO mode
- **Esc** = Cancel pending AUTO action

## Persistence

- Configuration saved in `config.py` and backend memory
- AUTO mode toggle persists across app restarts
- Grid squares cached from QRZ lookups

## Performance

- Bearing calculation: **<1ms**
- Grid conversion: **<1ms**
- QRZ lookup: **1-3 seconds** (network)
- Total trigger → rotor movement: **2-5 seconds**

## Support

- Check browser console for error messages
- Look for 🤖, ⏱️, ✅, ❌ emojis in logs
- Backend logs show rotor commands: `tail -f logs/flex_debug.log | grep -i rotor`

---

**You're all set! Start auto-rotating rotator. 73!**