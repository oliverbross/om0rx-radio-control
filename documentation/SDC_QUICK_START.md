# SDC Ticker - Quick Start (3 Minutes)

## The Idea

When you click on a CW spot, the radio tunes to it in CW mode. A new row appears showing live decoded CW text from your SDC Skimmer software in real-time.

## Prerequisites

1. **SDC Skimmer** - Running and configured with TCP Broadcast enabled
2. **Node.js** - v18 or higher installed (from https://nodejs.org/)
3. **Python 3** - For the FastAPI backend (already required)

## Quick Setup

### 1️⃣ Configure SDC (1 minute)

In **SDC Skimmer → Global Setup → Misc tab:**
- ✅ Enable "TCP Broadcast Data Port"
- ✅ Set to port `12166`
- ✅ Save

That's it! SDC is ready.

### 2️⃣ Start the Web App (1 minute)

The SDC bridge server **starts automatically** with your app!

**Windows:**
```powershell
.\start_webapp.ps1
```

**Linux:**
```bash
chmod +x start_webapp.sh
./start_webapp.sh
```

### What Happens Automatically:
✅ Checks for Node.js installation  
✅ Installs npm dependencies (if needed, only on first run)  
✅ **Starts SDC bridge server** on port 8091  
✅ Starts FastAPI backend on port 8000  
✅ Everything runs as one integrated system  

Expected output:
```
✅ Node.js found: v20.x.x
✅ npm dependencies ready
🚀 Starting SDC Bridge Server...
✅ SDC Bridge Server started (Job ID: X)
   WebSocket available on ws://localhost:8091

🚀 Starting FastAPI backend server...
```

### 3️⃣ Test It (1 minute)

1. Open web app (http://localhost:8000)
2. Click a CW spot in the DX cluster
3. Radio should tune to CW frequency
4. **SDC Decoded ticker appears** with live CW text!

## What You'll See

### Before Setup
- SDC ticker **hidden** (not in CW mode)

### After Setup (CW Mode Only)
```
📡 SDC Decoded                          ● Connected
K4ABC   •   N5DEF   •   W3GHI   •   K6JKL   •   N9MNO
```

Connection status:
- 🟢 `● Connected` = Green, receiving data
- 🔴 `● Disconnected` = Red, trying to reconnect

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Node.js is not installed" | Download from https://nodejs.org/ and install |
| Shows "Disconnected" | Check SDC has TCP Broadcast enabled on port 12166 |
| No text appearing | Make sure radio is in CW mode and SDC is receiving signals |
| Port 8091 already in use | Use different port: `WS_PORT=9000 .\start_webapp.ps1` |
| Bridge fails to start | Check console output, see documentation/SDC_TICKER_INTEGRATION.md |

## Using Custom Ports

If port 8091 is taken, use a different port:

**Windows (PowerShell):**
```powershell
$env:WS_PORT=9000
.\start_webapp.ps1
```

**Linux (bash):**
```bash
WS_PORT=9000 ./start_webapp.sh
```

Then update `frontend/js/sdc-ticker.js` line 19:
```javascript
const wsUrl = `ws://localhost:9000`; // Match your custom port
```

## Using Remote SDC Computer

If SDC is on a different computer:

**Windows (PowerShell):**
```powershell
$env:TCP_HOST="192.168.1.100"  # SDC computer IP
.\start_webapp.ps1
```

**Linux (bash):**
```bash
TCP_HOST=192.168.1.100 ./start_webapp.sh
```

Also update `frontend/js/sdc-ticker.js` line 19:
```javascript
const wsUrl = `ws://192.168.1.100:8091`; // Use SDC computer IP
```

## Browser Console Commands

```javascript
// Check if connected
this.sdcConnected

// Force reconnect
this.initSDCTicker()

// Clear buffer
this.clearSDCBuffer()

// See buffer contents
this.sdcBuffer
```

## Stopping the App

When you close the terminal, both the Python backend and Node.js bridge stop automatically.

---

## That's It! 🎉

Your web app now shows live decoded CW in a beautiful scrolling ticker when in CW mode. Click any CW spot and watch the magic happen!

**Everything starts with a single command!**

---

Need more info? See: `documentation/SDC_TICKER_INTEGRATION.md`