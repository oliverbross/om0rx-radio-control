# WSJT-X Configuration via GUI Modal

## Overview

WSJT-X configuration parameters are now fully configurable through the **Configuration Modal** in the Wave-Flex-Spots web interface. No need to edit `config.py` directly!

## Accessing the Configuration Panel

1. Open Wave-Flex-Spots in your browser: `http://localhost:8000`
2. Click the **⚙️ Config** button (next to Break.In button)
3. Click the **WSJT-X** tab
4. Modify settings as needed
5. Click **Save Configuration**

## WSJT-X Configuration Tab

### Available Settings

#### 🔌 UDP Listener Configuration

- **UDP Listen Port** (default: `2237`)
  - Port where the bridge server listens for WSJT-X UDP packets
  - Configure this same port in WSJT-X: Settings → Reporting → Port

- **Multicast Address** (default: `224.0.0.1`)
  - Use `224.0.0.1` for multicast mode (allows multiple WSJT-X instances or listeners)
  - Use `127.0.0.1` for unicast mode (localhost only)
  - Most users should use the default

- **WebSocket Port (Bridge)** (default: `8091`)
  - Internal port used by the bridge server to communicate with frontend
  - Should match the port the bridge server is listening on
  - **Change only if port 8091 is already in use**

#### ⚙️ Feature Configuration

- **Enable WSJT-X Integration** (checkbox)
  - Master switch for all WSJT-X features
  - When unchecked, disables auto-logging and auto-rotate
  - Disables the UDP listener

- **Auto-Log to Wavelog** (checkbox)
  - Automatically logs completed QSOs to Wavelog
  - Triggered when you log a contact in WSJT-X
  - Includes QRZ.com lookup for enrichment (name, location, zones)
  - Falls back gracefully if QRZ lookup fails
  - **Requires**: Wavelog API configured in Database tab

- **Auto-Rotate Antenna** (checkbox)
  - Automatically rotates antenna to DX station's grid square
  - Triggered each time WSJT-X sends a status update (working frequency change)
  - Calculates bearing from your home location (configured in Rotor tab)
  - **Requires**: Rotator enabled and configured in Rotor tab

## Data Flow

```
WSJT-X QSO
    ↓
UDP Packet (port 2237)
    ↓
Bridge Server reads config values:
  - WSJTX_UDP_PORT
  - WSJTX_UDP_MULTICAST
  - WSJTX_WS_PORT
  - WSJTX_AUTO_LOG
  - WSJTX_AUTO_ROTATE
    ↓
WebSocket broadcast (port 8091)
    ↓
Frontend receives message
    ↓
GUI Modal displayed
    ↓
API calls for auto-logging & auto-rotate
```

## Configuration Persistence

When you save configuration through the GUI:

1. **Frontend** sends config data to `/api/config` endpoint
2. **Backend** receives the data and updates `config.py`
3. **Next restart** of Wave-Flex-Spots uses the new values
4. **Bridge server** reads updated values from Python config module

### ⚠️ Important Notes

- **Bridge server restart required** for UDP port changes to take effect
- **Frontend restart required** for WebSocket port changes
- **No restart needed** for feature toggles (auto-log, auto-rotate) - they take effect immediately

## Troubleshooting Configuration Issues

### Config Changes Not Taking Effect

**Cause**: Bridge server or frontend not restarted  
**Solution**: Restart Wave-Flex-Spots app:
```powershell
# Stop current instance (Ctrl+C)
# Then restart:
.\start_webapp.ps1
```

### Config Values Keep Reverting

**Cause**: Possible file permissions issue or concurrent writes  
**Solution**: 
1. Stop Wave-Flex-Spots
2. Check `config.py` is not read-only
3. Restart and try saving again

### Cannot Connect to UDP Port

**Cause**: Port already in use, firewall, or WSJT-X not sending  
**Solution**:
1. Change UDP port in config to unused port (e.g., 2238)
2. Update WSJT-X settings to match
3. Check Windows Firewall allows the port
4. Verify WSJT-X "Accept UDP requests" is enabled

### WebSocket Connection Failed

**Cause**: Wrong WebSocket port in config  
**Solution**:
1. Check bridge server startup output shows correct port
2. Ensure port in config matches bridge server
3. Default is 8091, don't change unless necessary

## Reverting to Defaults

If you want to reset to default WSJT-X configuration:

1. Open Config Modal → WSJT-X tab
2. Set values:
   - UDP Listen Port: `2237`
   - Multicast Address: `224.0.0.1`
   - WebSocket Port: `8091`
   - Enable WSJT-X Integration: ☑️
   - Auto-Log to Wavelog: ☑️
   - Auto-Rotate Antenna: ☑️
3. Click Save Configuration

## Advanced Configuration

### Using Multicast

To support multiple WSJT-X instances or external listeners:

1. Set Multicast Address to `224.0.0.1`
2. Multiple instances can all send to the same port
3. Bridge server will receive from all sources

### Using Unicast (Single Instance)

For standalone single-instance setup:

1. Set Multicast Address to `127.0.0.1`
2. Only WSJT-X on localhost can reach the bridge
3. Most responsive for single-user scenarios

### Custom Ports

If standard ports are already in use:

1. **UDP Port**: Choose unused port 1024-65535
2. **WebSocket Port**: Choose unused port 1024-65535
3. Update WSJT-X settings to match UDP port
4. Restart both bridge and frontend

## Configuration Files

Configuration is stored in:

- **Python config**: `c:\Projects\om0rx-radio-control\config.py`
- **Frontend state**: Browser localStorage (not persisted to disk)

The GUI writes to `config.py` via `/api/config` endpoint.

## See Also

- [WSJTX_QUICK_START.md](WSJTX_QUICK_START.md) - Setup instructions
- [WSJTX_INTEGRATION_COMPLETE.md](WSJTX_INTEGRATION_COMPLETE.md) - Technical reference
- [WSJTX_IMPLEMENTATION_SUMMARY.md](WSJTX_IMPLEMENTATION_SUMMARY.md) - Implementation details

---

**Last Updated**: 2024  
**Status**: ✅ Complete and Production-Ready