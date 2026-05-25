# 📻 FlexRadio Web Control - Professional Web Application Project

## 🎯 Project Vision
Transform the current Tkinter desktop application into a professional, responsive web application that provides comprehensive FlexRadio control via SmartSDR API, accessible from desktop, tablet, and mobile devices.

---

## 📸 Design Reference
**Target GUI:** `c:\Users\Oliver\Pictures\sample-gui.JPG`
- Professional dark theme with modern UI
- Comprehensive radio control interface
- Touch-friendly controls for mobile/tablet
- Real-time status updates

---

## 🏗️ Technology Stack

### **Backend**
- **Framework:** FastAPI (Python 3.10+)
  - WebSocket support for real-time updates
  - REST API endpoints for control commands
  - CORS enabled for local network access
- **Existing Code:** Reuse `FlexCtl` class from `dxbridge.py`
- **Dependencies:**
  - `fastapi` - Web framework
  - `uvicorn` - ASGI server
  - `websockets` - Real-time communication
  - `pydantic` - Data validation

### **Frontend**
- **Framework:** Vue.js 3 (Composition API)
  - Reactive UI updates
  - Component-based architecture
  - Easy to learn, powerful
- **Styling:** Tailwind CSS
  - Professional dark theme
  - Responsive design utilities
  - No custom CSS needed
- **UI Components:** Headless UI / DaisyUI
  - Pre-built accessible components
  - Button groups, sliders, toggles
- **Build Tool:** Vite (optional, can use CDN for simplicity)

### **Deployment**
- **Development:** Local server (`http://localhost:8080`)
- **Production:** Local network access (`http://192.168.x.x:8080`)
- **Optional:** Package as standalone app with PyWebView

---

## 🎨 Feature Mapping: Sample GUI → SmartSDR API

### **Top Bar Controls (Row 1)**

| GUI Element | Description | SmartSDR API | Priority | Status |
|-------------|-------------|--------------|----------|--------|
| 🔵 Power | Master power | `radio set power=1/0` | P0 | ✅ Research |
| RX2 | Second receiver | `slice create freq=14.200` | P1 | 📋 Plan |
| BS | Band Stack | Custom local storage | P2 | 📋 Plan |
| 🔴 PA | PA Status/Control | `transmit set rfpower=` | P0 | ✅ Have |
| B.M | Band Monitor | Unknown/Custom | P3 | ❓ Research |
| XVTR | Transverter | `xvtr` commands | P3 | 📋 Plan |
| 0 dB | Attenuation | `slice set rfgain=0` | P2 | 📋 Plan |
| 🔊 Volume | AF Gain | `audio stream 0x` volume | P0 | ✅ Have |
| 🎧 Monitor | Monitor level | `transmit set mon_gain_sb=` | P1 | 📋 Plan |
| ⚙️ Settings | Settings panel | Custom UI modal | P2 | 📋 Plan |
| 📊 Info | System info | `info` command | P3 | 📋 Plan |
| ⛶ Fullscreen | Browser fullscreen | HTML5 Fullscreen API | P2 | 📋 Plan |

### **TX Controls (Row 2)**

| GUI Element | Description | SmartSDR API | Priority | Status |
|-------------|-------------|--------------|----------|--------|
| ▶️ TX | Transmit toggle | `xmit 1/0` | P0 | ✅ Have |
| TUNE | Antenna tuner | `tuner start` | P0 | ✅ Have |
| VOX | Voice activation | `transmit set vox_enable=1/0` | P0 | ✅ Have |
| ≡ | Menu/More | Custom | P2 | 📋 Plan |
| 🔇 Mute | Mute audio | Mute icon toggle | P1 | 📋 Plan |
| Break.In | CW break-in | `transmit set break_in=` | P2 | 📋 Plan |
| SQL | Squelch | `audio_stream squelch_level=` | P2 | 📋 Plan |
| SPLIT | Split operation | `slice set tx=1/0` | P1 | 📋 Plan |
| ⭕ Various | Function toggles | Multiple APIs | P2-P3 | 📋 Plan |

### **Band Buttons (Row 3)**

| GUI Element | Description | SmartSDR API | Priority | Status |
|-------------|-------------|--------------|----------|--------|
| 160M - 2M | HF/VHF bands | `slice set freq=` | P0 | ✅ Have |
| Highlight | Active band | CSS class based on freq | P0 | ✅ Have |

