# Rotor AUTO - UI Visual Guide

## Where to Find Everything

### 1. AUTO Button Location (Main UI)
```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  [Rotor Control - Left Side]                               │
│  ┌────────────────────────────┐                            │
│  │ Az: [  0  ] ° [GO] [AUTO] ← NEW BUTTON HERE!            │
│  │                                                         │
│  │ [Director ▼] [N] [S] [E] [W]                            │
│  └────────────────────────────┘                            │
│                                                             │
│  [Central Area - Frequency, DSP Buttons, Sliders]         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**AUTO Button States:**
- 🟦 Gray (default)      = AUTO disabled, click to enable
- 🟩 Green (glowing)     = AUTO enabled and ready
- 🟧 Amber (pulsing)     = 2-second countdown, click to cancel

---

### 2. Configuration Section Location (Settings)

```
SETTINGS PANEL
├─ Flex & UDP
├─ Rotor          ← CLICK THIS TAB
│  ├─ ☑ Rotator Enabled
│  ├─ Rotator Type: [Microham ARCO]
│  ├─ IP Address: [192.168.0.198]
│  ├─ TCP Port: [4001]
│  ├─ Protocol: [DCU-1 / Rotor-EZ ▼]
│  ├─ Read Timeout: [2.5]
│  │
│  ├─ ────────────────────────────
│  │
│  ├─ 🤖 AUTO MODE CONFIGURATION    ← NEW SECTION HERE!
│  │
│  ├─ ☑ Enable Rotor AUTO (auto-turn to spots/stations)
│  │
│  ├─ 📍 Your Home Location (Maidenhead Gridsquare)
│  │  ├─ Grid: [JN88TQ______] Format: 2/4/6/8 chars
│  │  ├─ Lat: [48.6875______] Lon: [17.6250______]
│  │
│  ├─ 📡 Select Bands for Rotor Control
│  │  ├─ ☐160m  ☐80m   ☐60m   ☐40m
│  │  ├─ ☐30m   ☑20m   ☑17m   ☑15m
│  │  ├─ ☑12m   ☑10m   ☐6m    ☐2m
│  │
│  ├─ ℹ️ When AUTO is enabled, the rotor will automatically
│  │     calculate and move toward DX spots based on your
│  │     gridsquare and the spot's gridsquare (from QRZ)...
│  │
│  ├─ ────────────────────────────
│  ├─ Configure your Microham ARCO...
│
├─ CTY / Paths
├─ Logging
└─ Colours
```

---

## Quick Start (30 seconds)

### Step 1: Open Settings
Click ⚙️ (Settings button) in top right

### Step 2: Go to Rotor Tab
Click "Rotor" tab in settings panel

### Step 3: Enable AUTO
1. Make sure "☑ Rotator Enabled" is checked
2. Scroll down to "🤖 AUTO MODE CONFIGURATION"
3. Check "☑ Enable Rotor AUTO"

### Step 4: Enter Your Location
1. In "📍 Your Home Location", enter your Maidenhead grid
   - Example: JN88TQ, FN30, IO87, etc.
   - Lat/Lon auto-fill below

### Step 5: Select Your Bands
1. In "📡 Select Bands for Rotor Control"
2. Check boxes for bands where you have a rotor
   - Example: ☑20m ☑17m ☑15m ☑12m ☑10m
3. Leave unchecked for omnidirectional or no rotor
   - Example: ☐160m ☐80m ☐40m (omni antenna on these)

### Step 6: Close Settings
Click anywhere outside settings panel

### Step 7: Test It!
1. Find a DX spot in the cluster
2. Click on it
3. Watch the AUTO button pulse amber (2-second countdown)
4. After 2 seconds, rotor moves automatically!
   - OR click CANCEL to prevent movement

---

## Field Guide

### 🟦 AUTO Button States & Actions

| State | Appearance | Meaning | Click Action |
|-------|-----------|---------|--------------|
| Disabled | Gray | AUTO off | Enables AUTO mode |
| Enabled | Green glow | AUTO ready | Disables AUTO mode |
| Countdown | Amber pulse | Rotor moving in 2s | Cancels movement |

### 📍 Home Location Fields

| Field | Format | Example | Purpose |
|-------|--------|---------|---------|
| Grid | 2-8 chars | JN88TQ | Maidenhead locator of your station |
| Lat | -90 to 90 | 48.6875 | Your latitude (degrees) |
| Lon | -180 to 180 | 17.6250 | Your longitude (degrees) |

**Note:** Lat/Lon auto-calculate from Grid. Edit if you know exact coordinates.

### 📡 Band Checkboxes

- **Common options:**
  - ☑ 20m, 17m, 15m, 12m, 10m (typical HF Yagi setup)
  - ☑ 6m, 2m (VHF Yagi setup)
  - ☐ 160m, 80m, 40m (omni antenna, no rotor needed)

- **All 12 bands:**
  - 160m, 80m, 60m, 40m (LF/MF)
  - 30m, 20m, 17m, 15m, 12m, 10m (HF)
  - 6m, 2m (VHF)

---

## Workflow Examples

### Example 1: Operator hears a spot on 20m
```
1. 🔊 Hears: "Calling CQ on 20.015 USB from N0N with 5 and 9"
2. 🖱️ Clicks spot in cluster window
   └─ Radio tunes to 20.015
   └─ Callsign: N0N entered in log form
