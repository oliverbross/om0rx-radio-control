"""Local configuration template.

Copy this file to config_local.py and fill in values for your station.
config_local.py is ignored by Git.
"""

# Database
DB_HOST = "127.0.0.1"
DB_PORT = 3306
DB_NAME = ""
DB_USER = ""
DB_PASS = ""
DATABASE_BACKEND = "auto"
POSTGRES_DSN = ""
POSTGRES_CONNECT_TIMEOUT_SECONDS = 2
POSTGRES_RETRY_COOLDOWN_SECONDS = 30

# Station
MY_STATION = "OM0RX"

# DX cluster
CLUSTERS = []
CLUSTER_HOST = "localhost"
CLUSTER_PORT = 7373
CLUSTER_USER = "N0CALL"
CLUSTER_PASS = ""

# Wavelog
WAVELOG_API_URL = ""
WAVELOG_API_KEY = ""
WAVELOG_STATION_ID = "1"

# QRZ
QRZ_USERNAME = ""
QRZ_PASSWORD = ""

# FlexRadio / local station network
FLEX_TCP_HOST = "192.168.0.199"
FLEX_TCP_PORT = 4992
SDR_UDP_HOST = "127.0.0.1"
SDR_UDP_PORT = 12061

# Elecraft amplifier/tuner (direct COM ports, or VSPE virtual endpoints)
KPA500_ENABLED = False
KPA500_PORT = "COM6"
KPA500_BAUDRATE = 38400
DIGITAL_KPA_POLICY = "operate"  # Master switch: operate uses the per-band digital matrix
KAT500_ENABLED = False
KAT500_PORT = "COM11"
KAT500_BAUDRATE = 38400
ELECRAFT_LEGACY_CONTROL_ENABLED = False  # Unsafe migration escape hatch; keep False normally
ELECRAFT_FOLLOW_RADIO = True
STATION_COORDINATOR_COMMISSIONED = False  # Enable only after physical route/interlock commissioning
STATION_AMPLIFIER_ALLOWED_BANDS = ["160m", "80m", "40m", "30m", "15m", "12m", "10m", "6m"]
STATION_AMPLIFIER_DRIVE_W = {band: 25 for band in ("160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m")}
STATION_BAREFOOT_DRIVE_W = {band: 25 for band in ("160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m")}
# DIGU, DIGL, RTTY, and every other non-voice/non-CW FLEX mode use these
# independent settings. DIGITAL_KPA_POLICY remains the global master switch.
STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS = ["160m", "80m", "40m", "30m", "15m", "12m", "10m", "6m"]
STATION_DIGITAL_AMPLIFIER_DRIVE_W = {band: 25 for band in ("160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m")}
STATION_ROUTE_VERIFY_TTL_SECONDS = 10.0
STATION_TUNE_POWER_W = 20
STATION_TUNE_TARGET_SWR = 1.5
STATION_TUNE_ABORT_SWR = 3.0
STATION_TUNE_TIMEOUT_SECONDS = 30.0
STATION_TELEMETRY_INTERVAL_SECONDS = 5.0
STATION_TELEMETRY_RETENTION_DAYS = 7
# Optional site-specific alarm limits. Leave unset unless your installation has
# documented limits; the alarm service never guesses hardware thresholds.
# KPA500_TEMPERATURE_MAX_C = 80
# KPA500_VOLTAGE_MIN_V = 45
# KPA500_VOLTAGE_MAX_V = 55
KAT500_ANTENNA_POLICY = {
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
}
KAT500_ANTENNA_NAMES = {
    "1": "KAT ANT1",
    "2": "KAT ANT2",
    "3": "KAT ANT3",
}

# Rotor
ROTOR_HOST = "192.168.0.198"
ROTOR_PORT = 4001
ROTOR_HOME_GRID = "JN88TQ"
ROTOR_HOME_LAT = 48.17
ROTOR_HOME_LON = 17.08

# WSJT-X bridge
WSJTX_UDP_PORT = 2237
WSJTX_UDP_MULTICAST = "224.0.0.1"
WSJTX_WS_PORT = 8091
