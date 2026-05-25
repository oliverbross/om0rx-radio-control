# FT8 Quick Fix Instructions

## 🚀 **GET FT8 WORKING IN 5 MINUTES**

---

## **Step 1: Restart Server** ⚡

```powershell
# Stop current server (Ctrl+C in server window)

# Restart
.\start_webapp.ps1
```

**Wait for:** "Application startup complete"

---

## **Step 2: Hard Refresh Browser** 🔄

```
Press: Ctrl + F5
```

This forces browser to reload the fixed JavaScript.

---

## **Step 3: Configure Audio Device** 🔊

1. **Open FT8 Modal** (click FT8 button)
2. **Go to Settings Tab**
3. **Audio Input:** Select `"23: DAX Audio RX 1 (FlexRadio Systems DAX Audio)"`
4. **Audio Output:** Select `"28: DAX Audio TX (FlexRadio Systems DAX Audio)"`
5. **Click:** `💾 Save Configuration`
6. **Verify:** Green checkmark appears "✅ FT8 configuration saved"

---

## **Step 4: Test Configuration Persistence** 💾

1. **Close FT8 Modal** (click X)
2. **Reopen FT8 Modal**
3. **Go to Settings Tab**
4. **Check:** Audio Input should STILL show "23: DAX Audio RX 1..."
   - ✅ If yes → Configuration working!
   - ❌ If shows "System Default" → See troubleshooting below

---

## **Step 5: Setup Radio** 📻

### **In SmartSDR:**

1. **Frequency:** 14.074 MHz (20m FT8)
2. **Mode:** DIGU
3. **Filter:** 0-3000 Hz
4. **DAX:** Enable "DAX 1" (Audio tab)
5. **Volume:** Adjust DAX output to comfortable level

### **Alternative Frequencies:**
- 7.074 MHz (40m) - Good at night
- 10.136 MHz (30m) - Often active
- 21.074 MHz (15m) - Good during day

---

## **Step 6: Start FT8 Service** ▶️

1. **FT8 Modal → Operate Tab**
2. **Click:** `▶️ Start`
3. **Watch Status Badge:**
   - Should turn green: `🟢 Active`
   - Should STAY green (not flash red)

### **Check Browser Console:**

Press `F12` → Console tab

**Should see:**
```
Loading FT8 configuration...
✅ FT8 configuration loaded
FT8 service started
```

**Should NOT see:**
```
❌ AttributeError: module 'scipy.signal' has no attribute 'hamming'
❌ Error starting FT8 service
```

---

## **Step 7: Wait for Decodes** ⏱️

**Normal behavior:**
- Service starts
- Waterfall begins updating
- After 15-30 seconds: First decoded messages appear
- Status bar shows: `📊 Decoded: 1, 2, 3...` (counting up)

**If no decodes after 2 minutes:**
1. Check https://pskreporter.info/pskmap.html
2. Look for green dots on your frequency
3. If none → band is dead, try different frequency or time

---

## **Step 8: Verify It's Working** ✅

### **Check 1: Status Bar**
```
📊 Decoded: 5    📤 Transmitted: 0    ✅ QSOs: 0    ⏱️ Uptime: 1m 23s
```
- Decoded count should increase every 15 seconds
- Uptime should always be counting up

### **Check 2: Decoded Messages Panel**
Should show messages like:
```
21:45:32  -12  0.3  1456  CQ DL1ABC JO62
21:45:32  -08  0.1  1678  W1XYZ K2ABC R-15
21:45:17  +03  0.2  1234  CQ OM0RX JN88
```

### **Check 3: Backend Logs**
```powershell
Get-Content "logs\flex_debug.log" -Tail 20
```

**Should see:**
```
Starting FT8 service with audio device: 23: DAX Audio RX 1...
Using audio device index: 23
Real audio capture started (device 23, 12000 Hz)
✅ FT8 service started successfully
```

**Should NOT see:**
```
❌ AttributeError: module 'scipy.signal' has no attribute 'hamming'
❌ Failed to start audio capture
❌ Error in Costas sync detection
```

