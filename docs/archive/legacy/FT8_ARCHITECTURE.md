# FT8/FT4 Integration Architecture

## 🏗️ System Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Browser Frontend                         │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Operate    │  │   Settings   │  │  Waterfall   │      │
│  │     Tab      │  │     Tab      │  │    Canvas    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                               │
│  Vue.js Component (ft8ModalMixin)                           │
│  - State management                                          │
│  - WebSocket communication                                   │
│  - UI event handlers                                         │
│  - Configuration management                                  │
└─────────────────────────────────────────────────────────────┘
                            │ WebSocket
                            │ HTTP REST API
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                           │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐   │
│  │        FT8 API Router (/api/ft8/)                   │   │
│  │  - WebSocket endpoint (/ws)                         │   │
│  │  - Status endpoint (/status)                        │   │
│  │  - Control endpoints (start/stop/config)            │   │
│  │  - Audio devices enumeration                        │   │
│  │  - Configuration management                         │   │
│  └─────────────────────────────────────────────────────┘   │
│                            │                                 │
│                            ▼                                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           FT8 Service Layer                         │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │   │
│  │  │  FT8Service  │  │ FT8Protocol  │  │FT8Audio  │ │   │
│  │  │              │  │              │  │Processor │ │   │
│  │  │ - TX/RX      │  │ - Encoding   │  │          │ │   │
│  │  │   timing     │  │ - Decoding   │  │ - FFT    │ │   │
│  │  │ - QSO mgmt   │  │ - Messages   │  │ - Tones  │ │   │
│  │  │ - Auto-seq   │  │ - Symbols    │  │ - Filter │ │   │
│  │  └──────────────┘  └──────────────┘  └──────────┘ │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ Audio I/O
                            │ CAT Control
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    External Systems                          │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  FlexRadio   │  │ Audio System │  │   Wavelog    │      │
│  │              │  │              │  │   Database   │      │
│  │ - CAT (4992) │  │ - Input dev  │  │              │      │
│  │ - PTT        │  │ - Output dev │  │ - QSO log    │      │
│  │ - Frequency  │  │ - DAX audio  │  │ - Sync       │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

## 📁 File Structure

```
om0rx-radio-control/
├── frontend/
│   ├── templates/
│   │   └── modal-ft8.html              ✅ Modal UI (Operate + Settings)
│   ├── js/
│   │   └── ft8-modal.js                ✅ Vue.js mixin with state & methods
│   └── ft8-modal.css                   ✅ Styling (tabs, settings, waterfall)
│
├── backend/
│   ├── api/
│   │   └── ft8.py                      ✅ REST API & WebSocket endpoints
│   └── core/
│       └── config.py                   ✅ Config endpoints delegation
│
├── services/
│   ├── ft8_service.py                  ⚠️ Service orchestrator (partial)
│   ├── ft8_protocol.py                 ⚠️ FT8 protocol logic (placeholder)
│   ├── ft8_audio.py                    ⚠️ Audio processing (partial)
│   └── (future)
│       ├── ft8_cat.py                  ❌ CAT control (not started)
│       └── ft8_qso.py                  ❌ QSO management (not started)
│
├── config.py                           ✅ FT8 configuration variables
│
└── documentation/
    ├── FT8_STAGE2_IMPLEMENTATION.md    ✅ This implementation doc
    ├── FT8_QUICK_START.md              ✅ User guide
    └── FT8_ARCHITECTURE.md             ✅ This document
```

**Legend:**
- ✅ Complete and functional
- ⚠️ Partial implementation / placeholder
- ❌ Not yet implemented

## 🔄 Data Flow

### Configuration Flow
```
User clicks Settings tab
    ▼
ft8LoadSettings() called
    ▼
GET /api/config/ft8
    ▼
Backend reads config.py
    ▼
Returns config + audio devices
    ▼
Vue updates ft8.config
    ▼
Settings form displays current values

User modifies settings
    ▼
User clicks Save
    ▼
ft8SaveSettings() called
    ▼
POST /api/config/ft8
    ▼
Backend updates config module
    ▼
Returns success
    ▼
Vue shows "✅ Saved!"
```

### WebSocket Message Flow
```
User clicks Start
    ▼
ft8ToggleConnection() called
    ▼
POST /api/ft8/start
    ▼
FT8Service.start()
    ▼
Background tasks start:
  - Timing loop (TX/RX cycles)
  - Decode loop (signal processing)
    ▼
WebSocket sends updates:
  - Decoded messages
  - Waterfall data
  - Status updates
  - QSO updates
    ▼
Vue receives and displays
```