3. ⏳ QRZ lookup fetches gridsquare (1-3 seconds)
4. 🔴 AUTO button turns amber and pulses
   └─ Calculates bearing from JN88TQ to N0N's gridsquare
   └─ "2 seconds until rotor moves..."
5. ✓ After 2 seconds (no CANCEL clicked):
   └─ 🤖 Rotor moves to 205°
   └─ Status shows: "🤖 Rotor → 205° for N0N"
6. 📻 Operator calls CQ now pointing toward N0N!
```

### Example 2: Operator on 40m band (omni antenna)
```
1. 🖱️ Clicks spot on 40m
2. ⏳ QRZ lookup proceeds
3. ✓ Rotor AUTO calculation happens
4. 🔇 Rotor does NOT move (40m is unchecked in bands)
5. 💬 Console shows: "ℹ️ Rotor AUTO not executed: band not configured"
6. 🎯 Operator proceeds normally (omni antenna doesn't need rotor)
```

### Example 3: Operator cancels rotor movement
```
1. 🖱️ Clicks spot on 20m
2. 🔴 AUTO button pulses amber
3. ⏸️ Operator realizes they're still in middle of QSO!
4. 🖱️ Quickly clicks CANCEL button
5. ✓ Rotor does NOT move
6. 🟩 AUTO button returns to green (still enabled)
7. 📻 Rotor stays on previous bearing
```

### Example 4: Manual callsign entry (no spot clicked)
```
1. 📝 Operator types "N0N" manually in log form
2. ⏳ Vue waits 1 second after typing stops
3. 🌐 QRZ lookup auto-starts
4. 🔴 AUTO button pulses amber
5. ✓ After 2 seconds:
   └─ Rotor moves to calculated bearing
6. 🟩 AUTO button back to green
```

---

## Troubleshooting

### AUTO button doesn't appear
**Problem:** No AUTO button visible next to GO button
**Solution:** Rotator must be enabled
1. Go to Settings → Rotor
2. Check ☑ "Rotator Enabled"
3. AUTO button should appear

### Configuration section missing
**Problem:** Don't see "🤖 AUTO MODE CONFIGURATION"
**Solution:** Rotator must be enabled
1. Settings → Rotor Tab
2. Check ☑ "Rotator Enabled"
3. Configuration section appears below

### Rotor doesn't move when clicking spot
**Problem:** Click spot but rotor stays still
**Causes:**
- AUTO mode disabled (Check ☑ Enable Rotor AUTO)
- Band not configured (Check if band is ☑ checked)
- Backend not running (Start with `.\start_webapp.ps1`)
- Gridsquare invalid (Check grid format: 2-8 chars like JN88TQ)

**Solution:**
1. Check browser console (F12 → Console tab)
2. Look for error messages
3. Verify settings are correct
4. Restart backend if needed

### Rotor moves in wrong direction
**Problem:** Rotor points wrong way
**Causes:**
- Home gridsquare wrong (verify your actual grid)
- Latitude/Longitude reversed or wrong

**Solution:**
1. Double-check your Maidenhead grid
2. Verify Lat/Lon values match your location
3. Test bearing manually: 
   - Use online calculator: maidenhead grid to lat/lon
   - Verify JN88TQ converts to ~48.68°N, 17.62°E

---

## Console Messages You'll See

### Good Signs ✅
```
✅ Rotor AUTO config loaded: { grid: 'JN88TQ', auto: true }
✅ Rotor AUTO config saved: {...updated config...}
🤖 Rotor AUTO ENABLED
⏱️ Rotor AUTO pending: W1AW - waiting 2s for cancellation
✅ AUTO rotor moved to 205°: W1AW
🤖 Rotor → 205° for W1AW
```

### Warning Signs ⚠️
```
ℹ️ Rotor AUTO not executed: band not configured for rotor
ℹ️ Rotor AUTO not executed: auto mode disabled
ℹ️ Rotor AUTO not executed: rotator disabled
```

### Error Signs ❌
```
❌ Failed to load rotor AUTO config: TypeError: Failed to fetch
   → Backend not running, start with .\start_webapp.ps1

❌ Invalid gridsquare: must be 2-8 characters
   → Check grid format (e.g., JN88TQ)

❌ Rotor AUTO config save error: ...
   → Backend error, check logs
```

---

## Next Steps

1. **Start the backend:**
   ```powershell
   .\start_webapp.ps1
   ```

2. **Open browser to:**
   ```
   http://localhost:8000
   ```

3. **Configure once:**
   - Settings → Rotor → Enter your grid + select bands

4. **Test it:**
   - Click a DX spot
   - Watch AUTO button pulse
   - See rotor move!

5. **Enjoy automatic rotor control! 🤖**