**Bands to include:**
- 160M, 80M, 60M, 40M, 30M, 20M, 17M, 15M, 12M, 11M (CB?), 10M, 6M, 2M

### **Mode Buttons (Row 4)**

| GUI Element | Description | SmartSDR API | Priority | Status |
|-------------|-------------|--------------|----------|--------|
| AM, LSB, USB, CW | HF modes | `slice set mode=` | P0 | ✅ Have |
| NFM, DIGL, DIGU, WFM | Digital/FM modes | `slice set mode=` | P0 | ✅ Have |
| Highlight | Active mode | CSS class based on mode | P0 | ✅ Have |

### **Main Display (Center)**

| GUI Element | Description | SmartSDR API | Priority | Status |
|-------------|-------------|--------------|----------|--------|
| 📊 S-Meter | Signal strength | `meter list` → parse | P1 | 📋 Plan |
| S5/S7/S9 | S-meter scale | Canvas/SVG visualization | P1 | 📋 Plan |
| -110 to +60 dB | dBm scale | Calculated from S-meter | P2 | 📋 Plan |
| RX.A2 / TX.A2 | Slice indicator | From slice number | P1 | 📋 Plan |
| ⚙️ Tuning icons | VFO controls | Custom controls | P2 | 📋 Plan |
| **014.233.400** | Large VFO display | `slice` frequency | P0 | ✅ Have |
| 🔴 TX indicator | Transmit status | `interlock` state | P0 | ✅ Have |
| 014.036.070 | Sub VFO/Memory | VFO B or memory | P2 | 📋 Plan |
| TX/SUB/A>B/B>A/SWAP | VFO functions | Slice commands | P2 | 📋 Plan |

### **Sliders (Right Side)**

| GUI Element | Description | SmartSDR API | Priority | Status |
|-------------|-------------|--------------|----------|--------|
| Agc | AGC slider | `slice set agc_mode=` | P1 | 📋 Plan |
| Drive | TX power | `transmit set rfpower=` | P0 | ✅ Have |
| Tune | Tune power | `transmit set tunepower=` | P0 | ✅ Have |
| Mic.PC | Mic/Proc level | `transmit set miclevel=` | P0 | ✅ Have |
| Color coding | Red/Green indicators | CSS based on value | P1 | 📋 Plan |

### **DSP Controls (Bottom Row)**

| GUI Element | Description | SmartSDR API | Priority | Status |
|-------------|-------------|--------------|----------|--------|
| NB | Noise blanker | `slice set nb=1/0` | P1 | 📋 Plan |
| BIN | Binaural | `slice set binaural_rx=1/0` | P2 | 📋 Plan |
| NR | Noise reduction | `slice set nr=1/0` | P1 | 📋 Plan |
| ANC | Auto notch | `slice set anf=1/0` | P1 | 📋 Plan |
| ANF | Auto notch filter | Same as ANC | P1 | 📋 Plan |
| APF | Audio peak filter | `slice set apf=1/0` | P2 | 📋 Plan |
| NF | Notch filter | `slice set notch freq=` | P2 | 📋 Plan |
| NF+ | Additional notch | Custom | P3 | 📋 Plan |

### **Filter Buttons (Bottom Right)**

| GUI Element | Description | SmartSDR API | Priority | Status |
|-------------|-------------|--------------|----------|--------|
| 2.5K, 2.7K, 3.0K, 3.3K | Filter presets | `slice set filter_lo/hi=` | P0 | ✅ Have |
| USER | Custom filter | User-defined values | P1 | 📋 Plan |
| Highlight | Active filter | CSS class | P0 | ✅ Have |

### **Additional Features (Our Custom Additions)**

| Feature | Description | Source | Priority | Status |
|---------|-------------|--------|----------|--------|
| 📡 DX Spots Table | Live spots from UDP | Existing code | P0 | ✅ Have |
| 🔍 Spot Filtering | Filter by band/mode/CQ/etc | Existing code | P0 | ✅ Have |
| 🔔 Click to Tune | Click spot to QSY | Existing code | P0 | ✅ Have |
| 📊 Waterfall | Spectrum display | `display pan` / Canvas | P3 | ⭐ Future |
| 📝 Logging | QSO logging integration | ADIF export | P2 | 📋 Plan |
| 🌍 World Map | Show spot locations | Leaflet.js + API | P2 | 📋 Plan |

