# FT8/FT4 Quick Start Guide

## 🚀 Getting Started with FT8/FT4 Integration

This guide will help you configure and test the FT8/FT4 digital mode integration in your FlexRadio web control application.

## ✅ Prerequisites

- FlexRadio connected to network
- Python packages installed:
  - ✅ `scipy` (installed)
  - ✅ `sounddevice` (installed)
- Browser refresh to load new UI

## 📝 Step-by-Step Setup

### Step 1: Refresh Your Browser
Hard refresh to load the updated interface:
- **Windows**: `Ctrl + Shift + R` or `Ctrl + F5`
- **Mac**: `Cmd + Shift + R`

### Step 2: Open FT8 Modal
Click the **🔊 FT8/DIGI** button in the top-right corner of the interface.

You should see the FT8 modal with two tabs:
- **📻 Operate** - Main operating interface
- **⚙️ Settings** - Configuration panel

### Step 3: Configure Settings

Click the **⚙️ Settings** tab and configure:

#### Station Information
```
My Callsign:  OM0RX     (your callsign)
My Grid:      JN88      (your grid square)
Mode:         FT8       (or FT4)
```

#### Network Server (CAT Control)
```
Server Address:  192.168.0.199:4992
PTT Method:      CAT (Software)
```

**Note**: Update the IP address to match your FlexRadio's network address.

#### Audio Configuration
```
Audio Input:   FlexRadio DAX RX  (or select your audio device)
Audio Output:  FlexRadio DAX TX  (or select your audio device)
Sample Rate:   12000 Hz
☑ Use FlexRadio DAX Audio
```

#### Operation Settings
```
☐ Auto Sequence QSOs       (enable for automatic responses)
☐ Enable TX by Default     (leave unchecked for safety)
Waterfall Height: 100
```

### Step 4: Save Configuration
Click **💾 Save Configuration**

You should see: **✅ Saved!**

### Step 5: Test the Interface

1. Click the **📻 Operate** tab
2. Verify your settings are displayed
3. **(DO NOT CLICK START YET)** - Audio processing not yet implemented

## 🔍 Verification

### Check Console
Open browser console (F12) and verify:
```
✅ FT8 configuration loaded
✅ Audio devices loaded: {...}
```

### Check Settings
In the Settings tab, verify:
- Audio device dropdowns are populated
- Your configuration is displayed correctly
- Save/Reload buttons work

### Check Network
Verify FlexRadio connectivity:
```powershell
ping 192.168.0.199
```

## 🎯 Current Capabilities

### ✅ Implemented
- Configuration UI with tabbed interface
- Settings persistence (in-memory)
- Audio device enumeration
- Network server configuration
- PTT method selection
- Mode selection (FT8/FT4)

### ⏳ In Progress (Stage 3)
- Real-time audio capture
- Waterfall visualization
- Signal detection
- FT8 protocol decoding

### 🔮 Future (Stage 4+)
- FlexRadio CAT integration
- PTT control
- Audio TX to radio
- QSO management
- Auto-sequencing

## 🧪 Testing Without Radio

You can test the configuration UI without a radio:

1. Open FT8 modal
2. Configure settings (use dummy values if needed)
3. Save configuration
4. Reload configuration
5. Switch between tabs
6. Check browser console for errors

## 📊 Audio Device Detection

### FlexRadio DAX Setup
To use FlexRadio DAX audio:

1. Open SmartSDR
2. Configure DAX channels:
   - **DAX RX**: For receiving FT8 audio
   - **DAX TX**: For transmitting FT8 audio
3. Select "FlexRadio DAX" in the dropdown

### System Audio Devices
The app will automatically detect:
- All audio input devices on your system
- All audio output devices on your system
- FlexRadio DAX channels (if configured)

If devices don't appear:
1. Refresh the page
2. Check Windows Sound settings
3. Verify audio drivers are installed

## ⚙️ Configuration Files

### Current Config Location
`c:\Projects\om0rx-radio-control\config.py`

