# 🎯 Spots Database Viewer - Quick Start Guide

## What's New? 🎉

### 1️⃣ **Bigger, Bolder Table Text**
- Table font size increased from **11px → 14px**
- Font weight increased (**bold**)
- Result: Much easier to read and scan data at a glance!

```
BEFORE: Small hard-to-read text
AFTER:  Large, clear, readable text
```

---

### 2️⃣ **Smart Filter Preservation During Auto-Refresh**
When auto-refresh is **enabled**, your filters now **STAY APPLIED**!

**Example:**
1. Set Band filter to "20M"
2. Toggle auto-refresh ON ✓
3. Spots update every 10 seconds
4. **20M filter STAYS APPLIED** ← (was getting cleared before)

---

### 3️⃣ **Collapsible Sections** 
Collapse sections you don't need to focus on what matters!

#### 📈 **Visualizations** (Expandable)
- Click arrow ▼ to collapse all charts
- Perfect when you just want to see the table

#### 📡 **API Endpoints** (Collapsed by Default)
- Expand with arrow ▶ to see available endpoints
- Reference docs for developers

#### 📋 **All Spots** (Expandable)
- Click arrow ▼ to collapse the data table
- More focus on charts if needed

**Animation:** Smooth 0.3 second transitions for elegant UX

---

### 4️⃣ **Worked Spots Highlighting** 🟢
**Instantly see which spotted stations you've already worked!**

**Visual Indicator:**
- 🟢 **Green highlighted rows** = Already worked
- Brighter green text color for clarity
- Hover effect darkens the green

**How It Works:**
1. Page loads and reads your QSO log (`/logs/qso_log.adif`)
2. All callsigns from your log are identified
3. When spots appear in table, matching callsigns are highlighted
4. Updates in real-time as new spots arrive

**Example:**
```
| Time    | Band | Frequency | Callsign   | Mode | Country      |
|---------|------|-----------|------------|------|--------------|
| 15:23   | 20M  | 14.245    | VE3KZE     | CW   | ON, CANADA   | ← GREEN (worked)
| 15:24   | 15M  | 21.091    | C5R        | FT8  | THE GAMBIA   | ← GREEN (worked)
| 15:25   | 40M  | 7.025     | K4OZJ      | SSB  | GA, USA      | ← NORMAL (not worked)
```

---

## 🎮 How to Use

### Enable Auto-Refresh with Filters
1. Set your filters (Band, Mode, Country, etc.)
2. Click "✓ Apply"
3. Toggle **Auto-Refresh** switch ON
4. Data updates every 10 seconds **while keeping your filters!**

### Collapse/Expand Sections
- Look for **▼** or **▶** arrow in section headers
- **Click the arrow** to toggle
- Works smoothly with animation

### Find Worked Spots
- Look for **green highlighted rows** in the table
- These are callsigns from your QSO log
- Perfect for avoiding dupes!

### Search Table
- Use built-in search box (says "Filter table:")
- Works with live filtering
- Search within your filtered results

---

## 🎨 Visual Design

### Worked Spots Colors
| State | Background | Text Color | Description |
|-------|-----------|-----------|-------------|
| Not Worked | Dark gray | Light gray | Normal spots |
| Worked | Light green | Bright green | Already in your log |
| Hover (Worked) | Dark green | Bright green | Enhanced visibility |

### Collapse Arrow States
- **▼** = Section is expanded (click to collapse)
- **▶** = Section is collapsed (click to expand)
- Purple color (#667eea) matches the app theme

---

## 📊 Table Features

### Columns Shown
1. **Time** - UTC time of spot (purple text)
2. **Band** - Radio band (orange, bold)
3. **Frequency** - In kHz (monospace gray)
4. **Callsign** - Station being spotted (blue, bold)
5. **Mode** - FT8, SSB, CW, etc. (green)
6. **Country** - Purple text for distinction
7. **CQ Zone** - Amateur radio zone
8. **Spotter** - Who reported the spot
9. **Comment** - Notes about the spot
10. **Special Tags** - POTA, SOTA, IOTA, etc.

### Table Controls
- **Pagination:** 50 spots per page
- **Sorting:** Click column headers
- **Search:** Filter table in real-time
- **Responsive:** Auto-scrolls on small screens

---

## ⚙️ Settings & Configuration

### Auto-Refresh Interval
- **Interval:** 10 seconds
- **Controlled by:** Auto-Refresh toggle

### Filter Persistence
- **Saved when:** You click "✓ Apply"
- **Restored on:** Every auto-refresh cycle
- **Cleared by:** Clicking "Clear" button

### Worked Callsigns Source
- **File:** `/logs/qso_log.adif`
- **Format:** ADIF 3.1.0 standard
- **Loaded:** On page load
- **Updated:** When new QSOs added to log

---

## 🔄 Data Flow

```
1. Load ADIF log file (get worked callsigns)
   ↓
2. Fetch spots from API (up to 5000)
   ↓
3. Apply user's current filters
   ↓
4. Check each spot against worked callsigns
   ↓
5. Highlight matching rows in green
   ↓
6. Display charts and table
   ↓
7. Auto-refresh triggers → repeat steps 2-6
```

---

## 💡 Pro Tips

1. **Fast Filtering:** Set filters, click Apply, enable auto-refresh
2. **Avoid Dupes:** Use green highlighting to skip worked stations
3. **Reduce Clutter:** Collapse unused sections (charts/API docs)
4. **Table Search:** Use the search box for quick lookup
5. **Large Fonts:** Easier to read at a glance while radio operating
6. **Charts Overview:** Charts update instantly with your filters

---

## 🐛 Troubleshooting

### Worked Spots Not Showing
- Check that `/logs/qso_log.adif` file exists
- Verify browser console for errors (F12 → Console)
- ADIF file must have valid CALL fields

### Filters Resetting
- Make sure to click "✓ Apply" button
- Filter state preserved during auto-refresh (new feature!)
- If stuck, click "Clear" and start over

### Auto-Refresh Not Working
- Check network connection
- Verify backend API is running
- Look for console errors (F12 → Console)

---

## 📞 Support

For issues or suggestions:
1. Check browser console for error messages (F12)
2. Verify backend is running: `python backend/main.py`
3. Check spots API endpoint: `/api/spots/recent?limit=10`
4. Verify ADIF file exists: `logs/qso_log.adif`

---

## 🎓 What Changed Under the Hood

| Feature | Before | After |
|---------|--------|-------|
| Table Font | 11px | 14px, bold |
| Filter Persistence | Lost on refresh | Preserved ✓ |
| Sections | All expanded | Collapsible |
| Worked Spots | No indication | Green highlight |
| Refresh Behavior | Resets all | Maintains state |

---

Enjoy your enhanced Spots Database Viewer! 🚀📡