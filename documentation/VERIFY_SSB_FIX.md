# SSB Mode Fix - Quick Verification Guide (5 Minutes)

## ✅ Pre-Flight Checks

1. **Verify Code Change**
   ```powershell
   # Check that app.js has the mode mapping logic (lines 840-847)
   Get-Content "c:\Projects\om0rx-radio-control\frontend\app.js" -TotalCount 850 | Select-Object -Last 20
   ```
   Should show:
   ```javascript
   let radioMode = spot.mode;
   if (spot.mode === 'SSB' || spot.mode === 'ssb') {
       radioMode = freqMhz < 14 ? 'LSB' : 'USB';
   }
   ```

2. **Run Automated Tests**
   ```powershell
   cd "c:\Projects\om0rx-radio-control"
   python test_ssb_mode_mapping.py
   ```
   Expected: ✅ ALL TESTS PASSED

---

## 🎯 Manual Testing Steps

### Setup (2 minutes)
1. Start webapp:
   ```powershell
   .\start_webapp.ps1
   ```
   
2. Open browser:
   - URL: http://localhost:8000
   - Open Developer Tools: Press **F12**
   - Click on **Console** tab

### Test Cases (3 minutes)

**TEST 1: FT8 Spot (DIGI Mode) - Baseline**
- In DX Spots table, find an **FT8** spot
- Click on it
- Expected: ✅ Mode in SmartSDR changes to **DIGI**
- Console shows: `Tuning to spot: XX.XXX Mode: FT8 → FT8`

**TEST 2: CW Spot (CW Mode) - Baseline**
- In DX Spots table, find a **CW** spot
- Click on it
- Expected: ✅ Mode in SmartSDR changes to **CW**
- Console shows: `Tuning to spot: XX.XXX Mode: CW → CW`

**TEST 3: SSB Spot on 80m Band (LSB) - CRITICAL**
- In DX Spots table, find an **SSB** spot with frequency between **3.5-4.0 MHz**
  - Example from image: 3.7 MHz or 7.0 MHz (40m band)
- Click on it
- Expected: ✅ Mode in SmartSDR changes to **LSB**
- Console shows: `Tuning to spot: 3.7 Mode: SSB → LSB` ✅ (NOT DIGI)

**TEST 4: SSB Spot on 20m Band (USB) - CRITICAL**
- In DX Spots table, find an **SSB** spot with frequency between **14.0-14.35 MHz**
- Click on it
- Expected: ✅ Mode in SmartSDR changes to **USB**
- Console shows: `Tuning to spot: 14.2 Mode: SSB → USB` ✅ (NOT DIGI)

**TEST 5: SSB Spot on 10m Band (USB) - Additional**
- In DX Spots table, find an **SSB** spot with frequency above **28 MHz** (10m band)
- Click on it
- Expected: ✅ Mode in SmartSDR changes to **USB**
- Console shows: `Tuning to spot: 28.X Mode: SSB → USB` ✅

---

## 🔍 What to Look For

### ✅ Success Indicators
- [ ] Console shows "SSB → LSB" for lower band SSB spots
- [ ] Console shows "SSB → USB" for upper band SSB spots
- [ ] SmartSDR Mode display changes correctly
- [ ] No errors in console
- [ ] Frequency changes correctly for all spots

### ❌ Failure Indicators
- [ ] Console shows "SSB → DIGI" (old bug)
- [ ] Red errors in console
- [ ] Radio mode doesn't change
- [ ] Wrong mode displayed

---

## 📊 Quick Reference

| Frequency | Band | Mode | Expected |
|-----------|------|------|----------|
| 1.8-2.0 MHz | 160m | SSB | → LSB ✅ |
| 3.5-4.0 MHz | 80m | SSB | → LSB ✅ |
| 5.3-5.4 MHz | 60m | SSB | → LSB ✅ |
| 7.0-7.3 MHz | 40m | SSB | → LSB ✅ |
| 10.1-10.15 MHz | 30m | SSB | → LSB ✅ |
| 14.0-14.35 MHz | 20m | SSB | → USB ✅ |
| 18+ MHz | 17m+ | SSB | → USB ✅ |

---

## 📝 Verification Checklist

- [ ] Automated tests pass
- [ ] FT8 spots still work correctly (mode: DIGI)
- [ ] CW spots still work correctly (mode: CW)
- [ ] SSB on 80m sets LSB mode
- [ ] SSB on 40m sets LSB mode
- [ ] SSB on 20m sets USB mode
- [ ] No console errors
- [ ] Frequency tuning works for all spot types

---

## 🆘 Troubleshooting

### "Console shows SSB → DIGI"
- ❌ Old code is still running
- Solution: Hard refresh browser (Ctrl+Shift+R or Cmd+Shift+R)
- Or clear browser cache and reload

### "Mode in SmartSDR doesn't change"
- Check SmartSDR is connected and responsive
- Verify no errors in console
- Check that frequency changes correctly
- Mode might take 1-2 seconds to update

### "Can't find SSB spots to test"
- Wait for DX cluster to send SSB spots
- Spots typically update every 30 seconds
- Try different times of day (more activity on upper bands at night)

### "Getting authentication error"
- Check that backend is running
- Start webapp: `.\start_webapp.ps1`
- Clear cache and reload page

---

## ✅ Sign-Off

Once all checks pass:
- [ ] Code changes verified
- [ ] Automated tests passing
- [ ] Manual tests completed
- [ ] No console errors
- [ ] Ready for production ✅

Date verified: __________
Tester: __________
