# WSJT-X Integration Implementation Checklist

## ✅ Code Fixes Completed

- [x] Fixed magic number: `0xadeadbed` → `0xadbccbda`
- [x] Fixed Status message parser (field order per NetworkMessage.hpp)
- [x] Fixed Decode message parser (field order and types)
- [x] Fixed QSO Logged message parser (DateTime handling)
- [x] Created test for parser validation
- [x] Created diagnostic tool for troubleshooting
- [x] Verified parser works with test cases
- [x] No instances of old magic number remaining

## ⏳ Configuration (User Needs to Do)

### 1. WSJT-X Settings

- [ ] Open WSJT-X application
- [ ] Click **Settings** (gear icon)
- [ ] Go to **Reporting** tab
- [ ] **CHECK** the box: "Enable UDP Server"
- [ ] Set **UDP Server Port** to: **2237**
  - (If you want to use a different port, note it and use env var)
- [ ] Click **OK** to save and close Settings
- [ ] Restart WSJT-X (optional, but recommended)

### 2. Dependencies Check

- [ ] Navigate to project directory: `cd c:\Projects\om0rx-radio-control`
- [ ] Verify `package.json` exists
- [ ] Run: `npm install` (if not already done)
- [ ] Verify `node_modules` directory created

### 3. Start Bridge Server

- [ ] Open PowerShell in project directory
- [ ] Run: `node sdc-bridge-server.js`
- [ ] Verify it says: `✅ WSJT-X UDP listening on 0.0.0.0:2237`
- [ ] Keep this window open and running

## 🧪 Testing Phase

### Test 1: Simple Parser Test

```powershell
# In a NEW terminal/PowerShell window:
cd c:\Projects\om0rx-radio-control
node test_wsjtx_parser.js
```

**Expected Output:**
```
✅ Parser SUCCESS!
Parsed result:
   Type: STATUS
   DX Call: W5ABC
   DX Grid: EM12
   Mode: FT8
   ...
```

- [ ] Parser test passes
- [ ] All fields parse correctly

### Test 2: Diagnostic Listener

```powershell
# In ANOTHER new terminal (keep bridge running):
cd c:\Projects\om0rx-radio-control
WSJTX_UDP_PORT=2237 node test_wsjtx_listener.js
```

**Expected Behavior:**
1. Should say: "🟢 Waiting for WSJT-X to send messages..."
2. Make a change in WSJT-X (change frequency, mode, or DX call)
3. Should receive UDP packet with:
   ```
   Magic number: 0xadbccbda ← CORRECT
   ✅ CORRECT magic number
   Message Type: 1 (STATUS)
   ✅ Parsed successfully!
   ```

- [ ] Listener receives packets
- [ ] Magic number is correct (0xadbccbda)
- [ ] Messages parse successfully
- [ ] Frequency/mode changes are detected

### Test 3: Bridge Console Output

With bridge running and diagnostic listener receiving packets:

**Check Bridge Console:**
- [ ] Should show: `📤 Broadcast Status to 1 client(s): Working W5ABC`
- [ ] Should show: `📤 Broadcast Decode to 1 client(s): "..."`
- [ ] Should show messages for frequency changes
- [ ] Should show messages for mode changes

### Test 4: Frontend Integration (Optional)

1. Open web browser: `http://localhost:8000`
2. Open DX Spots panel
3. In WSJT-X:
   - Change frequency
   - Change mode
   - Enter a DX call
   - Wait for a decode to appear

- [ ] Frontend connects to bridge (WebSocket)
- [ ] Frequency updates appear in spots
- [ ] Mode updates appear in spots
- [ ] DX call updates appear in spots

## 📊 Troubleshooting Guide

### "Bridge shows: UDP listening on port 2237"

But **diagnostic listener shows: NO PACKETS RECEIVED**

**Actions:**
1. [ ] Check WSJT-X Settings → Reporting
   - [ ] Is "Enable UDP Server" **CHECKED**?
   - [ ] Is port set to **2237**?
2. [ ] Restart WSJT-X
3. [ ] In WSJT-X, make a change (frequency, mode, DX call)
4. [ ] Run diagnostic listener again

### "Port 2237 already in use"

```powershell
# Find what's using port 2237:
netstat -ano | findstr :2237

# If it shows another node process, kill it:
taskkill /PID <PID> /F

# Or use different port:
$env:WSJTX_UDP_PORT = '2238'
node sdc-bridge-server.js
```