### Audio Processing Flow (Planned)
```
Audio device captures samples
    ▼
FT8AudioProcessor.add_audio_samples()
    ▼
Buffer fills (15 sec for FT8)
    ▼
Process audio chunk:
  - Apply bandpass filter
  - Compute FFT
  - Generate spectrum
    ▼
Update waterfall display
    ▼
Detect signals (peaks in spectrum)
    ▼
Extract tone sequence
    ▼
FT8Protocol.decode_symbols()
    ▼
Parse message text
    ▼
Notify via WebSocket
```

## 🎨 Frontend Components

### Vue.js Data Structure
```javascript
ft8: {
    // Connection state
    mode: 'FT8',
    connected: false,
    activeTab: 'operate',
    
    // Station info (quick access)
    mycall: 'OM0RX',
    mygrid: 'JN88',
    txEnabled: false,
    autoSequence: false,
    
    // Configuration (settings tab)
    config: {
        mode: 'FT8',
        mycall: 'OM0RX',
        mygrid: 'JN88',
        networkServer: '192.168.0.199:4992',
        pttMethod: 'CAT',
        audioInput: 'default',
        audioOutput: 'default',
        sampleRate: 12000,
        autoSequence: false,
        txEnabled: false,
        waterfallHeight: 100,
        useFlexRadioAudio: true
    },
    
    // Audio devices
    audioDevices: {
        input: [],   // Populated by API
        output: []   // Populated by API
    },
    
    // Operating data
    decodedMessages: [],
    selectedMessage: null,
    activeQSOs: [],
    txQueue: [],
    customMessage: '',
    
    // Statistics
    stats: {
        decoded_count: 0,
        transmitted_count: 0,
        qso_completed: 0,
        uptime: 0
    },
    
    // Waterfall
    waterfallData: [],
    waterfallCtx: null,
    isTxCycle: false
}
```

### Vue.js Methods
```javascript
// Modal control
openFT8Modal()
closeFT8Modal()

// Configuration
ft8LoadSettings()          ✅
ft8SaveSettings()          ✅
ft8GetAudioDevices()       ✅

// Service control
ft8ToggleConnection()      ⚠️ (API ready, service partial)
ft8StopService()           ⚠️
ft8ModeChanged()           ⚠️

// WebSocket
connectFT8WebSocket()      ✅
handleFT8WebSocketMessage()✅

// Operating
ft8CallCQ()                ⚠️
ft8ReplySelected()         ⚠️
ft8SendReport()            ⚠️
ft8SendRRR()               ⚠️
ft8Send73()                ⚠️
ft8SendCustom()            ⚠️

// QSO management
ft8SelectMessage()         ⚠️
ft8ClearDecoded()          ✅

// Waterfall
initFT8Waterfall()         ⚠️ (canvas ready, no data yet)
updateFT8Waterfall()       ⚠️
drawWaterfallSpectrum()    ⚠️
```

## 🔌 Backend API Endpoints

### Configuration Endpoints

**GET /api/config/ft8**
```json
Response: {
    "config": {
        "mode": "FT8",
        "mycall": "OM0RX",
        "mygrid": "JN88",
        "networkServer": "192.168.0.199:4992",
        "pttMethod": "CAT",
        "audioInput": "default",
        "audioOutput": "default",
        "sampleRate": 12000,
        "autoSequence": false,
        "txEnabled": false,
        "waterfallHeight": 100,
        "useFlexRadioAudio": true
    },
    "audioDevices": {
        "input": ["0: Microphone", "1: FlexRadio DAX RX"],
        "output": ["0: Speakers", "1: FlexRadio DAX TX"]
    }
}
```

**POST /api/config/ft8**
```json
Request: {
    "mode": "FT8",
    "mycall": "OM0RX",
    // ... other config fields
}

Response: {
    "status": "success",
    "message": "Configuration updated"
}
```

### Service Control Endpoints

**GET /api/ft8/status**
```json
Response: {
    "enabled": false,
    "mode": "FT8",
    "mycall": "OM0RX",
    "tx_enabled": false,
    "stats": {
        "decoded_count": 0,
        "transmitted_count": 0,
        "qso_completed": 0,
        "uptime": 0
    }
}
```

**POST /api/ft8/start**
```json
Request: {
    "mode": "FT8",
    "mycall": "OM0RX",
    "mygrid": "JN88",
    "auto_sequence": false,
    "tx_enabled": false
}

Response: {
    "status": "started",
    "mode": "FT8"
}
```

**POST /api/ft8/stop**
```json
Response: {
    "status": "stopped"
}
```

### Audio Endpoints

