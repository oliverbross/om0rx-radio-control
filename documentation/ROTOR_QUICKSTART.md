# Rotator Control - Quick Start Guide

## Overview
This guide shows you how to use the Microham ARCO rotator control feature.

## Part 1: Enable the Rotator

### Option A: Edit Config File (Recommended for Persistent Setup)

1. Open `config.py` in the project root
2. Find the "Rotator (ARCO) Configuration" section (around line 109)
3. Change the parameters to match your setup:

```python
# === Rotator (ARCO) Configuration ===
ROTOR_ENABLED = True                     # ← Change to True
ROTOR_TYPE = "Microham ARCO"             # Rotator type
ROTOR_HOST = "192.168.0.198"             # ← Your rotator's IP
ROTOR_PORT = 4001                        # ← Your rotator's port
ROTOR_PROTOCOL = "DCU-1"                 # ← "DCU-1" or "Yaesu GS-232A"
ROTOR_TIMEOUT_SEC = 2.5                  # Read timeout (usually OK as-is)
```

4. Save the file and restart the application

### Option B: Use API at Runtime (For Testing)

Send this command to enable the rotator without restarting:

```bash
curl -X POST http://localhost:8000/api/rotor/config \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "host": "192.168.0.198",
    "port": 4001,
    "protocol": "DCU-1",
    "timeout": 2.5
  }'
```

Then refresh your browser - the rotator controls should appear!

## Part 2: Using the Rotator

Once enabled, you'll see the rotator controls in the top-left corner of the UI:

```
┌─────────────────────┐
│ Az: [ 45 ] ° [GO]   │  ← Manual azimuth control
│ [Direction ▼]       │
│  [N] [S] [E] [W]    │  ← Cardinal direction buttons
└─────────────────────┘
```

### Manual Control - Go to Specific Azimuth

1. Type the azimuth value (0-359 degrees) in the input box
2. Click the **GO** button
3. The rotator will move to that bearing

**Example**: To point North (0°):
- Type `0` in the box
- Click GO
- Rotator moves to 0°

### Quick Directions - Cardinal Points

Click any direction button to move the rotator instantly:

| Button | Azimuth | Direction |
|--------|---------|-----------|
| **N** | 0° | North |
| **E** | 90° | East |
| **S** | 180° | South |
| **W** | 270° | West |

**Example**: To point East (90°):
- Click the **E** button
- Rotator moves to 90°

### View Current Azimuth

The current position is shown in the input box and updates every 5 seconds automatically.

## Part 3: Configuration Details

### Find Your Rotator's IP and Port

**Method 1: Router/Network Admin Panel**
- Log into your router
- Look for connected devices
- Find "ARCO" or your rotator's hostname
- Note the IP address and port

**Method 2: Rotator Manual**
- Check your rotator's manual for default IP/port
- Common defaults:
  - IP: `192.168.0.198` or `192.168.1.200`
  - Port: `4001` or `4002`

**Method 3: Network Scan**
```bash
# Using PowerShell (Windows)
Test-NetConnection -ComputerName 192.168.0.198 -Port 4001
```

### Protocol Selection

Choose based on your rotator model:

**DCU-1/Rotor-EZ** (Default)
- Microham ARCO uses this
- Commands: `AP1xxx`, `AM1`, `AS1`, `AI1`
- Recommended: Leave as "DCU-1"

**Yaesu GS-232A**
- Yaesu rotators use this
- Commands: `Mxxx`, `A`, `C`
- Use if you have a Yaesu rotator

## Part 4: Troubleshooting

### Rotator Controls Don't Appear
❌ **Problem**: You don't see the rotator controls in the UI

✅ **Solutions**:
1. Check if ROTOR_ENABLED is set to True in config.py
2. Restart the application if you edited config.py
3. Refresh your browser (Ctrl+F5 or Cmd+Shift+R)
4. Check browser console for errors (F12 → Console)

### "Rotator not enabled" Alert
❌ **Problem**: Click GO but get "Rotator not enabled" message

✅ **Solutions**:
1. Enable rotator in config.py: `ROTOR_ENABLED = True`
2. Or use the API command above
3. Restart application
4. Refresh browser

### Connection Timeout
❌ **Problem**: Click GO but get "TCP connect failed" error

✅ **Solutions**:
1. Check rotator IP address in config.py is correct
2. Check rotator port number in config.py
3. Verify rotator is powered on and connected to network
4. Ping the rotator to test connection:
   ```bash
   ping 192.168.0.198
   ```
