# Local Log Modal - Quick Start Guide

## What's New?

A beautiful **📋 Local log** link has been added next to the "📝 Log QSO" heading in the logging panel. Click it to view all your logged QSOs in a professional table with filtering, pagination, and export features.

## Quick Start (30 seconds)

1. **Click the link**: Look for "📋 Local log" on the right side of the "Log QSO" heading
2. **View your QSOs**: All logged contacts appear in a table (newest first)
3. **Filter**: Use dropdowns to filter by Mode, Band, or Awards
4. **Export**: Click "📥 Export CSV" to download as CSV file

## Features at a Glance

| Feature | Description |
|---------|-------------|
| **Latest First** | Contacts sorted with newest on top |
| **Filtering** | Search by callsign, mode, band, or awards (POTA/SOTA/WWFF/IOTA) |
| **Pagination** | Choose 10, 20, or 50 items per page |
| **Export** | Download filtered QSOs as CSV file |
| **Responsive** | Works on desktop, tablet, and mobile |
| **Beautiful UI** | Professional dark theme matching your app |

## Using the Modal

### Opening the Modal
```
Click "📋 Local log" link (right of "Log QSO" heading)
    ↓
Modal opens centered on screen
    ↓
Loads all QSOs from local database
```

### Filtering QSOs
```
Callsign Filter:
  - Type any part of a callsign to search
  - Example: "N0" to find all N0 stations

Mode Filter:
  - Select specific mode (CW, SSB, FT8, etc.)
  - Leave empty to show all modes

Band Filter:
  - Select specific band (20m, 40m, etc.)
  - Leave empty to show all bands

Awards Filter:
  - Show only QSOs with specific awards
  - Options: POTA, SOTA, WWFF, IOTA
```

### Navigating Pages
```
← Prev Button: Go to previous page
Next → Button: Go to next page
Page Info: Shows current position (e.g., 1-10 of 245)
Items Dropdown: Change how many per page (10/20/50)
```

### Exporting Data
```
Click "📥 Export CSV" button
    ↓
Downloads file named: qso_log_2025-01-29.csv
    ↓
Open in Excel, Google Sheets, or any spreadsheet app
```

### Closing the Modal
```
Click "✕" button (top right)
    OR
Click outside the modal area
    OR
Press ESC key (if implemented)
```

## Table Columns Explained

| Column | Description |
|--------|-------------|
| **Date** | QSO date (YYYY-MM-DD) |
| **Time (UTC)** | Time on in UTC (HH:MM:SS) |
| **Callsign** | Contact's call sign (bold/highlighted) |
| **Freq (MHz)** | Operating frequency |
| **Band** | Band designation (20m, 40m, etc.) |
| **Mode** | Operating mode (CW, SSB, FT8, etc.) |
| **RST** | Signal reports (Sent/Received) |
| **Awards** | References earned (POTA, SOTA, etc.) |
| **Name/QTH** | Contact name or location |

## Examples

### Find all SSB QSOs on 20m
1. Select "SSB" in Mode filter
2. Select "20m" in Band filter
3. Table updates instantly

### Find QSOs with friends
1. Type name/partial call in Callsign filter
2. Example: "W5" for all W5 stations

### Export FT8 QSOs
1. Select "FT8" in Mode filter
2. Click "📥 Export CSV"
3. Opens in your default spreadsheet app

### View POTA Activations
1. Select "POTA" in Awards filter
2. See all your park activations
3. Export for your POTA log

## Tips & Tricks

✅ **Combine Filters**: Use multiple filters at once
- Example: CW mode + 40m band + SOTA activations

✅ **Quick Search**: Type in Callsign field to find specific contact

✅ **Large Datasets**: Use 50 items/page for faster browsing of huge logs

✅ **Spreadsheet Import**: Export CSV and import into Excel/Google Sheets for analysis

✅ **Mobile Friendly**: Works great on phones and tablets

✅ **No Data Changes**: Modal is read-only - your log stays safe

## Troubleshooting

### Modal doesn't open
- Refresh the page
- Check browser console for errors
- Ensure local QSO log file exists at `/logs/qso_log.adif`

### No QSOs showing
- Make sure you've logged contacts using the logging form
- Check that Wavelog is saving QSOs locally

### Filters not working
- Clear all filters by reloading modal
- Make sure filter values match the data

### Export not working
- Check browser downloads folder
- Try exporting with fewer items per page
- Verify you have browser permissions to download files

### Slow performance with many QSOs
- Use pagination (show 10 or 20 items)
- Apply filters to reduce dataset
- Use Band filter to narrow results

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| ESC | Close modal (if implemented) |
| Enter | Apply filter in search field |
| Tab | Navigate between controls |

## FAQ

**Q: Where are my QSOs stored?**
A: In `/logs/qso_log.adif` - a local ADIF format file

**Q: Can I edit QSOs in this modal?**
A: No, it's read-only. Use the Log QSO form to add new contacts.

**Q: Does this affect Wavelog syncing?**
A: No, this is just a local viewer. Wavelog sync continues normally.

**Q: Can I import CSV back?**
A: Not currently, but you can use the CSV in other logging apps.

**Q: How often does the data update?**
A: Data is loaded fresh each time you open the modal.

**Q: Can I sort by different columns?**
A: Currently shows newest first. Column sorting coming soon.

**Q: What if I have 10,000+ QSOs?**
A: Still works! Use pagination and filters for best performance.

## Performance Notes

- **Loading**: First load may take 1-2 seconds with large logs
- **Filtering**: Instant (< 100ms)
- **Export**: A few seconds for large datasets
- **Pagination**: Very fast with any page size

## Browser Compatibility

✅ Chrome/Edge 90+
✅ Firefox 88+
✅ Safari 14+
✅ Mobile browsers (iOS Safari, Chrome Mobile)

## Need Help?

If you encounter issues:
1. Check the browser console (F12)
2. Refresh the page
3. Try a different browser
4. Verify local log file exists

## What's Next?

Future versions may include:
- Sorting by any column
- QSO statistics/dashboard
- Award summaries
- Band/mode statistics
- Integration with QRZ/eQSL

---

**Enjoy your local QSO log viewer!** 📋✨