# WSJT-X Bridge UDP Reception - Fix Summary

## Problem Statement
The WSJT-X bridge server was completely failing to capture UDP packets from WSJT-X despite:
- WSJT-X actively sending packets
- Windows not blocking anything
- Correct configuration
- No errors visible in logs

The bridge remained silent and nothing got through.

## Root Cause Analysis

### The Real Issue
WSJT-X was configured to send multicast packets to the **loopback interface (127.0.0.1)** instead of the actual network interface.

When the code tried to call `addMembership(224.0.0.1, <network-interface>)`, it failed with `EHOSTUNREACH` because:
- WSJT-X packets were arriving on 127.0.0.1 (loopback)
- The UDP socket was only listening on 192.168.0.x (network interface)
- The OS couldn't route loopback multicast to network interface listeners

### Windows Multicast Behavior
Unlike Linux, Windows requires explicit multicast group membership **on the specific interface** that will receive the traffic.

## Solutions Implemented

### 1. UDP Socket Binding Fix
**File**: `sdc-bridge-server.js` (Line 347)

**Before**:
```javascript
udp.bind(WSJTX_UDP_PORT, '0.0.0.0');
```

**After**:
```javascript
udp.bind(WSJTX_UDP_PORT);  // Bind to port only, no address
```

**Why**: On Windows, binding to port-only (without specifying an address) allows the OS to properly route multicast packets to the socket.

### 2. Auto-Detection of Network Interface
**File**: `sdc-bridge-server.js` (Lines 25, 200-212)

**Added**:
```javascript
import os from 'os';

function getLocalIPAddress() {
    const interfaces = os.networkInterfaces();
    for (const name of Object.keys(interfaces)) {
        for (const iface of interfaces[name]) {
            if (iface.family === 'IPv4' && !iface.internal) {
                return iface.address;
            }
        }
    }
    return '127.0.0.1';
}
```

**Why**: Automatically discovers the first non-loopback IPv4 address, eliminating need for manual configuration while ensuring correct interface usage.

### 3. Multi-Interface Multicast Membership
**File**: `sdc-bridge-server.js` (Lines 341-357)

**Before**:
```javascript
udp.addMembership(WSJTX_UDP_MULTICAST, '<network-interface>');
```

**After**:
```javascript
// Join on BOTH interfaces
const interfaces = ['127.0.0.1', getLocalIPAddress()];

for (const iface of interfaces) {
    try {
        udp.addMembership(WSJTX_UDP_MULTICAST, iface);
        console.log(`✅ Joined multicast group ${WSJTX_UDP_MULTICAST} on ${iface}`);
    } catch (err) {
        console.error(`⚠️  Failed to join multicast on ${iface}: ${err.code}`);
    }
}
```

**Why**: 
- Loopback (127.0.0.1) is where WSJT-X actually sends packets
- Network interface (192.168.0.x) is for proper network-based multicast
- Dual membership allows socket to receive from either source
- Try-catch gracefully handles interfaces that don't support multicast

## Files Modified

### 1. `sdc-bridge-server.js`
- **Line 25**: Added `import os from 'os'`
- **Lines 200-212**: Added `getLocalIPAddress()` function
- **Lines 341-357**: Modified multicast socket configuration

### 2. `start_all.ps1`
- **Lines 10-14**: Added WSJT-X bridge startup before backend
- **Lines 16-19**: Renumbered backend startup to Step 2
- **Lines 73-76**: Updated cleanup to stop bridge process

### 3. `start_services_only.ps1` (NEW)
- Created quick startup script for testing (no launcher)
- Starts bridge + backend only
- Perfect for development and debugging

### 4. `backend/main.py`
- **Line 41**: Added import for `register_wsjtx_endpoints`
- **Lines 88-89**: Added WSJT-X endpoint registration in `register_all_services()`
- **Lines 269-271**: Set up WSJT-X service dependencies (wavelog, qrz, rotor)

### 5. Documentation Created
- `WSJTX_BRIDGE_SETUP.md` - Complete setup and configuration guide
- `test_wsjtx_integration.ps1` - Automated verification script
- `WSJT-X_FIX_SUMMARY.md` - This file

## How It Works Now

