# FT8 Audio Input Fix

## Problem
The FT8 decoder was receiving audio but not detecting any signals because:
1. **Invalid audio input device**: Config had `"audioInput": "flexradio"` which is not a valid device name/index
2. **Result**: Audio capture failed silently, falling back to simulated low-amplitude noise
3. **Signal detection failed**: Audio energy (0.0001) was below detection threshold (0.001)

## Root Cause
The audio capture service tried to open device "flexradio" but couldn't find it, so it fell back to simulated audio (random noise with std=0.01), which is too quiet to detect.

## Solution Applied

### 1. Updated Audio Input Device
**File:** `logs/ft8_config.json`

**Before:**
```json
"audioInput": "flexradio"
```

**After:**
```json
"audioInput": "194: DAX Audio RX 1 (DAX Audio RX 1)"
```

This uses the correct FlexRadio DAX Audio RX 1 device for capturing audio from the radio's main receiver.

### 2. Enhanced Debug Logging
**Files modified:**
- `frontend/js/ft8-decoder.js` - Added audio statistics logging (min, max, avgAbs, energy)
- `frontend/js/ft8-modal.js` - Added audio stream reception logging

### 3. Lowered Detection Threshold
Changed signal detection threshold from **0.01** to **0.001** to detect weaker signals.

## Available DAX Audio Devices

### For Input (Capturing FROM Radio):
- **194: DAX Audio RX 1** - Main receiver (recommended for FT8) ✅ NOW CONFIGURED
- **196: DAX Audio RX 2** - Second receiver
- **198-208**: DAX Audio RX 3-8 - Additional receivers
- **219: DAX MIC Audio** - Microphone input

### For Output (Transmitting TO Radio):
- **28: DAX Audio TX** - Transmit audio ✅ ALREADY CONFIGURED

## Next Steps

### 1. Restart Backend Server
The backend needs to reload the `ft8_config.json`:

```powershell
# Stop current server (Ctrl+C)
# Start again:
python -m backend.main
```

### 2. Reload FT8 Modal in Browser
1. **Hard refresh browser**: `Ctrl + Shift + R`
2. **Close FT8 modal** if open
3. **Reopen FT8 modal** - It will reload the config

### 3. Verify Audio Capture
Check the backend console for this message:
```
✅ Real audio capture started: [194] DAX Audio RX 1 (DAX Audio RX 1) @ 12000 Hz
```

If you see "Simulated audio capture started", something is wrong.

### 4. Check Browser Console
After opening FT8 modal, you should see:
```
🎵 Audio received: XXXX samples from Array
🎵 Sample preview: min=-0.XXXX, max=0.XXXX, avgAbs=0.XXXX
📊 Audio stats: min=-0.XXXX, max=0.XXXX, avgAbs=0.XXXX, samples=132000
📊 Energy: max=0.XXXXX, threshold=0.001, chunks_above_threshold=XX
```

**Good signs:**
- `max` and `min` are NOT all zeros
- `avgAbs` > 0.001 (indicates actual audio, not just noise)
- `chunks_above_threshold` > 0
- `Found X potential signals` (where X > 0)

**Bad signs:**
- All values near zero = no audio
- `chunks_above_threshold=0` = audio too quiet
- `⚠️ Unknown audio format` = data format issue

## Troubleshooting

### Still No Audio?
1. **Check if FlexRadio is connected** and a panadapter is active
2. **Try a different DAX device**: Change audioInput to "23" or "76" in ft8_config.json
3. **Verify DAX channels are created** in SmartSDR
4. **Check Windows sound settings** to ensure DAX devices are enabled

### Audio Too Quiet?
If energy is still below threshold:
- Increase FlexRadio audio gain
- Lower threshold further in `ft8-decoder.js` (line 292)
- Check if the correct slice is being captured

### Wrong Frequency?
Make sure the DAX channel is connected to the correct slice/panadapter in SmartSDR.

## Technical Details

### Audio Flow
1. **FlexRadio** → SmartSDR DAX → **DAX Audio RX 1** (Windows audio device)
2. **Backend** → `audio_capture.py` → sounddevice captures from device 194
3. **Backend** → `ft8_service.py` → Buffers audio, sends to frontend every 0.5s
4. **Frontend** → `ft8-modal.js` → Receives audio stream via WebSocket
5. **Frontend** → `ft8-decoder.js` → Detects signals and decodes with WASM modules

### Debug Script
Created: `list_audio_devices.py` - Lists all FlexRadio DAX devices with indices

### Files Modified
- ✅ `logs/ft8_config.json` - Updated audioInput device
- ✅ `frontend/js/ft8-decoder.js` - Enhanced debug logging
- ✅ `frontend/js/ft8-modal.js` - Enhanced audio reception logging

## Expected Results After Fix

**Console output when FT8 is working correctly:**
```
🎵 Audio received: 6000 samples from Array
🎵 Sample preview: min=-0.0234, max=0.0189, avgAbs=0.0056
🔍 Decoding FT8 signals from 132000 samples...
📊 Audio stats: min=-0.0891, max=0.0823, avgAbs=0.0089, samples=132000
📊 Energy: max=0.008912, threshold=0.001, chunks_above_threshold=247
Found 3 potential signals
✅ Decoded: CQ DF2EQ JO31
✅ Decoded: 9A1A DL8DXL JO31
```

**If you see this, FT8 is working!** 🎉

---

**Created:** 2025-01-XX
**Status:** Ready to test - restart backend and reload browser