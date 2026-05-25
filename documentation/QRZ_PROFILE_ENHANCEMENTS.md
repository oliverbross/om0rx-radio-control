# QRZ Profile Display Enhancements

## Overview
The QRZ Profile panel has been enhanced to display significantly more operator information in a compact, scrollable format that maintains equal column heights across the three-column layout (Log QSO, QRZ Profile, DXCC Status).

## Changes Made

### 1. **Image Scaling Fix** 📸
**Problem**: QRZ profile pictures were unconstrained, causing them to overflow the column and extend the entire panel height.

**Solution**:
- Changed image container from `aspect-ratio: 1` to `max-height: 150px`
- Changed image fitting from `object-fit: cover` to `object-fit: contain`
- This preserves aspect ratio while keeping the image within bounds

### 2. **Column Height Synchronization** 📐
**CSS Changes** in `logging-panel.css`:
- Changed `.logging-panel` alignment from `align-items: flex-start` to `align-items: stretch`
- All three columns now grow to the same height
- Panel is vertically centered and balanced

### 3. **Extended Data Extraction** 📊
**Backend Changes** in `qrz_api.py`:

Now extracts 26+ fields from QRZ API (previously only 6):

| Field | Description | Example |
|-------|-------------|---------|
| **name** | Full name (formatted) | STANISLAW STYBURSKI |
| **nickname** | Call sign nickname | "The Boss" |
| **country** | Country name | Poland |
| **state** | State (USA only) | California |
| **grid** | Maidenhead grid | JO90hh |
| **cqzone** | CQ Zone | 16 |
| **ituzone** | ITU Zone | 29 |
| **class** | License class | E, A, General, etc. |
| **born** | Year of birth | 1953 |
| **iota** | IOTA reference | EU-017 |
| **county** | County (USA) | Santa Clara |
| **email** | Email address | op@example.com |
| **address** | Full mailing address | 123 Main St, Anytown |
| **zip** | Postal code | 95050 |
| **eqsl** | Accepts eQSL | Y/N |
| **mqsl** | Accepts paper QSL | Y/N |
| **lotw** | Accepts LoTW | Y/N |
| **qslmgr** | QSL manager info | W5XYZ |
| **url** | Operator's web page | https://qrz.com/db/... |

### 4. **Scrollable Info Section** 🔄
**CSS Enhancement**:
```css
.qrz-info {
    max-height: 300px;
    overflow-y: auto;
    padding-right: 4px;
}
```
- Information list is now scrollable when there are many fields
- Prevents panel from becoming too tall
- Maintains visual balance with other columns

### 5. **Frontend Display** 🎨
**Updated HTML** (`index.html`):
- Added conditional rendering for fields that may be empty
- Compact format with label/value pairs
- Added QSL options display (eQSL / Paper / LoTW)
- Added zone information (CQ/ITU)
- Added license class, birth year, IOTA, county

**New Vue Computed Property** (`app.js`):
```javascript
qrzQslOptions() {
    // Returns formatted string: "eQSL / Paper / LoTW"
    // or "" if none available
}
```

## Data Available in QRZ Profile Panel

### Currently Displayed (Auto-showing fields)
```
✅ Name           (with nickname if available)
✅ Country        (always shown)
✅ Grid           (always shown)
✅ State          (conditional - only if available)
✅ Email          (conditional - only if available)
✅ CQ/ITU Zones   (conditional - if available)
✅ License Class  (conditional - if available)
✅ Born Year      (conditional - if available)
✅ IOTA           (conditional - if available)
✅ County         (conditional - if available)
✅ QSL Methods    (conditional - formatted as "eQSL / Paper / LoTW")
```

### Available but Not Currently Displayed
These fields are extracted and can be displayed by editing the HTML template:
```
• Address (addr1 + addr2)
• Postal Code (zip)
• QSL Manager (qslmgr)
• Web URL (url)
• Aliases (callsign aliases)
• Previous Callsign (p_call)
• Coordinates (lat/lon)
• DXCC Code
• Area Code (USA)
• Metro Service Area (MSA - USA)
• Time Zone
• GMT Offset
• License Effective/Expiration Date (USA)
```

## Image Display Options

### Profile Picture
- Displays operator's QRZ profile photo when available
- Max height: 150px
- Maintains aspect ratio
- Falls back to "📷 No photo" if image URL unavailable
- Handles broken image links gracefully

## Usage Example

When clicking on a DX cluster spot (e.g., "OM0RX"), the QRZ Profile panel now displays:

```
👤 QRZ Profile
[Profile Photo - max 150px]
Name              Oliver Bross
Country           Slovak Republic
State             -
Grid              JN88bq
Email             oliver@example.com
CQ/ITU            16/29
Class             A
Born              1965
IOTA              EU-001
County            -
QSL               eQSL / Paper / LoTW
```

## Column Sizing

All three columns now maintain equal visual weight:

| Column | Content | Height |
|--------|---------|--------|
| Log QSO | Form fields, buttons | Flexible to content |
| QRZ Profile | Image + scrollable info | Matches Log QSO |
| DXCC Status | Worked status table | Matches Log QSO |

## Technical Details

### Backend Changes
- File: `qrz_api.py`
- Method: `get_profile_picture()`
- Returns: Extended dictionary with 26+ fields
- Backward compatible: Only new fields added

### Frontend Changes
- Files: `index.html`, `app.js`, `logging-panel.css`
- All changes are non-breaking
- Conditional rendering ensures clean display
- Scrollable content prevents layout issues

### QRZ XML API Version
- Using: `https://xmldata.qrz.com/xml/current/`
- Specification: Version 1.34
- Fields documented in official QRZ API specification

## Configuration

No new configuration needed! All fields are automatically extracted when available from QRZ API.

**Existing Config Requirements**:
- `QRZ_USERNAME` - Your QRZ callsign/username
- `QRZ_PASSWORD` - Your QRZ password (NOT API key)

These are already in your config.py

## Future Enhancements

Possible additions if needed:
1. Show full address with postal code
2. Display coordinates with distance/bearing calculator
3. Show license effective/expiration dates
4. Add previous callsigns (aliases)
5. Display previous contacts with this operator
6. Export operator info to logging form automatically
7. QRZ website link in profile panel

## Testing

The enhanced profile display works with:
- ✅ Domestic US operators
- ✅ International operators
- ✅ Operators with/without photos
- ✅ Operators with/without zones information
- ✅ Varying data completeness

Try clicking on different DX spots to see varied profile information!

## Notes

- Some fields are USA-specific (state, county, area code, etc.) and won't appear for non-US operators
- Profile picture quality depends on QRZ operator's uploaded image
- All data comes from QRZ's callsign database
- Session keys are cached to minimize API calls
- Handles session timeouts gracefully with auto re-authentication

---

**Last Updated**: 2024  
**Version**: 2.0  
**QRZ API**: XML Data Service v1.34