# WinKeyer Hardware Buttons - Diagnostic Guide

## Overview
This guide helps diagnose why hardware buttons may not be working after enabling the pushbutton notification command.

---

## Quick Diagnostic Steps

### 1. **Connect WinKeyer and Check Logs**

After connecting, you should see messages like:
```
📤 Sending pushbutton notification command: [0x00, 0x0B, 0x01]
✅ WK2 mode: pushbutton notify enabled - waiting for button presses...
```

**If you DON'T see these messages:**
- Connection may have failed
- Check browser console for errors
- Try reconnecting

### 2. **Open Browser Console (F12)**

The browser console will show detailed debug logs starting with `[WK-DEBUG]`.

**Important:** You should see logs like:
```
[WK-DEBUG] Raw byte: 0xc0 (192)  ← Status bytes
[WK-DEBUG] Status byte: 0xc0     ← Recognized as status
```

### 3. **Press Hardware Button and Look For:**

**Expected in Console:**
```
[WK-DEBUG] Raw byte: 0xc8 (200)        ← Any change
[WK-DEBUG] Status byte: 0xc8           ← Status recognized
```

**Expected in App Log:**
```
📊 Status received: tag=0, keyDown=true, busy=false...  ← Button press detected!
🔘 Button/Paddle pressed                               ← Feedback handler fired
```

---

## Troubleshooting Matrix

| Problem | Cause | Solution |
|---------|-------|----------|
| **No debug logs in console** | Debug mode off or connection failed | Reconnect device, ensure console open |
| **Status bytes received but no button change** | Device not sending button data | Check guide step 1 - may need different command |
| **Unrecognized bytes appear** | Button data in different format | Report to developer with console log |
| **Extended messages instead** | Device uses paddle format | Button data might come as `0xE0` extended blocks |
| **Only pot changes, no button data** | Pushbutton command failed | Device may be WK3, try different command |

---

## Advanced Diagnostics

### Method 1: Run Diagnostic Report
In browser console:
```javascript
window.winKeyerUI.printDiagnostics()
```

### Method 2: Enable/Disable Debug Logging
```javascript
window.winKeyerUI.setDebugMode(true)   // Enable detailed logging
window.winKeyerUI.setDebugMode(false)  // Disable for clean logs
```

### Method 3: Check Raw Bytes by Filter
Open console and search for:
- `[WK-DEBUG-UNRECOGNIZED]` - Unknown byte formats
- `[WK-DEBUG] Status byte:` - Status messages received
- `Status received:` - Parsed status with details

---

## Expected Behavior After Fix

### When Connected:
1. Console shows `📤 Sending pushbutton notification command`
2. Console shows `✅ WK2 mode: pushbutton notify enabled`

### When Button Pressed:
1. Console shows new `[WK-DEBUG]` raw bytes
2. Console shows `[WK-DEBUG] Status byte: 0x...`
3. App log shows `📊 Status received: keyDown=true`
4. App log shows `🔘 Button/Paddle pressed`

### When Button Released:
1. Console shows new status byte
2. App log shows `📊 Status received: keyDown=false`

---

## Button Press Data Format

Based on WinKeyer protocol, button presses should appear as **status bytes** in range `0xC0-0xFF` with **bit 3 set** for `keyDown`:

- `0xC8` = keyDown + normal status
- `0xC0` = key released + normal status
- `0xE0-0xFF` = Extended messages (paddles)

If you see different patterns, report them to the developer.

---

## Next Steps If Still Not Working

**Collect this information:**

1. **Screenshot of browser console after pressing button:**
   - Full log of [WK-DEBUG] messages
   - Any [WK-DEBUG-UNRECOGNIZED] warnings

2. **App log after pressing button:**
   - What messages appear?
   - Do you see "Status received" messages?

3. **Device info:**
   - WinKeyer model (WK1, WK2, WK3)?
   - Firmware revision (shown in connection log)
   - Serial port being used

**Then contact support with:**
- Screenshot of console debug logs
- Screenshot of app logs
- Device model and revision
- Description of what happens (or doesn't happen) when button is pressed

---

## Reference: Debug Log Legend

| Pattern | Meaning |
|---------|---------|
| `[WK-DEBUG] Raw byte:` | Every byte received from device |
| `[WK-DEBUG] Status byte:` | Recognized status message |
| `[WK-DEBUG] Extended block started` | 0xE0 prefix detected |
| `[WK-DEBUG-UNRECOGNIZED]` | Byte format not recognized - important! |
| `📤 Sending pushbutton notification` | Command being sent to device |
| `✅ WK2 mode: pushbutton notify enabled` | Command sent successfully |
| `📊 Status received:` | Parsed status with all flags |
| `🔘 Button/Paddle pressed` | Button press event detected |

---

**Last Updated:** 2025-01-15
**Author:** Enhanced diagnostic system for WinKeyer hardware button support