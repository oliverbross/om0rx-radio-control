# Separate Windows Implementation

## Overview
Three new HTML pages have been created to allow running each section of the application in separate browser windows/tabs:

1. **radio-control.html** - Radio controls (rows 1-4: buttons, sliders, bands, modes, frequency)
2. **logging.html** - Logging panel (3 columns: Log QSO form, QRZ Profile, DXCC/Wavelog Info)
3. **spots.html** - DX Spots (filter controls and spots table)

## How to Access

### Direct Access (Manual)
Open the following URLs in your browser:
- `http://localhost:8000/radio-control.html` - Radio Controls window
- `http://localhost:8000/logging.html` - Logging & QRZ window
- `http://localhost:8000/spots.html` - DX Spots window

Each page will open as a separate, independent window but will synchronize through the shared backend.

### Automatic Window Opening
You can open all three windows at once by including the following JavaScript in your page or running it in the browser console:

```javascript
// Open all three windows
const windows = {
    radio: window.open('radio-control.html', 'radio-control', 'width=1000,height=600'),
    logging: window.open('logging.html', 'logging', 'width=1200,height=700'),
    spots: window.open('spots.html', 'spots', 'width=1400,height=800')
};
```

## How They Work Together

### Synchronization
- All three windows connect to the same backend WebSocket server
- When you click a spot in the **spots** window, it sends a frequency command to the backend
- The **radio-control** window receives the frequency update through its WebSocket connection
- The **logging** window can also see the updated frequency for logging
- All updates are bidirectional through the shared backend

### Data Flow
```
User clicks spot in spots.html
    ↓
Sends frequency command to backend
    ↓
Backend broadcasts update to all connected clients
    ↓
radio-control.html and logging.html receive update
    ↓
All three windows display current state
```

## Technical Details

### Page Mode Support
- Each page sets `window.PAGE_MODE` before loading app.js
- app.js detects the page mode and can conditionally show/hide sections
- The original index.html uses `pageMode='main'` (default)

### WebSocket Connections
- Each page establishes its own WebSocket connection to the backend
- Multiple connections are supported by the backend
- All connections receive the same updates

### Code Integrity
- All three pages use the EXACT same app.js code
- No code duplication - all pages share:
  - Same app.js logic
  - Same logging-panel.css styles
  - Same WebSocket communication protocol

## Testing Checklist

Before finalizing the implementation, test the following:

- [ ] All three windows open correctly and independently
- [ ] Radio controls in radio-control.html work and update the radio
- [ ] Logging form in logging.html can be filled and QRZ data loads
- [ ] DX Spots in spots.html displays and filters correctly
- [ ] Clicking a spot in spots.html tunes the radio (frequency updates in radio-control.html)
- [ ] All three windows stay in sync with current radio state
- [ ] Closing one window doesn't affect the others
- [ ] Refreshing a page reconnects to backend properly

## Future Enhancement

Once verified to work correctly, the main index.html can be enhanced to:
1. Add three buttons ("Radio", "Logging", "Spots") to the interface
2. Automatically open the corresponding window when clicked
3. Or provide a landing page with 3 buttons to choose which section to view

This change will be made only after confirming the three separate pages work identically to the current single-page layout.