5. Check if your firewall blocks the port
6. Try increasing ROTOR_TIMEOUT_SEC to 5.0

### Rotator Doesn't Move
❌ **Problem**: Click GO but rotator doesn't move (no error)

✅ **Solutions**:
1. Check rotator protocol is correct (DCU-1 vs Yaesu GS-232A)
2. Verify azimuth value is between 0-359 degrees
3. Check rotator isn't in "local mode" (usually a switch on rotator)
4. Verify rotator has power to motor
5. Check rotator error logs/display panel

### Azimuth Shows Wrong Value
❌ **Problem**: UI shows 45° but rotator is actually at 90°

✅ **Solutions**:
1. Wait 5 seconds for auto-update
2. Click GO with current value to force sync
3. Check rotator's position on its own display panel
4. Restart rotator if it's stuck

## Part 5: Advanced - Short Path / Long Path (Future Feature)

The direction dropdown has options for "QSO SP" (Short Path) and "QSO LP" (Long Path), but these require integration with DX cluster data to calculate proper bearings.

For now, use manual azimuth entry or cardinal buttons. 

**Coming soon**: Automatic bearing calculation based on DX spots!

## Common Setups

### Setup 1: Simple North America Station
```python
ROTOR_ENABLED = True
ROTOR_HOST = "192.168.0.198"
ROTOR_PORT = 4001
ROTOR_PROTOCOL = "DCU-1"
```
Then use N/S/E/W buttons for quick positioning.

### Setup 2: Contesting Station (Need Precise Bearings)
```python
ROTOR_ENABLED = True
ROTOR_HOST = "192.168.0.198"
ROTOR_PORT = 4001
ROTOR_PROTOCOL = "DCU-1"
```
Use manual azimuth entry for specific bearings to DX stations.

### Setup 3: Yaesu Rotator
```python
ROTOR_ENABLED = True
ROTOR_HOST = "192.168.1.200"      # Your Yaesu rotator IP
ROTOR_PORT = 4002                 # Adjust to your port
ROTOR_PROTOCOL = "Yaesu GS-232A"  # ← Key difference
```

## API Reference

### Check Rotator Status
```bash
curl http://localhost:8000/api/rotor/status
```

**Response** (if enabled):
```json
{
  "ok": true,
  "enabled": true,
  "azimuth": 45
}
```

### Move to Azimuth
```bash
curl -X POST http://localhost:8000/api/rotor/goto \
  -H "Content-Type: application/json" \
  -d '{"azimuth": 90}'
```

### Move to Direction
```bash
curl -X POST http://localhost:8000/api/rotor/direction \
  -H "Content-Type: application/json" \
  -d '{"direction": "N"}'
```

### Stop Rotator
```bash
curl -X POST http://localhost:8000/api/rotor/stop
```

### Check Connection
```bash
curl http://localhost:8000/api/rotor/ping
```

## Tips & Tricks

### Tip 1: Quick Test
Before a contest, click each direction button and verify the rotator responds:
1. Click N → should point North
2. Click S → should point South
3. Click E → should point East
4. Click W → should point West

### Tip 2: Safe Default
Rotator is **disabled by default** - don't worry about accidentally sending commands!

### Tip 3: Manual Backup
If the rotator stops responding, you can often rotate it manually (check your rotator's manual for how).

### Tip 4: Log Monitoring
The application logs all rotator commands to the console. Open browser developer tools (F12) to see:
```
🌐 Rotor status: {ok: true, enabled: true, azimuth: 45}
Rotor GOTO: {ok: true, target: 90}
```

## Need Help?

### Check Documentation
- Backend code: `rotor_api.py` - see docstrings for technical details
- Configuration: `config.py` - detailed comments on each setting
- Implementation notes: `documentation/ARCO_IMPLEMENTATION_COMPLETE.md`

### Enable Debug Logging
Open browser Console (F12 → Console tab) to see real-time logs:
```
[Rotor direction: {ok: true, target: 0}]
[Rotor status error: (if any)]
```

### Manual Rotator Test
Test your rotator directly before using in application:
```bash
# DCU-1 example (set to 45 degrees)
echo "AP1045\r\nAM1" | nc -q 1 192.168.0.198 4001

# Query current position
echo "AI1" | nc 192.168.0.198 4001
```

---

**Happy rotating!** 🚀📡

For more details, see:
- `ARCO_IMPLEMENTATION_COMPLETE.md` - Full technical documentation
- `ROTOR_IMPLEMENTATION_VERIFICATION.md` - Verification details
- ARCO.md - Original requirements