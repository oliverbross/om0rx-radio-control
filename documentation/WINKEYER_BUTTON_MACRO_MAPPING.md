# WinKeyer Hardware Button to Macro Mapping

## Overview
Hardware buttons on the WinKeyer device are now automatically mapped to application macros M1-M4. When you press a button on the device, it triggers the corresponding macro without needing the WinKeyer's internal keying to work.

## Button Mapping

| Button | Memory Bytes | Triggers | Purpose |
|--------|-------------|----------|---------|
| Button 1 | 0xc9 | M1 | First macro |
| Button 2 | 0xca | M2 | Second macro |
| Button 3 | 0xcc | M3 | Third macro |
| Button 4 | 0xd8 | M4 | Fourth macro |

## How It Works

1. **Button Press Detection**: When you press a button on the WinKeyer, a unique status byte is sent
2. **Identification**: The app identifies which button based on the status byte signature
3. **Macro Trigger**: The corresponding macro (M1-M4) is automatically executed
4. **Radio Keying**: The macro text is sent to the radio via CW

## Testing the Feature

### Step 1: Configure Your Macros
In the WinKeyer UI, set up your M1-M4 macros with the text you want to send:
- **M1**: Your call sign (e.g., "OM0RX")
- **M2**: Signal report (e.g., "5NN TU")
- **M3**: Another message (e.g., "QRZ?")
- **M4**: Another message (e.g., "TK 73")

### Step 2: Connect WinKeyer
1. Start the application
2. Select the WinKeyer COM port
3. Click "Connect"
4. Wait for the green "Connected" indicator

### Step 3: Test Button Presses
Press each button on the WinKeyer and check:
- ✅ The app logs show "Button N pressed - triggering MN"
- ✅ The macro text appears in the CW transmission logs
- ✅ The radio receives the CW transmission
- ✅ Success message "MN transmitted successfully"

## Expected Console Logs

### When Button 1 is pressed:
```
[12:34:56 AM] 🔘 Button 1 pressed - triggering M1
[12:34:56 AM] 📡 Sending M1: "OM0RX"
[12:34:58 AM] ✅ M1 transmitted successfully
```

### If macro is not configured:
```
[12:34:56 AM] 🔘 Button 1 pressed - triggering M1
[12:34:56 AM] ❌ Memory M1 not found or empty
```

## Button Press Signatures (Technical Details)

The button signatures are detected by analyzing status bytes received from the WinKeyer:

- **Button 1 (0xc9)**: `11001001` - xoff bit set
- **Button 2 (0xca)**: `11001010` - breakIn bit set
- **Button 3 (0xcc)**: `11001100` - busy bit set
- **Button 4 (0xd8)**: `11011000` - unique pattern

Each button press also causes a transition from `keyDown=false` to `keyDown=true`, which triggers the detection logic.

## Troubleshooting

### Buttons don't trigger macros

**Check 1**: Are the macros configured?
- Open the WinKeyer config modal (gear icon)
- Verify M1, M2, M3, M4 have text values
- Solution: Add text to empty macros

**Check 2**: Is WinKeyer connected?
- Look for green "Connected" indicator
- Check browser console for connection logs
- Solution: Reconnect the device

**Check 3**: Open browser console (F12)
- Look for `[WK-DEBUG]` lines when pressing buttons
- Should see status bytes: 0xc9, 0xca, 0xcc, or 0xd8
- Solution: If no logs appear, button signals aren't being received

### Button presses show but macros don't send

**Possible causes**:
1. Radio not in CW mode or keying input not connected
2. WinKeyer keying output not connected to radio
3. Macro text contains invalid CW characters

**Check**:
- Look at the app logs - do you see "📡 Sending MN: ..."?
- Check radio logs to see if CW was keyed
- Verify radio mode is set to CW or SSB (for CW keying)

### Wrong button triggers wrong macro

**This shouldn't happen** if the button signatures are correct. If it does:
1. Note which button you pressed
2. Check the console logs for the status byte
3. Compare to the mapping table above
4. Contact support with the byte values

## Advanced: Debug Button Identification

To debug button identification, run this in the browser console:

```javascript
// Show the raw button signatures as they arrive
window.winKeyerUI.setDebugMode(true);

// Then press buttons and look for logs like:
// [WK-DEBUG] Status byte: 0xc9
// [WK-DEBUG] Status byte: 0xc8
```

The first byte (0xc9, 0xca, etc.) is the button press. The second byte (usually 0xc8) is the button release.

## Files Modified

- `frontend/js/winkeyer-client.js` - Added `rawByte` to status data
- `frontend/js/winkeyer-feedback.js` - Added button identification and macro triggering
- `frontend/js/winkeyer-ui.js` - Enhanced logging for macro transmission

## Key Features

✅ **Automatic Detection**: No configuration needed - buttons are identified automatically
✅ **Unique Mapping**: Each button has a unique signature
✅ **Full Logging**: All button presses and macro sends are logged
✅ **Error Handling**: Failed macro sends are logged with error details
✅ **Non-Intrusive**: Doesn't interfere with manual macro triggering from the UI

## Compatibility

- **WinKeyer 2** (WK2): Full support ✅
- **WinKeyer 3** (WK3): Supported but may require testing
- **WinKeyer 1** (WK1): Not tested, button byte signatures may differ

If you're using WK1 or WK3 and buttons don't map correctly, please test with debug mode enabled and share the status bytes you see.

## Next Steps

If buttons still don't work after checking the above:
1. Enable debug mode: `window.winKeyerUI.setDebugMode(true)`
2. Press all 4 buttons
3. Screenshot the console logs
4. Verify the macros are defined and not empty
5. Check radio keying connection
6. Contact support with logs and button signatures