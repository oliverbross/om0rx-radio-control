# Configuration System Architecture

## Complete Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         WEB BROWSER                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  User clicks: ⚙️ Config button                                       │
│              ↓                                                        │
│              Config Modal opens                                       │
│              ↓                                                        │
│         ┌────────────────────┐                                       │
│         │ configTabs array:  │                                       │
│         │ - Database         │                                       │
│         │ - Station          │                                       │
│         │ - Flex             │                                       │
│         │ - Rotor            │                                       │
│         │ - WSJT-X ← NEW!    │                                       │
│         │ - CTY              │                                       │
│         │ - Logging          │                                       │
│         │ - Colours          │                                       │
│         │ - Specials         │                                       │
│         └────────────────────┘                                       │
│              ↓                                                        │
│         User clicks WSJT-X tab                                       │
│              ↓                                                        │
│    GET /api/config (fetch request)                                   │
│              ↓                                                        │
│  (Network Request ↓↓↓ Backend)                                       │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────┐
│                    BACKEND (FastAPI)                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  @app.get("/api/config")                                             │
│      ↓                                                                │
│      import config module                                            │
│      reload config module  (get latest)                              │
│      ↓                                                                │
│  Build config_data dict:                                             │
│      {                                                                │
│        DB_HOST: cfg.DB_HOST,                                         │
│        DB_PORT: cfg.DB_PORT,                                         │
│        ...[other params]...                                           │
│        WSJTX_ENABLED: getattr(cfg, 'WSJTX_ENABLED', True),           │
│        WSJTX_UDP_PORT: getattr(cfg, 'WSJTX_UDP_PORT', 2237),         │
│        WSJTX_UDP_MULTICAST: getattr(..., '224.0.0.1'),               │
│        WSJTX_WS_PORT: getattr(..., 8091),                            │
│        WSJTX_AUTO_LOG: getattr(..., True),                           │
│        WSJTX_AUTO_ROTATE: getattr(..., True)                         │
│      }                                                                │
│      ↓                                                                │
│  Return JSON response:                                               │
│      {                                                                │
│        "success": true,                                              │
│        "config": config_data                                         │
│      }                                                                │
│      ↓                                                                │
│  (Network Response ↑↑↑ Frontend)                                     │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────┐
│                    CONFIG.PY (Python File)                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  WSJTX_ENABLED = True                   ← Values read by             │
│  WSJTX_UDP_PORT = 2237                     backend and              │
│  WSJTX_UDP_MULTICAST = "224.0.0.1"         passed to               │
│  WSJTX_WS_PORT = 8091                      frontend                 │
│  WSJTX_AUTO_LOG = True                                               │
│  WSJTX_AUTO_ROTATE = True                                            │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────┐
│                    FRONTEND (JavaScript)                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  Response received from /api/config                                  │
│      ↓                                                                │
│  configData = { ...configData, ...response.config }                  │
│      ↓                                                                │
│  showConfigModal = true                                              │
│  activeConfigTab = 'database' (default)                              │
│      ↓                                                                │
│  Modal renders with form fields populated:                           │
│                                                                       │
│  ┌──────────────────────────────────────┐                            │
│  │ WSJT-X Configuration Form            │                            │
│  ├──────────────────────────────────────┤                            │
│  │ ☑ Enable WSJT-X Integration          │                            │
│  │                                       │                            │
│  │ UDP Listen Port      [2237]           │                            │
│  │ Multicast Address    [224.0.0.1]     │                            │
│  │ WebSocket Port       [8091]           │                            │
│  │                                       │                            │
│  │ ☑ Auto-Log to Wavelog                │                            │
│  │ ☑ Auto-Rotate Antenna                │                            │
│  │                                       │                            │
│  │ [Cancel]      [Save Configuration]    │                            │
│  └──────────────────────────────────────┘                            │
│      ↓                                                                │
│  User modifies values:                                               │
│    - Uncheck "Auto-Log to Wavelog"                                   │
│    - Change UDP port to 2238                                         │
│    - etc.                                                             │
│      ↓                                                                │
│  User clicks "Save Configuration"                                    │
│      ↓                                                                │
│  POST /api/config                                                    │
│      with data: {                                                    │
│        "config": {                                                   │
│          "WSJTX_ENABLED": true,                                      │
│          "WSJTX_UDP_PORT": 2238,  ← Changed!                        │
│          "WSJTX_UDP_MULTICAST": "224.0.0.1",                         │
│          "WSJTX_WS_PORT": 8091,                                       │
│          "WSJTX_AUTO_LOG": false,  ← Changed!                        │
│          "WSJTX_AUTO_ROTATE": true,                                  │
│          ...all other config...                                       │
│        }                                                               │
│      }                                                                │
│      ↓                                                                │
│  (Network Request ↓↓↓ Backend)                                       │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────┐
│                    BACKEND - SAVE HANDLER                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  @app.post("/api/config")                                            │
│      ↓                                                                │
│  for key, value in req.config.items():                               │
│      ↓                                                                │
│      _format_py_value(value) → convert to Python syntax              │
│                                                                       │
│      For WSJTX_UDP_PORT: 2238                                        │
│        → "WSJTX_UDP_PORT = 2238"                                     │
│                                                                       │
│      For WSJTX_AUTO_LOG: false                                       │
│        → "WSJTX_AUTO_LOG = False"                                    │
│      ↓                                                                │
│      _replace_block(text, key, new_value_src)                        │
│        → Find line: "^WSJTX_UDP_PORT =" (regex)                      │
│        → Replace with: "WSJTX_UDP_PORT = 2238"                       │
│      ↓                                                                │
│  Write updated text to config.py                                     │
│      ↓                                                                │
│  Return: { "success": true }                                         │
│      ↓                                                                │
│  (Network Response ↑↑↑ Frontend)                                     │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────┐
│                    CONFIG.PY AFTER SAVE                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  WSJTX_ENABLED = True           (no change)                          │
│  WSJTX_UDP_PORT = 2238          ← UPDATED!                           │
│  WSJTX_UDP_MULTICAST = "224.0.0.1"  (no change)                      │
│  WSJTX_WS_PORT = 8091           (no change)                          │
│  WSJTX_AUTO_LOG = False         ← UPDATED!                           │
│  WSJTX_AUTO_ROTATE = True       (no change)                          │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────┐
│                    FRONTEND - AFTER SAVE                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  Response received with "success": true                              │
│      ↓                                                                │
│  Show message: ✅ Configuration saved successfully!                  │
│      ↓                                                                │
│  setTimeout 3 seconds:                                               │
│      ↓                                                                │
│  closeConfigDialog()                                                 │
│      ↓                                                                │
│  Modal closes                                                         │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────┐
│                    USER RESTARTS APP                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  Ctrl+C to stop app                                                  │
│      ↓                                                                │
│  ./start_webapp.ps1  (or .sh on Linux)                               │
│      ↓                                                                │
│  Backend starts:                                                     │
│    - Imports config module                                           │
│    - Reads config.py with NEW values                                 │
│    - WSJTX_UDP_PORT = 2238  ← Takes effect!                          │
│      ↓                                                                │
│  Bridge server starts:                                               │
│    - Reads WSJTX_UDP_PORT from config                                │
│    - Listens on port 2238 instead of 2237                            │
│      ↓                                                                │
│  WSJT-X should also be updated:                                      │
│    - Settings → Reporting → Port: 2238                               │
│      ↓                                                                │
│  Bridge now receives packets on new port                             │
│  Auto-logging now DISABLED                                           │
│      ↓                                                                │
│  ✅ All changes take effect!                                         │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Component Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                       USER INTERFACE                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Radio Control│  │   Spots      │  │  Config Modal        │  │
│  │    Panel     │  │   Panel      │  │  (with WSJT-X tab)  │  │
│  │              │  │              │  │                      │  │
│  │ Freq, Mode,  │  │ Live DX      │  │ - Database           │  │
│  │ Filters, etc │  │ Cluster Data │  │ - Station & Cluster  │  │
│  │              │  │              │  │ - Flex & UDP         │  │
│  │              │  │              │  │ - Rotor              │  │
│  │              │  │              │  │ - WSJT-X ← NEW!     │  │
│  │              │  │              │  │ - CTY / Paths        │  │
│  └──────────────┘  └──────────────┘  │ - Logging            │  │
│                                       │ - Colours            │  │
│                                       │ - Special Stations   │  │
│                                       └──────────────────────┘  │
│                           ↓                                       │
│           /api/config (GET and POST)                             │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                    FASTAPI BACKEND                               │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ @app.get("/api/config") endpoint                          │ │
│  │   ↓                                                         │ │
│  │   1. Import config module                                 │ │
│  │   2. Reload to get fresh values                           │ │
│  │   3. Extract all parameters                               │ │
│  │   4. Return as JSON                                        │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ @app.post("/api/config") endpoint                         │ │
│  │   ↓                                                         │ │
│  │   1. Receive config data from frontend                    │ │
│  │   2. Read config.py file                                  │ │
│  │   3. For each parameter:                                  │ │
│  │      - Format as Python syntax                            │ │
│  │      - Find matching line in file                         │ │
│  │      - Replace with new value                             │ │
│  │   4. Write updated config.py                              │ │
│  │   5. Return success response                              │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                    CONFIG.PY FILE                                │
│                                                                   │
│  All configuration parameters stored here:                       │
│  - Database credentials                                          │
│  - Cluster settings                                              │
│  - Flex radio settings                                           │
│  - Rotator settings                                              │
│  - WSJT-X settings ← Editable via GUI                           │
│  - CTY paths                                                     │
│  - Logging settings                                              │
│  - Color definitions                                             │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│                    STARTUP PROCESSES                             │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Backend Process (Python FastAPI)                          │ │
│  │   ↓                                                         │ │
│  │   1. Imports config module                                │ │
│  │   2. Reads config.py values                               │ │
│  │   3. Uses values for database, logging, etc.              │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Bridge Server (Node.js)                                   │ │
│  │   ↓                                                         │ │
│  │   1. Reads environment variables:                         │ │
│  │      WSJTX_UDP_PORT (from config.py via startup script)   │ │
│  │      WSJTX_UDP_MULTICAST                                  │ │
│  │      WS_PORT                                               │ │
│  │   2. Starts UDP listener on WSJTX_UDP_PORT                │ │
│  │   3. Starts WebSocket server on WS_PORT                   │ │
│  │   4. Relays SDC and WSJT-X messages                       │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## Configuration Save/Load Cycle

