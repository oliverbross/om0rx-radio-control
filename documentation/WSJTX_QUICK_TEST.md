# WSJT-X Integration Quick Test Guide

## ⚡ 30-Second Setup

### Step 1: Configure WSJT-X (1 minute)

1. **Open WSJT-X**
2. **Settings** → **Reporting** tab
3. Enable **UDP Server**
4. Set endpoint: `127.0.0.1:2237`
5. Click **Apply**
6. **Restart WSJT-X**

### Step 2: App Already Running

If you followed the previous guide:
- ✅ FastAPI backend on `http://localhost:8000`
- ✅ Bridge server on `ws://localhost:8091`
- ✅ WSJT-X listener on UDP port 2237

**Everything is ready!**

### Step 3: Test It

1. **Open** `http://localhost:8000` in browser
2. **Press F12** to open Developer Tools
3. Go to **Console** tab
4. **In WSJT-X**: Click on a CQ station (e.g., N0CALL)
5. **Watch the browser console**

---

## 🎯 What You Should See

### Success! ✅

```
📡 WSJT-X message received: wsjtx_status
📍 WSJT-X Status: N0CALL (FN23AB)
✅ QSO Form: Populated call with N0CALL
✅ QSO Form: Populated grid with FN23AB
✅ QSO Form: Populated frequency with 3.573 MHz
✅ QSO Form: Set mode to FT8
🔄 Auto-rotating to FN23AB (from JN88TQ)
✅ Rotor rotation started: { bearing: 42.5, ... }
```

### What If It Doesn't Work? ❌

#### Console Shows Nothing After Clicking Station

**Problem**: No WSJT-X messages received

**Check**:
1. WSJT-X Settings → Reporting → UDP Server **Enabled** ✓
2. Endpoint is exactly: `127.0.0.1:2237` ✓
3. WSJT-X restarted after enabling ✓
4. Run in **PowerShell**:
   ```powershell
   netstat -an | findstr 2237
   ```
   You should see: `UDP    127.0.0.1:2237    0.0.0.0:*`

**Fix**: Restart WSJT-X and try again

#### Form Doesn't Populate

**Problem**: Messages received but form not updating

**Check**:
1. Log QSO button exists on page ✓
2. Form has visible input fields ✓
3. Open the Log QSO form **before** clicking WSJT-X station

**Fix**: Click Log QSO button **first**, then click WSJT-X station

#### Rotor Not Rotating

**Problem**: Form populated but rotor not moving

**Check**:
1. ⚙️ Config → Rotor tab → **Rotor Enabled** ✓
2. ⚙️ Config → Rotor tab → **AUTO Mode** enabled ✓
3. Your station **grid** configured (e.g., JN88TQ) ✓
4. Target **band** enabled in rotor config ✓

**Fix**: Enable rotor, set grid, then try again

---

## 🔍 Advanced Troubleshooting

### Check Bridge Server Status

```powershell
# In browser console:
console.log('Bridge WebSocket state:', window.SDCTicker?.data?.sdcWebSocket?.readyState);
```

States:
- `0` = CONNECTING
- `1` = OPEN ✅
- `2` = CLOSING
- `3` = CLOSED ❌

### Check Bridge Server Logs

```powershell
# In PowerShell
Get-Job -Name "Bridge-Server" | Receive-Job -Newest 20
```

Should show:
```
🔌 WebSocket server started on ws://localhost:8091
📡 WSJT-X UDP listener: port 2237 (multicast: 224.0.0.1)
✅ Connected to SDC TCP stream
```

### Monitor WSJT-X Messages in Real-Time

```javascript
// Paste in browser console:
window.addEventListener('wsjtx-message', (e) => {
  console.table(e.detail);
});
```

Now every WSJT-X message will print as a table

### Verify UDP Port

**Windows PowerShell**:
```powershell
netstat -an | findstr 2237
```

Should show: `UDP  127.0.0.1:2237    0.0.0.0:*    LISTENING`

**Linux/Mac**:
```bash
netstat -an | grep 2237
```

---

## 📊 Test Scenarios

### Scenario 1: Basic Status

**What to do**:
1. Open WSJT-X
2. Wait for CQ decodes
3. Click on a CQ (without calling)
4. Observe form population

**Expected**:
- ✅ Callsign populated
- ✅ Grid populated (if decoded)
- ✅ Frequency populated

### Scenario 2: Full Auto-Rotation

**What to do**:
1. Configure rotor in ⚙️ Config
2. Enable AUTO mode
3. Set your grid (e.g., JN88TQ)
4. Click WSJT-X station in different grid

**Expected**:
- ✅ Form populated
- ✅ Antenna rotates to new bearing
- ✅ Rotation completes in ~2 seconds

### Scenario 3: Multi-Band

**What to do**:
1. Enable rotor AUTO
2. Have WSJT-X on 40m
3. Click station
4. Switch WSJT-X to 20m
5. Click different station

**Expected**:
- ✅ Rotor adjusts bearing for each band
- ✅ Only rotates if band enabled in config

---

## ✅ Complete Success Checklist

- [ ] WSJT-X UDP Server enabled
- [ ] Endpoint is `127.0.0.1:2237`
- [ ] App running on `localhost:8000`
- [ ] Bridge server running (no "Connection refused" errors)
- [ ] Browser console shows WSJT-X messages
- [ ] Log QSO form auto-populates
- [ ] Antenna rotates (if enabled)
- [ ] No errors in browser console
- [ ] Rotor bearing updates correctly

---

## 🚀 Next Steps

### If Everything Works ✅

Great! You have:
- ✅ WSJT-X integration working
- ✅ Auto-population of QSO form
- ✅ Auto-rotation to DX grids
- ✅ Full digital mode support (FT8, FT4, MSK144, etc.)

### Optimize Performance

1. **Reduce Rotor Polling**
   - Config → Rotor → Set polling interval to 5+ seconds
   - Reduces CPU usage

2. **Disable Unused Features**
   - If no SDC, disable SDC in config
   - If no rotator, disable rotor

3. **Enable Wavelog Integration**
   - Config → Database → Enable Wavelog
   - Auto-logs all QSOs to Wavelog with QRZ data

---

## 📞 Common Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| WebSocket error | Bridge crashed | Restart app with `.\start_webapp.ps1` |
| No form population | Wrong port | Check WSJT-X Reporting → `127.0.0.1:2237` |
| Rotor doesn't move | AUTO disabled | Enable in ⚙️ Config → Rotor → AUTO |
| Frequency shows 0 | WSJT-X variant | Some modes don't send frequency |
| Grid shows empty | Station not decoded | Wait for grid from QRZ/CTY |

---

## 📝 Notes

- **First Contact**: May take a few seconds for first message
- **Multiple Stations**: Each click sends a Status message (can test multiple)
- **Mode Detection**: Automatically detects FT8, FT4, MSK144, etc.
- **Frequency**: Sent in Hz (converted to MHz in form: 3573000 → 3.573 MHz)

---

**Status**: ✅ Ready to Test  
**Time to Setup**: 5 minutes  
**Dependencies**: None (all built-in)