"""Normalized Activity Intelligence domain models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


def compact_dict(value: Any) -> Any:
    """Convert dataclasses to dictionaries and drop empty optional values."""
    if hasattr(value, "__dataclass_fields__"):
        value = asdict(value)
    if isinstance(value, list):
        return [compact_dict(item) for item in value]
    if isinstance(value, dict):
        return {
            key: compact_dict(item)
            for key, item in value.items()
            if item not in (None, "", [], {})
        }
    return value


@dataclass
class SourceSyncState:
    source_id: str
    enabled: bool = True
    last_success_at_utc: str | None = None
    last_attempt_at_utc: str | None = None
    last_http_status: int | None = None
    last_error: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    next_allowed_at_utc: str | None = None
    consecutive_failures: int = 0


@dataclass
class RawFetchResult:
    source_id: str
    url: str
    fetched_at_utc: str
    body: str
    http_status: int | None = None
    etag: str | None = None
    last_modified: str | None = None
    content_type: str | None = None


@dataclass
class ActivityTag:
    type: str
    label: str
    confidence: float
    source_id: str
    ref_id: str | None = None


@dataclass
class SpotAction:
    id: str
    label: str
    type: Literal["TUNE", "BEAM", "OPEN_DETAILS", "WATCH", "FILL_LOG_FIELDS"]
    payload: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    reason_if_disabled: str | None = None


@dataclass
class Dxpedition:
    id: str
    source_id: str
    callsign: str
    aliases: list[str] = field(default_factory=list)
    dxcc_entity: str | None = None
    dxcc_code: int | None = None
    iota: str | None = None
    start_date_utc: str | None = None
    end_date_utc: str | None = None
    status: Literal["UPCOMING", "ACTIVE", "EXPIRED", "UNKNOWN"] = "UNKNOWN"
    bands: list[str] = field(default_factory=list)
    modes: list[str] = field(default_factory=list)
    qsl_info: str | None = None
    lotw_expected: bool | None = None
    clublog_expected: bool | None = None
    oqrs_url: str | None = None
    info_url: str | None = None
    source_url: str = ""
    notes: str | None = None
    last_seen_spot_utc: str | None = None
    last_updated_utc: str = ""


@dataclass
class ContestEvent:
    id: str
    source_id: str
    name: str
    start_utc: str
    end_utc: str
    modes: list[str] = field(default_factory=list)
    bands: list[str] = field(default_factory=list)
    geographic_focus: str | None = None
    participation: str | None = None
    classes: list[str] = field(default_factory=list)
    exchange: str | None = None
    work_stations_rule: str | None = None
    qso_points_rule: str | None = None
    multipliers_rule: str | None = None
    score_calculation: str | None = None
    log_due_utc: str | None = None
    log_upload_url: str | None = None
    rules_url: str | None = None
    cabrillo_name: str | None = None
    source_url: str = ""
    rule_confidence: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    last_updated_utc: str = ""


@dataclass
class PortableReference:
    program: Literal["POTA", "SOTA", "WWFF", "PARKSNPEAKS"]
    reference: str
    name: str | None = None
    association: str | None = None
    region: str | None = None
    grid: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    elevation_m: float | None = None
    location_desc: str | None = None
    official_url: str | None = None
    source_id: str = ""
    source_payload_hash: str | None = None
    last_verified_utc: str | None = None


@dataclass
class PortableActivation:
    id: str
    program: Literal["POTA", "SOTA", "WWFF", "PARKSNPEAKS"]
    type: Literal["ACTIVE_SPOT", "SCHEDULED", "ALERT", "AGENDA"]
    activator_call: str
    references: list[str]
    frequency_khz: float | None = None
    mode: str | None = None
    spotter_call: str | None = None
    comments: str | None = None
    start_utc: str | None = None
    end_utc: str | None = None
    expires_utc: str | None = None
    source_id: str = ""
    source_url: str | None = None
    raw_payload_hash: str = ""
    last_seen_utc: str = ""


@dataclass
class SpaceWeatherSnapshot:
    id: str
    timestamp_utc: str
    kp: float | None = None
    xray_class: str | None = None
    noaa_r_scale: str | None = None
    noaa_g_scale: str | None = None
    solar_wind_speed_kms: float | None = None
    solar_wind_bz_nt: float | None = None
    solar_flux_sfu: float | None = None
    drap_affected_frequency_mhz: float | None = None
    source_ids: list[str] = field(default_factory=list)
    raw_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class PropagationAssessment:
    score: int
    label: Literal["EXCELLENT", "GOOD", "FAIR", "MARGINAL", "POOR", "UNKNOWN"]
    confidence: float
    reasons: list[str] = field(default_factory=list)
    path_type: Literal["SHORT_PATH", "LONG_PATH", "GRAYLINE", "POLAR", "UNKNOWN"] = "UNKNOWN"


@dataclass
class RbnSpot:
    id: str
    timestamp_utc: str
    spotted_call: str
    skimmer_call: str
    frequency_khz: float
    band: str | None = None
    mode: str | None = None
    snr_db: float | None = None
    speed_wpm: float | None = None
    cq_flag: bool | None = None
    spot_comment: str | None = None
    skimmer_grid: str | None = None
    skimmer_lat: float | None = None
    skimmer_lon: float | None = None
    distance_km: float | None = None
    bearing_from_station_deg: float | None = None
    source_port: int | None = None
    raw_line: str = ""


@dataclass
class StationStateSample:
    id: str
    timestamp_utc: str
    frequency_khz: float | None = None
    mode: str | None = None
    rotator_bearing_deg: float | None = None
    antenna_name: str | None = None
    power_watts: float | None = None
    tx_state: bool | None = None
