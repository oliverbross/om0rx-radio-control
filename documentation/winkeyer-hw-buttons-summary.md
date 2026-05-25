# WinKeyer Hardware Button Enablement Guide

This document describes the changes required to make the **hardware pushbuttons** and **paddles** on the WinKeyer device function while your custom software is connected in host mode.

---

## ✅ Overview

By default, when a WinKeyer is in **host mode**, its hardware **buttons and paddles** are ignored unless the host explicitly enables them.  
To fix this, we need to:

1. **Enable pushbutton notifications** right after the host connects.  
2. **Send a “Host Close” command** when disconnecting, so standalone operation resumes immediately.  
3. (Optional) Adjust how the **speed potentiometer** is handled to avoid lag.

---

## 1. Enable Pushbutton Reporting

After opening the connection and reading the firmware revision, send this command:

```js
await this._write([0x00, 0x0b, 0x01]); // Admin: Set WK2 Mode, enable pushbutton notify
this.onLog('WK2 mode: pushbutton notify enabled');
```

**Where:** in `WinKeyerClient.open()` (after receiving the revision).  
**Effect:** hardware buttons and paddles will now send status updates to your `onStatus()` and `onExtended()` handlers.

---

## 2. Cleanly Return to Standalone on Disconnect

When the app closes or the device disconnects, send:

```js
await this._write([0x00, 0x03]); // Admin: Host Close
```

**Where:** in `WinKeyerClient.disconnect()` before closing the serial port.  
**Effect:** ensures the WinKeyer immediately returns to normal standalone mode so buttons and paddles work without unplugging.

---

## 3. Optional: Let the Hardware Pot Control WPM

Currently, your handler echoes the pot change back to the device (can cause lag).  
You may simplify it as follows:

```js
// in onPot handler
this.vue.$data.winkeyer.currentWpm = wpm;
// (remove immediate setWpm(wpm))
```

This makes the hardware pot the primary speed control and simply mirrors it in the UI.

---

## 4. Expected Behavior After Implementation

- Hardware **paddles and buttons** will key and trigger as expected.  
- Speed **potentiometer** changes will update the UI.  
- On host disconnect, device resumes standalone operation immediately.  
- `WinKeyerFeedbackHandler` will start logging pushbutton and paddle events automatically.

---

## Reference Commands

| Command | Bytes (hex) | Description |
|----------|-------------|--------------|
| Set WK2 Mode | 00 0B 01 | Enable pushbutton notifications |
| Host Close | 00 03 | Return to standalone mode |
| Paddle Echo (already used) | 00 09 nn | Echo paddle input to host |

---

**Summary:**  
Add `<00><0B><01>` after open, `<00><03>` before close, and optionally simplify pot handling.  
These two small changes make the hardware fully functional during and after host mode.

---

**Author:** Technical integration summary prepared for developer by ChatGPT (2025‑10‑31)
