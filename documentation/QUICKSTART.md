# 🚀 QUICK START GUIDE

## FlexRadio Web Control v2.0

### ⚡ START IN 3 STEPS:

#### **1. Start the Web App**
```powershell
.\start_webapp.ps1
```

#### **2. Open Your Browser**
**On this computer:**
```
http://localhost:8080
```

**From phone/tablet:**
```
http://YOUR_IP_ADDRESS:8080
```

#### **3. Start Operating!**
- ✅ Click band buttons to change bands
- ✅ Click mode buttons to change modes
- ✅ Move sliders to adjust levels
- ✅ Click DX spots to tune instantly
- ✅ Use TX controls (MOX, TUNE, VOX)
- ✅ Toggle DSP features (NB, NR, ANF, APF)

---

## 🎯 WHAT YOU GET

### **ALL Radio Controls:**
- 11 Band Buttons (160M-6M)
- 8 Mode Buttons (LSB, USB, CW, AM, DIGL, DIGU, FM, NFM)
- 6 Filter Presets (1.8K, 2.1K, 2.4K, 2.7K, 2.9K, 3.3K)
- Volume, Drive, Tune Power, Mic Level, Monitor Sliders
- MOX, TUNE, VOX Controls

### **Advanced Features:**
- S-Meter with Bar Graph
- AGC Control (OFF, SLOW, MED, FAST)
- DSP Controls (NB, NR, ANF, APF)
- RX2 / Dual Receiver
- SPLIT Operation
- Sub-VFO Display

### **DX Spots Integration:**
- Live DX Spots Table
- Click-to-Tune
- Filter by Callsign
- Filter by Band
- Real-Time Updates

### **User Experience:**
- Professional Glass-Morphism UI
- Real-Time WebSocket Sync
- 2-Way Sync with SmartSDR
- Mobile/Tablet Responsive
- Connection Status Indicator
- UTC Clock Display

---

## 📱 ACCESS FROM MOBILE

1. **Make sure phone is on same Wi-Fi**
2. **Find your computer's IP address**
   - On Windows: Run `ipconfig` in PowerShell
   - Look for "IPv4 Address" (e.g., 192.168.0.199)
3. **Open browser on phone**
4. **Go to: `http://YOUR_IP:8080`**

Example: `http://192.168.0.199:8080`

---

## 🔧 CONFIGURATION

Edit `config.py` if needed:

```python
# FlexRadio Connection
FLEX_TCP_HOST = "192.168.0.199"  # ← Your FlexRadio IP
FLEX_TCP_PORT = 4992
FLEX_SLICE_ID = 0  # Slice A

# Database (for DX Spots)
DB_HOST = "localhost"
DB_PORT = 3306
DB_NAME = "wavelog"
DB_USER = "<db_user>"
DB_PASS = "<db_password>"
```

---

## 🧪 TEST IT WORKS

### **Desktop Checklist:**
- [ ] Green connection indicator
- [ ] Frequency displays
- [ ] Click 20M → Frequency changes to ~14 MHz
- [ ] Click USB → Mode changes
- [ ] Move volume slider → Volume changes
- [ ] S-meter shows signal strength
- [ ] DX spots table shows data
- [ ] Click spot → Radio tunes

### **Mobile Checklist:**
- [ ] Can access from phone
- [ ] Touch controls work
- [ ] Layout adapts to small screen
- [ ] Can tune to DX spots

---

## ❌ TROUBLESHOOTING

### **Can't Start Server**
```powershell
# Install dependencies
pip install -r requirements.txt

# Check Python version (need 3.10+)
python --version

# Try manual start
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

### **Connection Failed (Red Dot)**
1. Check FlexRadio IP in `config.py`
2. Verify SmartSDR is running
3. Test: `ping 192.168.0.199`

### **No DX Spots**
1. Check database settings in `config.py`
2. Verify database is running
3. Check `dx_spots` table has data

### **Can't Access from Phone**
1. Phone on same Wi-Fi?
2. Using computer's IP (not `localhost`)?
3. Firewall blocking port 8080?

---

## 📖 FULL DOCUMENTATION

See `WEBAPP_COMPLETE.md` for:
- Complete feature list
- Architecture details
- API documentation
- Advanced configuration
- Performance metrics

---

## 🎉 YOU'RE READY!

```powershell
# Start the server
.\start_webapp.ps1

# Open browser
start http://localhost:8080
```

**73 DE OM0RX** 📻

Enjoy your professional FlexRadio web interface!