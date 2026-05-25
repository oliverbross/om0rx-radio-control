# WSJT-X Config Tab - Quick Reference

## What You'll See When You Click "⚙️ Config"

The Configuration Modal opens with multiple tabs. Click the **WSJT-X** tab to access settings.

### Tab Layout

```
┌─────────────────────────────────────────────────────────┐
│ Configuration Modal                                     │
├─────────────────────────────────────────────────────────┤
│ Database │ Station │ Flex │ Rotor │ WSJT-X │ CTY │ ... │
│                                    ^^^^^
│                                    (Click here)
├─────────────────────────────────────────────────────────┤
│                                                         │
│  📡 WSJT-X Integration Settings                        │
│                                                         │
│  ☑ Enable WSJT-X Integration                          │
│                                                         │
│  ────────────────────────────────────────────────────  │
│                                                         │
│  🔌 UDP Listener Configuration                         │
│                                                         │
│  UDP Listen Port            [2237]                     │
│  Configure this port in WSJT-X Settings → Reporting   │
│                                                         │
│  Multicast Address          [224.0.0.1]               │
│  Use 224.0.0.1 for multicast (multiple listeners)     │
│  or 127.0.0.1 for unicast                             │
│                                                         │
│  WebSocket Port (Bridge)    [8091]                     │
│  Internal WebSocket port for bridge server             │
│                                                         │
│  ────────────────────────────────────────────────────  │
│                                                         │
│  ⚙️ Feature Configuration                              │
│                                                         │
│  ☑ 📝 Auto-Log to Wavelog                             │
│  Automatically logs QSOs to Wavelog when logged...    │
│                                                         │
│  ☑ 🎪 Auto-Rotate Antenna                            │
│  Automatically rotates antenna to DX station's grid   │
│                                                         │
│  ────────────────────────────────────────────────────  │
│                                                         │
│  📖 Setup Instructions                                 │
│  1. In WSJT-X, go Settings → Reporting                │
│  2. ✅ Enable "Accept UDP requests"                   │
│  3. Set Address: 127.0.0.1                            │
│  4. Set Port: 2237                                     │
│  5. Restart Wave-Flex-Spots app                        │
│  6. Modal will appear when working a station!          │
│                                                         │
├─────────────────────────────────────────────────────────┤
│ [ Cancel ]                              [ Save Config ]  │
└─────────────────────────────────────────────────────────┘
```

---

## Each Field Explained

### 🔌 UDP Listener Configuration

**UDP Listen Port**
- **Default**: 2237
- **What it does**: Tells the bridge server which port to listen on for WSJT-X packets
- **When to change**: If port 2237 is already in use
- **Important**: Must match the port you configure in WSJT-X

**Multicast Address**
- **Default**: 224.0.0.1
- **224.0.0.1**: Multicast (multiple WSJT-X instances can send)
- **127.0.0.1**: Unicast (localhost only, single instance)
- **When to change**: Rarely needed unless network issues

**WebSocket Port (Bridge)**
- **Default**: 8091
- **What it does**: Internal communication between bridge and frontend
- **When to change**: Only if 8091 is already in use
- **Important**: Rarely needs changing, don't modify unless necessary

---

### ⚙️ Feature Configuration

**Enable WSJT-X Integration** (Master Switch)
- ☑ = All WSJT-X features active
- ☐ = All WSJT-X features disabled
- **Effect**: Takes effect after app restart

**Auto-Log to Wavelog**
- ☑ = When you log a contact in WSJT-X, it logs to Wavelog automatically
- ☐ = No automatic logging (manual entry still possible)
- **Requirements**: 
  - Wavelog API must be configured (Database tab)
  - QRZ.com credentials optional (for enrichment)
- **Speed**: Usually completes in 2-3 seconds
- **On Error**: Logs without QRZ data if lookup fails

**Auto-Rotate Antenna**
- ☑ = Antenna automatically points to DX station when you change frequency
- ☐ = Manual antenna control only
- **Requirements**:
  - Rotor must be enabled (Rotor tab)
  - Rotor home location must be configured
- **Timing**: Happens within 1 second of status update from WSJT-X
- **On Error**: Logs error but doesn't break WSJT-X operation

---

## Typical Configuration Scenarios

### Scenario 1: First Time Setup (Recommended)

```
✅ Enable WSJT-X Integration      (ON)
✅ Auto-Log to Wavelog             (ON)
✅ Auto-Rotate Antenna             (ON)
   (if rotator configured)

UDP Port: 2237
Multicast: 224.0.0.1
WebSocket: 8091
```