---

## 📁 Project Structure

```
om0rx-radio-control/
├── backend/
│   ├── main.py                  # FastAPI application
│   ├── flex_control.py          # FlexCtl class (from dxbridge.py)
│   ├── models.py                # Pydantic data models
│   ├── websocket_manager.py    # WebSocket handler
│   └── config.py                # Configuration
│
├── frontend/
│   ├── index.html               # Main HTML file
│   ├── css/
│   │   └── app.css              # Custom styles (minimal)
│   ├── js/
│   │   ├── app.js               # Main Vue.js app
│   │   ├── components/
│   │   │   ├── BandButtons.js   # Band selector component
│   │   │   ├── ModeButtons.js   # Mode selector component
│   │   │   ├── FreqDisplay.js   # Large frequency display
│   │   │   ├── SMeter.js        # S-meter visualization
│   │   │   ├── Sliders.js       # Slider controls
│   │   │   ├── DspControls.js   # DSP button panel
│   │   │   ├── FilterButtons.js # Filter selector
│   │   │   └── SpotsTable.js    # DX spots table
│   │   └── utils/
│   │       ├── websocket.js     # WebSocket client
│   │       └── formatter.js     # Frequency formatting
│   └── assets/
│       └── icons/               # SVG icons
│
├── static/                      # Served by FastAPI
│   └── (symlink to frontend/)
│
├── dxbridge.py                  # Original code (KEEP for reference)
├── config.py                    # Shared config
├── requirements.txt             # Python dependencies
├── package.json                 # Frontend dependencies (if using npm)
├── README.md                    # Project documentation
├── WEBAPP_PROJECT.md            # This file
└── .env                         # Environment variables
```

---

## 🚀 Development Phases

### **Phase 0: Foundation Setup** (Week 1)
**Goal:** Get basic web app running with minimal functionality

#### Backend Tasks:
- [ ] Set up FastAPI project structure
- [ ] Extract `FlexCtl` class to `flex_control.py`
- [ ] Create basic REST endpoints:
  - `GET /api/status` - Get radio status
  - `POST /api/command` - Send command to radio
  - `WS /ws/radio` - WebSocket for real-time updates
- [ ] Test radio connection and basic commands
- [ ] Set up CORS for local network access

#### Frontend Tasks:
- [ ] Create `index.html` with Tailwind CSS (CDN)
- [ ] Set up Vue.js 3 (CDN version for simplicity)
- [ ] Create basic dark theme layout
- [ ] Test WebSocket connection to backend
- [ ] Display radio status in console

#### Deliverable:
✅ Web page loads, connects to radio, displays "Connected" status

---

### **Phase 1: Core Controls** (Week 2-3)
**Goal:** Implement essential radio control features

#### Features to implement:
- [ ] **Band Buttons** (160M - 2M)
  - Click to change frequency
  - Highlight active band
  - Responsive grid layout
- [ ] **Mode Buttons** (AM, LSB, USB, CW, etc.)
  - Click to change mode
  - Highlight active mode
- [ ] **Large Frequency Display**
  - Format: 014.233.400
  - Real-time updates
  - Click to edit (stretch goal)
- [ ] **TX/TUNE/VOX Buttons**
  - Toggle transmit
  - Start tuner
  - Enable VOX
- [ ] **Basic Sliders**
  - Drive (TX power)
  - Tune (Tune power)
  - Mic level
  - Real-time sync with radio

#### Testing:
- [ ] Test on desktop browser (Chrome/Firefox)
- [ ] Test on mobile browser (iOS Safari/Android Chrome)
- [ ] Test on tablet
- [ ] Verify all controls work bidirectionally

#### Deliverable:
✅ Functional radio control from any device

---

### **Phase 2: Advanced Controls** (Week 4-5)
**Goal:** Add remaining controls from sample GUI

#### Features to implement:
- [ ] **S-Meter Display**
  - SVG-based visualization
  - S1-S9 scale
  - dBm scale
  - Real-time updates from meter data
- [ ] **Filter Buttons**
  - Preset filters (1.8K, 2.1K, 2.4K, etc.)
  - USER custom filter
  - Highlight active filter
- [ ] **DSP Controls**
  - NB (Noise Blanker)
  - NR (Noise Reduction)
  - ANF (Auto Notch Filter)
  - APF (Audio Peak Filter)
  - Toggle buttons with state indicators
