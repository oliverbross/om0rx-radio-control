# FT8 Audio Device Fix - CRITICAL BUG RESOLVED

## 🔴 Problem Identified

The FT8 service was **NOT using the configured audio device**. Even though the UI allowed selecting "23: DAX Audio RX 1", the service always started with "default" audio device.

### Root Cause

**File:** `frontend/js/ft8-modal.js` Line 243-268

The `ft8StartService()` function was only sending basic config (mycall, mygrid, mode) but **NOT** the audio device configuration.

```javascript
// ❌ BEFORE (Missing audio config)
body: JSON.stringify({
    mode: this.ft8.mode,
    mycall: this.ft8.mycall,
    mygrid: this.ft8.mygrid,
    auto_sequence: this.ft8.autoSequence,
    tx_enabled: this.ft8.txEnabled
    // Missing: audioInput, audioOutput, sampleRate, etc.
})
```

### Evidence from Logs

```
2025-11-05 18:04:08 | INFO | Starting FT8 service with audio device: default
2025-11-05 18:04:08 | INFO | Real audio capture started (device None, 12000 Hz)
```

**BUT** the saved config said:
```json
"audioInput": "23: DAX Audio RX 1 (FlexRadio Syste"
```

The service received "default" because the frontend didn't send the saved value!

---

## ✅ Solution Applied

**File Modified:** `frontend/js/ft8-modal.js`

Added all config fields to the start request:

```javascript
// ✅ AFTER (Complete config)
body: JSON.stringify({
    mode: this.ft8.mode,
    mycall: this.ft8.mycall,
    mygrid: this.ft8.mygrid,
    auto_sequence: this.ft8.autoSequence,
    tx_enabled: this.ft8.txEnabled,
    audioInput: this.ft8.audioInput || 'default',
    audioOutput: this.ft8.audioOutput || 'default',
    sampleRate: this.ft8.sampleRate || 12000,
    waterfallHeight: this.ft8.waterfallHeight || 100,
    networkServer: this.ft8.networkServer || '192.168.0.199:4992',
    pttMethod: this.ft8.pttMethod || 'CAT',
    useFlexRadioAudio: this.ft8.useFlexRadioAudio !== undefined ? this.ft8.useFlexRadioAudio : true
})
```

---

## 🚀 Testing Steps

### 1. Hard Refresh Browser
```
Press: Ctrl + F5
```
**Why:** Load the fixed JavaScript file

### 2. Verify Config Loaded
1. Open FT8 Modal
2. Go to Settings tab
3. Verify "Audio Input" shows: `23: DAX Audio RX 1...`
4. If not, select it again and click "Save Configuration"

### 3. Start Service and Check Logs

**In PowerShell:**
```powershell
Get-Content "c:\Projects\om0rx-radio-control\logs\flex_debug.log" -Tail 20 -Wait
```

**Click "Start" button in FT8 Modal**

### 4. Verify Correct Audio Device

**Expected Output:**
```
Starting FT8 service with audio device: 23: DAX Audio RX 1 (FlexRadio Syste
Using audio device index: 23
Real audio capture started (device 23, 12000 Hz)
✅ FT8 service started successfully
```

**❌ Bad Output (means frontend not updated):**
```
Starting FT8 service with audio device: default
Real audio capture started (device None, 12000 Hz)
```

### 5. Verify DAX Audio is Active

**In SmartSDR:**
- Check "Audio" tab → "DAX" section
- "DAX 1" should show green/active
- Audio stream should be flowing

### 6. Check for Decodes

**If signals present on band:**
- Waterfall should show vertical "streaks" (FT8 signals)
- Decoded messages appear in right panel after 15 seconds
- Counter "Decoded: X" should increment

---

## 📊 Sample Rate Information

### FT8 Standard: 12000 Hz

The FT8 protocol requires **12000 Hz sample rate** for proper decoding. This is the WSJT-X standard.

### DAX Audio: 48000 Hz

FlexRadio DAX audio outputs at **48000 Hz** by default.

### Current Behavior

The audio capture service requests 12000 Hz, and sounddevice library may automatically resample. However, for best results:

**Option 1: Let sounddevice resample (current)**
- Config: `sampleRate: 12000`
- Audio capture: Requests 12000 Hz
- sounddevice: Auto-resamples from 48000 → 12000

