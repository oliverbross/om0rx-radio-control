# Functional Controls Fixed - Complete Summary

This document summarizes all the fixes applied to make non-functional buttons and controls work with bidirectional sync to FlexRadio SmartSDR.

## Fixed Issues

### 1. ✅ RIT/XIT Controls - FULLY FUNCTIONAL
**Problem:** RIT/XIT buttons and arrows didn't work, no API commands sent.

**Solution:**
- **Backend (`dxbridge.py`):**
  - Added `set_rit(enabled, freq_hz)` method using `slice set X rit_on=1/0` and `rit_freq=Hz`
  - Added `set_xit(enabled, freq_hz)` method using `slice set X xit_on=1/0` and `xit_freq=Hz`
  - Added parsing of `rit_on`, `rit_freq`, `xit_on`, `xit_freq` in `get_current_levels()` and `refresh_radio_state()`
  
- **Backend (`main.py`):**
  - Added `/api/rit` and `/api/xit` endpoints with `RITXITRequest` model
  - Added RIT/XIT status to initial `/api/status` response
  
- **Frontend (`app.js`):**
  - Made `toggleRIT()` and `toggleXIT()` async and wired to API
  - Made `adjustRIT(direction)` and `adjustXIT(direction)` async with auto-enable when adjusting
  - Uses current tuning step value for arrow adjustments
  - Added data properties: `ritEnabled`, `ritValue`, `xitEnabled`, `xitValue`
  - Added real-time sync in `updateRadioStatus()` for `rit_enabled`, `rit_freq`, `xit_enabled`, `xit_freq`

- **Frontend (`index.html`):**
  - Added `:class="ritEnabled ? 'active' : ''"` for visual feedback on RIT button
  - Added `:class="xitEnabled ? 'active' : ''"` for visual feedback on XIT button

**How it works:**
1. Click "RIT" or "XIT" button to enable/disable
2. Use arrows (◀/▶) to adjust frequency offset by current tuning step
3. Arrows auto-enable RIT/XIT when clicked
4. Syncs bidirectionally with SmartSDR (changes in SmartSDR update web UI)

---

### 2. ✅ Step Dropdown - ALREADY WORKING (No API needed)
**Problem:** User thought step dropdown didn't work.

**Clarification:**
- Tuning step is a **client-side UI setting**, not sent to radio
- The step value is used locally for:
  - RIT/XIT arrow adjustments
  - Future frequency tuning controls
- **No FlexRadio API command needed** - step is stored in browser only

---

### 3. ✅ Break.In Button - FULLY FUNCTIONAL
**Problem:** Break.In button had no click handler, didn't sync with SmartSDR.

**Solution:**
- **Frontend (`index.html`):**
  - Changed from `<button>Break.In</button>` to `<button @click="toggleVox" :class="txState.vox ? 'vox-active' : ''">Break.In</button>`
  - Now calls the same `toggleVox()` method as the VOX button
  - Shows visual feedback when active (glows orange)

**How it works:**
- Click to toggle VOX (voice-activated transmit)
- Syncs with SmartSDR via existing `/api/vox` endpoint
- Both "VOX" and "Break.In" buttons control the same feature

---

### 4. ✅ Monitor Slider - AUTO-ENABLE ON MOVE
**Problem:** Monitor slider didn't auto-enable monitor when moved from 0. Didn't sync bidirectionally.

**Solution:**
- **Backend (`dxbridge.py`):**
  - Added `set_monitor(level, auto_enable=True)` method
  - When level > 0 and `auto_enable=True`, sends `transmit set mon=1` first
  - Then sets level with `transmit set mon_gain_sb={level}`
  - When level == 0, sends `transmit set mon=0` to disable
  - Added parsing of `mon` and `mon_gain_sb` in `get_current_levels()` and `refresh_radio_state()`

- **Backend (`main.py`):**
  - Updated `/api/monitor` endpoint to call `flex.set_monitor(req.value, auto_enable=True)`

**How it works:**
1. User moves slider from 0 → automatically enables monitor in SmartSDR
2. User moves slider to 0 → automatically disables monitor
3. Changes in SmartSDR sync to web UI slider

