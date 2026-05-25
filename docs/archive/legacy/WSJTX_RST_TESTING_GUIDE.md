# WSJT-X RST Capture - Quick Testing Guide

## Before You Start

✅ **Restart services** to apply changes:
1. Stop the bridge server (Ctrl+C in Node.js window)
2. Stop the Flask backend (Ctrl+C in Python window)
3. Refresh browser (F5 or Ctrl+R)
4. Restart backend: `python backend/main.py`
5. Restart bridge: `node sdc-bridge-server.js`
6. Open application: `http://localhost:8000`

## Test Scenario 1: Real-Time RST Updates

### Setup
- Have WSJT-X running and connected to the network
- Open the Log QSO form in om0rx-radio-control
- Open Browser Console (F12)
- Filter console for "WSJT-X" messages

### Steps
1. **Double-click a station in WSJT-X** (e.g., EA1CF)
2. **Watch the browser console** for:
   ```
   📍 WSJT-X Status: EA1CF (IN52XV)
      📤 TX RST: [should show value if contact in progress]
      📥 RX RST: [should show value if contact in progress]
   ✅ Form populated with WSJT-X data:
      Callsign: EA1CF
      Grid: IN52XV
      Frequency: 10.137
      Mode: FT8
      RST Sent: [value or empty]
      RST Received: [value or empty]
   ```
3. **Observe form in UI** - should show call, grid, frequency
4. **As you exchange messages** - RST fields should update with actual values

### Expected Results
- ✅ Form populates immediately
- ✅ Antenna rotates to correct grid (if enabled)
- ✅ RST values appear in console and update in real-time
- ✅ Form fields show actual signal reports (not hardcoded 599)

---

## Test Scenario 2: Form Clearing on New Contact

### Setup
- Continue from above or repeat Test Scenario 1

### Steps
1. **Complete the QSO** with the first station (RR73)
2. **Double-click a DIFFERENT station** (e.g., OZ7DR)
3. **Watch browser console** for:
   ```
   🆕 NEW CONTACT DETECTED: EA1CF → OZ7DR
   🗑️ Clearing form for new contact...
   ```
4. **Observe form in UI** - should be empty except mode (FT8)

### Expected Results
- ✅ Console shows contact change detection
- ✅ Form clears all previous data
- ✅ Ready for new contact with fresh fields
- ✅ QRZ lookup triggers for new callsign

---

## Test Scenario 3: QSO Auto-Save with RST

### Prerequisites
- **Wavelog integration must be ENABLED** in config
- Check config: `WAVELOG_ENABLED = True`
- Wavelog API credentials configured

### Setup
- Have a contact in progress
- Browser console visible
- Check "Messages" tab in browser DevTools

### Steps
1. **Complete a full QSO in WSJT-X**
   - Exchange: CQ → Call heard → Signal reports → RR73
   - Example: You send "R-12", they send "+15"
2. **Wait for WSJT-X to mark QSO as logged**
3. **Watch browser console** for:
   ```
   📝 Saving QSO to Wavelog: EA1CF
   ✅ Using actual RST values from WSJT-X:
      📤 TX RST: R-12
      📥 RX RST: +15
   📤 Sending QSO data to backend:
   {
     "callsign": "EA1CF",
     "frequency": 10.137,
     "mode": "FT8",
     "rst_sent": "R-12",
     "rst_received": "+15",
     "gridsquare": "IN52XV",
     "name": "John",
     "country": "Spain",
     ...
   }
   📡 API Response Status: 200 OK
   ✅ QSO saved to Wavelog successfully
   ```
4. **A modal popup should appear** showing:
   ```
   ✅ QSO Logged Successfully!
   
   Call: EA1CF
   Freq: 10.137 MHz
   Mode: FT8
   Grid: IN52XV
   RST Sent: R-12
   RST Rcvd: +15
   
   Name: John
   Country: Spain
   ```
5. **Click OK** to dismiss modal

### Expected Results
- ✅ Console shows actual RST values (not 599)
- ✅ API shows correct data types (strings for RST)
- ✅ Modal appears confirming save
- ✅ Form clears after modal dismissal

---

## Test Scenario 4: Verify Wavelog Database

