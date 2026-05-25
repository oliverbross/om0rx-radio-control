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