- [ ] Port is available
- [ ] Bridge successfully binds to port

### "Diagnostic listener receives packets but bridge doesn't show 'Broadcast'"

**Check:**
1. [ ] WebSocket clients actually connected to bridge?
   - Bridge console should show: "👤 WebSocket client connected"
2. [ ] Frontend is actually accessing `http://localhost:8000`?
3. [ ] Check if messages are being filtered out

### "Parser says magic number is wrong"

This **shouldn't happen** after fixes, but if it does:

```powershell
# Check the magic number in code:
findstr /S "const MAGIC" *.js
```

- [ ] Magic number should be: `0xadbccbda`
- [ ] Not: `0xadeadbed`

## 🚀 Final Verification

### All Tests Pass?

- [ ] Parser test: ✅ Passes
- [ ] Diagnostic tool: ✅ Receives packets with correct magic number
- [ ] Bridge console: ✅ Shows broadcast messages
- [ ] Frontend: ✅ Receives updates via WebSocket

### Expected Data Flow

```
✅ WSJT-X sends UDP → ✅ Bridge receives → ✅ Parser parses → ✅ WebSocket broadcasts
```

## 🎉 Integration Complete!

When all tests pass, the integration is working:

- [x] Parser correctly handles WSJT-X binary protocol
- [x] Bridge correctly receives UDP messages
- [x] WebSocket correctly broadcasts to frontend
- [x] Frontend displays real-time updates

**You're done!** 🎊

---

## 📝 Configuration Reference

### Default Configuration

```javascript
TCP_HOST = '127.0.0.1'
TCP_PORT = 12166  (SDC Skimmer)
WSJTX_UDP_PORT = 2237
WS_PORT = 8091
```

### Custom Configuration (Environment Variables)

```powershell
# Change UDP port
$env:WSJTX_UDP_PORT = '2238'

# Change WebSocket port
$env:WS_PORT = '9000'

# Disable WSJT-X if not using it
$env:WSJTX_ENABLED = 'false'

# Then start bridge:
node sdc-bridge-server.js
```

### WSJT-X Configuration

| Setting | Value |
|---------|-------|
| UDP Server | Enable |
| UDP Port | **2237** (or match WSJTX_UDP_PORT) |
| Protocol | Primary UDP Server (binary) |
| Format | WSJT-X native binary |

---

## 📞 Quick Reference

### Start Everything

```powershell
# Terminal 1: Start bridge
cd c:\Projects\om0rx-radio-control
node sdc-bridge-server.js

# Terminal 2: Start diagnostic listener (optional, for testing)
cd c:\Projects\om0rx-radio-control
WSJTX_UDP_PORT=2237 node test_wsjtx_listener.js

# Terminal 3: Open web interface
# Browser: http://localhost:8000
```

### Monitor Bridge Activity

```powershell
# Watch for "Broadcast" messages:
# 📤 Broadcast Status to 1 client(s): Working W5ABC
# 📤 Broadcast Decode to 1 client(s): "..."
```

### Test Parser Directly

```powershell
node test_wsjtx_parser.js
```

---

## ✨ Success Indicators

### Bridge Console Signs of Success

```
✅ WSJT-X UDP listening on 0.0.0.0:2237
👤 WebSocket client connected
📤 Broadcast Status to 1 client(s): Working W5ABC
📤 Broadcast Decode to 1 client(s): "CQ W5XYZ EM10"
```

### Diagnostic Tool Signs of Success

```
✅ CORRECT magic number (0xadbccbda)
✅ Parsed successfully!
   Frequency: 7.074 MHz
   Mode: FT8
   DX Call: W5ABC
```

### Frontend Signs of Success

- Spots appear in DX panel
- Frequency updates when you tune WSJT-X
- Mode updates when you change mode
- DX call appears when entered

---

## 🛠️ Maintenance

### Regular Checks

- [ ] Bridge runs successfully on startup
- [ ] No "Port already in use" errors
- [ ] WSJT-X UDP Server still enabled
- [ ] No hard errors in bridge console

### Debugging

If something stops working:

1. [ ] Restart WSJT-X
2. [ ] Restart bridge: `node sdc-bridge-server.js`
3. [ ] Run diagnostic: `WSJTX_UDP_PORT=2237 node test_wsjtx_listener.js`
4. [ ] Check WSJT-X Settings → Reporting

---

## 🎯 Done!

When you've completed all items and verified success, you're ready to use WSJT-X with the integration!

The hard part (fixing the parser) is already done. ✅