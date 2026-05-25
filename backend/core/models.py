"""
Pydantic models for the FlexRadio Web Control API
Extracted from main.py for better organization and reusability
"""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any


# === Radio Control Models ===

class FrequencyRequest(BaseModel):
    frequency: float


class ModeRequest(BaseModel):
    mode: str


class BandRequest(BaseModel):
    band: str


class FilterRequest(BaseModel):
    filter_lo: int
    filter_hi: int


class SliderRequest(BaseModel):
    value: int


class ToggleRequest(BaseModel):
    enabled: bool


class AGCRequest(BaseModel):
    mode: str  # off, slow, med, fast


class DSPRequest(BaseModel):
    control: str  # nb, nr, anf, apf
    enabled: bool


class DSPLevelRequest(BaseModel):
    control: str  # nb_level, nr_level, anf_level, apf_level
    value: int  # 0-100


class RITXITRequest(BaseModel):
    enabled: bool
    freq_hz: Optional[int] = 0


class RX2Request(BaseModel):
    frequency: Optional[float] = None
    enabled: bool


class SplitRequest(BaseModel):
    enabled: bool
    tx_frequency: Optional[float] = None


class SpotTuneRequest(BaseModel):
    frequency: float
    mode: Optional[str] = None


# === QSO Logging Models ===

class QSORequest(BaseModel):
    callsign: str
    frequency: float
    mode: str
    # RST values can be integers (SSB/CW) or strings (FT8/FT4 SNR like "-12", "+15")
    rst_sent: Optional[str] = None
    rst_received: Optional[str] = None
    date: Optional[str] = None
    time_off: Optional[str] = None
    name: Optional[str] = None
    qth: Optional[str] = None
    gridsquare: Optional[str] = None
    notes: Optional[str] = None
    pota: Optional[str] = None
    sota: Optional[str] = None
    iota: Optional[str] = None
    wwff: Optional[str] = None
    date_time: Optional[str] = None
    continent: Optional[str] = None
    cq_zone: Optional[int] = None
    itu_zone: Optional[int] = None
    region: Optional[str] = None
    country: Optional[str] = None
    state: Optional[str] = None
    us_county: Optional[str] = None
    tx_pwr: Optional[str] = None
    ant: Optional[str] = None
    qsl_rcvd: Optional[str] = None
    qsl_sent: Optional[str] = None
    lotw_member: Optional[bool] = None
    qsl_manager: Optional[str] = None
    email: Optional[str] = None
    prop_mode: Optional[str] = None
    ant_path: Optional[str] = None
    sat_name: Optional[str] = None
    sat_mode: Optional[str] = None
    freq_rx: Optional[str] = None
    mode_rx: Optional[str] = None


class RecentQSOsRequest(BaseModel):
    callsign: str
    limit: int = 5


# === Rotor Control Models ===

class RotorGotoRequest(BaseModel):
    azimuth: int  # 0-359


class RotorDirectionRequest(BaseModel):
    direction: str  # "N", "S", "E", "W"


class RotorConfigRequest(BaseModel):
    enabled: bool
    host: str
    port: int
    protocol: str  # "DCU-1" or "Yaesu GS-232A"
    timeout: float = 2.5


class RotorAutoModeRequest(BaseModel):
    enabled: bool


class RotorBearingRequest(BaseModel):
    callsign: str
    frequency_khz: Optional[float] = None  # Current frequency (to determine band)
    gridsquare: Optional[str] = None  # Station gridsquare (from QRZ or cty.dat)
    latitude: Optional[float] = None  # Station latitude
    longitude: Optional[float] = None  # Station longitude


class RotorAutoConfigRequest(BaseModel):
    home_grid: str
    home_lat: float
    home_lon: float
    bands: Dict[str, bool]  # Band name -> enabled (e.g., {"20m": true, "10m": false})
    auto_enabled: bool


# === WSJT-X Integration Models ===

class WSJTXQSORequest(BaseModel):
    """QSO data from WSJT-X to log"""
    call: str
    grid: Optional[str] = None
    mode: str  # "FT8", "FT4", etc.
    frequency_hz: Optional[int] = None  # Frequency in Hz
    # RST values can be integers (SSB/CW) or strings (FT8/FT4 SNR like "-12", "+15")
    rst_sent: Optional[str] = None
    rst_received: Optional[str] = None
    operator: Optional[str] = None
    comments: Optional[str] = None
    qrz_data: Optional[Dict[str, Any]] = None  # Pre-fetched QRZ data


class WSJTXAutoRotateRequest(BaseModel):
    """Auto-rotate request based on DX grid"""
    call: str
    grid: str
    frequency_hz: Optional[int] = None


# === Configuration Models ===

class ConfigUpdate(BaseModel):
    """Configuration update model"""
    config: Dict[str, Any]


# === Spots Models ===

class SpotAddRequest(BaseModel):
    """Request to add a spot to SmartSDR panadapter"""
    callsign: str
    frequency: float  # MHz
    mode: str
    spotter: str = "Web UI"
    comment: str = ""
    tag: Optional[str] = None