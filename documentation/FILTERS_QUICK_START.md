# Spots Database - Multi-Select Filters Quick Start

## 🎯 What Changed

The filters on `spots-database.html` are now **much more powerful** and user-friendly!

### Before ❌
- Could only select **ONE** band at a time
- Single-select dropdowns limited your options
- Had to apply filters multiple times to check different combinations

### After ✅
- Select **MULTIPLE** bands, modes, and countries **at once**
- "Show Worked Only" filter to see only contacts you've already made
- Better visual feedback (blue highlight when filters active)
- Dropdown indicators show you what's selected

---

## 📋 Filter Options Explained

### 1. **Band Filter** (Multi-select)
Click the "Band" button to open dropdown with checkboxes:
- ☐ 160
- ☐ 80
- ☐ 60
- ☐ 40
- ☐ 30
- ☐ 20
- ☐ 17
- ☐ 15
- ☐ 12
- ☐ 10
- ☐ 6
- ☐ 4
- ☐ 2

**Example**: Check "40", "20", "10" → Click Apply → See spots on all three bands

### 2. **Mode Filter** (Multi-select)
Click the "Mode" button to select one or more modes:
- SSB, CW, AM, FM, RTTY, FT8, FT4, PSK31, WSPR, etc.

**Example**: Check "SSB" and "CW" → See only phone and CW spots

### 3. **Country Filter** (Multi-select)
Click the "Country" button to select one or more countries:
- Over 300 countries available!

**Example**: Check "United States", "Canada", "Mexico" → See spots from North America

### 4. **Status Filter** ✅ NEW!
Checkbox: "Show Worked Only"
- When checked: Shows ONLY spots for callsigns in your ADIF log
- Perfect for finding repeat contacts or validation

**Example**: Check "Show Worked Only" + Band "20m" → See worked contacts on 20m

### 5. **Callsign Filter** (Text search)
Search box to find specific callsigns:
- Type "W5" → Shows all spots starting with W5
- Type "DL" → Shows all German callsigns
- Case-insensitive

### 6. **Spotter Filter** (Text search)
Search box to find spots posted by specific stations:
- Type "N0ARK" → Shows spots from that spotter

### 7. **Frequency Range** (Numeric)
Filter by frequency range in kHz:
- Min field: 14000 (bottom of 20m)
- Max field: 14350 (top of 20m)
- Leave blank to ignore

---

## 🎮 How to Use

### Quick Filter Examples

#### 📍 **Find worked SSB contacts on 20m**
1. Click "Band" → Check "20"
2. Click "Mode" → Check "SSB"
3. Check "Show Worked Only"
4. Click "✓ Apply"

#### 🌍 **See DX opportunities in Africa**
1. Click "Country" → Check "Egypt", "South Africa", "Kenya"
2. Click "✓ Apply"

#### 🔄 **Hear from your favorite spotter**
1. Type "N0ARK" in Spotter field
2. Check "Show Worked Only" (optional)
3. Click "✓ Apply"

#### 📡 **Check all your worked contacts**
1. Check "Show Worked Only"
2. Click "✓ Apply"

#### 🎯 **Multi-band SSB/CW activity**
1. Click "Band" → Check "40", "20", "10"
2. Click "Mode" → Check "SSB", "CW"
3. Click "✓ Apply"

### Pro Tips 💡

- **Quick Close**: Click outside the dropdown to close it
- **Visual Feedback**: Blue button = filters active
- **Count Badge**: "3 selected" shows how many items checked
- **Reset Everything**: Click "Clear" button to remove all filters
- **Auto-Update**: Charts update to match your filtered spots

---

## 🎨 Visual Indicators

| State | Appearance | Meaning |
|-------|-----------|---------|
| No filters | Gray button "All Bands" | No selections active |
| 1 selected | Blue button "SSB" | One item checked |
| 2+ selected | Blue button "3 selected" | Multiple items checked |
| Dropdown open | Button shows ▲ | Click items to check/uncheck |

---

## 🔄 Filter Combinations

All filters work **together**:
- Band AND Mode AND Country AND Callsign AND Spotter AND Frequency AND Worked Status

**Example**: "20m SSB from USA and Canada where I have a worked contact and the spotter is N0ARK"
1. Band: "20"
2. Mode: "SSB"
3. Country: "United States", "Canada"
4. Worked Only: ☑ checked
5. Spotter: "N0ARK"
6. Click Apply

---

## 📊 What Updates After Filtering

Once you click "Apply":
- ✅ Spots table shows only matching results
- ✅ Statistics update to show filtered count
- ✅ All 6 charts update with filtered data:
  - Spots by Band
  - Spots by Mode
  - Spots by Country
  - Timeline (hourly activity)
  - Top Spotters
  - Frequency distribution

---

## ⚙️ Technical Details

### Multi-Select Works Like This
```
Filter Type          | Can Select | Examples
-------------------|------------|----------
Band                | Multiple   | 40m, 20m, 10m at once
Mode                | Multiple   | SSB, CW, FT8 together
Country             | Multiple   | USA, Canada, Mexico
Callsign Search     | Single     | Text search (any match)
Spotter Search      | Single     | Text search (any match)
Frequency Range     | Min+Max    | 14000-14350 kHz
Worked Only         | Yes/No     | Toggle checkbox
```

### Performance Notes
- Filter updates are **instant**
- Filters are applied **client-side** (no server calls)
- Works offline after data is loaded
- Auto-refresh respects your filter selections

---

## 🐛 Troubleshooting

**Q: I selected filters but nothing changed**
- A: Click the "✓ Apply" button to apply your selections

**Q: How do I clear all filters?**
- A: Click the "Clear" button - resets everything

**Q: Can I search for multiple callsigns?**
- A: Use Country or other multi-select filters. Callsign search is text-based (substring match)

**Q: The dropdown closed, did I lose my selection?**
- A: No! Selections persist until you click Apply or Clear

**Q: Why is "Show Worked Only" empty?**
- A: Make sure your ADIF log file is loaded at `/logs/qso_log.adif`

---

## 🎓 Learning Path

1. **Start Simple**: Try filtering by single band
2. **Add Complexity**: Add a Mode filter too
3. **Use Worked Only**: See your worked contacts
4. **Combine All**: Mix multiple filters together
5. **Explore**: Find the DX patterns that interest you

Happy DX Spotting! 📻✨