**Result**: Full hands-free operation. Log in WSJT-X and everything happens automatically.

---

### Scenario 2: Logging Only (No Rotor)

```
✅ Enable WSJT-X Integration      (ON)
✅ Auto-Log to Wavelog             (ON)
☐ Auto-Rotate Antenna             (OFF)

UDP Port: 2237
Multicast: 224.0.0.1
WebSocket: 8091
```

**Result**: QSOs automatically log to Wavelog, but manual antenna control.

---

### Scenario 3: Monitoring Only

```
✅ Enable WSJT-X Integration      (ON)
☐ Auto-Log to Wavelog             (OFF)
☐ Auto-Rotate Antenna             (OFF)

UDP Port: 2237
Multicast: 224.0.0.1
WebSocket: 8091
```

**Result**: Modal shows QSO details but nothing logs automatically.

---

### Scenario 4: Disabled

```
☐ Enable WSJT-X Integration      (OFF)
(Other settings ignored)
```

**Result**: WSJT-X features completely disabled.

---

## Common Questions

**Q: Do I need to restart after saving?**  
A: Yes. Configuration changes take effect on next app restart. Click "Save" then restart Wave-Flex-Spots.

**Q: What if I get an error saving?**  
A: Try these:
1. Make sure config.py is writable (not read-only)
2. Stop the app before editing
3. Ensure Wave-Flex-Spots has permission to write to folder

**Q: Can I have multiple WSJT-X instances?**  
A: Yes, use multicast mode (224.0.0.1). Both will send to the same port.

**Q: What's the difference between 224.0.0.1 and 127.0.0.1?**  
A: Multicast (224.x.x.x) = multiple instances. Unicast (127.x.x.x) = localhost only.

**Q: Can I change the port while running?**  
A: The change saves to config.py but doesn't take effect until restart. Bridge server will use new port on next start.

**Q: What if the auto-rotate fails?**  
A: The modal will still appear. Check:
1. Rotor is turned on and connected (Rotor tab)
2. Home location (grid) is configured
3. Rotator controller is accessible

---

## Default Values

If you ever need to reset to defaults:

| Setting | Default Value |
|---------|---------------|
| Enable WSJT-X | ☑ (ON) |
| UDP Port | 2237 |
| Multicast | 224.0.0.1 |
| WebSocket Port | 8091 |
| Auto-Log | ☑ (ON) |
| Auto-Rotate | ☑ (ON) |

---

## Saving and Applying Changes

### Step 1: Modify Settings
- Adjust any values in the form
- Changes only affect form fields, not saved yet

### Step 2: Click "Save Configuration"
- Form data sent to backend
- Backend updates config.py file
- Success message appears
- Modal auto-closes after 3 seconds

### Step 3: Restart Application
- Stop current instance (Ctrl+C)
- Restart: `.\start_webapp.ps1`
- Bridge server reads updated config.py
- Changes now active

---

## Troubleshooting

### Changes Not Taking Effect

**Check 1**: Did you restart the app?
- Config changes require app restart
- Bridge server reads config.py on startup

**Check 2**: Is config.py actually updated?
- Open `config.py` and look for your values
- If not there, save again

**Check 3**: Check browser console (F12)
- Any JavaScript errors?
- Check "Console" tab for messages

### Port Already in Use

**Symptom**: Bridge server won't start / connection refused

**Solution**:
1. Find what's using the port (Windows):
   ```powershell
   netstat -ano | grep 2237
   ```
2. Change to different port (e.g., 2238)
3. Save config
4. Restart app

### Auto-Log Not Working

**Check 1**: Is auto-log enabled? ☑
**Check 2**: Is Wavelog configured? (Database tab)
**Check 3**: Check browser console for API errors
**Check 4**: Try manual log first to test connection

### Auto-Rotate Not Working

**Check 1**: Is auto-rotate enabled? ☑
**Check 2**: Is rotor enabled? (Rotor tab → "Rotator Enabled")
**Check 3**: Is rotor home location configured? (Rotor tab → grid)
**Check 4**: Is rotator controller turned on?

---

## See Also

- [WSJTX_QUICK_START.md](WSJTX_QUICK_START.md) - 5-minute setup
- [WSJTX_GUI_CONFIG_GUIDE.md](WSJTX_GUI_CONFIG_GUIDE.md) - Detailed guide
- [WSJTX_INTEGRATION_COMPLETE.md](WSJTX_INTEGRATION_COMPLETE.md) - Technical reference

---

**Happy operating! 🎉**

Last updated: 2024