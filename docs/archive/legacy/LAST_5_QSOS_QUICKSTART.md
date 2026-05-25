# Last 5 QSOs - Quick Start Guide

## What's New?
When you look up a callsign in the logging panel, you'll now see the **last 5 QSOs** with that person displayed in a formatted table below the additional information section.

## How to Use

### 1. Enter a Callsign
Type or paste a callsign in the **Callsign** field in the logging panel:
```
OM0AAO
```

### 2. Wait for Lookup (Automatic)
The system automatically searches for previous contacts after 500ms. You don't need to click anything!

### 3. View the Table
Below the "Additional Information" section, you'll see:
```
📋 Previous QSOs (Last 5)

┌────────────┬──────────┬──────┬───────┬───────┬───────┬──────────┐
│ Date       │ Callsign │ Mode │ RST S │ RST R │ Band  │ LoTW     │
├────────────┼──────────┼──────┼───────┼───────┼───────┼──────────┤
│ 14/10/24   │ OM0AAO   │ SSB  │ 599   │ 599   │ 20m   │ ✅ YES   │
│ 08/10/24   │ OM0AAO   │ SSB  │ 59    │ 59    │ 80m   │ ❌ NO    │
│ 01/10/24   │ OM0AAO   │ CW   │ 599   │ 599   │ 80m   │ ✅ YES   │
│ 04/06/24   │ OM0AAO   │ SSB  │ 599   │ 599   │ 20m   │ ✅ YES   │
│ 04/06/24   │ OM0AAO   │ SSB  │ 599   │ 599   │ 80m   │ ✅ YES   │
└────────────┴──────────┴──────┴───────┴───────┴───────┴──────────┘

Max. 5 previous contacts are shown
```

## Column Explanations

| Column | Meaning | Values |
|--------|---------|--------|
| **Date** | When you had contact | MM/DD/YYYY (with optional time) |
| **Callsign** | Contact's call (highlighted in blue) | e.g., OM0AAO, W1AW, G4BZH |
| **Mode** | Operating mode (in green) | SSB, CW, FT8, RTTY, etc. |
| **RST S** | Report Sent (S-meter report you sent) | 2-3 digit number |
| **RST R** | Report Received (report you got) | 2-3 digit number |
| **Band** | Ham radio band | 160m, 80m, 40m, 20m, 10m, etc. |
| **LoTW** | LoTW Confirmation status | ✅ YES / ❌ NO / - (unknown) |

## Data Sources

The system checks for recent QSOs in this order:
1. **Wavelog Server** (if available and configured)
2. **Local ADIF Log File** (fallback)

If both fail, no QSO history will be displayed.

## What If I Don't See the Table?

### No QSO History Found
- The callsign hasn't been worked before, OR
- The callsign isn't in your log file

### Table is Missing
- Your log file (`qso_log.adif`) might be empty or corrupted
- Wavelog API might be unavailable (check configuration)
- The callsign field is empty

## Features

✅ **Automatic Lookup** - No button needed, just type the call  
✅ **Dual Source** - Works with Wavelog server or local logs  
✅ **Smart Formatting** - Dates formatted nicely (MM/DD/YYYY)  
✅ **Color-Coded** - Easy to read with theme-appropriate colors  
✅ **Recent First** - Most recent QSOs shown first  
✅ **Limited Results** - Shows last 5 QSOs to keep UI clean  
✅ **LoTW Status** - Shows if QSO is confirmed via LoTW  

## Tips & Tricks

### Tip 1: Wide Display
The table automatically scrolls horizontally if the window is narrow. Make sure the info box is wide enough to see all columns.

### Tip 2: Hover for Details
Hover over cells to see the full content if text is truncated.

### Tip 3: Clear Search
Just clear the callsign field to hide the QSO history.

### Tip 4: Use for Pre-filling
In the future, you'll be able to click on a QSO in the history table to pre-fill the logging form!

## Troubleshooting

### I see "Enter a callsign to see Wavelog info" but I typed a callsign
- Make sure the callsign field has at least 1 character
- Wait a moment (500ms) for the automatic lookup to complete
- Check that your internet connection is working

### The LoTW column always shows "NO" or "-"
- Your ADIF file might not have LoTW confirmation data
- LoTW confirmations are only available from Wavelog server
- Check that your LoTW uploads are current

### All timestamps show as "14/10/24 17:42" format but I want different format
- This is the default MM/DD/YYYY HH:MM format
- Contact support to customize the date format

## Example Use Case

**Scenario**: You're in a contest and see OM0AAO spotted on 20m.

1. **Spot appears** - You see "OM0AAO spotted on 20m"
2. **Click on spot** - Callsign is entered automatically
3. **System loads** - "Additional Information" shows DXCC info
4. **QSO history loads** - You see previous contacts with OM0AAO
5. **Quick check** - You see you worked them on SSB last year, LoTW confirmed
6. **Decide to call** - You know it's a new band, so you call them!

## Performance Notes

- **First lookup**: ~500ms (debounce delay) + API response time
- **Subsequent lookups**: Similar time as Wavelog/ADIF responds
- **No impact on radio control**: Lookups happen asynchronously
- **Max response time**: ~10 seconds (API timeout)

## What Data is Collected?

The feature only collects and displays:
- Callsign (your search query)
- Previous QSO dates (from your log)
- Previous QSO modes and bands
- Previous QSO RST reports
- LoTW confirmation status

**No personal data is shared** - this is all from your local log file!

## Need Help?

Check the detailed implementation documentation:
- See: `LAST_5_QSOS_IMPLEMENTATION.md` for technical details
- See: `.zencoder/rules/repo.md` for project structure
- Check logs: `logs/flex_debug.log` for error messages

---

**Enjoy tracking your QSO history!** 📊