```
┌──────────────────────────────────────────────────────┐
│ CONFIGURATION LOAD CYCLE (View Current Settings)     │
├──────────────────────────────────────────────────────┤
│                                                       │
│  1. User opens Config modal                          │
│     └─→ showConfigDialog() called                    │
│                                                       │
│  2. Frontend makes GET /api/config request           │
│     └─→ Sends to backend server                      │
│                                                       │
│  3. Backend processes GET /api/config:               │
│     └─→ import config module                         │
│     └─→ importlib.reload(cfg) - get latest          │
│     └─→ Read all parameters from cfg                │
│     └─→ Build config_data dictionary                │
│     └─→ Return JSON response                         │
│                                                       │
│  4. Frontend receives JSON response                  │
│     └─→ configData = {...configData, ...response}   │
│                                                       │
│  5. Modal renders with loaded values                 │
│     └─→ Form fields show current settings           │
│     └─→ User can now view/edit                       │
│                                                       │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│ CONFIGURATION SAVE CYCLE (Update Settings)           │
├──────────────────────────────────────────────────────┤
│                                                       │
│  1. User modifies values in form                     │
│     └─→ v-model bindings update configData           │
│                                                       │
│  2. User clicks "Save Configuration"                 │
│     └─→ saveConfiguration() called                   │
│     └─→ POST /api/config with configData             │
│                                                       │
│  3. Backend processes POST /api/config:              │
│     └─→ Read config.py as text file                  │
│     └─→ For each parameter:                          │
│        • _format_py_value(value) - format to Python  │
│        • _replace_block(text, key, value) - regex    │
│        • Find line matching "^KEY ="                 │
│        • Replace with "KEY = new_value"              │
│     └─→ Write updated text back to config.py         │
│     └─→ Return {"success": true}                     │
│                                                       │
│  4. Frontend receives success response               │
│     └─→ configMessage = {type: 'success', ...}       │
│     └─→ Show ✅ "Configuration saved!"               │
│                                                       │
│  5. Timeout 3 seconds:                               │
│     └─→ closeConfigDialog()                          │
│     └─→ Modal closes                                 │
│                                                       │
│  6. User restarts application:                       │
│     └─→ Backend reloads config module                │
│     └─→ Bridge server reads config.py                │
│     └─→ New values take effect!                      │
│                                                       │
└──────────────────────────────────────────────────────┘
```

