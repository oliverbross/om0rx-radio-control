# 🚀 Quick Guide - Enhanced Wavelog Log Viewer

## 5-Minute Getting Started

### Step 1: Open the Log Viewer
```
1. Make sure your backend is running: .\start_webapp.ps1
2. Open browser: http://localhost:8000
3. Click the "📋 Log" button at the top
```

---

## Visual Layout

```
┌────────────────────────────────────────────────────────────────────┐
│  🎯 Filters  |  📋 Log    [📊 Show: 100 ▼] [🔄] [⚙️ Columns] [🗑️] │
│                                                    50 / 100 contacts │
├────────────────────────────────────────────────────────────────────┤
│ Date/Time      │ Call │ Mode │ Band │ Freq   │ Name  │ Country ... │ ← HEADERS (click edge to resize)
├────────────────────────────────────────────────────────────────────┤
│ [Filter...]    │ [..] │ [..] │ [..] │ [...]  │ [...] │ [.......]   │ ← FILTERS (type here)
├────────────────────────────────────────────────────────────────────┤
│ 11/04/25 17:38 │ EA8ED│ SSB  │ 20m  │ 14.315 │ José  │ Canary Is.. │
│ 11/04/25 17:02 │ 9U1RU│ SSB  │ 20m  │ 14.202 │ Team  │ Burundi     │
│ 11/04/25 16:17 │ 9U1RU│ SSB  │ 20m  │ 14.202 │ Team  │ Burundi     │
│ ...                                                                 │
│                         [Scroll here ↓]                             │
└────────────────────────────────────────────────────────────────────┘
     [Scroll here →]
```

---

## 🎯 Feature Locations

### Header Buttons (Top Row):
```
[📊 Show: 100 ▼]  ← Click to select 50/100/250/500 contacts
[🔄 Refresh]      ← Click to reload from database
[⚙️ Columns]      ← Click to show/hide columns
[🗑️ Clear Filters]← Click to reset all filters (only shows when active)
```

### Contact Count (Top Right):
```
100 contacts           ← No filters active (showing all)
50 / 100 contacts      ← 50 match filters out of 100 total
```

---

## ⚡ Quick Actions

### 1️⃣ Resize a Column
```
1. Hover mouse over right edge of any column header
2. Cursor changes to: ↔
3. Click and drag left or right
4. Release mouse button
5. ✅ Width is saved automatically!
```

**Visual Feedback**:
- Hover: Edge turns **blue**
- Dragging: Edge turns **green**

---

### 2️⃣ Filter Contacts
```
1. Look at the row below column headers (has input boxes)
2. Click in any input box
3. Type your search term (case doesn't matter)
4. ✅ Table updates instantly!
```

**Examples**:
```
Callsign box:  Type "EA"     → Shows EA1, EA2, EA8...
Mode box:      Type "SSB"    → Shows only SSB contacts
Band box:      Type "20"     → Shows only 20m contacts
Country box:   Type "spain"  → Shows Spanish contacts
```

**Multiple Filters**:
```
Callsign: "EA"  +  Band: "20m"  = All EA stations on 20m
Mode: "FT8"     +  DXCC: "404"  = All FT8 contacts with Burundi
```

---

### 3️⃣ Show/Hide Columns
```
1. Click "⚙️ Columns" button
2. Modal opens with checkboxes
3. ✅ Check = Show column
4. ❌ Uncheck = Hide column
5. Click "Done"
```

**Quick Actions in Modal**:
```
[Show All]  ← Enable all 23 columns
[Hide All]  ← Disable all columns  
[Reset]     ← Restore defaults (16 visible)
[Done]      ← Close modal
```

**Default Visible Columns** (16):
- Date/Time, Callsign, Mode, RST(S), RST(R), Band, Frequency
- Name, QTH, Gridsquare, Country, CQ, ITU, DXCC, LoTW, QSL

**Default Hidden Columns** (7):
- State, IOTA, POTA, SOTA, WWFF, eQSL, Comment

---

### 4️⃣ Scroll the Table
```
VERTICAL (up/down):
- Mouse wheel
- Right scrollbar
- Arrow keys (when focused on table)

HORIZONTAL (left/right):
- Shift + Mouse wheel
- Bottom scrollbar
- Drag scrollbar handle
```

**Pro Tip**: Column headers stay visible when scrolling vertically!

---

## 🎨 Visual Indicators

### Row Colors:
```
🟢 Green background  = LoTW confirmed
🔵 Blue background   = QSL card confirmed
⬜ No color          = Not confirmed
```

### QSL Status Icons:
```
✅ = Confirmed (Y)
❌ = No (N)
📬 = Requested (R)
📤 = Queued (Q)
⏳ = In Progress (I)
-  = Not set
```