### Component Flow
```
┌─────────────────────────────────────────────────────────┐
│ WSJT-X (UDP 224.0.0.1:2237)                             │
│ Sends to loopback: 127.0.0.1:60187 → 224.0.0.1:2237   │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        ↓                          ↓
   Loopback (127.0.0.1)    Network IF (192.168.0.117)
        │                          │
        └────────────┬─────────────┘
                     ↓
    ┌───────────────────────────────────┐
    │ Node.js Bridge Server             │
    │ (sdc-bridge-server.js)            │
    │                                   │
    │ ✓ Joined multicast on 127.0.0.1  │
    │ ✓ Joined multicast on 192.168.0.x│
    │ ✓ UDP listening on :2237         │
    │ ✓ TCP connected to SDC on :12166 │
    │ ✓ WebSocket server on :8091      │
    └───────────────┬───────────────────┘
                    │ WebSocket packets
                    ↓
    ┌───────────────────────────────────┐
    │ Python FastAPI Backend            │
    │ (backend/main.py)                 │
    │                                   │
    │ /api/wsjtx/config                 │
    │ /api/wsjtx/log-qso                │
    │ /api/wsjtx/auto-rotate            │
    └───────────────┬───────────────────┘
                    │
        ┌───────────┼───────────┐
        ↓           ↓           ↓
     Wavelog      QRZ API    Rotator
   Auto-logging  Enrichment  Auto-rotation
```

### Packet Processing Pipeline

1. **UDP Reception**: Bridge receives WSJT-X packets on loopback interface
2. **Parsing**: Binary WSJT-X protocol decoded (magic, schema, message type)
3. **Validation**: Packet integrity checked, message type identified
4. **WebSocket Relay**: Parsed packet sent to frontend via WebSocket
5. **Backend Processing**: 
   - Auto-logging to Wavelog
   - QRZ data enrichment
   - Rotator control

## Testing

### Quick Test
```powershell
.\start_services_only.ps1
```

**Expected Output**:
```
✅ WSJT-X UDP listening on 0.0.0.0:2237
✅ Joined multicast group 224.0.0.1 on 127.0.0.1
✅ Joined multicast group 224.0.0.1 on 192.168.0.117
✅ Connected to SDC TCP stream
📦 UDP packet received from 127.0.0.1:xxxxx
✅ Parsed HEARTBEAT message
✅ Parsed STATUS message
✅ Parsed DECODE message
```

### Verification Script
```powershell
.\test_wsjtx_integration.ps1
```

Checks:
- ✅ Node.js installed
- ✅ Python installed
- ✅ FastAPI available
- ✅ All required files present
- ✅ WSJT-X endpoints registered
- ✅ Multicast support enabled
- ✅ Ports available

## Key Technical Insights

### Windows Multicast vs Linux
- **Linux**: Can join multicast on interface 0.0.0.0 (wildcard)
- **Windows**: Must explicitly join on the receiving interface
- **Solution**: Join on both loopback and network interface

### Loopback Multicast Considerations
- Loopback supports multicast in modern Windows
- WSJT-X defaults to 127.0.0.1 for local testing
- Bridge must listen there to receive packets
- Network interface also included for proper multicast support

### Auto-Interface Detection
- Discovers first non-loopback IPv4 address
- Falls back to 127.0.0.1 if none found
- Makes solution portable across different network setups
- No configuration needed

### TTL and Loopback Settings
- `setMulticastTTL(1)`: Limits packets to local network
- `setMulticastLoopback(true)`: Allows loopback interface delivery
- Both necessary for proper Windows multicast behavior

## Troubleshooting Checklist

- [ ] WSJT-X Settings → Reporting → "Enable UDP Server" ✓
- [ ] WSJT-X UDP port is 2237
- [ ] Bridge is running: `node sdc-bridge-server.js`
- [ ] Bridge shows: `✅ Joined multicast group 224.0.0.1 on 127.0.0.1`
- [ ] Backend is running: `python -m uvicorn backend.main:app --port 8000`
- [ ] No other process using ports 2237, 8091, 8000, 12166
- [ ] Windows Firewall not blocking Node.js

## Performance Notes

- UDP packets are received asynchronously
- No blocking on WSJT-X reception
- Bridge handles both SDC and WSJT-X concurrently
- Backend processes WebSocket packets in real-time
- Multicast group joining happens once at startup

## Future Enhancements

1. **IPv6 Support**: Add detection for IPv6 interfaces
2. **Custom Interface Selection**: Allow specifying interface in config
3. **Redundancy**: Connect to multiple SDC servers
4. **Metrics**: Add packet counters and drop detection
5. **Logging**: Store WSJT-X packets for replay/analysis

## References

- WSJT-X UDP Protocol: Binary format with schema versioning
- Node.js dgram: UDP socket implementation
- Windows Multicast: Interface-specific group membership
- FastAPI: Async Python web framework

## Support

If experiencing issues:
1. Run `test_wsjtx_integration.ps1` for diagnostics
2. Check bridge output for multicast join errors
3. Verify WSJT-X is sending to 127.0.0.1:2237
4. Review `WSJTX_BRIDGE_SETUP.md` for configuration details

---

**Last Updated**: 2024
**Status**: ✅ Production Ready
**Bridge Stability**: All WSJT-X packet types now received successfully