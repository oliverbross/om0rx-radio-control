import os
import importlib.util
from pathlib import Path

from radio_control.settings_store import load_app_settings, load_local_secrets

# config.py (ver5.8)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"
SETTINGS_DIR = PROJECT_ROOT / "settings"

_local_config_path = PROJECT_ROOT / "config_local.py"
if _local_config_path.exists():
    _local_spec = importlib.util.spec_from_file_location("config_local", _local_config_path)
    _local_config = importlib.util.module_from_spec(_local_spec)
    _local_spec.loader.exec_module(_local_config)
else:
    _local_config = None

_app_settings = load_app_settings()
_local_secrets = load_local_secrets()


def _cfg_value(name, default):
    if name in os.environ:
        return os.environ[name]
    if name in _local_secrets:
        return _local_secrets[name]
    if name in _app_settings:
        return _app_settings[name]
    if _local_config is not None and hasattr(_local_config, name):
        return getattr(_local_config, name)
    return default


def _cfg_int(name, default):
    return int(_cfg_value(name, default))


def _cfg_float(name, default):
    return float(_cfg_value(name, default))


def _cfg_bool(name, default):
    value = _cfg_value(name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _cfg_list(name, default):
    value = _cfg_value(name, default)
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            import json

            parsed = json.loads(stripped)
            if not isinstance(parsed, list):
                raise ValueError(f"{name} must be a JSON array or comma-separated list")
            return parsed
        return [item.strip() for item in stripped.split(",") if item.strip()]
    return default


def _cfg_dict(name, default):
    value = _cfg_value(name, default)
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        import json

        parsed = json.loads(stripped)
        if not isinstance(parsed, dict):
            raise ValueError(f"{name} must be a JSON object")
        return parsed
    return default


BACKEND_HOST = _cfg_value("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = _cfg_int("BACKEND_PORT", 8080)
REMOTE_CONTROL_ENABLED = _cfg_bool("REMOTE_CONTROL_ENABLED", False)
CONTROL_TOKEN = _cfg_value("CONTROL_TOKEN", "")
WSJTX_BRIDGE_TOKEN = _cfg_value("WSJTX_BRIDGE_TOKEN", CONTROL_TOKEN)
CORS_ALLOWED_ORIGINS = _cfg_list(
    "CORS_ALLOWED_ORIGINS",
    [
        f"http://localhost:{BACKEND_PORT}",
        f"http://127.0.0.1:{BACKEND_PORT}",
    ],
)

DB_HOST = _cfg_value("DB_HOST", "")
DB_PORT = _cfg_int("DB_PORT", 3306)
DB_NAME = _cfg_value("DB_NAME", "")
DB_USER = _cfg_value("DB_USER", "")
DB_PASS = _cfg_value("DB_PASS", "")
DATABASE_BACKEND = _cfg_value("DATABASE_BACKEND", "auto")
POSTGRES_DSN = _cfg_value("POSTGRES_DSN", "")
POSTGRES_HOST = _cfg_value("POSTGRES_HOST", "")
POSTGRES_PORT = _cfg_int("POSTGRES_PORT", 5432)
POSTGRES_DB = _cfg_value("POSTGRES_DB", "")
POSTGRES_USER = _cfg_value("POSTGRES_USER", "")
POSTGRES_PASSWORD = _cfg_value("POSTGRES_PASSWORD", "")
POSTGRES_CONNECT_TIMEOUT_SECONDS = _cfg_int("POSTGRES_CONNECT_TIMEOUT_SECONDS", 2)
POSTGRES_RETRY_COOLDOWN_SECONDS = _cfg_int("POSTGRES_RETRY_COOLDOWN_SECONDS", 30)
MY_STATION = _cfg_value("MY_STATION", "OM0RX")
CLUSTERS = _cfg_value("CLUSTERS", [])
CLUSTER_HOST = _cfg_value("CLUSTER_HOST", "localhost")
CLUSTER_PORT = _cfg_int("CLUSTER_PORT", 7373)
CLUSTER_USER = _cfg_value("CLUSTER_USER", "N0CALL")
CLUSTER_PASS = _cfg_value("CLUSTER_PASS", "")
RBL_ENABLE_COMMAND = _cfg_value("RBL_ENABLE_COMMAND", "set/skimmer")
RBL_DISABLE_COMMAND = _cfg_value("RBL_DISABLE_COMMAND", "unset/skimmer")
RBL_MODE_COMMANDS = _cfg_dict("RBL_MODE_COMMANDS", {})
RBL_COMMAND_PROFILE = _cfg_value("RBL_COMMAND_PROFILE", "dxspider")
RBL_COMMAND_PROFILES = _cfg_dict("RBL_COMMAND_PROFILES", {})
RADIO_SHOW_DETAILED_CONTROLS = _cfg_bool("RADIO_SHOW_DETAILED_CONTROLS", False)
RADIO_LAYOUT_PRESET = _cfg_value("RADIO_LAYOUT_PRESET", "compact")
RBL_ALERT_RULES = _cfg_dict("RBL_ALERT_RULES", {
    "enabled": True,
    "newDxcc": True,
    "newBand": True,
    "newCall": False,
    "localHeard": True,
    "minScore": 55,
    "minSnr": 8,
    "modes": [],
    "bands": [],
    "cooldownMinutes": 10,
    "sound": False,
    "toast": True,
})
ACTIVITY_INTELLIGENCE = _cfg_dict("ACTIVITY_INTELLIGENCE", {})
LOGIN_SCRIPT  = []

SDR_UDP_HOST = _cfg_value("SDR_UDP_HOST", "127.0.0.1")
SDR_UDP_PORT = _cfg_int("SDR_UDP_PORT", 12061)
UDP_ENABLED_DEFAULT = _cfg_bool("UDP_ENABLED_DEFAULT", False)
FLEX_TCP_HOST = _cfg_value("FLEX_TCP_HOST", "192.168.0.199")
FLEX_TCP_PORT = _cfg_int("FLEX_TCP_PORT", 4992)
FLEX_ANTENNA_POLICY = _cfg_dict("FLEX_ANTENNA_POLICY", {
    "enabled": True,
    "bands": {
        "160m": "ANT2",
        "80m": "ANT2",
        "60m": "ANT2",
        "40m": "ANT2",
        "30m": "ANT2",
        "20m": "ANT1",
        "17m": "ANT1",
        "15m": "ANT1",
        "12m": "ANT1",
        "10m": "ANT1",
    },
})
FLEX_ENABLED_DEFAULT = _cfg_bool("FLEX_ENABLED_DEFAULT", True)

# === Elecraft KPA500 / KAT500 ===
KPA500_ENABLED = _cfg_bool("KPA500_ENABLED", False)
KPA500_PORT = _cfg_value("KPA500_PORT", "COM6")
KPA500_BAUDRATE = _cfg_int("KPA500_BAUDRATE", 38400)
DIGITAL_KPA_POLICY = str(_cfg_value("DIGITAL_KPA_POLICY", "operate") or "operate").strip().lower()
KAT500_ENABLED = _cfg_bool("KAT500_ENABLED", False)
KAT500_PORT = _cfg_value("KAT500_PORT", "COM11")
KAT500_BAUDRATE = _cfg_int("KAT500_BAUDRATE", 38400)
ELECRAFT_FOLLOW_RADIO = _cfg_bool("ELECRAFT_FOLLOW_RADIO", True)
# Temporary migration switch. Keep legacy direct writes disabled until the
# station safety coordinator performs TX/interlock checks and exact readback.
ELECRAFT_LEGACY_CONTROL_ENABLED = _cfg_bool("ELECRAFT_LEGACY_CONTROL_ENABLED", False)
# Station-level writes stay locked until the installation has been physically
# verified and this independent commissioning latch is explicitly enabled.
STATION_COORDINATOR_COMMISSIONED = _cfg_bool("STATION_COORDINATOR_COMMISSIONED", False)
STATION_AMPLIFIER_ALLOWED_BANDS = _cfg_value("STATION_AMPLIFIER_ALLOWED_BANDS", [
    "160m", "80m", "40m", "30m", "15m", "12m", "10m", "6m",
])
STATION_AMPLIFIER_DRIVE_W = _cfg_dict("STATION_AMPLIFIER_DRIVE_W", {
    "160m": 25,
    "80m": 25,
    "60m": 25,
    "40m": 25,
    "30m": 25,
    "20m": 25,
    "17m": 25,
    "15m": 25,
    "12m": 25,
    "10m": 25,
    "6m": 25,
})
STATION_BAREFOOT_DRIVE_W = _cfg_dict("STATION_BAREFOOT_DRIVE_W", {
    "160m": 25,
    "80m": 25,
    "60m": 25,
    "40m": 25,
    "30m": 25,
    "20m": 25,
    "17m": 25,
    "15m": 25,
    "12m": 25,
    "10m": 25,
    "6m": 25,
})
STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS = _cfg_value(
    "STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS",
    list(STATION_AMPLIFIER_ALLOWED_BANDS),
)
STATION_DIGITAL_AMPLIFIER_DRIVE_W = _cfg_dict(
    "STATION_DIGITAL_AMPLIFIER_DRIVE_W",
    dict(STATION_AMPLIFIER_DRIVE_W),
)
STATION_ROUTE_VERIFY_TTL_SECONDS = _cfg_float("STATION_ROUTE_VERIFY_TTL_SECONDS", 10.0)
STATION_TUNE_POWER_W = _cfg_int("STATION_TUNE_POWER_W", 20)
STATION_TUNE_TARGET_SWR = _cfg_float("STATION_TUNE_TARGET_SWR", 1.5)
STATION_TUNE_ABORT_SWR = _cfg_float("STATION_TUNE_ABORT_SWR", 3.0)
STATION_TUNE_TIMEOUT_SECONDS = _cfg_float("STATION_TUNE_TIMEOUT_SECONDS", 30.0)
STATION_TELEMETRY_INTERVAL_SECONDS = _cfg_float("STATION_TELEMETRY_INTERVAL_SECONDS", 5.0)
STATION_TELEMETRY_RETENTION_DAYS = _cfg_int("STATION_TELEMETRY_RETENTION_DAYS", 7)
# Alarm thresholds are deliberately unset by default. Telemetry alone must not
# invent a safe operating envelope for a particular amplifier installation.
KPA500_TEMPERATURE_MAX_C = _cfg_value("KPA500_TEMPERATURE_MAX_C", None)
KPA500_VOLTAGE_MIN_V = _cfg_value("KPA500_VOLTAGE_MIN_V", None)
KPA500_VOLTAGE_MAX_V = _cfg_value("KPA500_VOLTAGE_MAX_V", None)
KAT500_ANTENNA_POLICY = _cfg_dict("KAT500_ANTENNA_POLICY", {
    "160m": 2,
    "80m": 2,
    "60m": 2,
    "40m": 2,
    "30m": 2,
    "20m": 1,
    "17m": 1,
    "15m": 1,
    "12m": 1,
    "10m": 1,
    "6m": 1,
})
KAT500_ANTENNA_NAMES = _cfg_dict("KAT500_ANTENNA_NAMES", {
    "1": "KAT ANT1",
    "2": "KAT ANT2",
    "3": "KAT ANT3",
})
CTY_CSV_PATH = str(DATA_DIR / "cty.csv")
CTY_IGNORE_SUFFIXES = ["P","M","MM","AM","QRP","QRPP","A","B","QTH"]
CTY_OVERRIDES = {
    "PJ6Y": 305,  # Saba & St. Eustatius (ADIF 305)
    "PJ": 305,    # PJ prefix -> Saba & St. Eustatius
}

COLOR_ATNO           = "#FFFF8C00"
COLOR_NEW_BAND       = "#FF00BFFF"
COLOR_NEW_MODE       = "#FFFFC000"
COLOR_NEW_BAND_MODE  = "#FFE91E63"
COLOR_NEED_LOTW      = "#FF32CD32"
COLOR_WORKED         = "#FFB0B0B0"
COLOR_DEFAULT        = "#FFFFFFFF"

# New Call/DXCC Status Colors (added for classification fix)
COLOR_NEW_CALL       = "#FFFF6B35"  # Orange-Red
COLOR_CONFIRMED      = "#FF10B981"  # Green
COLOR_C_NEW_BAND     = "#FF4A9EFF"  # Bright Blue
COLOR_C_NEW_MODE     = "#FFFFD93D"  # Yellow
COLOR_C_NEW_BAND_MODE= "#FF9C27B0"  # Purple
COLOR_W_NEW_BAND     = "#FF00BCD4"  # Cyan
COLOR_W_NEW_MODE     = "#FFFFA726"  # Orange
COLOR_W_NEW_BAND_MODE= "#FFFF5722"  # Deep Orange
COLOR_UNKNOWN        = "#FF666666"  # Dark Gray

COLORS = {'ATNO': '#FFFF8C00', 'New band': '#FF00BFFF', 'New mode': '#FFFFC000', 'New band+mode': '#FFE91E63', 'Need LoTW': '#FF32CD32', 'Worked': '#FFB0B0B0', 'Default': '#FFFFFFFF', 'New Call': '#FFFF6B35', 'Confirmed': '#FF10B981', 'C/New Band': '#FF4A9EFF', 'C/New Mode': '#FFFFD93D', 'C/New Band+Mode': '#FF9C27B0', 'W/New Band': '#FF00BCD4', 'W/New Mode': '#FFFFA726', 'W/New Band+Mode': '#FFFF5722', 'Unknown': '#FF666666'}
LOG_LEVEL = _cfg_value("LOG_LEVEL", "INFO").upper()
HEARTBEAT_SEC = 30
RECONNECT_BACKOFF = [2,5,10,20,30,60]
BANNER_LOG_LINES = 6
RESOLVE_DEBUG_MISSES = 25

# Path to Big CTY (cty.dat). If set, takes precedence over CSV.
CTY_DAT_PATH = str(DATA_DIR / "cty.dat")
WAVELOG_API_URL = _cfg_value("WAVELOG_API_URL", "")
WAVELOG_API_KEY = _cfg_value("WAVELOG_API_KEY", "")
WAVELOG_STATION_ID = _cfg_value("WAVELOG_STATION_ID", "1")
QRZ_USERNAME = _cfg_value("QRZ_USERNAME", "")
QRZ_PASSWORD = _cfg_value("QRZ_PASSWORD", "")
ADIF_LOG_PATH = str(LOGS_DIR / "qso_log.adif")
SPECIAL_PATTERNS = {
    "POTA":      r"\bPOTA\b|\bPOTA\s*[-:]?\s*[A-Z]{1,3}-?\d+",
    "SOTA":      r"\bSOTA\b|\bSOTA\s*[A-Z]{2}/[A-Z]-\d+",
    "IOTA":      r"\bIOTA\b|\b[Ii]OTA\s*[A-Z]{1,2}-\d{3}",
    "WWFF":      r"\bWWFF\b|\b[A-Z0-9]{1,4}FF-\d{3,5}\b",
    "BUNKER":    r"\b(?:WWBOTA|UKBOTA|BUNKERS?\s+ON\s+THE\s+AIR)\b|\bB/[A-Z0-9]{1,4}-\d{4}\b",
    "CASTLE":    r"\bWCA\b|\bCASTLE\b|\b[A-Z]{1,3}-\d{5}\b",
    "LIGHTHOUSE":r"\bLIGHTHOUSE\b|\bARLHS\b|\bILLW\b",
    "CONTEST":   r"\bCONTEST\b",
    "IARU":      r"\bIARU\b"
}


# Preset values that pre-seed the Special dropdown in the UI.
# Do not include '(none)' — it is auto-added so you can filter untagged rows.
SPECIAL_PRESET = ["POTA", "SOTA", "IOTA", "WWFF", "BUNKER", "CONTEST", "LIGHTHOUSE", "CASTLE", "IARU"]

# === Rotator (ARCO) Configuration ===
ROTOR_ENABLED = _cfg_bool("ROTOR_ENABLED", True)
ROTOR_TYPE = _cfg_value("ROTOR_TYPE", "Microham ARCO")
ROTOR_HOST = _cfg_value("ROTOR_HOST", "192.168.0.198")
ROTOR_PORT = _cfg_int("ROTOR_PORT", 4001)
ROTOR_PROTOCOL = _cfg_value("ROTOR_PROTOCOL", "DCU-1")
ROTOR_TIMEOUT_SEC = _cfg_float("ROTOR_TIMEOUT_SEC", 2.5)
ROTOR_HOME_GRID = _cfg_value("ROTOR_HOME_GRID", "JN88TQ")
ROTOR_HOME_LAT = _cfg_float("ROTOR_HOME_LAT", 48.17)
ROTOR_HOME_LON = _cfg_float("ROTOR_HOME_LON", 17.08)
ROTOR_BANDS = _cfg_value("ROTOR_BANDS", {})
ROTOR_AUTO_ENABLED = _cfg_bool("ROTOR_AUTO_ENABLED", True)
ROTOR_AUTO_DELAY_SEC = _cfg_int("ROTOR_AUTO_DELAY_SEC", 2)
WSJTX_ENABLED = _cfg_bool("WSJTX_ENABLED", True)
WSJTX_UDP_PORT = _cfg_int("WSJTX_UDP_PORT", 2237)
WSJTX_UDP_MULTICAST = _cfg_value("WSJTX_UDP_MULTICAST", "224.0.0.1")
WSJTX_WS_PORT = _cfg_int("WSJTX_WS_PORT", 8091)
WSJTX_BRIDGE_COMMAND_URL = _cfg_value("WSJTX_BRIDGE_COMMAND_URL", "http://127.0.0.1:8092/wsjtx/command")
WSJTX_AUTO_LOG = _cfg_bool("WSJTX_AUTO_LOG", True)
WSJTX_AUTO_ROTATE = _cfg_bool("WSJTX_AUTO_ROTATE", False)
WSJTX_MODAL_FIELDS = {
    "call": {"label": "Call", "type": "text", "readonly": False},
    "grid": {"label": "Grid", "type": "text", "readonly": False},
    "frequency": {"label": "Frequency", "type": "number", "readonly": False},
    "mode": {"label": "Mode", "type": "select", "readonly": False},
    "rst_r": {"label": "RST Received", "type": "text", "readonly": False},
    "rst_s": {"label": "RST Sent", "type": "text", "readonly": False},
}
WAVELOG_ENABLED = _cfg_bool("WAVELOG_ENABLED", True)
QRZ_ENABLED = _cfg_bool("QRZ_ENABLED", True)
CLUSTER_ENABLED = _cfg_bool("CLUSTER_ENABLED", False)
WINKEYER_ENABLED = _cfg_bool("WINKEYER_ENABLED", True)
WINKEYER_PORT = _cfg_value("WINKEYER_PORT", "COM11")
WINKEYER_BAUDRATE = _cfg_int("WINKEYER_BAUDRATE", 1200)
WINKEYER_DEFAULT_WPM = _cfg_int("WINKEYER_DEFAULT_WPM", 20)
WINKEYER_MEMORIES = _cfg_value("WINKEYER_MEMORIES", {'M1': 'OM0RX', 'M2': '5NN TU', 'M3': 'QSL TU DE OM0RX', 'M4': 'TNX'})

# Wavelog local read-cache sync interval (seconds)
WAVELOG_SYNC_INTERVAL = _cfg_int("WAVELOG_SYNC_INTERVAL", 60)
WAVELOG_OUTBOX_RETRY_INTERVAL = _cfg_int("WAVELOG_OUTBOX_RETRY_INTERVAL", 15)
WAVELOG_OUTBOX_RETRY_BATCH_SIZE = _cfg_int("WAVELOG_OUTBOX_RETRY_BATCH_SIZE", 50)

# === FT8/FT4 Digital Mode Configuration ===
FT8_ENABLED = _cfg_bool("FT8_ENABLED", True)
FT8_MODE = _cfg_value("FT8_MODE", "FT8")  # "FT8" or "FT4"
FT8_MYCALL = _cfg_value("FT8_MYCALL", "OM0RX")
FT8_MYGRID = _cfg_value("FT8_MYGRID", "JN88")
FT8_NETWORK_SERVER = _cfg_value("FT8_NETWORK_SERVER", "192.168.0.199:4992")  # FlexRadio CAT control (host:port)
FT8_RIG_BACKEND = _cfg_value("FT8_RIG_BACKEND", "auto")
FT8_HAMLIB_RIGCTL_PATH = _cfg_value("FT8_HAMLIB_RIGCTL_PATH", "")
FT8_HAMLIB_MODEL = _cfg_int("FT8_HAMLIB_MODEL", 23005)  # FlexRadio SmartSDR Slice A
FT8_HAMLIB_RIG_PATH = _cfg_value("FT8_HAMLIB_RIG_PATH", "")
FT8_HAMLIB_TIMEOUT_SECONDS = _cfg_float("FT8_HAMLIB_TIMEOUT_SECONDS", 3.0)
FT8_AUDIO_INPUT = _cfg_value("FT8_AUDIO_INPUT", "default")  # Audio input device name or "default" or "flexradio"
FT8_AUDIO_OUTPUT = _cfg_value("FT8_AUDIO_OUTPUT", "default")  # Audio output device name or "default" or "flexradio"
FT8_SAMPLE_RATE = _cfg_int("FT8_SAMPLE_RATE", 12000)  # Audio sample rate in Hz
FT8_AUTO_SEQUENCE = _cfg_bool("FT8_AUTO_SEQUENCE", False)  # Enable automatic QSO sequencing
FT8_TX_ENABLED = _cfg_bool("FT8_TX_ENABLED", False)  # Enable TX capability
FT8_LEGACY_TX_ROUTES_ENABLED = _cfg_bool("FT8_LEGACY_TX_ROUTES_ENABLED", False)  # Opt-in only compatibility TX routes
FT8_WATERFALL_HEIGHT = _cfg_int("FT8_WATERFALL_HEIGHT", 100)  # Waterfall display height in pixels
FT8_USE_FLEXRADIO_AUDIO = _cfg_bool("FT8_USE_FLEXRADIO_AUDIO", True)  # Use FlexRadio DAX audio channels
FT8_PTT_METHOD = _cfg_value("FT8_PTT_METHOD", "CAT")  # PTT method: "CAT", "VOX", "DTR", "RTS"
FT8_OPERATOR_SETTINGS = _cfg_dict("FT8_OPERATOR_SETTINGS", {})