### Column Text Colors:
```
🟢 Green    = Callsign (bold)
🔵 Blue     = Frequency
🟡 Yellow   = POTA/SOTA/WWFF references
⚪ Gray     = Name, QTH, Country, Comment
```

---

## 💾 Your Settings Are Saved!

### Automatically Saved:
- ✅ Column widths (when you resize)
- ✅ Column visibility (show/hide settings)

### Where Saved:
- Browser localStorage
- Key: `wavelog-log-columns`

### Persists Across:
- ✅ Page refreshes
- ✅ Browser restarts
- ✅ Computer restarts

### Reset Settings:
```
Option 1: Click ⚙️ Columns → Reset button
Option 2: Clear browser localStorage (F12 → Application → Storage)
```

---

## 🔥 Try These Now!

### Test 1: Scrolling
1. Switch to Log view (📋 Log button)
2. Scroll down with mouse wheel → See older contacts
3. Scroll right with Shift+wheel → See more columns
4. Notice header stays at top ✅

### Test 2: Resizing
1. Hover over edge between "Callsign" and "Mode" headers
2. Drag "Callsign" wider (e.g., 150px)
3. Refresh page (F5)
4. Width is remembered ✅

### Test 3: Filtering
1. Type "SSB" in Mode filter box
2. See only SSB contacts
3. Add "20m" in Band filter box
4. See only 20m SSB contacts ✅
5. Click 🗑️ Clear Filters

### Test 4: Column Config
1. Click ⚙️ Columns button
2. Uncheck "Comment" and "eQSL"
3. Check "POTA" and "SOTA"
4. Click Done
5. Table updates instantly ✅

---

## 🐛 Troubleshooting

### Can't see resize cursor?
- Hover exactly on the **right edge** of column header
- Try hovering slowly left-to-right near the border

### Filters not working?
- Make sure you're typing in the filter row (2nd row, below headers)
- Check spelling (though it's case-insensitive)
- Click 🗑️ Clear Filters and try again

### Columns too narrow?
- Drag them wider!
- Or click ⚙️ Columns → Reset

### Can't scroll horizontally?
- Try Shift + Mouse Wheel
- Or drag the bottom scrollbar
- Make sure some columns are visible

### Lost my settings?
- Click ⚙️ Columns → Reset to restore defaults
- Or close and reopen browser (settings reload from localStorage)

---

## 🎓 Pro Tips

### Tip 1: Hide Unused Columns
If you never use QSL cards:
```
⚙️ Columns → Uncheck "QSL" and "eQSL" → Done
```
Result: More space for useful data!

### Tip 2: POTA/SOTA Activators
If you do park/summit activations:
```
⚙️ Columns → Check "POTA", "SOTA", "WWFF" → Done
```
Result: See your activation references!

### Tip 3: Find Specific Contact
```
Callsign filter: Type partial call (e.g., "W1")
Band filter: Type band (e.g., "40m")
Mode filter: Type mode (e.g., "CW")
```
Result: Instant search without database load!

### Tip 4: Explore New DXCC
```
Country filter: Type country name (e.g., "Burundi")
```
Result: See all contacts with that country!

### Tip 5: Review Recent Confirmations
```
Look for 🟢 green rows (LoTW confirmed)
Look for 🔵 blue rows (QSL confirmed)
```
Result: Quick visual scan of confirmations!

---

## 📊 Example Workflows

### Workflow 1: "Find all FT8 on 20m"
```
1. Click 📋 Log
2. Mode filter: Type "FT8"
3. Band filter: Type "20m"
4. Result: Shows only those contacts
5. Counter shows: X / 100 contacts
```

### Workflow 2: "Customize for contesting"
```
1. ⚙️ Columns → Show only: Date, Call, Mode, RST(S), RST(R), Band
2. Hide: Name, QTH, Country, etc.
3. Resize columns for compact view
4. Result: Contest-style log display
```

### Workflow 3: "Review POTA activations"
```
1. ⚙️ Columns → Check "POTA", "SOTA", "WWFF"
2. POTA filter: Type "K-"
3. Result: All parks matching K- prefix
4. Scroll through to review
```

### Workflow 4: "Check LoTW confirmations"
```
1. Scroll down to see 🟢 green rows
2. Or enable only: Date, Call, Mode, Band, LoTW columns
3. Result: Focus on LoTW status
```

---

## 🎉 That's It!

You're now ready to:
- ✅ Scroll anywhere in the table
- ✅ Resize columns to your preference
- ✅ Show/hide columns as needed
- ✅ Filter data instantly
- ✅ Have settings remembered

**Your 41,795 QSOs are waiting to be explored! 📻✨**

---

## 📚 Full Documentation

For complete details, see:
`documentation/WAVELOG_LOG_VIEWER_ENHANCED.md`

**Happy Logging! 73!**