# FT8 Decoder Troubleshooting Guide

## ✅ **What's Working**
- FT8 service starts successfully
- Audio devices detected (221 devices!)
- Waterfall generation functional
- Signal detection working
- WebSocket communication active

## ❌ **Why No Decodes?**

### **Problem #1: Wrong Audio Device**
You're probably using "System Default" audio device, not FlexRadio DAX.

**Solution:**
1. Open FT8 modal → Settings tab
2. For **Audio Input**, select: `DAX Audio RX 1 (FlexRadio Systems DAX Audio)`
3. **Save Configuration**
4. Restart FT8 service (Stop → Start)

### **Problem #2: Radio Not Tuned to FT8**
FT8 is active on specific frequencies at specific times.

**FT8 Frequencies:**
- **20m**: 14.074 MHz (Most active!)
- **40m**: 7.074 MHz
- **80m**: 3.573 MHz
- **15m**: 21.074 MHz
- **10m**: 28.074 MHz

**When to Find Activity:**
- **Daytime (EU/US)**: Try 20m (14.074)
- **Evening**: Try 40m (7.074)
- **Night**: Try 80m (3.573)
- **Always check**: https://pskreporter.info/pskmap.html

**Solution:**
1. Tune your FlexRadio to 14.074 MHz (20m FT8)
2. Set mode to **DIGU** (Digital Upper)
3. Set filter width: 0-3000 Hz
4. Check pskreporter.info to see if FT8 is active NOW

### **Problem #3: No DAX Channel Assigned**
FlexRadio needs DAX enabled for your slice.

**Solution in SmartSDR:**
1. Click your slice (Slice A)
2. Click **DAX** button
3. Select **DAX 1**
4. Verify audio is flowing (you should see audio indicators)

### **Problem #4: Audio Sample Rate Mismatch**
FT8 needs 12kHz or 48kHz sample rate.

**Solution:**
1. FT8 modal → Settings
2. Sample Rate: **12000 Hz** (default)
3. Save Configuration

### **Problem #5: No FT8 Signals Present**
Sometimes the band is just dead!

**How to Check:**
- Visit: https://pskreporter.info/pskmap.html
- Look for green markers on your frequency
- If none → band is dead, try another frequency
- Check time of day (FT8 is time-synchronized every 15 seconds)

## 🧪 **Quick Test**

### **Test 1: Is Audio Flowing?**
```powershell
python test_ft8_status.py
```
Should show:
- ✅ Audio devices found
- ✅ Service starts
- ✅ Waterfall generated

### **Test 2: Is FT8 Service Running?**
1. Open browser console (F12)
2. Open FT8 modal
3. Click **Start**
4. Watch console for:
   - `FT8 service started`
   - `FT8 WebSocket connected`
   - WebSocket messages arriving

### **Test 3: Is Audio Being Captured?**
Look at the **Status Bar** (when service is running):
- **Decoded**: Should increase when signals are present
- **Uptime**: Should count up (proves service is running)
- **Waterfall**: Should show colors (not just black)

## 📝 **Step-by-Step Setup**

### **1. Configure FT8 Settings**
```
Open FT8 Modal → Settings Tab

Station:
  Mode: FT8
  My Callsign: OM0RX
  My Grid: JN88

Audio:
  Input: 23: DAX Audio RX 1 (FlexRadio Systems DAX Audio)  ← KEY!
  Output: 28: DAX Audio TX (FlexRadio Systems DAX Audio)
  Sample Rate: 12000 Hz
  [✓] Use FlexRadio DAX Audio

Click: Save Configuration
```

### **2. Setup FlexRadio**
```
SmartSDR:
  1. Tune to: 14.074 MHz
  2. Mode: DIGU
  3. Filter: 0-3000 Hz
  4. Click DAX → Select DAX 1
  5. Verify audio is flowing
```

### **3. Start FT8 Service**
```
FT8 Modal → Operate Tab
  1. My Call: OM0RX
  2. My Grid: JN88
  3. Mode: FT8
  4. Click: ▶️ Start

Watch Status Bar:
  📊 Decoded: (should increment)
  ⏱️ Uptime: (should count up)
```

### **4. Wait for Decodes**
FT8 works in 15-second cycles:
- **0-15s**: RX (receive, decode)
- **15-30s**: RX (receive, decode)
- **30-45s**: RX (receive, decode)
- etc.

Decodes appear at the **END** of each 15-second cycle.

## 🎯 **Expected Behavior**

### **When Working:**
```
Status Bar shows:
  📊 Decoded: 12 (increases every 15s)
  📤 Transmitted: 0
  ✅ QSOs: 0
  ⏱️ Uptime: 2m 30s

Decoded Messages Panel:
  21:45:32  -12  0.3  1456  CQ DL1ABC JO62
  21:45:32  -08  0.1  1678  W1XYZ K2ABC R-15
  21:45:32  +03  0.2  1234  CQ OM0RX JN88  ← YOUR CQ!
  21:45:17  -15  0.4  2145  CQ G3XYZ IO91
```

### **When NOT Working:**
```
Status Bar shows:
  📊 Decoded: 0  ← Stuck at zero
  ⏱️ Uptime: 3m 45s  ← Service is running

Possible causes:
  1. Wrong audio device selected
  2. No FT8 signals on frequency
  3. Radio not tuned correctly
  4. DAX not enabled
```

## 🆘 **Still Not Working?**

### **Check Browser Console:**
```javascript
F12 → Console tab

Should see:
  "FT8 service started"
  "FT8 WebSocket connected"
  WebSocket messages every second
```

### **Check Backend Logs:**
```powershell
Get-Content "c:\Projects\om0rx-radio-control\logs\flex_debug.log" -Tail 50

Should see:
  "FT8 service starting..."
  "Audio capture initialized"
  "Audio processing loop started"
```

### **Test with WSJT-X Audio**
If you have WSJT-X running:
1. WSJT-X → File → Settings → Audio
2. Note the input device it's using
3. Use the SAME device in FT8 settings
4. If WSJT-X decodes, yours should too!

## 🔗 **Resources**

- **Live FT8 Activity**: https://pskreporter.info/pskmap.html
- **FT8 Frequencies**: https://www.sigidwiki.com/wiki/FT8
- **Band Conditions**: https://www.hamqsl.com/solar.html
- **FT8 Protocol**: http://physics.princeton.edu/pulsar/k1jt/FT8_Protocol.pdf

## ✅ **Quick Checklist**

Before asking "why no decodes?":

- [ ] Radio tuned to FT8 frequency (e.g., 14.074 MHz)
- [ ] Mode set to DIGU
- [ ] DAX enabled in SmartSDR (DAX 1 or DAX Audio RX 1)
- [ ] FT8 settings show correct DAX device as audio input
- [ ] FT8 service started (green "🟢 Active")
- [ ] Status bar showing increasing uptime
- [ ] pskreporter.info shows FT8 activity on that frequency NOW
- [ ] Tried waiting at least 2 minutes for decodes
- [ ] Browser console shows no errors

## 📞 **Support**

If still not working after checking everything:
1. Run: `python test_ft8_status.py`
2. Share the output
3. Share browser console log (F12)
4. Share last 50 lines of `logs/flex_debug.log`

---

**Remember**: FT8 is time-synchronized. Decodes happen at the END of each 15-second cycle. If the band is dead, you'll see nothing - and that's normal!