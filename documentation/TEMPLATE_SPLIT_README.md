# Index.html Template Split Documentation

## Overview
The monolithic `index.html` (2131 lines) has been intelligently split into smaller, manageable template files to:
- Prevent VSCode truncation issues
- Improve maintainability
- Keep files under 500 lines
- Preserve full Vue.js functionality
- Maintain loading order and dependencies

## File Structure

### Main Files
- **index.html** (63 lines)
  - Entry point containing head, meta tags, CSS imports, script imports
  - Loads the template loader and all JavaScript modules
  - **DO NOT manually add HTML content here**

- **templates-loader.js**
  - Loads all template fragments dynamically before Vue initializes
  - Fetches templates via HTTP and injects them into `#app` container
  - Fires `'templates-loaded'` event when complete

### Template Files (in `/templates/` folder)

#### Control Interface Templates
1. **controls-row1.html** (76 lines)
   - Top row: Main buttons (RX2, MOX, TUNE, VOX, Break.In, Config)
   - Volume, Monitor, AGC-T, Drive, Tune, Mic sliders
   - UTC clock and sync status indicator

2. **controls-row2.html** (37 lines)
   - Band selection buttons (left)
   - Mode buttons (right, line 1)
   - Filter buttons (right, line 2)

3. **controls-row3.html** (172 lines)
   - **Rotor/Beaming Controls** (left) - Azimuth input, direction presets, beaming display
   - **Frequency Display** (center) - Interactive keyboard/wheel tuning, DSP buttons (NB/NR/ANF/APF)
   - **DSP Level Sliders** (center) - Conditional sliders for active DSP modes
   - **RIT/XIT Controls** (right) - RIT/XIT toggle and adjustment buttons
   - **Step/AGC Dropdowns** (right) - Tuning step and AGC mode selection
   - **WinKeyer Widget** - CW keyer interface with macro buttons

4. **controls-row4-5.html** (20 lines)
   - TX Frequency display (Row 4) - Shown when split/RX2 enabled
   - SDC Decoded CW Text Ticker (Row 5) - Displayed in CW mode only

#### Logging & QSO Panel Templates
5. **logging-panel.html** (628 lines)
   - QSO Logging Form with multiple tabs:
     - **Station Tab**: Callsign, frequency, date, time, mode, RST, operator info
     - **Awards Tab**: POTA, SOTA, WWFF, IOTA fields
     - **General Tab**: Continental/zone data, power, antenna
     - **QSL Tab**: QSL received/sent status, LoTW member, QSL manager
     - **SAT Tab**: Satellite propagation, antenna path, satellite name/mode
   - QRZ Profile Panel with photo display
   - Previous QSOs dropdown with pagination (Wavelog and Local Log tabs)
   - Log QSO, Clear, and Previous QSO buttons
   - Status message display

#### DX Spots & Information Templates
6. **dx-spots.html** (243 lines)
   - Spots container with filtering options
   - Dynamic filter controls (mode, band, awards)
   - Spots table with interactive rows
   - Spot actions (double-click to tune, hover for details)
   - Statistics display

#### Configuration Modal Templates
7. **modal-config.html** (573 lines)
   - Configuration dialog with tabbed interface:
     - Database settings (host, port, name, user, password)
     - Wavelog API configuration
     - Rotor settings and controls
     - WSJT-X UDP integration settings
     - CTY/Paths configuration
   - Feature toggles and setup instructions

8. **modal-country.html** (281 lines)
   - Additional information modal with country overlay map
   - Geographic and zone information display
   - Modal styling and interactions

#### Log & History Modals
9. **modal-local-log.html** (106 lines)
   - Local QSO log viewer modal
   - Filters for callsign, mode, band, awards
   - Paginated table display
   - CSV export functionality
   - Pagination controls

10. **modal-wavelog-log.html** (108 lines)
    - Wavelog QSO log viewer modal
    - Filters for callsign, mode, band, awards
    - Paginated table with Wavelog data
    - Refresh button
    - Last updated timestamp

11. **modal-sync.html** (96 lines)
    - Database synchronization status modal
    - Sync progress and statistics
    - ADIF file vs Database comparison
    - Last modified timestamp display

## How It Works

### Loading Process
1. Browser loads `index.html`
2. Vue.js 3 library loads from CDN
3. All CSS stylesheets load
4. **templates-loader.js** executes:
   - Fetches all template HTML files from `/templates/`
   - Injects each template into `#app` container in order
   - Fires `'templates-loaded'` event
5. Modular JavaScript files load (`js/*.js`)
6. **app-main.js** initializes Vue app

### Important Notes

⚠️ **Template Loading Order Matters**
- Templates are loaded in the order specified in `templates-loader.js`
- All Vue directives and data bindings span across template files
- The app container (#app) is a single Vue root element containing all templates

## Making Changes

### Editing Existing Templates
1. Find the relevant template file in `/templates/`
2. Edit directly - all Vue features work normally across template boundaries
3. Changes apply immediately on page refresh

### Adding New Sections
1. Create new template file in `/templates/` with descriptive name
2. Add to loading list in `templates-loader.js`
3. Ensure file is under 500 lines
4. Test in browser

### Moving Content Between Templates
⚠️ **CAUTION**: Be careful when moving Vue content:
- Keep related functionality together
- Don't break Vue directives (e.g., v-if, v-for)
- Ensure parent-child div relationships are maintained
- Test thoroughly

## File Size Summary

| File | Lines | Size |
|------|-------|------|
| index.html | 63 | - |
| controls-row1.html | 76 | 4.5 KB |
| controls-row2.html | 37 | 1.7 KB |
| controls-row3.html | 172 | 13 KB |
| controls-row4-5.html | 20 | 1.2 KB |
| logging-panel.html | 628 | 38.6 KB |
| modal-config.html | 573 | 40.7 KB |
| modal-country.html | 281 | 17.9 KB |
| modal-local-log.html | 106 | 5.8 KB |
| modal-wavelog-log.html | 108 | 6.3 KB |
| modal-sync.html | 96 | 6.6 KB |
| **Total Templates** | **2,170** | **~136 KB** |

## Troubleshooting

### Templates Not Loading
- Check browser console for fetch errors
- Verify `/templates/` directory exists
- Ensure all template files are properly formatted HTML
- Check `templates-loader.js` error logs

### Vue Not Initializing
- Ensure `templates-loader.js` loads before `js/app-main.js`
- Check that all templates finish loading (console: "✅ Template Loader: All templates loaded successfully!")
- Verify Vue.js CDN loads correctly

### Missing Functionality
- Check that Vue directives/data aren't split incorrectly
- Verify template file encoding is UTF-8
- Ensure closing tags aren't in different files

## Backup
Original file backed up to: `index.html.backup-[timestamp]`

For detailed debugging, check the browser's Network and Console tabs while loading the page.