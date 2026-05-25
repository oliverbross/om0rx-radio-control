# WSJT-X Bridge Server Integration

## Overview
The WSJT-X bridge server receives UDP packets from WSJT-X on multicast address `224.0.0.1:2237` and relays them via WebSocket to the backend for processing.

## Fixed Issues ✅

### Root Cause
WSJT-X was configured to send multicast packets to the **loopback interface (127.0.0.1)**, but the bridge server was only listening on the network interface. The OS-level mismatch caused `EHOSTUNREACH` errors.

### Solutions Implemented

1. **UDP Socket Binding** (`sdc-bridge-server.js`, line 347)
   - Changed from `udp.bind(port, '0.0.0.0')` to `udp.bind(port)`
   - Binding to port-only allows Windows to properly route multicast packets

2. **Auto-Detection of Network Interface** (`sdc-bridge-server.js`, lines 25, 200-212)
   - Added `getLocalIPAddress()` function
   - Automatically discovers first non-loopback IPv4 address
   - Eliminates manual configuration

3. **Multi-Interface Multicast Membership** (`sdc-bridge-server.js`, lines 341-357)
   - Bridge now joins multicast group on **BOTH**:
     - **127.0.0.1** (loopback) - where WSJT-X sends
     - **Detected Network IP** (e.g., 192.168.0.117) - for standard multicast
   - Each join wrapped in try-catch for graceful handling

## Quick Start

### Option 1: Simple Services-Only Startup (Testing)
```powershell
.\start_services_only.ps1
```
Starts:
- 🌐 WSJT-X Bridge on WebSocket `:8091`
- 🔌 Backend on HTTP `:8000`

### Option 2: Full Application Startup
```powershell
.\start_all.ps1
```
Starts:
- 🌐 WSJT-X Bridge
- 🔌 Backend
- 🪟 Native Windows launcher

## Configuration

### WSJT-X Settings
1. Open WSJT-X → **Settings → Reporting**
2. Enable: **"Enable UDP Server"**
3. **Host**: `127.0.0.1` (loopback is fine!)
4. **Port**: `2237`

### Bridge Environment Variables
```powershell
$env:TCP_HOST = "127.0.0.1"           # SDC TCP host
$env:TCP_PORT = "12166"               # SDC TCP port
$env:WSJTX_UDP_PORT = "2237"          # WSJT-X UDP port
$env:WSJTX_UDP_MULTICAST = "224.0.0.1" # Multicast address
$env:WS_PORT = "8091"                 # WebSocket port
$env:WSJTX_ENABLED = "true"           # Enable WSJT-X listener
```

## Testing WSJT-X Packets

### Test 1: Run Bridge Only
```powershell
cd "c:\Projects\om0rx-radio-control"
$env:TCP_HOST="127.0.0.1"
$env:TCP_PORT="12166"
$env:WSJTX_UDP_PORT="2237"
$env:WSJTX_UDP_MULTICAST="224.0.0.1"
$env:WS_PORT="8091"
$env:WSJTX_ENABLED="true"
node sdc-bridge-server.js
```

**Expected output:**
```
✅ Joined multicast group 224.0.0.1 on 127.0.0.1
✅ Joined multicast group 224.0.0.1 on 192.168.0.117
📦 UDP packet received from 127.0.0.1:xxxxx
✅ Parsed HEARTBEAT message
✅ Parsed STATUS message
✅ Parsed DECODE message
```

### Test 2: Check Backend Receives WSJT-X
Once backend is running, call:
```bash
curl http://localhost:8000/api/wsjtx/config
```

**Expected response:**
```json
{
  "enabled": true,
  "udp_port": 2237,
  "multicast": "224.0.0.1",
  "ws_port": 8091,
  "auto_log": true,
  "auto_rotate": true,
  "modal_fields": {}
}
```

## API Endpoints

### Get WSJT-X Configuration
```
GET /api/wsjtx/config
```
Returns enabled state, ports, multicast settings, and feature flags.

### Auto-Log QSO to Wavelog
```
POST /api/wsjtx/log-qso
Content-Type: application/json

{
  "call": "W5ABC",
  "frequency_hz": 3573000,
  "mode": "FT8",
  "grid": "EM13AB",
  "rst_sent": "579",
  "rst_received": "589",
  "operator": "N0CALL",
  "comments": "Auto-logged from WSJT-X (FT8)"
}
```

### Auto-Rotate to DX Station
```
POST /api/wsjtx/auto-rotate
Content-Type: application/json

{
  "call": "W5ABC",
  "grid": "EM13AB",
  "frequency_hz": 3573000,
  "mode": "FT8"
}
```

## Architecture

```
WSJT-X (UDP 224.0.0.1:2237)
    ↓
Node.js Bridge (sdc-bridge-server.js)
    ├─ UDP: Listens on 127.0.0.1 + Network IP
    ├─ TCP: Connects to SDC (127.0.0.1:12166)
    └─ WebSocket: Broadcasts to frontend (ws://localhost:8091)
    ↓
Python Backend (FastAPI)
    ├─ WebSocket: Receives bridge packets
    ├─ API: /api/wsjtx/* endpoints
    ├─ Wavelog: Auto-logging
    ├─ QRZ: Data enrichment
    └─ Rotator: Auto-rotation
    ↓
Web UI (Vue.js)
    └─ Real-time display of WSJT-X activity
```

## Key Technical Insights

- **Windows Multicast**: On Windows, multicast must be explicitly joined on the specific interface that receives traffic
- **Loopback vs Network**: WSJT-X's local UDP broadcast goes to loopback by default; the bridge listens on both
- **Auto-Detection**: Network interface is automatically discovered (first non-loopback IPv4)
- **Graceful Fallback**: If an interface doesn't support multicast, it's skipped with try-catch

## Files Modified

- `sdc-bridge-server.js` - Multi-interface multicast support
- `start_services_only.ps1` - Quick test startup (NEW)
- `start_all.ps1` - Updated to start bridge + backend
- `backend/main.py` - WSJT-X service registration and dependency setup

## Troubleshooting

### Bridge not receiving packets?
1. Check WSJT-X: Settings → Reporting → "Enable UDP Server" ✓
2. Verify port: Should be `2237`
3. Look for errors: `EHOSTUNREACH` means interface mismatch
4. **Solution**: Update bridge to join multicast on both loopback AND network (already done!)

### No response from `/api/wsjtx/config`?
1. Backend may not be running: `python -m uvicorn backend.main:app --port 8000`
2. Check WSJT-X service is registered
3. Verify: `register_wsjtx_endpoints(app)` is called in `backend/main.py`

### WebSocket not connecting?
1. Bridge must be running: `node sdc-bridge-server.js`
2. Check WebSocket port: Default is `:8091`
3. Verify environment variable: `$env:WS_PORT="8091"`

## Notes
- WSJT-X uses standard protocol schema v2
- Message types: HEARTBEAT (0), STATUS (1), DECODE (2), etc.
- The bridge auto-detects network interface via OS API
- No firewall rules needed (local traffic only)