---

## Key Data Structures

### Frontend configData Object
```javascript
configData: {
    // Existing parameters...
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS,
    MY_STATION, CLUSTER_HOST, CLUSTER_PORT, etc.
    
    // NEW: WSJT-X Parameters
    WSJTX_ENABLED: true,           // bool
    WSJTX_UDP_PORT: 2237,          // int
    WSJTX_UDP_MULTICAST: '224.0.0.1',  // string
    WSJTX_WS_PORT: 8091,           // int
    WSJTX_AUTO_LOG: true,          // bool
    WSJTX_AUTO_ROTATE: true,       // bool
}
```

### Backend config_data Response
```python
config_data = {
    "DB_HOST": cfg.DB_HOST,
    # ... other parameters ...
    "WSJTX_ENABLED": getattr(cfg, 'WSJTX_ENABLED', True),
    "WSJTX_UDP_PORT": getattr(cfg, 'WSJTX_UDP_PORT', 2237),
    "WSJTX_UDP_MULTICAST": getattr(cfg, 'WSJTX_UDP_MULTICAST', '224.0.0.1'),
    "WSJTX_WS_PORT": getattr(cfg, 'WSJTX_WS_PORT', 8091),
    "WSJTX_AUTO_LOG": getattr(cfg, 'WSJTX_AUTO_LOG', True),
    "WSJTX_AUTO_ROTATE": getattr(cfg, 'WSJTX_AUTO_ROTATE', True),
}
```

### Config.py File Values
```python
WSJTX_ENABLED = True
WSJTX_UDP_PORT = 2237
WSJTX_UDP_MULTICAST = "224.0.0.1"
WSJTX_WS_PORT = 8091
WSJTX_AUTO_LOG = True
WSJTX_AUTO_ROTATE = True
```

---

## Summary

The configuration system uses a **three-tier architecture**:

1. **Frontend** (HTML/JavaScript)
   - User interface for editing config
   - Sends/receives data via HTTP REST API

2. **Backend** (Python FastAPI)
   - REST endpoints to GET/POST config
   - Reads/writes config.py file using regex

3. **Storage** (config.py file)
   - Python module with all configuration values
   - Plain text file, human-readable
   - Loaded by backend and bridge server

All WSJT-X parameters flow through this system seamlessly!

---

**Architecture Version**: 1.0  
**Last Updated**: 2024