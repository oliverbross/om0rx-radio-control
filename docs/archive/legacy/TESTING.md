# Testing Guide - Wave-Flex Spot Sync FlexRadio Controls

## Quick Start

### 1. Prerequisites
```
✅ SmartSDR is running on your FlexRadio
✅ Radio IP: 192.168.0.199 (verify in config.py)
✅ Port 4992 is accessible
✅ You have a slice active (usually Slice A)
```

### 2. Run the Application
```powershell
cd c:\Projects\om0rx-radio-control
python dxbridge.py
```

### 3. Watch for Startup Messages
Look for these in the console:
```
✅ File logging enabled: c:\Projects\om0rx-radio-control\flex_debug.log
INFO FlexCtl initialized for 192.168.0.199:4992 slice 0
INFO FlexCtl connecting to 192.168.0.199:4992...
INFO FlexCtl connected successfully
INFO Fetching initial radio state...
INFO Got initial levels: {'audio_level': 50, 'rfpower': 25, ...}
```

## What Was Fixed

### ❌ BEFORE (Broken)
```python
# WRONG API parameter names:
audio_gain=X      # ❌ Does not exist in API
tune_power=X      # ❌ Wrong - has underscore
mic_level=X       # ❌ Wrong - has underscore

# WRONG commands:
radio set tune=1  # ❌ Does not work
transmit set mox=1 # ❌ Does not work
```

### ✅ AFTER (Fixed)
```python
# CORRECT API parameter names:
audio_level=X     # ✅ Correct (Slice parameter)
tunepower=X       # ✅ Correct (no underscore)
miclevel=X        # ✅ Correct (no underscore)

# CORRECT commands:
transmit tune on  # ✅ Works
xmit on          # ✅ Works
```

## Control Testing Checklist

### Volume Control
```
1. Move volume slider → Audio should change in real-time
2. Check log: "FlexCtl SEND: slice set 0 audio_level=XX"
3. Click mute checkbox → Audio should mute
4. Check log: "FlexCtl SEND: slice set 0 audio_mute=1"
```

### Drive/RF Power
```
1. Move drive slider → RF power changes
2. Check log: "FlexCtl SEND: transmit set rfpower=XX"
3. Value display should update
```

### Tune Power
```
1. Move tune slider → Tune power changes
2. Check log: "FlexCtl SEND: transmit set tunepower=XX"
3. NOT "tune_power" (old wrong name)
```

### Mic Level
```
1. Move mic slider → Mic level changes
2. Check log: "FlexCtl SEND: transmit set miclevel=XX"
3. NOT "mic_level" (old wrong name)
```

### TUNE Button
```
1. Click TUNE → Button text changes to "TUNE ON"
2. Check log: "FlexCtl SEND: transmit tune on"
3. Radio goes into tune mode
4. Click again → Button text changes to "TUNE"
5. Check log: "FlexCtl SEND: transmit tune off"
```

### MOX Button
```
1. Click MOX → Button text changes to "MOX ON"
2. Check log: "FlexCtl SEND: xmit on"
3. Radio transmits
4. Click again → Button text changes to "MOX"
5. Check log: "FlexCtl SEND: xmit off"
```

### VOX Checkbox
```
1. Check VOX → VOX enabled
2. Check log: "FlexCtl SEND: transmit set vox_enable=1"
```

### Band Buttons
```
1. Click "20M" → Radio tunes to 14.074 MHz
2. Check log: "FlexCtl set_band: 20m -> 14.074 MHz"
3. Check log: "FlexCtl SEND: slice tune 0 14.074000"
```

### Mode Buttons
```
1. Click "USB" → Mode changes to USB
2. Check log: "FlexCtl SEND: slice set 0 mode=USB"
3. Filter buttons should update for USB presets
```

### Filter Buttons
```
1. Click a filter (e.g., "2.4K") → Filter changes
2. Check log: "FlexCtl SEND: slice set 0 filter_lo=100 filter_hi=2500"
3. Filter display should update (Lo: 100  Hi: 2500)
```

## Initial State Reading

### What Should Happen on Startup
```
✅ Volume slider shows current radio volume
✅ Drive slider shows current RF power
✅ Tune slider shows current tune power
✅ Mic slider shows current mic level
✅ Filter display shows current lo/hi values
✅ All values match what's in SmartSDR GUI
```

### Check the Log
Open `flex_debug.log` and look for:
```
INFO FlexCtl querying radio for initial state...
DEBUG FlexCtl STATUS: S0|slice 0 freq=14.074 mode=USB audio_level=50 ...
DEBUG   Parsed audio_level=50
DEBUG   Parsed filter_lo=100
DEBUG   Parsed filter_hi=2900
INFO FlexCtl initial state: {'audio_level': 50, 'rfpower': 25, ...}
INFO Set volume slider to 50
INFO Set drive slider to 25
```

## Troubleshooting

### Problem: "FlexCtl connect FAILED"
**Cause:** Cannot reach radio
**Fix:**
1. Check radio IP in config.py (currently 192.168.0.199)
2. Ping the radio: `ping 192.168.0.199`
3. Check SmartSDR is running
4. Check firewall allows port 4992

