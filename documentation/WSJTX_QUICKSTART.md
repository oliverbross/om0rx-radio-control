# WSJT-X Integration - Quick Start Guide

## ⚡ The Problem (Now FIXED!)

The WSJT-X integration was completely non-functional due to a **typo in the binary protocol parser**.

- **Old magic number**: `0xadeadbed` (WRONG ❌)
- **Correct magic number**: `0xadbccbda` (FIXED ✅)

This single typo caused every WSJT-X message to be silently rejected!

## ✅ What's Fixed

1. ✅ Magic number corrected
2. ✅ Status message parsing fixed (proper field order)
3. ✅ Decode message parsing fixed (proper field order)
4. ✅ QSO Logged message parsing fixed (proper field order)
5. ✅ Parser tested and verified with test cases

## 🚀 Getting It Working - 3 Simple Steps

### Step 1: Configure WSJT-X UDP Server

1. Open **WSJT-X**
2. Click **Settings** (gear icon)
3. Go to **Reporting** tab
4. ✅ **Check** the box: "Enable UDP Server"
5. Set the **UDP Server Port** to: **2237**
   - (This matches the default in `sdc-bridge-server.js`)
6. Click **OK** to save

### Step 2: Install Dependencies (if not already done)

```powershell
cd c:\Projects\om0rx-radio-control
npm install
```

### Step 3: Start the Bridge

```powershell
cd c:\Projects\om0rx-radio-control
node sdc-bridge-server.js
```

You should see:
```
📡 WSJT-X UDP listener: port 2237 (multicast: 224.0.0.1)
✅ WSJT-X UDP listening on 0.0.0.0:2237
```

## 🧪 Testing It Works

### Method 1: Watch the Console Log

Keep the bridge running and:
1. Open WSJT-X
2. Change the frequency, mode, or DX call in WSJT-X
3. You should see in the bridge console:
   ```
   📤 Broadcast Status to 1 client(s): Working W5ABC
   ```

### Method 2: Run Diagnostic Tool

In a **new terminal** window:

```powershell
cd c:\Projects\om0rx-radio-control
WSJTX_UDP_PORT=2237 node test_wsjtx_listener.js
```

This will show you:
- ✅ If UDP packets are arriving from WSJT-X
- ✅ If the magic number is correct
- ✅ What message type it is
- ✅ The parsed details (frequency, mode, DX call, etc.)

## 📡 How It Works Now

```
WSJT-X (running on your machine)
    ↓ sends UDP messages to port 2237
    ↓
Bridge Server (sdc-bridge-server.js)
    ↓ listens on UDP port 2237
    ↓
Parser (wsjtx-parser.js) - NOW FIXED!
    ↓ correctly parses binary messages
    ↓
WebSocket Broadcast (port 8091)
    ↓ sends to frontend web client
    ↓
DX Spots Panel
    ↓ displays spots in real-time
```

## 🔍 Troubleshooting

### "I don't see any messages in the bridge console"

**Check:**
1. Is WSJT-X UDP Server enabled? (Settings → Reporting)
2. Is the port 2237? (Or match it to bridge config)
3. Is WSJT-X actually running?
4. Is the bridge actually listening?

**Run the diagnostic:**
```powershell
WSJTX_UDP_PORT=2237 node test_wsjtx_listener.js
```

If it says "NO PACKETS RECEIVED":
- WSJT-X settings are wrong
- WSJT-X is not running
- Firewall is blocking port 2237

### "Magic number error" in diagnostic output

This shouldn't happen anymore, but if it does:
- Your WSJT-X version might have a different protocol
- Check `NetworkMessage.hpp` for the correct magic number
- Report an issue with WSJT-X version info

### "Port already in use"

```powershell
# Find what's using port 2237
netstat -ano | findstr :2237

# If it's another instance of the bridge:
# Kill it and restart
```

## 📊 Real-Time Data Flow

When you tune WSJT-X, the bridge receives:

1. **Status Message** (type 1)
   - Frequency
   - Mode
   - DX call
   - DX grid
   - TX state

2. **Decode Message** (type 2)
   - In-progress decodes
   - SNR
   - Message text
   - Real-time

3. **QSO Logged Message** (type 5)
   - When you log a contact
   - Full contact details
   - Frequency, mode, grid, report

All broadcast to WebSocket clients in real-time!

## 📝 Configuration Options

You can customize the port via environment variables:

```powershell
# Use port 2238 instead of 2237
$env:WSJTX_UDP_PORT = '2238'
node sdc-bridge-server.js
```

Make sure WSJT-X is configured to use the same port!

## ✨ What Comes Next

Once confirmed working:
1. Frontend receives spots via WebSocket
2. DX panel shows real-time activity
3. Auto-tuning to spots should work
4. QSO logging should be available
5. Contact information should populate

## 🎯 Summary

| Task | Status | What To Do |
|------|--------|-----------|
| Magic number fixed | ✅ Done | Already fixed in code |
| Parser fixed | ✅ Done | Already fixed in code |
| WSJT-X config | ⏳ Your turn | Enable UDP Server, port 2237 |
| Bridge running | ⏳ Your turn | `node sdc-bridge-server.js` |
| Testing | ⏳ Your turn | Run diagnostic or watch console |
| Integration working | 🎉 Should work! | Verify with tests above |

## 🤔 Questions?

- Bridge console shows: `📤 Broadcast Status to 1 client(s)` → **Working!** ✅
- Diagnostic shows: `✅ Parsed successfully!` → **Working!** ✅
- Frontend receives spots → **Integration complete!** 🎉

**The hard part (fixing the parser) is done!** Now just configure WSJT-X and run the bridge.