### Steps
1. **Log in to Wavelog** web interface
2. **Go to QSO Log**
3. **Find the latest QSO** (should be EA1CF or whoever you contacted)
4. **Check the fields**:
   - ✅ Call: EA1CF
   - ✅ Frequency: 10.137 MHz
   - ✅ Mode: FT8
   - ✅ Grid: IN52XV
   - ✅ **RST Sent: R-12** (actual value, not 599)
   - ✅ **RST Received: +15** (actual value, not 599)
   - ✅ Name: John (from QRZ if available)
   - ✅ Country: Spain (from DXCC)

### Expected Results
- ✅ QSO saved correctly
- ✅ All fields populated
- ✅ RST values match what was exchanged in WSJT-X
- ✅ QRZ and DXCC data merged

---

## Troubleshooting

### Issue: Modal doesn't appear
**Cause**: Wavelog might be disabled or fetch failed
**Solution**:
1. Check console for error messages
2. Verify WAVELOG_ENABLED = True in config
3. Check Wavelog credentials are valid
4. Look for HTTP error status in console logs

### Issue: RST shows empty in form
**Cause**: WSJT-X hasn't sent status updates yet
**Solution**:
1. Give it a moment - status updates come as contact progresses
2. Check bridge is running and receiving WSJT-X packets
3. Verify WSJT-X Settings > Reporting > "Enable UDP Server" is checked

### Issue: QSO saves but RST still shows 599
**Cause**: Bridge not restarted, or old code still running
**Solution**:
1. Kill all Node.js processes: `taskkill /F /IM node.exe`
2. Kill all Python processes: `taskkill /F /IM python.exe`
3. Close and reopen browser completely
4. Restart backend and bridge
5. Repeat test

### Issue: "NEW CONTACT DETECTED" doesn't appear
**Cause**: Switching back to same station, not a new one
**Solution**:
1. Make sure you double-click a DIFFERENT callsign
2. Check browser console has filtering set correctly
3. Try switching between two very different callsigns

---

## Console Message Reference

| Message | Meaning | Status |
|---------|---------|--------|
| `📍 WSJT-X Status` | Station selected | ℹ️ Info |
| `📤 TX RST:` | Value we sent | ℹ️ Info |
| `📥 RX RST:` | Value they sent | ℹ️ Info |
| `✅ Form populated` | Form updated | ✅ Success |
| `🆕 NEW CONTACT` | Different station detected | ℹ️ Info |
| `🗑️ Clearing form` | Form reset | ℹ️ Info |
| `✅ Using actual RST` | Values captured | ✅ Success |
| `📤 Sending QSO data` | API call made | ℹ️ Info |
| `❌ HTTP Error` | API failed | ❌ Error |
| `✅ QSO saved` | Success! | ✅ Success |
| `⚠️ Missing RST` | No signal reports | ⚠️ Warning |

---

## Files to Check

**Log Messages:** `logs/log.md` in browser console
- Shows all WSJT-X status messages
- Shows RST values as they arrive
- Shows API responses
- Shows modal confirmations

**Backend Logs:** Flask/Python output
- Check for API errors (400, 422, 500)
- Check Wavelog API responses
- Check database writes

**Bridge Logs:** Node.js output
- Check if UDP packets received from WSJT-X
- Check if Status messages parsed correctly
- Check if RST fields populated

---

## Quick Checklist

- [ ] Bridge restarted after code changes
- [ ] Backend restarted after code changes
- [ ] Browser cache cleared (Ctrl+Shift+Delete)
- [ ] WSJT-X running and sending UDP packets
- [ ] Wavelog integration enabled in config
- [ ] Wavelog API credentials valid
- [ ] Complete at least one full QSO in WSJT-X
- [ ] Check console logs for RST values
- [ ] Verify modal appears after QSO
- [ ] Verify Wavelog database has correct RST values

---

## Next Steps

If everything works:
1. ✅ Document the RST values captured
2. ✅ Verify Wavelog integration complete
3. ✅ Check form clearing works correctly
4. ✅ Confirm modal shows proper confirmation

If issues persist:
1. Check sdc-bridge-server.js logs for WSJT-X parsing errors
2. Check backend/main.py logs for API validation errors
3. Check browser Network tab for HTTP responses
4. Verify WSJT-X is sending txRst/rxRst in packets