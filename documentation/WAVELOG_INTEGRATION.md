# Wavelog QSO Logging Integration

## Overview
Complete integration of Wavelog QSO logging with QRZ profile display and DXCC status matrix in the FlexRadio web interface.

## Features Implemented

### 1. Three-Column Logging Panel
- **Logging Form Column**: QSO entry with auto-population from DX spots
- **QRZ Profile Column**: Operator photo, recent QSOs, and contact info
- **DXCC Status Column**: Band/mode matrix showing worked/confirmed status

### 2. Automatic Population
When entering a callsign:
- Auto-fills from matching DX spot (frequency, mode, comments)
- Loads QRZ profile picture and recent contact history
- Retrieves DXCC status matrix from Wavelog

### 3. QSO Submission Flow
1. User fills logging form or clicks a DX spot
2. Form auto-populates from spot data
3. User clicks "Log QSO" button
4. QSO submitted to Wavelog API
5. Local ADIF file created as backup
6. Form cleared for next QSO

### 4. Local ADIF Backup
- Every QSO creates a local ADIF record
- File stored at: `logs/qso_log.adif`
- ADIF v3.1.0 format compatible
- Acts as fallback if Wavelog API fails

## Backend Implementation

### New API Modules

#### `wavelog_api.py`
- WavelogClient class for Wavelog API operations
- Methods:
  - `log_qso(qso_data)` - Submit QSO to Wavelog
  - `get_dxcc_status(callsign)` - Retrieve DXCC matrix
  - `get_recent_qsos(callsign)` - Get contact history

#### `qrz_api.py`
- QRZClient class for QRZ Logbook API
- Methods:
  - `get_profile_picture(callsign)` - Fetch operator photo & info
  - `get_contact_history(callsign)` - Get recent QSOs
  - Session-based authentication with QRZ

#### `adif_handler.py`
- ADIFHandler class for local ADIF file operations
- Methods:
  - `add_qso(qso_dict)` - Append QSO to ADIF file
  - `read_qso_count()` - Get total QSOs logged locally
- Handles ADIF v3.1.0 format automatically

### Backend API Endpoints

#### QSO Logging
- **POST** `/api/qso/log` - Submit QSO to Wavelog + save ADIF

#### QRZ Integration
- **GET** `/api/qrz/profile/{callsign}` - Get profile picture & info
- **GET** `/api/qrz/history/{callsign}?limit=N` - Get recent QSOs

#### Wavelog Integration
- **GET** `/api/wavelog/dxcc/{callsign}` - Get DXCC status matrix

#### ADIF Management
- **GET** `/api/adif/count` - Get number of logged QSOs

## Frontend Implementation

### HTML Components
- Three-column logging panel (responsive grid)
- QSO form with special references (POTA/SOTA/IOTA/WWFF)
- QRZ profile display with photo and history
- DXCC status matrix with color coding

### Vue.js Methods
- `autoPopulateForm()` - Fill form from spot click or callsign entry
- `loadQRZProfile()` - Fetch QRZ data
- `loadDXCCStatus()` - Fetch DXCC matrix
- `submitQSO()` - Submit to backend
- `clearLoggingForm()` - Reset form for next QSO
- `formatDate()` - Helper for date formatting

### Styling
- Separate `logging-panel.css` file
- 3-column responsive grid layout
- Color-coded DXCC matrix (Green=Confirmed, Orange=Worked, Red=Needed, Gray=Not worked)
- Loading spinners and status messages

## Configuration

### Config File Settings
```python
# Wavelog
WAVELOG_API_URL = "https://om0rx.wavelog.online/index.php"
WAVELOG_API_KEY = "<wavelog_api_key>"
WAVELOG_STATION_ID = "1"

# QRZ
QRZ_USERNAME = "<qrz_username>"
QRZ_PASSWORD = "<qrz_password>"

# Local ADIF
ADIF_LOG_PATH = "C:\\Projects\\om0rx-radio-control\\logs\\qso_log.adif"
```

### Config Modal Integration
- "Logging" tab contains all integration settings
- Sections:
  - System Logging Level
  - Wavelog API credentials and URL
  - QRZ account credentials
  - Local ADIF file path

## Data Flow

### On Spot Click / Callsign Entry
```
User enters callsign
  ↓
Check DX spots cache for frequency/mode
  ↓
Auto-fill form fields
  ↓
Fetch QRZ profile (async)
  ↓
Fetch DXCC status (async)
  ↓
Display QRZ photo and DXCC matrix
```

### On QSO Submission
```
User clicks "Log QSO"
  ↓
Validate callsign and frequency
  ↓
POST to /api/qso/log
  ↓
Backend sends to Wavelog API (parallel)
  ↓
Backend appends to local ADIF file
  ↓
Return success/error status
  ↓
Clear form if successful
```

## Error Handling

- If Wavelog API fails: Local ADIF file still created
- If QRZ unavailable: Shows placeholder message
- If DXCC lookup fails: Shows empty matrix
- Status messages with auto-clear (5 seconds)

## File Locations

### Backend
- `wavelog_api.py` - Wavelog API client
- `qrz_api.py` - QRZ API client
- `adif_handler.py` - ADIF file handler

### Frontend
- `frontend/logging-panel.css` - Styling
- `frontend/index.html` - HTML structure (lines 1398-1574)
- `frontend/app.js` - Vue.js methods (lines 1141-1335)

### Config
- `config.py` - Credentials and paths

### Data
- `logs/qso_log.adif` - Local QSO archive

## Dependencies

- `aiohttp` - Async HTTP client for APIs
- `fastapi` - Already present
- Vue.js 3 - Already present

## Usage

1. **Configure Integration**
   - Open Settings (⚙️ button)
   - Go to "Logging" tab
   - Enter Wavelog and QRZ credentials
   - Save configuration

2. **Log a QSO**
   - Enter or copy callsign from DX spot
   - Form auto-fills from spot
   - QRZ profile loads automatically
   - DXCC status displays
   - Click "Log QSO" to submit
   - Form clears for next entry

3. **View Local Archive**
   - Check `logs/qso_log.adif` file
   - Compatible with ADIF readers
   - Can import into other logging software

## Future Enhancements

- Export ADIF file to user
- Bulk import from ADIF
- Direct spot-to-log workflow
- Band-mode statistics
- LoTW synchronization
- eQSL integration