---

## **Common Issues & Solutions**

### **❌ Service stops immediately after start**

**Cause:** Old code still loaded in browser  
**Fix:**
```
1. Press Ctrl+F5 (hard refresh)
2. Close all browser tabs
3. Reopen application
```

---

### **❌ Audio device resets to "System Default"**

**Cause:** Configuration not saved properly  
**Fix:**
```
1. Settings tab → Select DAX device
2. Click "💾 Save Configuration"
3. Wait for green checkmark
4. Close modal and reopen
5. Verify device selection persists
```

**If still fails:**
```powershell
# Check if config file exists
Get-Content "logs\ft8_config.json"

# Should show your audio device
# If file missing or wrong, delete it and reconfigure:
Remove-Item "logs\ft8_config.json" -ErrorAction SilentlyContinue
```

---

### **❌ No decodes appearing**

**Possible causes:**

1. **Wrong audio device**
   - Settings → Verify "23: DAX Audio RX 1" selected
   - Not "System Default"

2. **DAX not enabled in SmartSDR**
   - SmartSDR → Audio tab → Enable DAX 1

3. **Radio not on FT8 frequency**
   - Tune to 14.074 MHz exactly
   - Mode must be DIGU (not USB or DIGL)

4. **No signals on band**
   - Check https://pskreporter.info
   - Try different frequency
   - Try different time of day

5. **Volume too low**
   - SmartSDR → Increase DAX output volume
   - FT8 needs clean audio signal

---

### **❌ Waterfall not updating**

**Don't worry!** Waterfall canvas error is not critical.

**Focus on:**
- Status bar "Decoded" count
- Decoded messages appearing
- Service staying active

Waterfall is visual only - doesn't affect decoding.

---

## **What Fixed?**

### **Fixed #1: scipy.signal.hamming error** ✅
- Replaced with numpy.hamming
- No more crashes during audio processing

### **Fixed #2: Configuration not saved** ✅
- Now saves to `logs/ft8_config.json`
- Settings persist across page reloads

### **Fixed #3: Audio device ignored** ✅
- Service now uses selected device
- Device index parsed correctly

### **Fixed #4: Frontend not loading config** ✅
- Modal loads saved settings on open
- All settings preserved

---

## **Testing Checklist**

- [ ] Server restarted
- [ ] Browser hard refreshed (Ctrl+F5)
- [ ] Audio device selected and saved
- [ ] Configuration persists after modal close/reopen
- [ ] Radio tuned to 14.074 MHz DIGU
- [ ] DAX 1 enabled in SmartSDR
- [ ] Service starts and stays active (green badge)
- [ ] No errors in browser console
- [ ] No scipy.signal.hamming errors in backend logs
- [ ] Decoded count increases (if signals present)
- [ ] Messages appear in decoded panel (if signals present)

---

## **Success Criteria**

✅ **Configuration saves and loads**  
✅ **Service starts without errors**  
✅ **Service stays running (doesn't stop immediately)**  
✅ **Audio device is used correctly**  
✅ **If signals present → Decodes appear**  

---

## **If Still Having Issues**

1. **Check backend logs:**
```powershell
Get-Content "logs\flex_debug.log" -Tail 50
```

2. **Check saved config:**
```powershell
Get-Content "logs\ft8_config.json"
```

3. **Test audio devices:**
```powershell
python -c "import sounddevice as sd; devices = sd.query_devices(); [print(f'{i}: {d[\"name\"]}') for i, d in enumerate(devices)]"
```

4. **Verify DAX in SmartSDR:**
   - Audio tab → DAX 1 should show "Active"
   - Sample rate: 24000 Hz
   - TX should be enabled

---

## **Need Help?**

**Check these files:**
- `FT8_CRITICAL_FIXES_APPLIED.md` - Technical details
- `FT8_TROUBLESHOOTING.md` - Comprehensive troubleshooting
- `logs/flex_debug.log` - Backend errors
- `logs/ft8_config.json` - Saved configuration

---

**Status: ALL FIXES APPLIED** ✅  
**Ready for testing!** 🚀