---

### 5. ✅ AGC-T Slider - ALREADY WORKING
**Problem:** User reported AGC-T slider not working.

**Status:**
- **Backend:** `/api/agc_threshold` endpoint already exists and functional
- **Frontend:** `setAGCThreshold()` method wired to slider `@input` event
- **API:** Uses `audio client 0 slice X rxagc_threshold={value}`
- Added parsing in `get_current_levels()` and `refresh_radio_state()` for bidirectional sync

**Note:** AGC-T (AGC Threshold) controls the AGC knee point (0-100), separate from AGC mode (OFF/SLOW/MED/FAST).

---

### 6. ✅ DSP Level Sliders - FULLY FUNCTIONAL
**Problem:** NB/NR/ANF/APF buttons only turned features on/off, couldn't adjust levels.

**Solution:**
- **Backend (`dxbridge.py`):**
  - Added `set_dsp_level(control, level)` method using `slice set X {control}={level}`
  - Added parsing of `nb_level`, `nr_level`, `anf_level`, `apf_level` in both status methods
  - Added parsing of `nb_on`, `nr_on`, `anf_on`, `apf_on` for on/off states

- **Backend (`main.py`):**
  - Added `/api/dsp_level` endpoint with `DSPLevelRequest` model
  - Added DSP levels to `/api/status` initial response
  - Added DSP level tracking to real-time broadcasts

- **Frontend (`app.js`):**
  - Added `dspLevels: { nb: 50, nr: 50, anf: 50, apf: 50 }` data properties
  - Added `showDSPSlider: { nb: false, nr: false, anf: false, apf: false }` for visibility
  - Modified `toggleDSP(control)` to toggle slider visibility when enabling DSP
  - Added `setDSPLevel(control)` method to send level to API
  - Added real-time sync in `updateRadioStatus()` for all DSP levels

- **Frontend (`index.html`):**
  - Added DSP level sliders below DSP buttons
  - Sliders appear/disappear when you click DSP buttons (NB/NR/ANF/APF)
  - Compact design with mini sliders (font-size: 9px, width: 80px)
  - Dark semi-transparent background for slider group
  - Aligned with DSP buttons (position: relative; left: -55px)

**How it works:**
1. Click NB/NR/ANF/APF button to turn feature ON → slider appears
2. Click again to toggle slider visibility (feature stays on)
3. Turn feature OFF → slider disappears
4. Move slider to adjust DSP level (0-100)
5. Changes in SmartSDR sync to web UI in real-time

**Visual Layout:**
```
[NB] [NR] [ANF] [APF]  ← DSP buttons

 NB ──────●── 50       ← Sliders appear when clicked
 NR ──────●── 50
 ANF ─────●── 50
```

---

## API Commands Used

### FlexRadio SmartSDR TCP/IP API Commands:

1. **RIT:**
   - `slice set 0 rit_on=1` / `rit_on=0` - Enable/disable
   - `slice set 0 rit_freq=40` - Set offset in Hz

2. **XIT:**
   - `slice set 0 xit_on=1` / `xit_on=0` - Enable/disable
   - `slice set 0 xit_freq=40` - Set offset in Hz

3. **Monitor:**
   - `transmit set mon=1` / `mon=0` - Enable/disable
   - `transmit set mon_gain_sb=50` - Set level 0-100

4. **DSP Levels:**
   - `slice set 0 nb_level=50` - Noise Blanker level
   - `slice set 0 nr_level=50` - Noise Reduction level
   - `slice set 0 anf_level=50` - Auto Notch Filter level
   - `slice set 0 apf_level=50` - Audio Peak Filter level

5. **AGC Threshold:**
   - `audio client 0 slice 0 rxagc_threshold=65` - Set AGC threshold

---

## Bidirectional Sync

All controls now support **full bidirectional synchronization**:

### From Web UI → SmartSDR:
- User interactions in web UI send commands to radio
- Radio applies changes immediately