- [ ] **Volume/Monitor Sliders**
  - Audio volume control
  - Monitor level
  - Speaker icons
- [ ] **Top Bar Buttons**
  - RX2 (second receiver)
  - Attenuation (0 dB button)
  - SPLIT operation
  - SQL (Squelch)
- [ ] **AGC Slider**
  - AGC level control
  - Mode indicator (NORM/FAST/SLOW)

#### Testing:
- [ ] Verify DSP controls affect audio
- [ ] Test S-meter accuracy
- [ ] Test filter changes
- [ ] Mobile touch testing

#### Deliverable:
✅ Near-complete radio control matching sample GUI

---

### **Phase 3: DX Spots Integration** (Week 6)
**Goal:** Integrate existing DX spots functionality

#### Features to implement:
- [ ] **DX Spots Table**
  - Port existing spots table from Tkinter
  - Responsive table layout (horizontal scroll on mobile)
  - Auto-update from UDP stream
  - Highlight new spots
- [ ] **Spot Filtering**
  - Band filter dropdown
  - Mode filter dropdown
  - CQ Zone filter
  - DXCC filter
  - Special filter (IARU, contest, etc.)
  - Call status filter (New Band, Confirmed, etc.)
- [ ] **Click to Tune**
  - Click spot to QSY radio
  - Visual feedback on click
  - Update frequency display
- [ ] **Spot Highlighting**
  - Color coding by status
  - Row selection
  - Auto-scroll to new spots

#### Testing:
- [ ] Verify UDP spots received
- [ ] Test filtering combinations
- [ ] Test click-to-tune accuracy
- [ ] Mobile table usability

#### Deliverable:
✅ Full DX spots functionality in web interface

---

### **Phase 4: Polish & UX** (Week 7-8)
**Goal:** Make it beautiful and professional

#### UX Improvements:
- [ ] **Responsive Layouts**
  - Desktop: Full layout (spots table on bottom or right)
  - Tablet: Collapsible sections
  - Mobile: Tabbed interface (Controls / Spots / Settings)
- [ ] **Visual Polish**
  - Smooth animations on button clicks
  - Slider value tooltips
  - Loading states
  - Error notifications
- [ ] **Keyboard Shortcuts**
  - Arrow keys for frequency tuning
  - Number keys for band selection
  - Letter keys for mode (U for USB, L for LSB, etc.)
  - Space for TX toggle
- [ ] **Theme Customization**
  - Dark mode (default)
  - Optional light mode
  - Color accent options
- [ ] **Settings Panel**
  - Radio IP/Port configuration
  - Slice selection
  - Display preferences
  - Save to localStorage
- [ ] **Status Indicators**
  - Connection status (green/red dot)
  - TX indicator (red border when transmitting)
  - VFO A/B indicators

#### Mobile Optimizations:
- [ ] Touch-friendly button sizes (min 44x44px)
- [ ] Swipe gestures for band/mode switching
- [ ] Haptic feedback on button press (if supported)
- [ ] Prevent zoom on double-tap
- [ ] iOS safe area handling

#### Deliverable:
✅ Professional, polished interface ready for daily use

---

### **Phase 5: Advanced Features** (Week 9-10+)
**Goal:** Add power-user features

#### Optional Features:
- [ ] **VFO B / Dual Receiver**
  - Sub-VFO display
  - RX2 controls
  - A/B swap buttons
- [ ] **Memory Channels**
  - Save/recall frequencies
  - Memory list
  - Import/export
- [ ] **Band Stack**
  - Save last freq/mode per band
  - Local storage
- [ ] **Antenna Selection**
  - Antenna switcher control (if available in API)
- [ ] **Equalizer**
  - TX/RX EQ controls
  - Graphical sliders
- [ ] **Notch Filters**
  - Manual notch frequency
  - Multiple notches
  - Visual indicator
- [ ] **AGC Controls**
  - AGC threshold
  - AGC mode (FAST/MED/SLOW/OFF)
- [ ] **Monitor Controls**
  - Monitor gain
  - Monitor pan
- [ ] **Profiles**
  - Save/load complete radio settings
  - Contest profiles
  - DX profiles
- [ ] **World Map**
  - Show spots on map
  - Click country to filter
  - Beam heading indicator
