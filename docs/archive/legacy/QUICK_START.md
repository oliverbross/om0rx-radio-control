# 🚀 WSJT-X Bridge + Backend - Quick Start

## 30-Second Setup

### 1️⃣ Ensure WSJT-X is Ready
```
Settings → Reporting
✓ Enable UDP Server
✓ Host: 127.0.0.1
✓ Port: 2237
```

### 2️⃣ Start Services
```powershell
# Quick test (bridge + backend only):
.\start_services_only.ps1

# Full app (with launcher):
.\start_all.ps1
```

### 3️⃣ Verify It Works
**Expected in Bridge Window**:
```
✅ Joined multicast group 224.0.0.1 on 127.0.0.1
✅ Joined multicast group 224.0.0.1 on 192.168.0.xxx
📦 UDP packet received from 127.0.0.1:xxxxx
✅ Parsed HEARTBEAT message
```

---

## 📊 URLs & Ports

| Service | URL | Port | Protocol |
|---------|-----|------|----------|
| **Web UI** | http://localhost:8000 | 8000 | HTTP |
| **WebSocket Bridge** | ws://localhost:8091 | 8091 | WebSocket |
| **WSJT-X UDP** | 127.0.0.1:2237 | 2237 | UDP |
| **SDC TCP** | 127.0.0.1:12166 | 12166 | TCP |

---

## 🔌 Environment Variables
```powershell
$env:WSJTX_ENABLED = "true"           # Enable WSJT-X
$env:WSJTX_UDP_PORT = "2237"          # UDP port
$env:WSJTX_UDP_MULTICAST = "224.0.0.1" # Multicast address
$env:WS_PORT = "8091"                 # WebSocket port
$env:TCP_HOST = "127.0.0.1"           # SDC host
$env:TCP_PORT = "12166"               # SDC port
```

---

## 🧪 Testing

### Test Bridge Only
```powershell
cd "c:\Projects\om0rx-radio-control"
# Set environment variables (see above)
node sdc-bridge-server.js
```

### Test Full Stack
```powershell
.\start_services_only.ps1
# Then in another terminal:
curl http://localhost:8000/api/wsjtx/config
```

### Run Diagnostic
```powershell
.\test_wsjtx_integration.ps1
```

---

## 🆘 Troubleshooting

| Issue | Solution |
|-------|----------|
| No UDP packets | Enable WSJT-X → Settings → Reporting → "Enable UDP Server" |
| Port in use | Close conflicting app or change port in env vars |
| EHOSTUNREACH | Bridge not joined on loopback (should see: ✅ 127.0.0.1) |
| Backend won't start | Check Python installed: `python --version` |
| Bridge won't start | Check Node.js installed: `node --version` |

---

## 📋 API Endpoints

### Get Config
```bash
curl http://localhost:8000/api/wsjtx/config
```

### Auto-Log QSO
```bash
curl -X POST http://localhost:8000/api/wsjtx/log-qso \
  -H "Content-Type: application/json" \
  -d '{
    "call": "W5ABC",
    "frequency_hz": 3573000,
    "mode": "FT8",
    "grid": "EM13AB",
    "rst_sent": "579",
    "rst_received": "589"
  }'
```

### Auto-Rotate
```bash
curl -X POST http://localhost:8000/api/wsjtx/auto-rotate \
  -H "Content-Type: application/json" \
  -d '{
    "call": "W5ABC",
    "grid": "EM13AB",
    "frequency_hz": 3573000,
    "mode": "FT8"
  }'
```

---

## 📁 Key Files

- **Bridge**: `sdc-bridge-server.js`
- **Backend**: `backend/main.py`
- **WSJT-X Service**: `services/wsjtx.py`
- **Startup Scripts**: 
  - `start_services_only.ps1` (quick)
  - `start_all.ps1` (full app)

---

## 🔍 Component Status

| Component | Status | Details |
|-----------|--------|---------|
| UDP Socket Binding | ✅ Fixed | Binds to port-only for multicast routing |
| Multicast Join | ✅ Fixed | Joins on both loopback AND network interface |
| Interface Detection | ✅ Auto | Auto-discovers network interface |
| Backend Registration | ✅ Fixed | WSJT-X endpoints now registered |
| Dependencies | ✅ Set | Wavelog, QRZ, Rotor initialized |

---

## 📚 Documentation

- **Full Setup**: `WSJTX_BRIDGE_SETUP.md`
- **Technical Details**: `WSJT-X_FIX_SUMMARY.md`
- **Diagnostics**: `test_wsjtx_integration.ps1`

---

## 🎯 Success Indicators

You'll know it's working when you see:

1. **Bridge Window**:
   ```
   ✅ Joined multicast group 224.0.0.1 on 127.0.0.1
   ✅ Joined multicast group 224.0.0.1 on 192.168.0.xxx
   📦 UDP packet received from 127.0.0.1:xxxxx
   ✅ Parsed HEARTBEAT message
   ✅ Parsed STATUS message
   ✅ Parsed DECODE message
   ```

2. **Backend Window**:
   ```
   ✅ Uvicorn running on http://0.0.0.0:8000
   ```

3. **Frontend** (http://localhost:8000):
   - WSJT-X decodes appear in real-time
   - Auto-logging works
   - Auto-rotation works

---

**TL;DR**: Run `.\start_services_only.ps1`, open WSJT-X, start a decode, watch the bridge capture packets! 🎉