### From SmartSDR → Web UI:
- `refresh_radio_state()` polls radio every 1 second
- Parses subscription updates for all parameters
- Broadcasts changes via WebSocket to all connected clients
- Frontend updates UI controls to match radio state

**Tracked Parameters:**
- `rit_enabled`, `rit_freq`
- `xit_enabled`, `xit_freq`
- `monitor` (level)
- `nb_enabled`, `nb_level`
- `nr_enabled`, `nr_level`
- `anf_enabled`, `anf_level`
- `apf_enabled`, `apf_level`
- `agc_mode`, `agc_threshold`
- `vox_enabled`

---

## Testing Checklist

- [x] RIT enable/disable works
- [x] RIT arrows adjust frequency offset
- [x] XIT enable/disable works
- [x] XIT arrows adjust frequency offset
- [x] Break.In button toggles VOX
- [x] Monitor slider auto-enables at >0
- [x] Monitor slider disables at 0
- [x] AGC-T slider adjusts threshold
- [x] NB/NR/ANF/APF buttons turn features on/off
- [x] Clicking DSP buttons shows/hides level sliders
- [x] DSP level sliders adjust levels
- [x] All controls sync FROM SmartSDR to web UI
- [x] All controls sync FROM web UI to SmartSDR

---

## Files Modified

### Backend:
1. **`dxbridge.py`:**
   - Added `set_rit()`, `set_xit()`, `set_monitor()`, `set_dsp_level()` methods
   - Enhanced `get_current_levels()` to parse RIT/XIT/DSP/monitor
   - Enhanced `refresh_radio_state()` to track changes in real-time

2. **`main.py`:**
   - Added `RITXITRequest`, `DSPLevelRequest` models
   - Added `/api/rit`, `/api/xit`, `/api/dsp_level` endpoints
   - Updated `/api/monitor` to use auto-enable
   - Updated `/api/status` to include all new parameters

### Frontend:
1. **`app.js`:**
   - Added data properties for RIT/XIT/DSP levels/slider visibility
   - Wired `toggleRIT()`, `adjustRIT()`, `toggleXIT()`, `adjustXIT()`
   - Enhanced `toggleDSP()` to control slider visibility
   - Added `setDSPLevel()` method
   - Added real-time sync in `updateRadioStatus()`

2. **`index.html`:**
   - Fixed Break.In button to call `toggleVox`
   - Added active class to RIT/XIT buttons
   - Added DSP level slider UI with show/hide logic

---

## Technical Notes

### RIT/XIT Step Resolution:
- Uses current tuning step from dropdown
- Converts step string (e.g., "10 Hz", "1 kHz") to Hz value
- Sends integer Hz offset to radio

### Monitor Auto-Enable:
- SmartSDR requires monitor to be enabled before level has effect
- Auto-enable logic ensures smooth UX (just move slider)
- Prevents user confusion about why slider doesn't work

### DSP Slider Visibility:
- Only shows sliders for active DSP features
- Prevents UI clutter when features are off
- Toggle click on active button shows/hides slider

### Bidirectional Sync Strategy:
- Poll every 1 second via `refresh_radio_state()`
- Parse all slice/transmit subscription messages
- Track changes in `state_changed` dict
- Broadcast only changed parameters to reduce traffic

---

## References

- [FlexRadio SmartSDR API Documentation](https://github.com/flexradio/smartsdr-api-docs/wiki)
- [FlexRadio Community: TCP/IP API RIT/XIT](https://community.flexradio.com/discussion/8026500/tcp-ip-api-commands-to-manipulate-rit-and-xit)
- [SmartSDR Software User Guide (PDF)](https://edge.flexradio.com/www/uploads/20200818184951/SmartSDR-Software-User-Guide.pdf)

---

## Summary

All previously non-functional controls are now **fully operational** with **complete bidirectional synchronization** between the web UI and SmartSDR. Users can control the radio from either the web interface or SmartSDR itself, and both interfaces stay in sync in real-time.

**Date:** 2025
**Version:** 2.0
**Status:** ✅ ALL CONTROLS FUNCTIONAL