New FT8 settings added:
```python
FT8_ENABLED = True
FT8_MODE = "FT8"
FT8_MYCALL = "OM0RX"
FT8_MYGRID = "JN88"
FT8_NETWORK_SERVER = "192.168.0.199:4992"
FT8_AUDIO_INPUT = "default"
FT8_AUDIO_OUTPUT = "default"
FT8_SAMPLE_RATE = 12000
FT8_AUTO_SEQUENCE = False
FT8_TX_ENABLED = False
FT8_WATERFALL_HEIGHT = 100
FT8_USE_FLEXRADIO_AUDIO = True
FT8_PTT_METHOD = "CAT"
```

### Editing Configuration
To manually edit:
1. Stop the server
2. Edit `config.py`
3. Restart the server
4. Reload configuration in UI

## 🐛 Troubleshooting

### Modal Doesn't Open
- **Refresh browser** (Ctrl + Shift + R)
- **Check console** for JavaScript errors
- **Verify button** is visible in top-right

### Settings Tab is Empty
- **Check browser console** for errors
- **Reload page** completely
- **Verify CSS** file is loaded (ft8-modal.css)

### Audio Devices Not Listed
- **Verify sounddevice** is installed: `pip list | findstr sounddevice`
- **Check Windows** audio devices are working
- **Restart application** after installing sounddevice

### Configuration Not Saving
- **Check browser console** for API errors
- **Verify backend** is running
- **Check network tab** (F12) for failed requests

### FlexRadio Not Connecting
- **Verify IP address** is correct
- **Check port 4992** is open
- **Ping radio**: `ping 192.168.0.199`
- **Check SmartSDR** is running

## 📱 Mobile/Responsive

The FT8 modal is responsive and works on:
- Desktop browsers (Chrome, Edge, Firefox)
- Tablets (landscape mode recommended)
- Mobile phones (limited, portrait mode challenging)

## 🔐 Safety Features

### TX Protection
- **TX disabled by default** on modal open
- **Enable TX** checkbox must be checked
- **Start button** required before operation
- **Stop button** immediately stops all operations

### Fail-safes
- Connection status indicator (🟢 Active / 🔴 Inactive)
- Settings disabled while connected (prevents mid-operation changes)
- Automatic WebSocket reconnection
- Error logging to console

## 📈 Performance Tips

1. **Sample Rate**: Use 12000 Hz for best performance
2. **Waterfall Height**: Lower values = better performance
3. **Browser**: Chrome/Edge recommended for best WebSocket performance
4. **Network**: Low latency to FlexRadio improves responsiveness

## 🎓 Learning Resources

### FT8 Protocol
- [WSJT-X User Guide](https://physics.princeton.edu/pulsar/k1jt/wsjtx.html)
- [FT8 Operating Guide](https://www.g4ifb.com/FT8_Hinson_tips_for_HF_DXers.pdf)

### FlexRadio
- [SmartSDR User Guide](https://www.flexradio.com/documentation/)
- [DAX Setup Guide](https://helpdesk.flexradio.com/)

### Digital Modes
- [ARRL Digital Modes](http://www.arrl.org/digital)
- [FT8 Tutorial Videos](https://www.youtube.com/results?search_query=ft8+tutorial)

## 💬 Support

If you encounter issues:

1. **Check browser console** (F12) for errors
2. **Check server logs** in `logs/` directory
3. **Verify prerequisites** are installed
4. **Review documentation** in `/documentation/`

## ✨ What's Next

Once configuration is working:

### Stage 3: Real Audio Processing
- Connect audio capture to waterfall
- Implement spectrum analysis
- Add real-time visualization

### Stage 4: FlexRadio Integration
- CAT control implementation
- PTT functionality
- Frequency synchronization

### Stage 5: Protocol Implementation
- FT8/FT4 encoding
- FT8/FT4 decoding
- Message parsing

### Stage 6: QSO Management
- Auto-sequencing
- Contact logging
- Wavelog integration

---

**Last Updated**: 2025-01-05  
**Version**: Stage 2 Complete  
**Status**: Configuration UI Functional ✅