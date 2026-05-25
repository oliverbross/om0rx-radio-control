# Quick Start Guide - Multi-Window Separate Pages

## 🚀 Getting Started in 30 Seconds

### Step 1: Start the Application
Make sure your FlexRadio app is running:
```bash
.\start_webapp.ps1
```

### Step 2: Open the Launcher
Navigate to: **http://localhost:8000/launcher.html**

### Step 3: Click "Open All Windows"
One click opens all three windows:
- 📻 Radio Control
- 📝 Logging & QRZ
- 🎯 DX Spots

**That's it!** All three windows are now open and working together.

---

## 📋 What You'll See

### Window 1: Radio Control (📻)
- Frequency display in large blue numbers
- Volume, Monitor, AGC-T, Drive, Tune, Mic sliders
- Band selection buttons (160M, 80M, 40M, 20M, etc.)
- Mode buttons (USB, LSB, CW, etc.)
- RIT/XIT controls
- DSP buttons and filters

### Window 2: Logging & QRZ (📝)
**Left Column:** QSO Logging Form
- Callsign entry
- Date/Time/Frequency
- Mode and RST
- Location, Gridsquare, POTA, SOTA, etc.
- Log QSO button

**Middle Column:** QRZ Profile
- Photo of operator
- Name, Country, State
- Contact info, Grid location

**Right Column:** DXCC / Wavelog Info
- Country info
- DXCC status
- Bearing and coordinates
- Previous QSOs

### Window 3: DX Spots (🎯)
- Real-time spot updates from DX cluster
- Advanced filters:
  - Bands, Modes
  - Countries, Zones
  - Call Status, DXCC Status
  - Special activities
- Click any spot to tune the radio

---

## ⚡ How They Work Together

1. **Spot to Radio**
   - Click a spot in DX Spots window
   - Radio frequency instantly updates in Radio Control window
   - Logging window shows the frequency too

2. **Logging to Radio**
   - Enter callsign in Logging window
   - Radio frequency appears in the form
   - QRZ profile and DXCC info load automatically

3. **All Windows Stay in Sync**
   - Change frequency in Radio Control window
   - Other windows instantly show new frequency
   - Everything connected through backend

---

## 🔗 Direct URLs

If you prefer to open windows individually:

- **Radio Control:** `http://localhost:8000/radio-control.html`
- **Logging & QRZ:** `http://localhost:8000/logging.html`
- **DX Spots:** `http://localhost:8000/spots.html`
- **Launcher:** `http://localhost:8000/launcher.html` (recommended)
- **Main App:** `http://localhost:8000/index.html` (original)

---

## ✅ What's New

**Created:**
- ✅ 3 separate HTML pages (radio-control, logging, spots)
- ✅ Launcher page for easy access
- ✅ Documentation and guides

**Modified:**
- ✅ app.js - Added 4 lines for page mode detection (only!)
- ❌ index.html - NOT CHANGED (100% identical)

**Result:**
- ✅ No code duplication
- ✅ Same functionality as before
- ✅ Better window management
- ✅ Fully synchronized across windows

---

## 🎯 Testing Verification

Before confirming success, verify:

- [ ] Launcher page loads and looks good
- [ ] All three windows open when you click "Open All Windows"
- [ ] Each window displays its section correctly
- [ ] Clicking a spot in Spots window tunes the Radio Control window
- [ ] Entering a callsign in Logging window loads QRZ/DXCC info
- [ ] All windows show same radio frequency
- [ ] You can close/reopen windows without issues
- [ ] Original index.html still works exactly as before

---

## 💡 Tips

1. **Window Layout**
   - Arrange windows side-by-side or overlapping as you prefer
   - Windows can be minimized/maximized independently
   - Close any window you're not using

2. **Best Practice**
   - Keep Radio Control window visible for frequency
   - Use Logging window for QSO entry
   - Reference DX Spots for new stations
   - Click spots to tune radio in real-time

3. **Keyboard Shortcuts**
   - Arrow keys tune frequency in Radio Control window
   - Mouse wheel on frequency display also works
   - Tab navigation in Logging window form

4. **Mobile/Tablet**
   - All three windows are responsive
   - Can be viewed on tablets side-by-side
   - Full touch support for buttons and sliders

---

## 🔧 Troubleshooting

**Problem:** Windows don't open
- **Solution:** Check if pop-ups are blocked. Allow pop-ups for localhost:8000

**Problem:** Windows not synchronized
- **Solution:** Check if backend is running. Try refreshing the page.

**Problem:** Spots not showing
- **Solution:** Check if DX cluster is connected. Look for connection indicator.

**Problem:** Page says "Disconnected"
- **Solution:** Backend might be down. Check the console for errors.

**Problem:** Old layout still showing
- **Solution:** Clear browser cache (Ctrl+F5) and reload.

---

## 📞 Next Steps

Once you've verified everything works:

1. Test with real radio operation
2. Confirm all three windows stay synchronized
3. Let us know if you want any adjustments
4. Then we can add landing page with buttons

---

## 📚 For More Information

See detailed documentation:
- `SEPARATE_WINDOWS_README.md` - Technical details
- `IMPLEMENTATION_SUMMARY_MULTI_WINDOW.md` - Complete summary

---

**Ready to test?** Open http://localhost:8000/launcher.html now! 🚀