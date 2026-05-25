
# 🌞 Solar & HF Conditions Widget with Overlay Integration Guide

This guide describes how to implement **Solar / HF Conditions overlays** that appear at the bottom of **QRZ Profile boxes** and **DX Spots callsign cells** - neat, visible, non-obtrusive implementation for your **FlexRadio Vue + Python/HTML/JS** application.

## ✨ **NEW: Overlay Implementation**

The overlay system provides **compact solar/HF condition badges** that appear as subtle overlays at the bottom of profile pictures, callsign displays, and DX spots - always visible but never distracting.

---

## 1. 📡 Data Source API

**Backend Solar API Endpoint:** `/api/solar`  
**Data Source:** [HamQSL Solar Data API](https://www.hamqsl.com/solarjson.php)  
**Cache:** 10 minutes TTL to avoid excessive API calls

### Provided Data:
- **SFI** (Solar Flux Index) - Propagation quality indicator  
- **A-index** - Geomagnetic activity level  
- **K-index** - Geomagnetic disturbance level  
- **HF Band Conditions** - Day/Night conditions for 80m-10m  

---

## 2. 🐍 Python FastAPI Backend (IMPLEMENTED)

The complete backend endpoint is implemented in `backend/api/solar.py`:

### Key Features:
- **10-minute caching** to prevent API abuse
- **Error handling** with fallback to cached data  
- **Quality level assessment** (Good/Fair/Poor)
- **Health check endpoint** at `/api/solar/health`
- **Manual refresh** via `/api/solar/refresh`

### API Response Format:
```json
{
  "source": "HamQSL",
  "updated": "2025-11-01 14:30 UTC",
  "indices": {
    "sfi": 142,
    "a_index": 8,
    "k_index": 2
  },
  "hf_conditions": {
    "80m_40m": {"day": "Fair", "night": "Good"},
    "30m_20m": {"day": "Good", "night": "Good"},
    "17m_15m": {"day": "Good", "night": "Fair"},
    "12m_10m": {"day": "Poor", "night": "Poor"}
  },
  "quality_levels": {
    "sfi": "good",
    "a_index": "good", 
    "k_index": "good"
  }
}
```

---

## 3. 🎨 Frontend Solar Overlay System (IMPLEMENTED)

Complete JavaScript module: `frontend/js/solar-overlay.js`

### 🔧 **Overlay Features:**

#### **Compact Mode (Default)**
- Tiny badges showing **SFI**, **A**, **K** indices
- Color-coded quality levels (Green/Yellow/Red)
- Minimal space usage (perfect for overlays)

#### **Positioning Options**
- `bottom` - Center bottom (default for callsigns)
- `bottom-right` - Right bottom corner  
- `top` - Center top
- `top-right` - Right top corner

#### **Auto-Integration**
- Automatically adds overlays to **DX Spots callsign cells**
- Watches for spots table updates
- Refreshes data every 10 minutes

---

## 4. 🔌 Vue.js Integration (IMPLEMENTED)

### Automatic Initialization
The system auto-initializes when the Vue app starts:

```javascript
// In app-main.js initializeApp()
if (window.SolarOverlay) {
    await window.SolarOverlay.init();
    console.log('✅ Solar Overlay initialized');
}
```

### Vue Methods Available
```javascript
// Toggle overlay visibility
this.toggleSolarOverlays();

// Force refresh solar data  
await this.refreshSolarData();

// Manually add overlays to spots
this.addSolarOverlayToSpots();

// Get current solar data
const solarData = this.getSolarData();
```

### Automatic Spot Integration
```javascript
// Watcher automatically adds overlays when spots update
filteredSpots: {
    handler(newSpots) {
        this.$nextTick(() => {
            window.SolarOverlay.addToSpotsCells();
        });
    }
}
```

---

## 5. 🎯 **QRZ Profile Box Implementation**

### For Existing QRZ Profile Displays
```javascript
// Add overlay to any profile container
SolarOverlay.addToElement('.qrz-profile-container', {
    position: 'bottom-right'
});

// Add to specific callsign displays
SolarOverlay.addToElement('.callsign-display', {
    position: 'bottom'
});
```

### CSS Classes for QRZ Integration
```css
.qrz-profile-container {
    position: relative; /* Required for overlay positioning */
}

.qrz-profile-image {
    /* Your existing profile image styles */
}

/* The overlay will automatically position itself */
```

---

## 6. 📊 **DX Spots Integration (ACTIVE)**

The overlay system is **already integrated** with your DX Spots table:

- Overlays appear on **callsign cells** (4th column)
- Positioned at **bottom-right** of each cell  
- Updates automatically when spots refresh
- Doesn't interfere with spot clicking/tuning

---

## 7. 🔧 **Customization Options**

### Global Configuration
```javascript
SolarOverlay.config = {
    showOverlays: true,           // Enable/disable overlays
    autoRefresh: true,            // Auto-refresh every 10min
    overlayPosition: 'bottom',    // Default position
    showDetailedBands: false,     // Show band conditions
    compactMode: true            // Use compact display
};
```

### Manual Control
```javascript
// Toggle all overlays
SolarOverlay.toggleOverlays();

// Remove all overlays
SolarOverlay.removeAllOverlays();

// Force data refresh
await SolarOverlay.refresh();
```

---

## 8. 🎨 **Visual Examples**

### Compact Overlay (DX Spots)
```
┌─────────────────┐
│     OH2ABC      │ ← Callsign
│ SFI142 A8 K2    │ ← Solar overlay (bottom-right)
└─────────────────┘
```

### QRZ Profile Overlay
```
┌─────────────────┐
│                 │
│   Profile Pic   │
│                 │
│ SFI142 A8 K2    │ ← Overlay (bottom center)
└─────────────────┘
```

### Color Coding
- **🟢 Good:** SFI≥150, A≤10, K≤3
- **🟡 Fair:** SFI≥120, A≤20, K≤4  
- **🔴 Poor:** Below fair thresholds

---

## 9. 🚀 **Implementation Status**

✅ **Backend API:** Complete (`/api/solar`)  
✅ **Frontend Module:** Complete (`solar-overlay.js`)  
✅ **Vue Integration:** Complete (auto-init + methods)  
✅ **DX Spots Integration:** Active and working  
✅ **Auto-refresh:** Every 10 minutes  
✅ **Error Handling:** Fallback to cached data  

### 🔜 **Ready for QRZ Profile Integration**
Simply add this wherever you have QRZ profile displays:
```javascript
SolarOverlay.addToElement('.your-qrz-container', {
    position: 'bottom-right'
});
```

---

## 10. 🛠️ **Manual Testing**

### Browser Console Commands
```javascript
// Check if loaded
SolarOverlay.getSolarData()

// Add to any element
SolarOverlay.createOverlay(document.querySelector('.some-element'))

// Force refresh
await SolarOverlay.refresh()

// Toggle visibility
SolarOverlay.toggleOverlays()
```

### API Testing
```bash
# Test the backend endpoint
curl http://localhost:8000/api/solar

# Health check
curl http://localhost:8000/api/solar/health

# Force refresh
curl -X POST http://localhost:8000/api/solar/refresh
```

---

## 11. 📋 **Quality Thresholds**

### Solar Flux Index (SFI)
- **Good (🟢):** ≥ 150 - Excellent propagation
- **Fair (🟡):** ≥ 120 - Normal propagation  
- **Poor (🔴):** < 120 - Poor propagation

### A-Index (Geomagnetic Activity)
- **Good (🟢):** ≤ 10 - Quiet conditions
- **Fair (🟡):** ≤ 20 - Unsettled conditions
- **Poor (🔴):** > 20 - Active/stormy conditions

### K-Index (Geomagnetic Disturbance)
- **Good (🟢):** ≤ 3 - Quiet to unsettled
- **Fair (🟡):** 4 - Active conditions
- **Poor (🔴):** ≥ 5 - Minor to major storms

---

## 🏆 **Benefits of Overlay Implementation**

1. **Non-obtrusive:** Always visible but never in the way
2. **Context-aware:** Shows conditions relevant to each callsign
3. **Real-time:** Auto-updates every 10 minutes
4. **Performance:** Cached data prevents API abuse  
5. **Responsive:** Works on mobile and desktop
6. **Integrated:** Seamlessly works with existing DX spots
7. **Expandable:** Easy to add to any callsign/profile display

---

**Author:** Enhanced by Zencoder AI Assistant  
**Version:** 2.0 - Overlay Implementation  
**Date:** November 2025  
**License:** MIT  
**Status:** ✅ **FULLY IMPLEMENTED AND ACTIVE**
