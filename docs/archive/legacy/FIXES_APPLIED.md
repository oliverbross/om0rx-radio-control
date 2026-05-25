# Fixes Applied - 2-Way Sync for All Parameters + UI Layout

## Issues Fixed

### 1. **Mic Level Not Syncing (2-Way)**
**Problem**: Mic level was showing 0 and not syncing when changed in SmartSDR
**Root Cause**: 
- `refresh_radio_state()` only monitored slice parameters (mode/freq/filter)
- Did NOT parse transmit subscription updates (mic/drive/tune/vox)

**Solution**: 
- Extended `refresh_radio_state()` to parse `|transmit` and `|interlock` messages
- Added tracking for: `miclevel`, `rfpower`, `tunepower`, `vox_enable`
- Changes logged: `MICLEVEL CHANGED: 50 → 75`
- Results stored in `last_state_changed` dict for UI updates

### 2. **UI Layout Wrong**
**Problem**: Value labels ("Vol 53 Drive 28...") appeared in wrong position (middle of screen instead of below sliders)
**Root Cause**: 
- Both `strip` frame (sliders) and `vals` frame (labels) used `side='right'`
- This caused horizontal stacking instead of vertical stacking

**Solution**: 
- Changed packing to `side='top', anchor='e'` for both frames
- Now sliders appear at top, values directly below

### 3. **UI Not Updating on External Changes**
**Problem**: When user changed mic/drive/tune in SmartSDR, app sliders didn't move
**Root Cause**: 
- `_sync_ui_with_radio()` only updated buttons (band/mode/filter)
- Did NOT update sliders or checkboxes

**Solution**: 
- Added slider sync code to `_sync_ui_with_radio()`
- Checks `last_state_changed` dict from `refresh_radio_state()`
- Updates sliders: `mic_var.set(new_mic)`
- Updates value labels: `val_mic.config(text=str(new_mic))`
- Logs: `UI SYNC: Mic slider updated to 75`

## Code Changes

### File: `dxbridge.py`

#### **1. FlexCtl.__init__() - Initialize Tracking Variables** (Lines 733-740)
```python
# Transmit state tracking (for 2-way sync)
self.current_rfpower = None
self.current_tunepower = None
self.current_miclevel = None
self.current_vox_enable = None
# State change tracking (for UI updates)
self.last_state_changed = {}
```

#### **2. refresh_radio_state() - Parse Transmit Updates** (Lines 1141-1181)
```python
# Parse transmit/interlock updates for mic/drive/tune power changes
if "|transmit " in resp or "|interlock " in resp:
    # rfpower (Drive)
    m_rf = _re.search(r"\brfpower=(\d+)", resp)
    if m_rf:
        new_rfpower = int(m_rf.group(1))
        if not hasattr(self, 'current_rfpower') or new_rfpower != self.current_rfpower:
            if hasattr(self, 'current_rfpower'):
                logging.info(f"FlexCtl: RFPOWER CHANGED: {self.current_rfpower} → {new_rfpower}")
            state_changed['rfpower'] = new_rfpower
        self.current_rfpower = new_rfpower
    
    # miclevel (MIC LEVEL - THIS IS THE KEY FIX!)
    m_mic = _re.search(r"\bmiclevel=(\d+)", resp)
    if m_mic:
        new_miclevel = int(m_mic.group(1))
        if not hasattr(self, 'current_miclevel') or new_miclevel != self.current_miclevel:
            if hasattr(self, 'current_miclevel'):
                logging.info(f"FlexCtl: MICLEVEL CHANGED: {self.current_miclevel} → {new_miclevel}")
            state_changed['miclevel'] = new_miclevel
        self.current_miclevel = new_miclevel
```

#### **3. UI Layout - Fixed Frame Packing** (Lines 1847, 1866)
```python
# Pack the slider strip first (so it appears at the top)
strip.pack(side='top', anchor='e', padx=8, pady=4)

# Pack the value labels AFTER the sliders (so they appear below)
vals.pack(side='top', anchor='e', padx=6, pady=(0,2))
```