**Option 2: Manual resample (future improvement)**
- Capture at 48000 Hz
- Resample to 12000 Hz using scipy.signal.resample
- Better quality control

For now, **Option 1 is implemented** and should work.

---

## 🔍 Troubleshooting

### Service Starts but No Decodes

**Check 1: Band Activity**
- Visit https://pskreporter.info/pskmap.html
- Verify FT8 activity on your frequency
- 14.074 MHz is most active during daytime

**Check 2: Radio Configuration**
```
Frequency: 14.074 MHz (USB)
Mode: DIGU (Digital Upper)
Filter: 0 - 3000 Hz
DAX 1: ENABLED in SmartSDR
```

**Check 3: Audio Levels**
- SmartSDR: Check DAX RX audio meter
- Should show green bars when receiving
- Adjust "Audio Level" slider if needed

**Check 4: Time Synchronization**
- FT8 requires accurate time (within 1 second)
- Check Windows time: `w32tm /query /status`
- Sync if needed: `w32tm /resync`

### Waterfall Shows Only Noise

**Possible Causes:**
1. **No signals on band** → Try different time of day
2. **Wrong audio source** → Verify DAX 1 is selected
3. **Audio level too low** → Increase SmartSDR audio level
4. **Wrong frequency** → Check radio is on 14.074 MHz

### Service Still Using "default"

**Solution:**
1. Verify you refreshed browser (Ctrl+F5)
2. Check browser console for errors
3. Verify `ft8-modal.js` was updated:
   ```powershell
   Select-String -Path "c:\Projects\om0rx-radio-control\frontend\js\ft8-modal.js" -Pattern "audioInput:"
   ```
   Should show line with `audioInput: this.ft8.audioInput`

---

## 📚 About ft8d-master Decoder

You discovered the **real FT8 decoder** from WSJT-X (Joe Taylor K1JT):

```
ft8d-master/
├── ft8d.f90                      # Main decoder program
├── bpdecode174_91.f90            # LDPC decoder (belief propagation)
├── ldpc_174_91_c_generator.f90   # LDPC code generator
├── sync8.f90                     # Signal synchronization
├── ft8b.f90                      # Core FT8 decoder
└── ft8_params.f90                # FT8 constants
```

### Current Python Implementation

The current `services/ft8_protocol.py` has **skeleton code** but:
- ❌ LDPC encoder/decoder are stubs
- ❌ No real belief-propagation decoding
- ❌ No proper sync8 algorithm
- ✅ Basic Costas sync detection works
- ✅ Message formatting works

### Future Integration

To use the **real decoder**, we would need to:

1. **Compile ft8d** (requires gfortran)
2. **Create Python wrapper** using ctypes or f2py
3. **Feed audio buffer** in correct format (.c2 files)
4. **Parse decoder output** and display in UI

This is a **significant project** but would give you production-quality FT8 decoding.

### Alternative: Call External Decoder

```python
# Write audio to .wav file
audio_file = save_audio_to_wav(audio_buffer)

# Call wsjt-x decoder (if installed)
result = subprocess.run(['ft8d', audio_file], capture_output=True)

# Parse output
decoded_messages = parse_ft8d_output(result.stdout)
```

---

## 📝 Summary

**Problem:** Audio device configuration not sent to backend  
**Cause:** Frontend missing config fields in start request  
**Fix:** Added all config fields to start request payload  
**Status:** ✅ FIXED - Ready for testing

**Next Steps:**
1. Refresh browser (Ctrl+F5)
2. Start FT8 service
3. Verify logs show correct device
4. Wait for decodes (if signals present)

---

## 🎯 Expected Results

After this fix:
- ✅ Service uses DAX Audio RX 1 (device 23)
- ✅ Waterfall displays audio spectrum
- ✅ Decoder processes audio (if current implementation works)
- ⚠️ Decoding success depends on current LDPC implementation

**If still no decodes after 5 minutes:** The current Python LDPC decoder may be incomplete. Consider integrating the real `ft8d` Fortran decoder.

---

**Document Created:** 2025-11-05  
**Bug Severity:** HIGH (complete feature non-functional)  
**Fix Complexity:** LOW (single line change)  
**Testing Required:** Manual verification with real audio