- [ ] **Statistics**
  - Spots per hour graph
  - Band activity
  - Top spotters
- [ ] **Logging Integration**
  - Quick QSO logging
  - Export to ADIF
  - Integration with QRZ.com

#### Deliverable:
⭐ Power-user features for serious operators

---

## 🎨 UI Design Specifications

### **Color Palette (Dark Theme)**
```css
--bg-primary: #1a1a1a      /* Main background */
--bg-secondary: #2d2d2d    /* Panels */
--bg-elevated: #3a3a3a     /* Buttons, inputs */
--text-primary: #e0e0e0    /* Main text */
--text-secondary: #a0a0a0  /* Secondary text */
--accent-blue: #4a9eff     /* Active/selected */
--accent-green: #4ade80    /* Good/RX */
--accent-red: #ef4444      /* Alert/TX */
--accent-yellow: #fbbf24   /* Warning */
--border: #404040          /* Borders */
```

### **Typography**
- **Frequency Display:** 48px, monospace, bold
- **Button Labels:** 14px, sans-serif, medium
- **Slider Labels:** 12px, sans-serif
- **Table Text:** 13px, monospace

### **Spacing**
- Button padding: 12px 20px
- Section gaps: 16px
- Control groups: 8px between items
- Sliders: 200px width (desktop), 100% (mobile)

### **Breakpoints**
```css
/* Mobile */
@media (max-width: 640px) {
  /* Stacked layout, full-width controls */
}

/* Tablet */
@media (min-width: 641px) and (max-width: 1024px) {
  /* 2-column layout */
}

/* Desktop */
@media (min-width: 1025px) {
  /* Full layout, spots on right or bottom */
}
```

---

## 🔧 Technical Implementation Details

### **WebSocket Protocol**

#### Server → Client (Status Updates):
```json
{
  "type": "status",
  "data": {
    "frequency": 14233400,
    "mode": "USB",
    "filter_low": 100,
    "filter_high": 2900,
    "tx": false,
    "smeter": -73,
    "rfpower": 31,
    "tunepower": 18,
    "miclevel": 32,
    "vox_enable": false
  }
}
```

#### Server → Client (DX Spot):
```json
{
  "type": "spot",
  "data": {
    "callsign": "K3WI",
    "frequency": 14074000,
    "spotter": "VE3XN",
    "comment": "FT8",
    "time": "2025-10-15T16:37:24Z"
  }
}
```

#### Client → Server (Command):
```json
{
  "type": "command",
  "action": "set_frequency",
  "value": 14074000
}
```

### **REST API Endpoints**

```python
GET  /api/status          # Get current radio status
POST /api/frequency       # Set frequency
POST /api/mode           # Set mode
POST /api/filter         # Set filter
POST /api/transmit       # Toggle TX
POST /api/tune           # Start tuner
POST /api/slider         # Update slider (drive/mic/tune)
GET  /api/meters         # Get meter readings
POST /api/dsp            # Toggle DSP functions
GET  /api/config         # Get app configuration
POST /api/config         # Update app configuration
```

### **Vue.js Component Structure**

```javascript
// Main App
createApp({
  data() {
    return {
      radioStatus: {},
      spots: [],
      settings: {},
      connected: false
    }
  },
  components: {
    BandButtons,
    ModeButtons,
    FreqDisplay,
    SMeter,
    Sliders,
    DspControls,
    FilterButtons,
    SpotsTable
  },
  methods: {
    sendCommand(action, value) { ... },
    handleSpot(spot) { ... },
    updateStatus(status) { ... }
  },
  mounted() {
    this.connectWebSocket();
    this.loadSettings();
  }
})
```

---

## 📊 Testing Strategy

### **Unit Testing**
- Backend: pytest for FlexCtl class
- Frontend: Jest for utility functions
- API: FastAPI TestClient

### **Integration Testing**
- WebSocket message flow
- Command execution → radio response
- Spot reception → table update

### **Browser Testing**
| Device | Browser | Priority |
|--------|---------|----------|
| Windows Desktop | Chrome | P0 |
| Windows Desktop | Firefox | P1 |
| macOS Desktop | Safari | P1 |
| iOS (iPhone) | Safari | P0 |
| Android Phone | Chrome | P0 |
| iPad | Safari | P1 |
| Android Tablet | Chrome | P2 |