**GET /api/ft8/audio-devices**
```json
Response: {
    "input": [
        "0: Microphone (Realtek)",
        "1: FlexRadio DAX RX 1",
        "2: FlexRadio DAX RX 2"
    ],
    "output": [
        "0: Speakers (Realtek)",
        "1: FlexRadio DAX TX 1",
        "2: FlexRadio DAX TX 2"
    ]
}
```

### WebSocket Messages

**Connection**
```
ws://localhost:8000/api/ft8/ws
```

**Message Types Received**

**Status Update**
```json
{
    "type": "status",
    "data": {
        "enabled": true,
        "is_tx_cycle": false,
        "stats": { ... }
    }
}
```

**Decoded Message**
```json
{
    "type": "decoded",
    "data": {
        "timestamp": "2025-01-05T12:34:56Z",
        "snr": -8.5,
        "dt": 0.3,
        "freq": 1234,
        "message": "CQ DX OM0RX JN88"
    }
}
```

**Waterfall Data**
```json
{
    "type": "waterfall",
    "data": [[0,5,10,15,...], ...]  // 2D spectrum array
}
```

**Active QSOs**
```json
{
    "type": "qsos",
    "data": [
        {
            "their_call": "DL1ABC",
            "state": "sending_report",
            "my_report": "R-15",
            "their_report": "-10"
        }
    ]
}
```

**TX Notification**
```json
{
    "type": "transmitting",
    "data": {
        "message": "OM0RX DL1ABC R-15"
    }
}
```

**QSO Complete**
```json
{
    "type": "qso_complete",
    "data": {
        "their_call": "DL1ABC",
        "their_grid": "JO62",
        "started_at": "2025-01-05T12:30:00Z",
        "tx_count": 3,
        "rx_count": 3
    }
}
```

## 🧩 Service Layer Components

### FT8Service (services/ft8_service.py)

**Purpose**: Main orchestrator for FT8 operations

**Responsibilities:**
- Manage TX/RX timing cycles
- Coordinate decoding pipeline
- Handle QSO state machine
- Manage message queue
- Provide callbacks for events

**Key Methods:**
```python
async def start()                      # Start service
async def stop()                       # Stop service
async def queue_tx_message(msg)        # Queue message for TX
async def call_cq()                    # Send CQ call
async def reply_to_call(call, report)  # Reply to station
async def send_73(call)                # Send 73
def get_stats()                        # Get statistics
def get_decoded_messages(limit)        # Get decoded list
def get_active_qsos()                  # Get QSO sessions
def get_waterfall_data()               # Get waterfall
```

### FT8Protocol (services/ft8_protocol.py)

**Purpose**: FT8/FT4 protocol encoding/decoding

**Responsibilities:**
- Encode text messages to tone sequences
- Decode tone sequences to text
- Handle FT8/FT4 differences
- Message validation
- Symbol mapping

**Key Methods:**
```python
def encode_message(text)               # Text → tones
def decode_symbols(tones, snr, dt, f)  # Tones → text
def validate_message(text)             # Check valid format
def parse_message(text)                # Extract components
```

### FT8AudioProcessor (services/ft8_audio.py)

**Purpose**: Audio signal processing

**Responsibilities:**
- Audio buffer management
- FFT analysis
- Bandpass filtering
- Tone generation
- Waterfall generation
- Signal detection

**Key Methods:**
```python
def add_audio_samples(samples)         # Add to buffer
def process_audio_chunk(audio)         # FFT processing
def detect_signals(audio)              # Find peaks
def extract_signal(audio, freq)        # Isolate signal
def decode_tone_sequence(audio, freq)  # Extract tones
def generate_tone_sequence(tones, f0)  # Generate audio
def apply_bandpass_filter(audio)       # Filter audio
def update_waterfall(spectrum)         # Update display
def get_waterfall_data()               # Get display data
```

## 🔧 Configuration Management

### Config Variables (config.py)

```python
# FT8/FT4 Digital Mode Configuration
FT8_ENABLED = True                     # Enable FT8 feature
FT8_MODE = "FT8"                       # FT8 or FT4
FT8_MYCALL = "OM0RX"                   # Station callsign
FT8_MYGRID = "JN88"                    # Grid square
FT8_NETWORK_SERVER = "192.168.0.199:4992"  # CAT control
FT8_AUDIO_INPUT = "default"            # Input device
FT8_AUDIO_OUTPUT = "default"           # Output device
FT8_SAMPLE_RATE = 12000                # Audio sample rate
FT8_AUTO_SEQUENCE = False              # Auto QSO mode
FT8_TX_ENABLED = False                 # Enable TX
FT8_WATERFALL_HEIGHT = 100             # Display height
FT8_USE_FLEXRADIO_AUDIO = True         # Use DAX
FT8_PTT_METHOD = "CAT"                 # PTT method
```

