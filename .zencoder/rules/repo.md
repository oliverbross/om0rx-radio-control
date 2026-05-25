# wave-flex-spots Repository Information

## Project Overview
**FlexRadio Web Control Application** - A modern web-based control interface for FlexRadio systems with DX cluster spot integration.

## Technology Stack
- **Frontend**: Vue.js 3 (CDN-based), vanilla JavaScript
- **Backend**: Python FastAPI with WebSocket support
- **Radio Interface**: FlexRadio SmartSDR API via `dxbridge.py`
- **DX Spots**: Integration with DX cluster for real-time spot updates

## Project Structure
```
wave-flex-spots/
├── frontend/
│   ├── app.js           # Vue.js application (809 lines)
│   └── index.html       # Main HTML interface
├── backend/
│   ├── main.py          # FastAPI server with WebSocket
│   └── __init__.py
├── documentation/       # All project documentation
├── logs/                # All log files (flex_debug.log, etc.)
├── config.py            # Configuration (DO NOT MODIFY config-original*)
├── dxbridge.py          # FlexRadio interface (DO NOT MODIFY dxbridge-original*)
├── test_backend.py      # Backend tests
└── start_webapp.ps1     # PowerShell startup script
```

## Architecture
- **WebSocket Communication**: Real-time bidirectional sync between UI and radio
- **Optimistic Updates**: Immediate UI feedback with backend confirmation
- **Debounced Commands**: 150ms delay on slider controls to prevent flooding
- **Responsive Design**: Modern, mobile-friendly interface

## Key Features
1. **Full Radio Control**: Frequency, mode, filters, power, audio levels
2. **DX Spots Integration**: Live spot updates with filtering
3. **Interactive Frequency Control**: Mouse wheel and arrow key tuning
4. **Bidirectional Sync**: All 30+ controls sync both ways (UI ↔ Radio)
5. **Real-time Updates**: S-meter, TX state, all controls

## Development Guidelines
1. **Documentation**: All `.md` files go in `/documentation/` folder
2. **Logs**: All log files go in `/logs/` folder
3. **Original Files**: Never modify `*-original-do-not-modify.*` files
4. **WebSocket Updates**: All radio state changes go through `updateRadioStatus()`
5. **Slider Debouncing**: Use 150ms debounce for all slider controls
6. **Optimistic Updates**: Update local state immediately, then send command

## CRITICAL - WSJT-X Configuration
⚠️ **NEVER CHANGE** the WSJT-X UDP multicast address - it is ALWAYS **224.0.0.1**
- WSJT-X broadcasts packets to multicast address 224.0.0.1
- This is the standard WSJT-X protocol behavior
- Environment variable: `WSJTX_UDP_MULTICAST` must ALWAYS be "224.0.0.1"
- WSJT-X UDP port: **2237** (do not change)
- Bridge WebSocket: **8091** (do not change)

## Important Files
- `frontend/app.js`: Main Vue.js application with all UI logic
- `backend/main.py`: FastAPI server with WebSocket and API endpoints
- `dxbridge.py`: FlexRadio SmartSDR interface layer
- `config.py`: Application configuration settings
- `documentation/PROJECT.md`: Detailed project documentation

## Testing
- Run backend tests: `python test_backend.py`
- Start application: `.\start_webapp.ps1`
- Access UI: http://localhost:8000

## Notes
- This is a Windows-based project (PowerShell, Win32)
- Python 3.14 is being used
- Vue.js 3 is loaded from CDN (no build process)
- Real-time communication via WebSocket on `/ws/radio`