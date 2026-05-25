import os
from pathlib import Path
# config.py (ver5.8)
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"

try:
    import config_local as _local_config
except ImportError:
    _local_config = None


def _cfg_value(name, default):
    if name in os.environ:
        return os.environ[name]
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


DB_HOST = _cfg_value("DB_HOST", "")
DB_PORT = _cfg_int("DB_PORT", 3306)
DB_NAME = _cfg_value("DB_NAME", "")
DB_USER = _cfg_value("DB_USER", "")
DB_PASS = _cfg_value("DB_PASS", "")
MY_STATION = _cfg_value("MY_STATION", "OM0RX")
CLUSTERS = _cfg_value("CLUSTERS", [])
CLUSTER_HOST = _cfg_value("CLUSTER_HOST", "localhost")
CLUSTER_PORT = _cfg_int("CLUSTER_PORT", 7373)
CLUSTER_USER = _cfg_value("CLUSTER_USER", "N0CALL")
CLUSTER_PASS = _cfg_value("CLUSTER_PASS", "")
LOGIN_SCRIPT  = []

SDR_UDP_HOST = _cfg_value("SDR_UDP_HOST", "127.0.0.1")
SDR_UDP_PORT = _cfg_int("SDR_UDP_PORT", 12061)
UDP_ENABLED_DEFAULT = _cfg_bool("UDP_ENABLED_DEFAULT", False)
FLEX_TCP_HOST = _cfg_value("FLEX_TCP_HOST", "192.168.0.199")
FLEX_TCP_PORT = _cfg_int("FLEX_TCP_PORT", 4992)
FLEX_ENABLED_DEFAULT = _cfg_bool("FLEX_ENABLED_DEFAULT", True)
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
LOG_LEVEL = "DEBUG"
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
    "WWFF":      r"\bWWFF\b|\bWFF\b|\b[A-Z]{2}FF-\d{4}",
    "CASTLE":    r"\bWCA\b|\bCASTLE\b",
    "LIGHTHOUSE":r"\bLH\b|\bLGT\b|\bLIGHTHOUSE\b",
    "CONTEST":   r"\bTEST\b|\bCONTEST\b|\bCWT\b",
    "IARU":      r"\bIARU\b"
}


# Preset values that pre-seed the Special dropdown in the UI.
# Do not include '(none)' — it is auto-added so you can filter untagged rows.
SPECIAL_PRESET = ["POTA", "SOTA", "IOTA", "WWFF", "CONTEST", "LIGHTHOUSE", "CASTLE", "IARU"]

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
ROTOR_AUTO_DELAY_SEC = _cfg_int("ROTOR_AUTO_DELAY_SEC", 5)
WSJTX_ENABLED = _cfg_bool("WSJTX_ENABLED", True)
WSJTX_UDP_PORT = _cfg_int("WSJTX_UDP_PORT", 2237)
WSJTX_UDP_MULTICAST = _cfg_value("WSJTX_UDP_MULTICAST", "224.0.0.1")
WSJTX_WS_PORT = _cfg_int("WSJTX_WS_PORT", 8091)
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

# Wavelog to DuckDB sync interval (seconds)
WAVELOG_SYNC_INTERVAL = _cfg_int("WAVELOG_SYNC_INTERVAL", 60)

# === FT8/FT4 Digital Mode Configuration ===
FT8_ENABLED = _cfg_bool("FT8_ENABLED", True)
FT8_MODE = _cfg_value("FT8_MODE", "FT8")  # "FT8" or "FT4"
FT8_MYCALL = _cfg_value("FT8_MYCALL", "OM0RX")
FT8_MYGRID = _cfg_value("FT8_MYGRID", "JN88")
FT8_NETWORK_SERVER = _cfg_value("FT8_NETWORK_SERVER", "192.168.0.199:4992")  # FlexRadio CAT control (host:port)
FT8_AUDIO_INPUT = _cfg_value("FT8_AUDIO_INPUT", "default")  # Audio input device name or "default" or "flexradio"
FT8_AUDIO_OUTPUT = _cfg_value("FT8_AUDIO_OUTPUT", "default")  # Audio output device name or "default" or "flexradio"
FT8_SAMPLE_RATE = _cfg_int("FT8_SAMPLE_RATE", 12000)  # Audio sample rate in Hz
FT8_AUTO_SEQUENCE = _cfg_bool("FT8_AUTO_SEQUENCE", False)  # Enable automatic QSO sequencing
FT8_TX_ENABLED = _cfg_bool("FT8_TX_ENABLED", False)  # Enable TX capability
FT8_WATERFALL_HEIGHT = _cfg_int("FT8_WATERFALL_HEIGHT", 100)  # Waterfall display height in pixels
FT8_USE_FLEXRADIO_AUDIO = _cfg_bool("FT8_USE_FLEXRADIO_AUDIO", True)  # Use FlexRadio DAX audio channels
FT8_PTT_METHOD = _cfg_value("FT8_PTT_METHOD", "CAT")  # PTT method: "CAT", "VOX", "DTR", "RTS"