#### **4. _sync_ui_with_radio() - Update Sliders** (Lines 2144-2176)
```python
# Sync transmit parameters (mic/drive/tune) if they changed in SmartSDR
if hasattr(_flex_ctl, 'last_state_changed'):
    state_changes = _flex_ctl.last_state_changed
    
    # Update mic level slider
    if 'miclevel' in state_changes:
        new_mic = state_changes['miclevel']
        mic_var.set(new_mic)
        val_mic.config(text=str(new_mic))
        logging.info(f"UI SYNC: Mic slider updated to {new_mic}")
    
    # Update drive slider
    if 'rfpower' in state_changes:
        new_drive = state_changes['rfpower']
        drv_var.set(new_drive)
        val_drv.config(text=str(new_drive))
        logging.info(f"UI SYNC: Drive slider updated to {new_drive}")
    
    # Update tune power slider
    if 'tunepower' in state_changes:
        new_tune = state_changes['tunepower']
        tun_var.set(new_tune)
        val_tun.config(text=str(new_tune))
        logging.info(f"UI SYNC: Tune slider updated to {new_tune}")
    
    # Update VOX checkbox
    if 'vox_enable' in state_changes:
        new_vox = state_changes['vox_enable']
        vox_on.set(new_vox)
        logging.info(f"UI SYNC: VOX checkbox updated to {new_vox}")
    
    # Clear state_changed dict after processing
    _flex_ctl.last_state_changed = {}
```

## How 2-Way Sync Works Now

### App → SmartSDR (Already Working)
1. User moves mic slider in app
2. `set_mic_level()` sends: `transmit set miclevel=75`
3. Radio confirms with status message
4. Mic level updates immediately

### SmartSDR → App (NOW FIXED!)
1. User changes mic level in SmartSDR
2. Radio sends subscription update: `S12345|transmit ... miclevel=75 ...`
3. `refresh_radio_state()` reads message (every 1 second)
4. Parses mic level change: `MICLEVEL CHANGED: 50 → 75`
5. Stores in `last_state_changed['miclevel'] = 75`
6. `_sync_ui_with_radio()` detects change
7. Updates slider: `mic_var.set(75)`
8. Updates label: `val_mic.config(text='75')`
9. Logs: `UI SYNC: Mic slider updated to 75`

## Testing Checklist

✅ **Mic Level Initial Value**
- [ ] App shows correct mic level on startup (not 0)

✅ **2-Way Sync - App to SmartSDR**
- [ ] Move mic slider in app → SmartSDR updates immediately

✅ **2-Way Sync - SmartSDR to App**
- [ ] Change mic level in SmartSDR → App slider moves within 1-2 seconds
- [ ] Change drive in SmartSDR → App slider moves
- [ ] Change tune power in SmartSDR → App slider moves
- [ ] Toggle VOX in SmartSDR → App checkbox updates

✅ **UI Layout**
- [ ] Value labels appear BELOW sliders (not in middle of screen)
- [ ] "Vol 53 Drive 28 Tune 13 Mic 75 Lo -3000 Hi 3000" aligned under sliders

✅ **All Other Features Still Work**
- [ ] Band buttons work and highlight correctly
- [ ] Mode buttons work and highlight correctly
- [ ] Filter buttons work and highlight correctly
- [ ] Mode/band/filter changes in SmartSDR reflect in app

## Log Messages to Watch For

### Startup
```
FlexCtl initialized for 192.168.1.100:4992 slice 0
Fetching initial radio state...
  Parsed miclevel=50
Set mic slider to 50
```

### External Change Detection
```
FlexCtl: MICLEVEL CHANGED: 50 → 75
UI SYNC: Mic slider updated to 75
```

### Polling Summary
```
FlexCtl refresh: Read 3 message(s), changes: ['miclevel', 'rfpower']
```

## Key Technical Details

1. **Transmit Subscriptions**: The `sub transmit all` command triggers radio to send updates
2. **Message Types**: Radio sends `|transmit` messages with `miclevel=XX` parameter
3. **Polling Frequency**: 1 second interval (1000ms) - fast enough for real-time feel
4. **Change Detection**: Only updates UI when values actually changed (avoids slider jitter)
5. **State Tracking**: `current_miclevel` stores last known value, `last_state_changed` stores delta
6. **Layout Fix**: `side='top', anchor='e'` creates vertical stacking with right alignment

## Files Modified
- `c:\Projects\om0rx-radio-control\dxbridge.py` - All changes
- Python bytecode cache cleared

## Next Steps
1. Test mic level initial value
2. Test 2-way sync for all sliders (mic/drive/tune)
3. Test VOX checkbox sync
4. Verify layout is correct
5. Report any remaining issues