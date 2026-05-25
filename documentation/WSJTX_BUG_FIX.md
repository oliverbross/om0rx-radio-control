# WSJT-X Handler Bug Fix

## The Problem

WSJT-X handler was **not listening properly** due to conflicting implementations:

### Root Cause
Two competing WSJT-X implementations were interfering with each other:

1. **`wsjtx-widget.js`** (WRONG - causing the bug)
   - Connected directly to the bridge WebSocket (port 8091)
   - Received WSJT-X messages but handled them internally
   - **Never dispatched window events** that other code was waiting for
   - Result: Messages consumed silently, never reaching the handler

2. **`wsjtx-handler.js`** (CORRECT design)
   - Listening for window events named `'wsjtx-message'`
   - Events never arrived because `wsjtx-widget.js` was consuming them
   - Handler remained inactive despite appearing "initialized"

3. **`sdc-ticker.js`** (CORRECT - already configured to work)
   - Connected to bridge on port 8091
   - Designed to dispatch WSJT-X messages as window events (lines 48-50)
   - But blocked by `wsjtx-widget.js` interfering

## Correct Architecture

```
sdc-bridge-server.js (Node.js on port 8091)
        ↓
sdc-ticker.js (receives and forwards)
        ↓
window event: 'wsjtx-message'
        ↓
wsjtx-handler.js (processes and acts)
```

## The Fix

### Changes Made

1. **Removed `wsjtx-widget.js` from `index.html`** (line 48)
   - Eliminates the competing implementation
   - Stops interference with the event flow

2. **Disabled auto-instantiation in `wsjtx-widget.js`**
   - File remains in repo for reference/backup
   - Auto-initialization commented out
   - Won't run even if accidentally included

## Verification

After the fix, the message flow should be:

1. Bridge server sends WSJT-X data on port 8091
2. `sdc-ticker.js` receives it and dispatches:
   ```javascript
   window.dispatchEvent(new CustomEvent('wsjtx-message', { detail: data }));
   ```
3. `wsjtx-handler.js` catches the event and:
   - Updates form fields (auto-populate with call/grid/frequency)
   - Auto-rotates antenna if enabled
   - Auto-logs to Wavelog if enabled

## What to Look For in Console Logs

✅ **After fix, you should see:**
```
🔌 Initializing SDC Ticker WebSocket connection...
✅ SDC WebSocket connected
🔄 Forwarding WSJT-X message to handler: Status
📍 WSJT-X Status: CALLSIGN (GRID)
✅ Form populated with WSJT-X data
```

❌ **Before fix (broken), you saw:**
```
✅ WSJT-X WebSocket connected
(silence - no handler messages)
```

## Files Modified

- `frontend/index.html` - Removed wsjtx-widget.js script tag
- `frontend/js/wsjtx-widget.js` - Disabled auto-instantiation

## Why This Works

- **Single source of truth**: Bridge server handles both SDC + WSJT-X
- **Event-driven architecture**: Clean separation of concerns
- **No competition**: Only one handler processes the data
- **Proper event dispatch**: sdc-ticker.js is designed to forward to handlers

## Notes

- `wsjtx-widget.js` is kept in the repository for reference but should not be used
- If future WSJT-X features need advanced handling, extend `wsjtx-handler.js` instead
- The backend API endpoints (`/api/wsjtx/*`) remain unchanged