### Runtime Configuration

Configuration can be updated via:
1. **UI Settings Tab** → Saves to memory
2. **API POST** → Updates config module
3. **File Edit** → Requires server restart

**Note**: Current implementation updates in-memory only. For persistence, implement:
- JSON configuration file
- Database storage
- Write-back to config.py

## 🎯 Implementation Status

### ✅ Completed (Stage 2)

#### Frontend
- [x] Settings tab UI with all configuration fields
- [x] Tabbed interface (Operate / Settings)
- [x] Configuration form layout
- [x] Audio device dropdowns
- [x] Save/Reload functionality
- [x] Configuration state management
- [x] API integration for config

#### Backend
- [x] Configuration endpoints (/api/config/ft8)
- [x] Audio device enumeration (/api/ft8/audio-devices)
- [x] Config persistence (in-memory)
- [x] FT8 API router setup
- [x] WebSocket infrastructure

#### Infrastructure
- [x] FT8 configuration variables in config.py
- [x] sounddevice package installed
- [x] scipy package installed
- [x] Documentation written

### ⏳ In Progress (Stage 3)

#### Audio Processing
- [ ] Real-time audio capture from device
- [ ] Audio buffer streaming
- [ ] FFT spectrum generation
- [ ] Waterfall canvas rendering
- [ ] Signal detection (peak finding)

#### FlexRadio Integration
- [ ] CAT control connection
- [ ] PTT control
- [ ] Frequency synchronization
- [ ] DAX audio channel setup

### 🔮 Planned (Stage 4+)

#### Protocol Implementation
- [ ] FT8 LDPC encoding
- [ ] FT8 LDPC decoding
- [ ] Tone sequence generation
- [ ] Tone sequence decoding
- [ ] Message parsing

#### TX Implementation
- [ ] Audio waveform generation
- [ ] TX timing synchronization
- [ ] Power level control
- [ ] TX audio output

#### QSO Management
- [ ] Auto-sequencing logic
- [ ] QSO state machine
- [ ] Contact logging
- [ ] Wavelog integration
- [ ] ADIF export

#### Advanced Features
- [ ] CQ monitoring
- [ ] Band activity display
- [ ] Spot alerting
- [ ] Worked before checking
- [ ] DX entity tracking

## 📊 Performance Considerations

### Audio Processing
- **Sample Rate**: 12000 Hz optimal for FT8
- **Buffer Size**: 15 seconds for FT8, 6 for FT4
- **FFT Size**: 2048 samples
- **Update Rate**: 1 Hz for waterfall

### Network
- **WebSocket**: Low latency required
- **Message Rate**: ~1-10 per second during active decoding
- **Waterfall Data**: ~10 KB per update

### CPU
- **FFT Processing**: Moderate load with scipy
- **Decoding**: High load (LDPC computationally intensive)
- **UI Updates**: Low load (Vue.js handles efficiently)

## 🔐 Security Considerations

1. **Audio Device Access**: Limited to enumeration (no actual capture yet)
2. **Network Access**: FlexRadio on local network only
3. **Configuration**: In-memory only (not persisted to disk)
4. **WebSocket**: No authentication (local access only)
5. **TX Control**: Multiple safeguards (enable checkbox, start button)

## 🧪 Testing Strategy

### Unit Tests
- Configuration API endpoints
- Audio device enumeration
- WebSocket message parsing
- Vue.js component methods

### Integration Tests
- Full configuration flow
- WebSocket connection lifecycle
- FlexRadio CAT communication
- Audio pipeline (when implemented)

### Manual Tests
- UI interaction flow
- Configuration persistence
- Error handling
- Browser compatibility

## 📚 References

### FT8 Protocol
- [FT8 Specification (K1JT)](https://physics.princeton.edu/pulsar/k1jt/FT8_Protocol.pdf)
- [WSJT-X Source Code](https://sourceforge.net/projects/wsjt/)

### Audio Processing
- [PortAudio Documentation](http://www.portaudio.com/)
- [SciPy Signal Processing](https://docs.scipy.org/doc/scipy/reference/signal.html)

### FlexRadio
- [SmartSDR CAT Commands](https://www.flexradio.com/documentation/)
- [DAX Audio Setup](https://helpdesk.flexradio.com/)

### Web Technologies
- [Vue.js Documentation](https://vuejs.org/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [WebSocket Protocol](https://tools.ietf.org/html/rfc6455)

---

**Document Version**: 1.0  
**Last Updated**: 2025-01-05  
**Implementation Stage**: Stage 2 Complete  
**Next Milestone**: Stage 3 - Real Audio Processing