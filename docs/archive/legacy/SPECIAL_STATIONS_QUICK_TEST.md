# Quick Testing Guide - Special Stations Fix

## What Was Fixed
✅ **WWFF is now properly detected and displayed**  
✅ **Multiple special activities show as separate badges**  
✅ **New configuration tab allows managing special stations**  
✅ **All 8 special types now fully supported**

## Quick Test (2 minutes)

### Test 1: View Special Badges
1. Look at the DX Spots table
2. Find a spot with special activity in the comment
3. Look at the "Special" column
4. **Expected:** See colored badges (not just plain text)
   - POTA spots show brown "POTA" badge
   - WWFF spots show cyan "WWFF" badge
   - Other types have distinct colors

### Test 2: Multiple Specials
1. Find or wait for a spot with both POTA and WWFF in comment
   - Example comment: "POTA K-1234 WWFF CHFF-1234"
2. **Expected:** See both "POTA" and "WWFF" as separate badges
   - Not merged as single text
   - Each with its own color

### Test 3: Configuration Tab
1. Click ⚙️ **Config** button (top right)
2. Look for new **"Special Stations"** tab
3. You should see:
   - 📍 Active Special Stations section (with colored badges)
   - ➕ Available Special Stations section (with + buttons)
4. Try clicking a "+" button
   - **Expected:** Special moves to Active section
5. Try clicking the "×" on an Active special
   - **Expected:** Special moves back to Available section

### Test 4: Filter by WWFF
1. Close config dialog
2. Find the **Specials** filter in spots panel
3. Click the Specials dropdown (triangle ▼)
4. Check the box for **"WWFF"**
5. Click **All** or **Clear** buttons
6. **Expected:** Table updates to show only WWFF spots
   - Spots with POTA but no WWFF disappear
   - Spots with WWFF stay visible

### Test 5: Multiple Filter Selection
1. Keep Specials dropdown open
2. Check **"POTA"** AND **"WWFF"**
3. **Expected:** Spots with EITHER activity appear
   - POTA-only spots visible
   - WWFF-only spots visible
   - Mixed POTA+WWFF spots visible

## If Something Looks Wrong

### Issue: WWFF still not showing
- **Check:** Is there a WWFF pattern in a comment?
  - Valid formats: "CHFF-1234", "FRFF-5678", "WFF"
- **Fix:** Refresh the browser (F5 or Ctrl+R)
- **Check:** Backend was restarted after changes

### Issue: Badges not colored
- **Check:** CSS file was properly updated
- **Fix:** Clear browser cache (Ctrl+Shift+Delete)
- **Test:** Open DevTools (F12) → Elements → inspect badge
  - Should see classes like `special-pota`, `special-wwff`, etc.

### Issue: Configuration tab not visible
- **Check:** app-main.js was properly edited
- **Fix:** Refresh browser (F5)
- **Check:** Browser console (F12) for JavaScript errors

### Issue: Multiple specials showing as comma-separated text
- **Check:** Spot was indexed before code changes
- **Fix:** Restart backend to reprocess spots
- **Verify:** New spots from cluster show proper badges

## Example Test Comments

Copy these into a test comment to verify detection:

```
Plain POTA: "K-1234"
Plain WWFF: "CHFF-1234"
Plain SOTA: "W6/CS-001"
Plain IOTA: "EU-001"

Mixed: "POTA K-1234 WWFF CHFF-1234 IOTA EU-001"
Multiple: "K-0123 + CHFF-0456"
Verbose: "POTA activation from K-0001 World Wide Flora Fauna CHFF-0002"
```

## Performance Notes

- Special extraction happens server-side (one time per spot)
- Display is optimized with CSS classes (no JavaScript processing)
- Filter uses exact string matching (very fast)
- Multiple specials don't slow down the application

## Support Information

If you need to:

1. **Add a new special activity:**
   - Edit `config.py` → `SPECIAL_PATTERNS` dict
   - Add pattern regex
   - Add to `SPECIAL_PRESET` list
   - Add CSS class in `main-styles.css`
   - Restart backend

2. **Customize badge colors:**
   - Edit `frontend/main-styles.css`
   - Find `.special-{type}` classes
   - Modify `background` and `color` properties

3. **Change filter behavior:**
   - Edit `frontend/js/dx-spots.js`
   - Look for special filter logic
   - Modify comparison conditions

---

**Last Updated:** After WWFF/Multiple Specials Fix  
**Status:** ✅ Complete and Ready for Testing  
**Files Modified:** 6 files (backend + frontend)