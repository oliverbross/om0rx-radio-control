# SmartSDR Panadapter Spot Colors - DXCC Status Based

## Overview
Spots are automatically sent to SmartSDR Panadapter with colors that indicate their DXCC status. This helps you quickly identify priority targets on the radio display.

## Color Scheme

| DXCC Status | Color | Hex Code | Priority | Meaning |
|-------------|-------|----------|----------|---------|
| **ATNO** | 🟠 Orange | `#FFFF8C00` | ⭐⭐⭐ HIGHEST | Already Taken Number On - Never worked this entity before! |
| **Confirmed** | 🟢 Bright Green | `#FF00D000` | ⭐ LOW | Entity already confirmed - you have LoTW confirmation |
| **Confirmed/New Band** | 🟢 Lime Green | `#FF32CD32` | ⭐⭐ MEDIUM | Confirmed entity but new band opportunity |
| **Confirmed/New Mode** | 🟢 Lime Green | `#FF32CD32` | ⭐⭐ MEDIUM | Confirmed entity but new mode opportunity |
| **Confirmed/New Band+Mode** | 🟢 Lime Green | `#FF32CD32` | ⭐⭐ MEDIUM | Confirmed entity with both band AND mode opportunity |
| **Worked** | 🔵 Blue | `#FF0066FF` | ⭐ LOW | Already worked this entity (but not confirmed yet) |
| **Worked/New Band** | 🔷 Cyan | `#FF00FFFF` | ⭐⭐ MEDIUM | Worked entity with new band opportunity |
| **Worked/New Mode** | 🟡 Yellow | `#FFFFFF00` | ⭐⭐ MEDIUM | Worked entity with new mode opportunity |
| **Worked/New Band+Mode** | 🟣 Magenta | `#FFFF00FF` | ⭐⭐⭐ HIGH | Most interesting - worked but never on this band+mode combo! |
| **Unknown** | ⚫ Gray | `#FFB0B0B0` | ⭐ LOW | Status couldn't be determined |
| *(No Status)* | ⚪ White | `#FFFFFFFF` | DEFAULT | Default fallback |

## Priority Guidelines

When tuning the radio, focus on spots in this order:

1. **🟠 Orange (ATNO)** - These are your most important targets. No QSO recorded with this entity!
2. **🟣 Magenta (Worked/New Band+Mode)** - Very valuable: you've worked them, but never on this exact band+mode
3. **🔷 Cyan & 🟡 Yellow (Worked with new opportunities)** - Good secondary targets
4. **🟢 Green (Confirmed opportunities)** - Already confirmed but band/mode new
5. **🔵 Blue (Just Worked)** - Already have them, lower priority

## How It Works

1. **Automatic Classification**: Each incoming spot is classified based on your Wavelog database
2. **DXCC Status Determined**: The system checks if you've worked the entity, what band/modes are confirmed
3. **Color Assigned**: Based on status, a specific color is sent to SmartSDR
4. **Displayed on Panadapter**: Spots appear on your radio display in the assigned color
5. **Quick Visual Scanning**: You can instantly see valuable targets by color

## Implementation Details

The color mapping is handled by `get_dxcc_color()` function in `utils.py`:

- Takes DXCC status string as input
- Returns SmartSDR-compatible color hex code (#AARRGGBB format)
- Applied to ALL spots sent via:
  - `services/spots.py` - Main spot processing
  - `services/background_tasks.py` - Background processing
  - `backend/core/__init__.py` - Backend service

## Configuration

To modify colors, edit the `get_dxcc_color()` function in `utils.py`:

```python
def get_dxcc_color(dxcc_status: str) -> str:
    """Map DXCC status to SmartSDR panadapter color"""
    # Color format: #AARRGGBB (alpha + RGB)
    # Modify hex values as needed
```

## Notes

- Color persistence: Spot colors persist for the 1-hour spot lifetime on your radio
- Real-time updates: Imported spots update with current colors based on your log
- Alpha channel: All colors use full opacity (FF prefix)
- The color is logged for debugging: Check logs for `[Color: #...]` messages

## Debugging

To verify colors are being sent correctly:

1. Check application logs for: `Spot sent to SmartSDR: CALLSIGN FREQ [Color: #AARRGGBB]`
2. Verify DXCC classification: `[dxcc_status]` shown in spot log message
3. Enable debug logging in config for detailed color mapping information