### Problem: "FlexCtl command ... returned error: 5000XXXX"
**Cause:** Command failed on radio side
**Fix:**
1. Check flex_debug.log for exact error code
2. Common errors:
   - `50000004` = Wrong number of parameters
   - `5000000D` = Invalid slice receiver
   - `50000033` = Parameter out of range
   - `5000002D` = Bad field name

### Problem: Controls don't work
**Check these in order:**
1. Is connection established? Look for "FlexCtl connected successfully"
2. Are commands being sent? Look for "FlexCtl SEND: ..." in log
3. Are errors being returned? Look for "FlexCtl command ... returned error"
4. Is slice active? Try clicking a band button first

### Problem: Initial values not showing
**Check:**
1. Is get_current_levels() being called? Look for "Fetching initial radio state"
2. Are status messages received? Look for "FlexCtl STATUS: ..."
3. Are values parsed? Look for "Parsed audio_level=..." messages
4. Are sliders updated? Look for "Set volume slider to ..." messages

## Log File Locations

### Main Debug Log
```
c:\Projects\om0rx-radio-control\flex_debug.log
```

### What to Look For
```
✅ INFO messages: High-level operations (connect, set volume, etc.)
✅ DEBUG messages: Detailed command/response traffic
⚠️ WARNING messages: Non-fatal issues (connection retry, etc.)
❌ ERROR messages: Serious problems (command failed, exception, etc.)
```

### Log Rotation
- Log file max size: 2 MB
- Backups kept: 5 (flex_debug.log.1, flex_debug.log.2, etc.)
- Old logs automatically rotated

## API Reference (Quick)

### Slice Commands (Receiver Control)
```
slice set 0 audio_level=50      # Volume 0-100
slice set 0 audio_mute=1        # Mute on/off
slice set 0 mode=USB            # Set mode
slice set 0 filter_lo=100       # Set low filter edge
slice set 0 filter_hi=2900      # Set high filter edge
slice tune 0 14.074000          # Tune to frequency
slice set 0 active=1            # Activate slice
```

### Transmit Commands
```
transmit set rfpower=50         # RF power 1-100
transmit set tunepower=10       # Tune power 1-100
transmit set miclevel=75        # Mic level 0-100
transmit tune on                # Start tune mode
transmit tune off               # Stop tune mode
transmit set vox_enable=1       # Enable VOX
```

### Xmit Commands (Transmit/Receive Toggle)
```
xmit on                         # Start transmitting (MOX)
xmit off                        # Stop transmitting
```

### Subscription Commands
```
sub slice all                   # Subscribe to slice updates
sub transmit all                # Subscribe to TX updates
sub radio all                   # Subscribe to radio updates
```

## Expected Behavior Summary

| Control | Action | Log Entry | Radio Response |
|---------|--------|-----------|----------------|
| Volume slider | Move to 75 | `slice set 0 audio_level=75` | Audio volume changes |
| Mute checkbox | Check | `slice set 0 audio_mute=1` | Audio mutes |
| Drive slider | Move to 50 | `transmit set rfpower=50` | RF power changes |
| Tune slider | Move to 20 | `transmit set tunepower=20` | Tune power changes |
| Mic slider | Move to 80 | `transmit set miclevel=80` | Mic level changes |
| TUNE button | Click | `transmit tune on` | Radio enters tune mode |
| MOX button | Click | `xmit on` | Radio transmits |
| VOX checkbox | Check | `transmit set vox_enable=1` | VOX enabled |
| Band button (20M) | Click | `slice tune 0 14.074000` | Tunes to 14.074 MHz |
| Mode button (USB) | Click | `slice set 0 mode=USB` | Mode changes to USB |
| Filter (2.4K) | Click | `slice set 0 filter_lo=100 filter_hi=2500` | Filter changes |

## Success Criteria

### ✅ All Working Correctly
```
✅ Application starts without errors
✅ Connects to radio (check log)
✅ Initial values loaded and displayed
✅ All sliders control radio in real-time
✅ All buttons/checkboxes work
✅ Commands appear in log with correct parameter names
✅ No error messages in log
✅ Radio responds to all controls
```

## Getting Help

If you see errors:

1. **Check flex_debug.log first** - Most issues are logged with details
2. **Look for ERROR or WARNING messages** - They explain what went wrong
3. **Check the exact command sent** - Compare with API reference above
4. **Verify radio state** - Make sure slice is active, SmartSDR running
5. **Test with SmartSDR GUI** - Verify radio itself is working

## Useful Debug Commands

### Check Connection
```powershell
# Ping radio
ping 192.168.0.199

# Test port connectivity (requires telnet client)
telnet 192.168.0.199 4992
```

### View Recent Log
```powershell
# View last 50 lines of log
Get-Content c:\Projects\om0rx-radio-control\flex_debug.log -Tail 50

# Follow log in real-time (like tail -f)
Get-Content c:\Projects\om0rx-radio-control\flex_debug.log -Wait -Tail 20
```

### Find Errors in Log
```powershell
# Find all ERROR messages
Select-String -Path c:\Projects\om0rx-radio-control\flex_debug.log -Pattern "ERROR"

# Find all WARNING messages
Select-String -Path c:\Projects\om0rx-radio-control\flex_debug.log -Pattern "WARNING"

# Find specific command
Select-String -Path c:\Projects\om0rx-radio-control\flex_debug.log -Pattern "audio_level"
```

---

**Last Updated:** 2025-01-24  
**Status:** All FlexRadio controls operational with comprehensive logging