### **Performance Testing**
- WebSocket latency < 100ms
- Spot table updates < 50ms
- Page load time < 2s
- Memory usage < 100MB

---

## 🚢 Deployment

### **Development**
```powershell
# Start backend
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8080

# Access from any device
http://192.168.1.50:8080
```

### **Production (Local Network)**
```powershell
# Run as background service
python -m backend.main
# Or use Windows Task Scheduler to start on boot
```

### **Optional: Standalone Desktop App**
```python
# Using PyWebView - wraps web app in native window
import webview
webview.create_window('FlexRadio Control', 'http://localhost:8080')
webview.start()
```

---

## 📚 SmartSDR API Commands Reference

### **Commands We Need to Implement**

#### Slice Control:
```
slice set <slice> freq=<hz>
slice set <slice> mode=<USB|LSB|CW|AM|DIGL|DIGU|FM|NFM|DFM>
slice set <slice> filter_lo=<hz>
slice set <slice> filter_hi=<hz>
slice set <slice> rfgain=<0-100>
slice set <slice> agc_mode=<off|slow|med|fast>
slice set <slice> nb=<0|1>
slice set <slice> nr=<0|1>
slice set <slice> anf=<0|1>
slice set <slice> apf=<0|1>
slice set <slice> tx=<0|1>
```

#### Transmit Control:
```
xmit <0|1>
transmit set rfpower=<0-100>
transmit set tunepower=<0-100>
transmit set miclevel=<0-100>
transmit set vox_enable=<0|1>
transmit set mon_gain_sb=<0-100>
tuner start
```

#### Meters:
```
sub meter <meter_num>
# Response: meter <num> src=<name> level=<value>
```

#### Audio:
```
audio stream <id> slice=<slice> gain=<0-100>
```

---

## 📋 Priority Legend

- **P0:** Must have - Core functionality
- **P1:** Should have - Important features
- **P2:** Nice to have - Enhanced features
- **P3:** Future - Advanced/optional features

---

## ✅ Success Criteria

### **Minimum Viable Product (MVP):**
- ✅ Works on desktop, mobile, tablet browsers
- ✅ Band/Mode/Filter selection
- ✅ Frequency display and control
- ✅ TX/TUNE/VOX controls
- ✅ Drive/Mic/Tune sliders
- ✅ DX spots table with filtering
- ✅ Click-to-tune from spots
- ✅ Real-time 2-way sync with radio
- ✅ Professional dark theme UI

### **Full Release:**
- ✅ All controls from sample GUI implemented
- ✅ S-meter visualization
- ✅ DSP controls (NB, NR, ANF, etc.)
- ✅ Mobile-optimized responsive layout
- ✅ Settings panel
- ✅ Keyboard shortcuts
- ✅ Error handling and notifications
- ✅ <100ms latency for controls

---

## 🎯 Next Steps

1. **Review this document** - Confirm goals and scope
2. **Set up development environment** - Install dependencies
3. **Start Phase 0** - Basic FastAPI + Vue.js skeleton
4. **Build one feature end-to-end** - Prove the stack works
5. **Iterate rapidly** - Add features incrementally

---

## 📝 Notes & Decisions

### **Technology Choices:**
- **Why FastAPI?** Modern, fast, WebSocket support, easy to learn
- **Why Vue.js?** Easier than React, powerful, great docs
- **Why Tailwind?** Professional look without custom CSS skills
- **Why not Electron?** Web app is lighter, more flexible

### **Design Philosophy:**
- **Mobile-first:** Design for touch, scale up to desktop
- **Responsive:** One codebase for all devices
- **Real-time:** WebSocket for instant updates
- **Simple:** Use CDN when possible, avoid complex build tools

### **Known Limitations:**
- Some FlexRadio features may not have API access
- Waterfall/panadapter requires complex canvas work (Phase 5+)
- Local network only (no remote access without VPN/port forwarding)

---

## 📞 Support & Resources

- **SmartSDR API Docs:** Check FlexRadio wiki/community
- **FastAPI Docs:** https://fastapi.tiangolo.com
- **Vue.js Docs:** https://vuejs.org
- **Tailwind CSS:** https://tailwindcss.com
- **WebSocket Testing:** Use browser dev tools

---

**Project Start Date:** 2025-01-XX  
**Target MVP Date:** 3 weeks from start  
**Target Full Release:** 8 weeks from start  

**Let's build something amazing! 🚀**