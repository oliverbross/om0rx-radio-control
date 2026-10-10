"""Stopped-engine configuration for the packaged MSHV Auto DX runtime.

The native application and the OM0RX settings page share this schema.  MSHV
remains the planner, but every setting exposed here is consumed by its active
``AutoDxerCore`` rather than by a decorative settings dialog.
"""

from __future__ import annotations

import configparser
from io import StringIO
import os
from pathlib import Path
import re
from typing import Any

from fastapi import HTTPException

from radio_control.persistence import atomic_write_json, atomic_write_text, locked_file, read_json_object


ROOT = Path(__file__).resolve().parents[1]
GRID_RE = re.compile(r"^[A-R]{2}[0-9]{2}(?:[A-X]{2})?$", re.IGNORECASE)
CALLSIGN_RE = re.compile(r"^[A-Z0-9/]{3,16}$", re.IGNORECASE)
HOST_RE = re.compile(r"^[A-Z0-9.-]{1,253}$", re.IGNORECASE)
LOCAL_TIME_RE = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
ALLOWED_BANDS = {
    3: "160m", 4: "80m", 6: "40m", 7: "30m", 8: "20m",
    9: "17m", 10: "15m", 11: "12m", 12: "10m", 14: "6m",
}
DEFAULT_ENABLED_BANDS = (3, 4, 6, 7, 8, 9, 10, 11, 12)
US_STATE_DEFAULTS = {
    "enabled": True,
    "minimum_worked": 3,
    "require_confirmation": True,
    "prefer_lotw": True,
    "missing_confirmation_weight": 8500,
    "under_quota_weight": 7000,
}
DXPEDITION_DEFAULTS = {
    "enabled": True,
    "allow_same_band_off_standard_qsy": True,
    "allow_cross_band_qsy": True,
    "chase_scope": "needed-only",
    "min_spotters": 1,
    "max_spot_age_seconds": 120,
    "rx_audio_hz": 1000,
    "tx_offset_hz": 1000,
    "return_to_standard": True,
}
CLUSTER_CHASE_DEFAULTS = {
    "enabled": True,
    "chase_new_dxcc": True,
    "chase_band_dxcc": True,
    "chase_us_states": True,
    "chase_dxpeditions": True,
    "chase_unconfirmed_continents": True,
    "chase_unconfirmed_cq_zones": True,
    "chase_unconfirmed_itu_zones": True,
    "min_spotters": 1,
    "consensus_spotters": 2,
    "queue_limit": 12,
}
AWARD_HUNTING_DEFAULTS = {
    "enabled": True,
    # Award gaps are deliberately cumulative: one QSO may advance several
    # awards and receives the sum of every applicable weight.
    "stack_scores": True,
    "new_dxcc_weight": 10000,
    "new_dxcc_band_weight": 1000,
    "unconfirmed_dxcc_weight": 8500,
    "new_continent_weight": 2500,
    "new_cq_zone_weight": 2200,
    "new_itu_zone_weight": 2000,
    "new_grid_weight": 500,
}
REFERENCE_HUNTING_DEFAULTS = {
    "enabled": True,
    # Program switches are independent.  They are never represented as an
    # enum or campaign mode because portable awards must compose with DXCC.
    "pota_enabled": True,
    "sota_enabled": True,
    "wwff_enabled": True,
    "pota_weight": 1800,
    "sota_weight": 1800,
    "wwff_weight": 1400,
    "new_reference_weight": 2500,
    "new_reference_band_weight": 1000,
    "new_reference_band_mode_weight": 500,
    "max_activation_age_seconds": 900,
    "require_local_decode": True,
}
PROPAGATION_ADAPTATION_DEFAULTS = {
    "enabled": True,
    "window_seconds": 900,
    "unique_decode_weight": 20,
    "distant_decode_weight": 40,
    "successful_qso_weight": 250,
    "max_band_boost": 1500,
}
PILEUP_STRATEGY_DEFAULTS = {
    "enabled": True,
    "audio_offsets_hz": [0, -120, 120, -240, 240],
    "rotate_after_attempts": 2,
    "revisit_delay_seconds": 120,
}
DIRECTED_CALLERS_DEFAULTS = {
    "enabled": True,
    "inbox_size": 8,
    "max_age_seconds": 90,
}
CAMPAIGN_DEFAULTS = {
    "profile": "balanced",
    "dxcc_weight_percent": 100,
    "state_weight_percent": 100,
    "zone_weight_percent": 100,
    "grid_weight_percent": 100,
    "reference_weight_percent": 100,
}
CAMPAIGN_PRESETS = {
    "balanced": (100, 100, 100, 100, 100),
    "dxcc-challenge": (175, 75, 100, 75, 75),
    "five-band-dxcc": (200, 50, 75, 50, 50),
    "worked-all-states": (75, 200, 75, 75, 50),
    "waz": (75, 50, 200, 50, 50),
    "itu-zones": (75, 50, 200, 50, 50),
    "grids": (75, 50, 50, 200, 50),
    "references": (75, 50, 50, 50, 200),
}
CAMPAIGN_WEIGHT_NAMES = (
    "dxcc_weight_percent", "state_weight_percent", "zone_weight_percent",
    "grid_weight_percent", "reference_weight_percent",
)
OUTCOME_LEARNING_DEFAULTS = {
    "enabled": True,
    "telemetry_file": "logs/autodx-outcomes.jsonl",
}
AUTO_DX_MODES = ("FT8", "FT4")
TARGET_PRIORITY_DEFAULTS = {
    # The names below intentionally mirror DigitalAutomationSettings.to_dict().
    # MSHV remains the planner; this module only persists the native policy.
    "non_europe": 7500,
    "new_dxcc": 10000,
    "new_grid": 500,
    # Compatibility alias consumed by the current Phase-1 native scorer.
    "new_band_slot": 1000,
    "calling_me": 400,
    "cq": 200,
    "snr_per_db": 10,
}
TARGET_PRIORITY_KEYS = {
    "non_europe": "NonEuropeBoost",
    "new_dxcc": "NewDxcc",
    "new_band_slot": "NewBandSlot",
    "new_grid": "NewGrid",
    "calling_me": "CallingMe",
    "cq": "Cq",
    "snr_per_db": "SnrPerDb",
}
CONTINENTS = ("EU", "AF", "OC", "AS", "SA", "NA", "AN")
NEED_DIMENSIONS = ("call", "dxcc", "continent", "grid", "cq_zone", "itu_zone")
NATIVE_POLICY_DEFAULTS = {
    "prefer_non_europe": True,
    # The default new/new-on-band selections are active policy, not inert
    # decorations. An explicit false in an existing INI is still preserved.
    "filter_matrix_enabled": True,
    "filter_lotw_only": False,
    "allow_band_dxcc_outside_continent": True,
    "treat_73_as_cq": False,
    "watch_unconfirmed_dxcc": True,
    "call_window_seconds": 120,
    "max_consecutive_windows": 1,
    "same_target_revisit_delay_seconds": 1800,
    "recent_qso_cooldown_seconds": 3600,
    "min_band_dwell_seconds": 180,
    "engaged_completion_grace_seconds": 120,
}
NATIVE_POLICY_INI_KEYS = {
    "prefer_non_europe": ("TargetPriority", "PreferNonEurope"),
    "filter_matrix_enabled": ("Eligibility", "FilterMatrixEnabled"),
    "filter_lotw_only": ("Eligibility", "FilterLotwOnly"),
    "allow_band_dxcc_outside_continent": (
        "Eligibility", "AllowBandDxccOutsideContinent",
    ),
    "treat_73_as_cq": ("Eligibility", "Treat73AsCq"),
    "watch_unconfirmed_dxcc": ("Eligibility", "WatchUnconfirmedDxcc"),
    "call_window_seconds": ("Attempt", "CallWindowSeconds"),
    "max_consecutive_windows": ("Attempt", "MaxConsecutiveWindows"),
    "same_target_revisit_delay_seconds": ("Attempt", "SameTargetRetrySeconds"),
    "recent_qso_cooldown_seconds": ("Attempt", "RecentQsoCooldownSeconds"),
    "min_band_dwell_seconds": ("BandSwitching", "MinimumDwellSeconds"),
    "engaged_completion_grace_seconds": ("Attempt", "EngagedCompletionGraceSeconds"),
}
NATIVE_POLICY_BOUNDS = {
    "call_window_seconds": (120, 240),
    "max_consecutive_windows": (1, 20),
    "same_target_revisit_delay_seconds": (0, 86400),
    "recent_qso_cooldown_seconds": (0, 86400),
    "min_band_dwell_seconds": (0, 7200),
    "engaged_completion_grace_seconds": (15, 120),
}
AUTOMATION_TIMING_DEFAULTS = {
    "quiet_band_seconds": 300,
    "target_heard_fresh_seconds": 60,
    "cross_band_verify_seconds": 60,
    "band_switch_cooldown_seconds": 120,
    "persist_new_dxcc_while_heard": True,
    "persist_new_band_slot_while_heard": True,
}
AUTOMATION_TIMING_INI_KEYS = {
    "quiet_band_seconds": "QuietBandSeconds",
    "target_heard_fresh_seconds": "TargetHeardFreshSeconds",
    "cross_band_verify_seconds": "CrossBandVerifySeconds",
    "band_switch_cooldown_seconds": "BandSwitchCooldownSeconds",
    "persist_new_dxcc_while_heard": "PersistNewDxccWhileHeard",
    "persist_new_band_slot_while_heard": "PersistNewBandSlotWhileHeard",
}
AUTOMATION_TIMING_BOUNDS = {
    "quiet_band_seconds": (60, 3600),
    "target_heard_fresh_seconds": (15, 300),
    "cross_band_verify_seconds": (15, 300),
    "band_switch_cooldown_seconds": (0, 1800),
}
STARTUP_SAFETY_PATH = ROOT / "settings" / "mshv_startup_safety.json"


def runtime_path() -> Path:
    return Path(os.environ.get("OM0RX_MSHV_RUNTIME", ROOT / "data/build/mshv-auto-dx/runtime"))


def settings_path() -> Path:
    return runtime_path() / "settings" / "autodx.ini"


def _write_settings_text(path: Path, content: str) -> None:
    """Atomically save settings without adding undeclared files to runtime."""
    backup_path = runtime_path().parent / "operator-backups" / "mshv-settings" / "autodx.ini.bak"
    with locked_file(path):
        if path.is_file():
            atomic_write_text(backup_path, path.read_text(encoding="utf-8"), backup=False)
        atomic_write_text(path, content, backup=False)


def _parser(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    if path.exists():
        with locked_file(path):
            parser.read(path, encoding="utf-8")
    return parser


def _integer(parser: configparser.ConfigParser, section: str, key: str, default: int) -> int:
    try:
        return parser.getint(section, key, fallback=default)
    except ValueError:
        return default


def _boolean(parser: configparser.ConfigParser, section: str, key: str, default: bool) -> bool:
    try:
        return parser.getboolean(section, key, fallback=default)
    except ValueError:
        return default


def _min_signal(parser: configparser.ConfigParser) -> int:
    value = _integer(
        parser, "Eligibility", "MinSignal",
        _integer(parser, "SpotSources", "MinSNR", -20),
    )
    return max(-30, min(0, value))


def _qt_csv_items(raw: str) -> list[str]:
    """Parse a comma-separated QString persisted by QSettings.

    Qt quotes values containing commas in INI files.  ConfigParser preserves
    those outer quotes, so splitting first would otherwise turn the first and
    last items into values such as ``\"3`` and ``12\"``.
    """
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return [item.strip() for item in value.split(",") if item.strip()]


def _enabled_bands(parser: configparser.ConfigParser) -> list[int]:
    raw = parser.get(
        "BandSelection", "EnabledBands",
        fallback=",".join(str(item) for item in DEFAULT_ENABLED_BANDS),
    )
    bands: list[int] = []
    for token in _qt_csv_items(raw):
        try:
            band = int(token.strip())
        except ValueError:
            continue
        if band in ALLOWED_BANDS and band not in bands:
            bands.append(band)
    return bands or list(DEFAULT_ENABLED_BANDS)


def _auto_dx_modes(parser: configparser.ConfigParser) -> list[str]:
    configured = parser.has_option("AutoDx", "Modes")
    modes = [item.strip().upper() for item in parser.get("AutoDx", "Modes", fallback="FT8,FT4").split(",")]
    accepted = [mode for mode in AUTO_DX_MODES if mode in modes]
    return accepted if configured else list(AUTO_DX_MODES)


def _cluster_servers(parser: configparser.ConfigParser) -> list[dict[str, Any]]:
    count = max(0, min(16, _integer(parser, "DxClusterServers", "Count", 0)))
    servers: list[dict[str, Any]] = []
    for index in range(count):
        parts = parser.get("DxClusterServers", f"Server{index}", fallback="").split("|")
        if len(parts) < 4:
            continue
        try:
            port = int(parts[2])
        except ValueError:
            continue
        if not 1 <= port <= 65535 or not HOST_RE.fullmatch(parts[1].strip()):
            continue
        servers.append({
            "name": parts[0].strip() or f"Server {index + 1}",
            "host": parts[1].strip(),
            "port": port,
            "enabled": parts[3].strip().lower() == "true",
        })
    return servers


def _automation_timing(
    parser: configparser.ConfigParser, *, call_window_seconds: int, max_consecutive_windows: int,
) -> dict[str, Any]:
    timing: dict[str, Any] = {}
    for name, default in AUTOMATION_TIMING_DEFAULTS.items():
        ini_key = AUTOMATION_TIMING_INI_KEYS[name]
        timing[name] = (
            _boolean(parser, "AutomationTiming", ini_key, default)
            if isinstance(default, bool)
            else _integer(parser, "AutomationTiming", ini_key, default)
        )
    for name, (minimum, maximum) in AUTOMATION_TIMING_BOUNDS.items():
        timing[name] = max(minimum, min(maximum, timing[name]))
    # This is an observation derived from the canonical attempt policy, never
    # an independently writable legacy AutomationTiming/NormalCallSeconds.
    timing["normal_call_seconds"] = call_window_seconds * max_consecutive_windows
    return timing


def _filter_dimensions(parser: configparser.ConfigParser, *, on_band: bool) -> dict[str, bool]:
    return {
        name: _boolean(
            parser,
            "Eligibility",
            ("FilterBand" if on_band else "FilterNew") + {
                "call": "Call", "dxcc": "Dxcc", "continent": "Continent",
                "grid": "Grid", "cq_zone": "CqZone", "itu_zone": "ItuZone",
            }[name],
            (name in {"call", "dxcc", "grid"}) if not on_band else (name in {"call", "grid"}),
        )
        for name in NEED_DIMENSIONS
    }


def _selection_order(parser: configparser.ConfigParser) -> str:
    value = parser.get("Selection", "Order", fallback="score").strip().lower()
    return value if value in {"score", "last"} else "score"


def _native_policy(parser: configparser.ConfigParser) -> dict[str, Any]:
    policy: dict[str, Any] = {}
    for name, default in NATIVE_POLICY_DEFAULTS.items():
        section, key = NATIVE_POLICY_INI_KEYS[name]
        policy[name] = (
            _boolean(parser, section, key, default)
            if isinstance(default, bool)
            else _integer(parser, section, key, default)
        )
    for name, (minimum, maximum) in NATIVE_POLICY_BOUNDS.items():
        policy[name] = max(minimum, min(maximum, policy[name]))
    if (
        not parser.has_option("Attempt", "EngagedCompletionGraceSeconds")
        and parser.has_option("AutoDX", "EngagedCompletionGraceSeconds")
    ):
        # Compatibility for the short-lived accidental path. New writes and
        # native authority use Attempt/EngagedCompletionGraceSeconds.
        policy["engaged_completion_grace_seconds"] = max(
            15,
            min(120, _integer(parser, "AutoDX", "EngagedCompletionGraceSeconds", 120)),
        )
    policy["call_window_seconds"] = 240 if policy["call_window_seconds"] >= 240 else 120
    policy["engaged_completion_grace_seconds"] = (
        (policy["engaged_completion_grace_seconds"] + 14) // 15
    ) * 15
    raw_continents = parser.get("Eligibility", "FilterContinents", fallback=",".join(CONTINENTS))
    requested_continents = {item.upper() for item in _qt_csv_items(raw_continents)}
    enabled_continents = [continent for continent in CONTINENTS if continent in requested_continents]
    return {
        **policy,
        "filter_new": _filter_dimensions(parser, on_band=False),
        "filter_new_on_band": _filter_dimensions(parser, on_band=True),
        "filter_continents": enabled_continents,
        "selection_order": _selection_order(parser),
    }


def _band_schedules(parser: configparser.ConfigParser) -> dict[str, dict[str, Any]]:
    schedules: dict[str, dict[str, Any]] = {}
    for band in ALLOWED_BANDS:
        start = parser.get("BandSchedules", f"Band{band}Start", fallback="18:00").strip()
        end = parser.get("BandSchedules", f"Band{band}End", fallback="06:00").strip()
        schedules[str(band)] = {
            "restricted": _boolean(parser, "BandSchedules", f"Band{band}Restricted", band in {3, 4}),
            "start": start if LOCAL_TIME_RE.fullmatch(start) else "18:00",
            "end": end if LOCAL_TIME_RE.fullmatch(end) else "06:00",
        }
    return schedules


def _us_states(parser: configparser.ConfigParser) -> dict[str, Any]:
    raw_bands = parser.get(
        "USStates", "Bands", fallback=",".join(str(item) for item in DEFAULT_ENABLED_BANDS),
    )
    bands: list[int] = []
    for token in _qt_csv_items(raw_bands):
        try:
            band = int(token)
        except ValueError:
            continue
        if band in DEFAULT_ENABLED_BANDS and band not in bands:
            bands.append(band)
    return {
        "enabled": _boolean(parser, "USStates", "Enabled", True),
        "minimum_worked": max(1, min(10, _integer(parser, "USStates", "MinimumWorked", 3))),
        "require_confirmation": _boolean(parser, "USStates", "RequireConfirmation", True),
        "prefer_lotw": _boolean(parser, "USStates", "PreferLotw", True),
        "missing_confirmation_weight": max(0, min(100000, _integer(parser, "USStates", "MissingConfirmationWeight", 8500))),
        "under_quota_weight": max(0, min(100000, _integer(parser, "USStates", "UnderQuotaWeight", 7000))),
        "bands": bands or list(DEFAULT_ENABLED_BANDS),
    }


def _dxpedition(parser: configparser.ConfigParser) -> dict[str, Any]:
    scope = parser.get("Dxpedition", "ChaseScope", fallback="needed-only").strip().lower()
    if scope not in {"needed-only", "any-active"}:
        scope = "needed-only"
    return {
        "enabled": _boolean(parser, "Dxpedition", "Enabled", True),
        "allow_same_band_off_standard_qsy": _boolean(parser, "Dxpedition", "AllowSameBandOffStandardQsy", True),
        "allow_cross_band_qsy": _boolean(parser, "Dxpedition", "AllowCrossBandQsy", True),
        "chase_scope": scope,
        "min_spotters": max(1, min(20, _integer(parser, "Dxpedition", "MinSpotters", 1))),
        "max_spot_age_seconds": max(15, min(1800, _integer(parser, "Dxpedition", "MaxSpotAgeSeconds", 120))),
        "rx_audio_hz": max(300, min(2700, _integer(parser, "Dxpedition", "RxAudioHz", 1000))),
        "tx_offset_hz": max(0, min(2400, _integer(parser, "Dxpedition", "TxOffsetHz", 1000))),
        "return_to_standard": _boolean(parser, "Dxpedition", "ReturnToStandard", True),
    }


def _cluster_chase(parser: configparser.ConfigParser) -> dict[str, Any]:
    return {
        "enabled": _boolean(parser, "ClusterChase", "Enabled", True),
        "chase_new_dxcc": _boolean(parser, "ClusterChase", "ChaseNewDxcc", True),
        "chase_band_dxcc": _boolean(parser, "ClusterChase", "ChaseBandDxcc", True),
        "chase_us_states": _boolean(parser, "ClusterChase", "ChaseUsStates", True),
        "chase_dxpeditions": _boolean(parser, "ClusterChase", "ChaseDxpeditions", True),
        "chase_unconfirmed_continents": _boolean(parser, "ClusterChase", "ChaseUnconfirmedContinents", True),
        "chase_unconfirmed_cq_zones": _boolean(parser, "ClusterChase", "ChaseUnconfirmedCqZones", True),
        "chase_unconfirmed_itu_zones": _boolean(parser, "ClusterChase", "ChaseUnconfirmedItuZones", True),
        "min_spotters": max(1, min(20, _integer(parser, "ClusterChase", "MinSpotters", 1))),
        "consensus_spotters": max(1, min(20, _integer(parser, "ClusterChase", "ConsensusSpotters", 2))),
        "queue_limit": max(1, min(50, _integer(parser, "ClusterChase", "QueueLimit", 12))),
        "continent_filter_override_for_needed_targets": True,
    }


def _read_flat_policy(
    parser: configparser.ConfigParser,
    section: str,
    defaults: dict[str, Any],
    ini_keys: dict[str, str],
    bounds: dict[str, tuple[int, int]] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, default in defaults.items():
        key = ini_keys[name]
        if isinstance(default, bool):
            result[name] = _boolean(parser, section, key, default)
        else:
            value = _integer(parser, section, key, int(default))
            if bounds and name in bounds:
                low, high = bounds[name]
                value = max(low, min(high, value))
            result[name] = value
    return result


AWARD_HUNTING_INI_KEYS = {
    "enabled": "Enabled",
    "stack_scores": "StackScores",
    "new_dxcc_weight": "NewDxccWeight",
    "new_dxcc_band_weight": "NewDxccBandWeight",
    "unconfirmed_dxcc_weight": "UnconfirmedDxccWeight",
    "new_continent_weight": "NewContinentWeight",
    "new_cq_zone_weight": "NewCqZoneWeight",
    "new_itu_zone_weight": "NewItuZoneWeight",
    "new_grid_weight": "NewGridWeight",
}
REFERENCE_HUNTING_INI_KEYS = {
    "enabled": "Enabled",
    "pota_enabled": "PotaEnabled",
    "sota_enabled": "SotaEnabled",
    "wwff_enabled": "WwffEnabled",
    "pota_weight": "PotaWeight",
    "sota_weight": "SotaWeight",
    "wwff_weight": "WwffWeight",
    "new_reference_weight": "NewReferenceWeight",
    "new_reference_band_weight": "NewReferenceBandWeight",
    "new_reference_band_mode_weight": "NewReferenceBandModeWeight",
    "max_activation_age_seconds": "MaxActivationAgeSeconds",
    "require_local_decode": "RequireLocalDecode",
}


def _award_hunting(parser: configparser.ConfigParser) -> dict[str, Any]:
    return _read_flat_policy(
        parser,
        "AwardHunting",
        AWARD_HUNTING_DEFAULTS,
        AWARD_HUNTING_INI_KEYS,
        {name: (0, 100000) for name in AWARD_HUNTING_DEFAULTS if name.endswith("_weight")},
    )


def _reference_hunting(parser: configparser.ConfigParser) -> dict[str, Any]:
    return _read_flat_policy(
        parser,
        "ReferenceHunting",
        REFERENCE_HUNTING_DEFAULTS,
        REFERENCE_HUNTING_INI_KEYS,
        {
            **{name: (0, 100000) for name in REFERENCE_HUNTING_DEFAULTS if name.endswith("_weight")},
            "max_activation_age_seconds": (60, 86400),
        },
    )


PROPAGATION_ADAPTATION_INI_KEYS = {
    "enabled": "Enabled",
    "window_seconds": "WindowSeconds",
    "unique_decode_weight": "UniqueDecodeWeight",
    "distant_decode_weight": "DistantDecodeWeight",
    "successful_qso_weight": "SuccessfulQsoWeight",
    "max_band_boost": "MaxBandBoost",
}
PILEUP_STRATEGY_INI_KEYS = {
    "enabled": "Enabled",
    "rotate_after_attempts": "RotateAfterAttempts",
    "revisit_delay_seconds": "RevisitDelaySeconds",
}
DIRECTED_CALLERS_INI_KEYS = {
    "enabled": "Enabled",
    "inbox_size": "InboxSize",
    "max_age_seconds": "MaxAgeSeconds",
}
CAMPAIGN_INI_KEYS = {
    "dxcc_weight_percent": "DxccWeightPercent",
    "state_weight_percent": "StateWeightPercent",
    "zone_weight_percent": "ZoneWeightPercent",
    "grid_weight_percent": "GridWeightPercent",
    "reference_weight_percent": "ReferenceWeightPercent",
}


def _propagation_adaptation(parser: configparser.ConfigParser) -> dict[str, Any]:
    return _read_flat_policy(
        parser,
        "PropagationAdaptation",
        PROPAGATION_ADAPTATION_DEFAULTS,
        PROPAGATION_ADAPTATION_INI_KEYS,
        {
            "window_seconds": (60, 86400),
            "unique_decode_weight": (0, 100000),
            "distant_decode_weight": (0, 100000),
            "successful_qso_weight": (0, 100000),
            "max_band_boost": (0, 100000),
        },
    )


def _pileup_strategy(parser: configparser.ConfigParser) -> dict[str, Any]:
    result = _read_flat_policy(
        parser,
        "PileupStrategy",
        {key: value for key, value in PILEUP_STRATEGY_DEFAULTS.items() if key != "audio_offsets_hz"},
        PILEUP_STRATEGY_INI_KEYS,
        {"rotate_after_attempts": (1, 20), "revisit_delay_seconds": (0, 86400)},
    )
    raw = parser.get(
        "PileupStrategy", "AudioOffsetsHz",
        fallback=",".join(str(value) for value in PILEUP_STRATEGY_DEFAULTS["audio_offsets_hz"]),
    )
    offsets: list[int] = []
    for token in _qt_csv_items(raw):
        try:
            value = int(token)
        except ValueError:
            continue
        if -2400 <= value <= 2400 and value not in offsets:
            offsets.append(value)
    result["audio_offsets_hz"] = offsets or list(PILEUP_STRATEGY_DEFAULTS["audio_offsets_hz"])
    return result


def _directed_callers(parser: configparser.ConfigParser) -> dict[str, Any]:
    return _read_flat_policy(
        parser,
        "DirectedCallers",
        DIRECTED_CALLERS_DEFAULTS,
        DIRECTED_CALLERS_INI_KEYS,
        {"inbox_size": (1, 100), "max_age_seconds": (15, 3600)},
    )


def _campaign(parser: configparser.ConfigParser) -> dict[str, Any]:
    result = _read_flat_policy(
        parser,
        "Campaign",
        {key: value for key, value in CAMPAIGN_DEFAULTS.items() if key != "profile"},
        CAMPAIGN_INI_KEYS,
        {name: (0, 500) for name in CAMPAIGN_INI_KEYS},
    )
    profile = parser.get("Campaign", "Profile", fallback="balanced").strip().lower().replace("_", "-")
    if profile not in {*CAMPAIGN_PRESETS, "custom"}:
        profile = "balanced"
    if profile in CAMPAIGN_PRESETS:
        result.update(dict(zip(CAMPAIGN_WEIGHT_NAMES, CAMPAIGN_PRESETS[profile], strict=True)))
    result["profile"] = profile
    return result


def _outcome_learning(parser: configparser.ConfigParser) -> dict[str, Any]:
    telemetry = parser.get(
        "OutcomeLearning", "TelemetryFile",
        fallback=OUTCOME_LEARNING_DEFAULTS["telemetry_file"],
    ).strip().replace("\\", "/")
    path = Path(telemetry)
    if path.is_absolute() or ".." in path.parts or not telemetry:
        telemetry = OUTCOME_LEARNING_DEFAULTS["telemetry_file"]
    return {
        "enabled": _boolean(parser, "OutcomeLearning", "Enabled", True),
        "telemetry_file": telemetry,
    }


_PARITY_PATHS = (
    ("enabled", "desired_enabled"),
    ("band_switching_enabled", "band_switching_enabled"),
    ("automation_timing", "automation_timing"),
    ("band_schedules", "band_schedules"),
    ("enabled_bands", "enabled_bands"),
    ("auto_dx_modes", "auto_dx_modes"),
    ("atno_chase_type", "atno_chase_type"),
    ("scarce_threshold", "scarce_threshold"),
    ("callsign", "callsign"),
    ("grid", "grid"),
    ("min_snr", "min_snr"),
    ("grid_chase_enabled", "grid_chase_enabled"),
    ("grid_chase_us_only", "grid_chase_us_only"),
    ("target_priority", "target_priority"),
    ("eligibility", "eligibility"),
    ("spot_sources", "spot_sources"),
    ("filter_matrix_enabled", "filter_matrix_enabled"),
    ("prefer_non_europe", "prefer_non_europe"),
    ("filter_new", "filter_new"),
    ("filter_new_on_band", "filter_new_on_band"),
    ("filter_continents", "filter_continents"),
    ("allow_band_dxcc_outside_continent", "allow_band_dxcc_outside_continent"),
    ("filter_lotw_only", "filter_lotw_only"),
    ("treat_73_as_cq", "treat_73_as_cq"),
    ("watch_unconfirmed_dxcc", "watch_unconfirmed_dxcc"),
    ("selection_order", "selection_order"),
    ("call_window_seconds", "call_window_seconds"),
    ("max_consecutive_windows", "max_consecutive_windows"),
    ("same_target_revisit_delay_seconds", "same_target_revisit_delay_seconds"),
    ("recent_qso_cooldown_seconds", "recent_qso_cooldown_seconds"),
    ("min_band_dwell_seconds", "min_band_dwell_seconds"),
    ("engaged_completion_grace_seconds", "engaged_completion_grace_seconds"),
    ("us_states", "us_states"),
    ("dxpedition", "dxpedition"),
    ("cluster_chase", "cluster_chase"),
    ("award_hunting", "award_hunting"),
    ("reference_hunting", "reference_hunting"),
    ("propagation_adaptation", "propagation_adaptation"),
    ("pileup_strategy", "pileup_strategy"),
    ("directed_callers", "directed_callers"),
    ("campaign", "campaign"),
    ("outcome_learning", "outcome_learning"),
)


def _canonical_runtime_config(desired: dict[str, Any], effective: dict[str, Any]) -> dict[str, Any]:
    """Translate native runtimeConfigStatus JSON into the backend schema."""
    normalized = dict(effective)
    native_eligibility = effective.get("eligibility")
    flattened_eligibility = isinstance(native_eligibility, dict) and any(
        key in native_eligibility
        for key in ("filter_matrix_enabled", "filter_new_call", "filter_band_call", "continents")
    )
    if flattened_eligibility:
        normalized["eligibility"] = {
            name: native_eligibility.get(name)
            for name in ("new_dxcc", "new_band_slot", "new_grid", "calling_me", "random_worked_calls")
        }
        normalized["filter_matrix_enabled"] = native_eligibility.get("filter_matrix_enabled")
        normalized["filter_new"] = {
            name: native_eligibility.get(f"filter_new_{name}") for name in NEED_DIMENSIONS
        }
        normalized["filter_new_on_band"] = {
            name: native_eligibility.get(f"filter_band_{name}") for name in NEED_DIMENSIONS
        }
        normalized["filter_continents"] = native_eligibility.get("continents")
        normalized["allow_band_dxcc_outside_continent"] = native_eligibility.get(
            "allow_band_dxcc_outside_continent"
        )
        normalized["filter_lotw_only"] = native_eligibility.get("lotw_only")
        normalized["treat_73_as_cq"] = native_eligibility.get("treat_73_as_cq")
        normalized["watch_unconfirmed_dxcc"] = native_eligibility.get("watch_unconfirmed_dxcc")

    native_timing = effective.get("automation_timing")
    if isinstance(native_timing, dict) and "call_window_seconds" in native_timing:
        call_window = native_timing.get("call_window_seconds")
        max_windows = native_timing.get("max_consecutive_windows")
        normalized["call_window_seconds"] = call_window
        normalized["max_consecutive_windows"] = max_windows
        normalized["same_target_revisit_delay_seconds"] = native_timing.get("same_target_retry_seconds")
        normalized["recent_qso_cooldown_seconds"] = native_timing.get(
            "recent_qso_cooldown_seconds",
            effective.get("recent_qso_cooldown_seconds"),
        )
        normalized["min_band_dwell_seconds"] = native_timing.get("minimum_band_dwell_seconds")
        normalized["engaged_completion_grace_seconds"] = native_timing.get(
            "engaged_completion_grace_seconds",
            effective.get("engaged_completion_grace_seconds"),
        )
        desired_timing = desired.get("automation_timing") if isinstance(desired.get("automation_timing"), dict) else {}
        normalized_timing = {
            name: native_timing.get(name)
            for name in desired_timing if name != "normal_call_seconds"
        }
        try:
            normalized_timing["normal_call_seconds"] = int(call_window) * int(max_windows)
        except (TypeError, ValueError):
            normalized_timing["normal_call_seconds"] = None
        normalized["automation_timing"] = normalized_timing

    native_priority = effective.get("target_priority")
    if isinstance(native_priority, dict):
        desired_priority = desired.get("target_priority") if isinstance(desired.get("target_priority"), dict) else {}
        normalized["target_priority"] = {
            name: (
                native_priority.get("non_europe_boost", native_priority.get("non_europe"))
                if name == "non_europe" else native_priority.get(name)
            )
            for name in desired_priority
        }
    return normalized


def _runtime_parity(desired: dict[str, Any], effective: Any) -> dict[str, Any]:
    """Compare every operator-visible Phase 1 knob with native telemetry."""
    if not isinstance(effective, dict) or effective.get("schema_version") != 1:
        return {"status": "unknown", "drift": [], "reason": "native-runtime-config-not-reported"}
    effective = _canonical_runtime_config(desired, effective)
    drift: list[str] = []
    missing: list[str] = []
    for desired_key, effective_key in _PARITY_PATHS:
        if effective_key not in effective:
            missing.append(effective_key)
            continue
        desired_value = desired.get(desired_key)
        effective_value = effective.get(effective_key)
        if desired_key == "filter_continents":
            desired_members = {str(item).upper() for item in (desired_value or [])}
            effective_members = {str(item).upper() for item in (effective_value or [])}
            desired_value = [item for item in CONTINENTS if item in desired_members]
            effective_value = [item for item in CONTINENTS if item in effective_members]
        if desired_key == "spot_sources" and isinstance(effective_value, dict):
            effective_value = {
                **effective_value,
                "dx_cluster": {
                    **(effective_value.get("dx_cluster") or {}),
                },
            }
            effective_value["dx_cluster"].pop("server_count", None)
        if desired_key == "band_schedules" and isinstance(effective_value, dict):
            normalized_schedules = {}
            for band, schedule in effective_value.items():
                if not isinstance(schedule, dict):
                    continue
                normalized = {
                    "restricted": bool(schedule.get("restricted")),
                    "start": schedule.get("start", schedule.get("start_local")),
                    "end": schedule.get("end", schedule.get("end_local")),
                }
                if "min_dwell_seconds" in schedule:
                    normalized["min_dwell_seconds"] = schedule.get("min_dwell_seconds")
                normalized_schedules[str(band)] = normalized
            effective_value = normalized_schedules
        if desired_key in {"us_states", "reference_hunting", "directed_callers"} \
                and isinstance(desired_value, dict) and isinstance(effective_value, dict):
            # Native telemetry appends live award/queue observations to these
            # blocks (for example activation_count, index_valid, and queued).
            # Compare only operator-controlled keys so changing counters do not
            # produce a false runtime-settings drift warning.
            effective_value = {
                name: effective_value.get(name)
                for name in desired_value
            }
        if desired_value != effective_value:
            drift.append(desired_key)
    if missing:
        return {"status": "unknown", "drift": drift, "missing": missing}
    return {"status": "drift" if drift else "match", "drift": drift}


def read_mshv_auto_dx_settings(
    *, engine_running: bool, engine_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = settings_path()
    parser = _parser(path)
    priority = {
        name: _integer(parser, "TargetPriority", TARGET_PRIORITY_KEYS[name], default)
        for name, default in TARGET_PRIORITY_DEFAULTS.items()
    }
    grid = parser.get("SpotSources", "Grid", fallback="").strip().upper()
    grid_enabled = _boolean(parser, "GridChase", "Enabled", True) and priority["new_grid"] > 0
    persisted_enabled = _boolean(parser, "AutoDx", "Enabled", False)
    startup_safety = read_json_object(STARTUP_SAFETY_PATH)
    desired_enabled = persisted_enabled
    enabled_bands = _enabled_bands(parser)
    callsign = parser.get("SpotSources", "Callsign", fallback="").strip().upper()
    grid_chase_us_only = _boolean(parser, "GridChase", "USOnly", False)
    eligibility = {
        "new_dxcc": priority["new_dxcc"] > 0,
        "new_band_slot": priority["new_band_slot"] > 0,
        "new_grid": grid_enabled,
        "calling_me": priority["calling_me"] > 0,
        "random_worked_calls": False,
    }
    native_policy = _native_policy(parser)
    configured = {
        "schema_version": 1,
        "band_switching_enabled": _boolean(parser, "BandSwitching", "Enabled", False),
        "automation_timing": _automation_timing(
            parser,
            call_window_seconds=native_policy["call_window_seconds"],
            max_consecutive_windows=native_policy["max_consecutive_windows"],
        ),
        "band_schedules": _band_schedules(parser),
        "enabled_bands": enabled_bands,
        "enabled_band_names": [ALLOWED_BANDS[band] for band in enabled_bands],
        "auto_dx_modes": _auto_dx_modes(parser),
        "atno_chase_type": max(0, min(3, _integer(parser, "AutoDx", "ATNOChaseType", 3))),
        "scarce_threshold": max(0, min(20, _integer(parser, "AutoDx", "ScarceThreshold", 5))),
        "us_states": _us_states(parser),
        "dxpedition": _dxpedition(parser),
        "cluster_chase": _cluster_chase(parser),
        "award_hunting": _award_hunting(parser),
        "reference_hunting": _reference_hunting(parser),
        "propagation_adaptation": _propagation_adaptation(parser),
        "pileup_strategy": _pileup_strategy(parser),
        "directed_callers": _directed_callers(parser),
        "campaign": _campaign(parser),
        "outcome_learning": _outcome_learning(parser),
        "spot_sources": {
            "rbn": {
                "enabled": _boolean(parser, "SpotSources", "RbnEnabled", True),
                "host": parser.get("SpotSources", "RbnHost", fallback="telnet.reversebeacon.net").strip(),
                "port": max(1, min(65535, _integer(parser, "SpotSources", "RbnPort", 7001))),
            },
            "psk_reporter": {
                "enabled": _boolean(parser, "SpotSources", "PskEnabled", True),
                "poll_interval_seconds": max(60, min(600, _integer(parser, "SpotSources", "PskPollInterval", 120))),
            },
            "dx_cluster": {
                "enabled": _boolean(parser, "SpotSources", "DxcEnabled", True),
                "use_default_servers": _boolean(parser, "SpotSources", "UseDefaultDxClusterServers", True),
                "servers": _cluster_servers(parser),
            },
            "us_only": _boolean(parser, "SpotSources", "UsOnlyFilter", False),
            "us_only_semantics": "preferred_with_rare_dx_exceptions",
        },
        **native_policy,
    }
    effective = None
    if engine_running and isinstance(engine_state, dict):
        native = engine_state.get("autodx_config")
        effective = native if isinstance(native, dict) else {
            "enabled": bool(engine_state.get("enabled")),
            "status": "native-runtime-config-not-reported",
        }
    lotw_membership_capability = (
        effective.get("lotw_membership_capability")
        if isinstance(effective, dict) and isinstance(effective.get("lotw_membership_capability"), bool)
        else None
    )
    confirmed_dxcc_data_available = (
        effective.get("confirmed_dxcc_data_available")
        if isinstance(effective, dict) and isinstance(effective.get("confirmed_dxcc_data_available"), bool)
        else None
    )
    configured["filter_lotw_only_effective"] = bool(
        configured["filter_lotw_only"] and lotw_membership_capability is True
    )
    desired = {
        "enabled": desired_enabled,
        **configured,
        "callsign": callsign,
        "grid": grid,
        "min_snr": _min_signal(parser),
        "grid_chase_enabled": grid_enabled,
        "grid_chase_us_only": grid_chase_us_only,
        "target_priority": priority,
        "eligibility": eligibility,
    }
    from services.mshv_history import history_status
    return {
        "success": True,
        "path": str(path),
        "engine_running": engine_running,
        "editable": True,
        "restart_required_after_save": False,
        "config_hot_reload": (
            effective.get("config_hot_reload")
            if isinstance(effective, dict) and isinstance(effective.get("config_hot_reload"), dict)
            else {"poll_seconds": 2, "pending": False, "last_applied_utc": None}
        ),
        "callsign": callsign,
        "grid": grid,
        "grid_valid": bool(GRID_RE.fullmatch(grid)),
        "min_snr": _min_signal(parser),
        "spot_sources_us_only": configured["spot_sources"]["us_only"],
        "grid_chase_enabled": grid_enabled,
        "grid_chase_us_only": grid_chase_us_only,
        "auto_dx_enabled": persisted_enabled,
        "auto_dx_saved_preference": desired_enabled,
        "auto_dx_startup_forced_off": bool(startup_safety.get("staged_off", False)),
        "desired": desired,
        "effective": effective,
        "runtime_parity": _runtime_parity(desired, effective),
        **configured,
        "target_priority": priority,
        "eligibility": {**eligibility, "cq_and_snr_are_bonuses_only": True},
        "history_authority": history_status(),
        "native_policy_capabilities": {
            "schema_version": 1,
            "lotw_only_supported": lotw_membership_capability,
            "confirmed_dxcc_data_available": confirmed_dxcc_data_available,
            "policy_is_native": True,
            "backend_planner_active": False,
        },
        "lotw_membership_capability": lotw_membership_capability,
        "confirmed_dxcc_data_available": confirmed_dxcc_data_available,
    }


def stage_mshv_safe_startup() -> dict[str, Any]:
    """Preserve the native Auto DX preference across a managed launch.

    MSHV owns its planner and persists the operator's Auto DX checkbox in the
    portable runtime.  Managed lifecycle code records that preference for
    status reporting but must not rewrite or disarm it.
    """
    path = settings_path()
    parser = _parser(path)
    persisted_enabled = _boolean(parser, "AutoDx", "Enabled", False)
    atomic_write_json(STARTUP_SAFETY_PATH, {
        "desired_enabled": persisted_enabled,
        "staged_off": False,
    })
    return {
        "effective_enabled": persisted_enabled,
        "saved_preference": persisted_enabled,
        "requires_explicit_native_arm": False,
    }


def _bounded_integer(value: Any, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise HTTPException(422, f"{name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, f"{name} must be an integer") from exc
    if parsed < minimum or parsed > maximum:
        raise HTTPException(422, f"{name} must be between {minimum} and {maximum}")
    return parsed


def _strict_boolean(value: Any, *, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise HTTPException(422, f"{name} must be a boolean")


def _validated_bands(value: Any) -> list[int]:
    if not isinstance(value, list) or not value:
        raise HTTPException(422, "enabled_bands must be a non-empty list")
    bands: list[int] = []
    for item in value:
        band = _bounded_integer(item, name="enabled_bands", minimum=3, maximum=14)
        if band not in ALLOWED_BANDS:
            raise HTTPException(422, f"Band index {band} is not allowed for Auto DX")
        if band not in bands:
            bands.append(band)
    return bands


def _validated_modes(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise HTTPException(422, "auto_dx_modes must be a non-empty list")
    requested = [str(item).strip().upper() for item in value]
    unsupported = [mode for mode in requested if mode not in AUTO_DX_MODES]
    if unsupported:
        raise HTTPException(422, "Auto DX supports FT8 and FT4 only")
    return [mode for mode in AUTO_DX_MODES if mode in requested]


def _validated_servers(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 16:
        raise HTTPException(422, "spot_sources.dx_cluster.servers must contain at most 16 servers")
    servers: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise HTTPException(422, f"DX cluster server {index + 1} must be an object")
        name = str(item.get("name") or f"Server {index + 1}").strip()
        host = str(item.get("host") or "").strip()
        if "|" in name or not HOST_RE.fullmatch(host):
            raise HTTPException(422, f"DX cluster server {index + 1} has an invalid name or host")
        port = _bounded_integer(item.get("port"), name=f"DX cluster server {index + 1} port", minimum=1, maximum=65535)
        enabled = _strict_boolean(item.get("enabled", True), name=f"DX cluster server {index + 1} enabled")
        servers.append({"name": name, "host": host, "port": port, "enabled": enabled})
    return servers


def _validated_automation_timing(value: Any, current: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HTTPException(422, "automation_timing must be an object")
    unknown = set(value) - set(AUTOMATION_TIMING_DEFAULTS)
    if unknown:
        raise HTTPException(422, f"Unknown automation_timing setting: {sorted(unknown)[0]}")
    timing = {name: current[name] for name in AUTOMATION_TIMING_DEFAULTS}
    for name, (minimum, maximum) in AUTOMATION_TIMING_BOUNDS.items():
        if name in value:
            timing[name] = _bounded_integer(
                value[name], name=f"automation_timing.{name}", minimum=minimum, maximum=maximum,
            )
    for name in ("persist_new_dxcc_while_heard", "persist_new_band_slot_while_heard"):
        if name in value:
            timing[name] = _strict_boolean(value[name], name=f"automation_timing.{name}")
    return timing


def _validated_band_schedules(
    value: Any, current: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise HTTPException(422, "band_schedules must be an object")
    schedules = {key: dict(schedule) for key, schedule in current.items()}
    for raw_band, raw_schedule in value.items():
        try:
            band = int(raw_band)
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, f"band_schedules key {raw_band!r} is invalid") from exc
        if band not in ALLOWED_BANDS:
            raise HTTPException(422, f"Band index {band} is not allowed for Auto DX schedules")
        if not isinstance(raw_schedule, dict):
            raise HTTPException(422, f"band_schedules.{band} must be an object")
        unknown = set(raw_schedule) - {"restricted", "start", "end"}
        if unknown:
            raise HTTPException(422, f"Unknown band_schedules.{band} setting: {sorted(unknown)[0]}")
        schedule = schedules[str(band)]
        if "restricted" in raw_schedule:
            schedule["restricted"] = _strict_boolean(
                raw_schedule["restricted"], name=f"band_schedules.{band}.restricted",
            )
        for key in ("start", "end"):
            if key in raw_schedule:
                local_time = str(raw_schedule[key]).strip()
                if not LOCAL_TIME_RE.fullmatch(local_time):
                    raise HTTPException(422, f"band_schedules.{band}.{key} must use HH:mm local time")
                schedule[key] = local_time
    return schedules


def _validated_filter_dimensions(value: Any, *, name: str, current: dict[str, bool]) -> dict[str, bool]:
    if not isinstance(value, dict):
        raise HTTPException(422, f"{name} must be an object")
    unknown = set(value) - set(NEED_DIMENSIONS)
    if unknown:
        raise HTTPException(422, f"Unknown {name} setting: {sorted(unknown)[0]}")
    return {
        dimension: _strict_boolean(value.get(dimension, current[dimension]), name=f"{name}.{dimension}")
        for dimension in NEED_DIMENSIONS
    }


def _validated_continents(value: Any) -> list[str]:
    if isinstance(value, dict):
        values = [key for key, enabled in value.items() if _strict_boolean(enabled, name=f"filter_continents.{key}")]
    elif isinstance(value, list):
        values = value
    else:
        raise HTTPException(422, "filter_continents must be a list or object")
    normalized = {str(item).strip().upper() for item in values}
    unknown = normalized - set(CONTINENTS)
    if unknown:
        raise HTTPException(422, f"Unknown continent: {sorted(unknown)[0]}")
    return [continent for continent in CONTINENTS if continent in normalized]


def _validated_selection_order(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in {"score", "last"}:
        raise HTTPException(422, "selection_order must be score or last")
    return normalized


def _write_flat_policy(
    parser: configparser.ConfigParser,
    *,
    request: dict[str, Any],
    current: dict[str, Any],
    request_key: str,
    section: str,
    defaults: dict[str, Any],
    ini_keys: dict[str, str],
    bounds: dict[str, tuple[int, int]],
) -> None:
    if request_key not in request:
        return
    raw = request[request_key]
    if not isinstance(raw, dict):
        raise HTTPException(422, f"{request_key} must be an object")
    unknown = set(raw) - set(defaults)
    if unknown:
        raise HTTPException(422, f"Unknown {request_key} setting: {sorted(unknown)[0]}")
    values = {**current, **raw}
    if not parser.has_section(section):
        parser.add_section(section)
    for name, default in defaults.items():
        if isinstance(default, bool):
            value = _strict_boolean(values[name], name=f"{request_key}.{name}")
            parser.set(section, ini_keys[name], "true" if value else "false")
        else:
            low, high = bounds.get(name, (0, 100000))
            value = _bounded_integer(values[name], name=f"{request_key}.{name}", minimum=low, maximum=high)
            parser.set(section, ini_keys[name], str(value))


def update_mshv_auto_dx_settings(request: dict[str, Any], *, engine_running: bool) -> dict[str, Any]:
    current = read_mshv_auto_dx_settings(engine_running=False)
    if not isinstance(request, dict) or not request:
        raise HTTPException(422, "At least one MSHV Auto DX setting is required")
    priority_request = request.get("target_priority", {})
    if not isinstance(priority_request, dict):
        raise HTTPException(422, "target_priority must be an object")

    path = settings_path()
    parser = _parser(path)
    if parser.has_option("AutoDX", "EngagedCompletionGraceSeconds"):
        # A stopped-engine save is the migration boundary: retain the legacy
        # value if no canonical value exists, then remove only the old key.
        if not parser.has_section("Attempt"):
            parser.add_section("Attempt")
        if not parser.has_option("Attempt", "EngagedCompletionGraceSeconds"):
            parser.set(
                "Attempt", "EngagedCompletionGraceSeconds",
                str(current["engaged_completion_grace_seconds"]),
            )
        parser.remove_option("AutoDX", "EngagedCompletionGraceSeconds")
    auto_dx_enabled = None
    if "enabled" in request:
        auto_dx_enabled = _strict_boolean(request["enabled"], name="enabled")
        if not parser.has_section("AutoDx"):
            parser.add_section("AutoDx")
        parser.set("AutoDx", "Enabled", "true" if auto_dx_enabled else "false")
    if not parser.has_section("TargetPriority"):
        parser.add_section("TargetPriority")
    for name, ini_key in TARGET_PRIORITY_KEYS.items():
        minimum = 1 if name == "new_grid" else 0
        value = _bounded_integer(
            priority_request.get(name, current["target_priority"][name]),
            name=f"target_priority.{name}",
            minimum=minimum,
            maximum=100000,
        )
        parser.set("TargetPriority", ini_key, str(value))

    for name, default in NATIVE_POLICY_DEFAULTS.items():
        if name not in request:
            continue
        section, key = NATIVE_POLICY_INI_KEYS[name]
        if not parser.has_section(section):
            parser.add_section(section)
        if isinstance(default, bool):
            value = _strict_boolean(request[name], name=name)
            parser.set(section, key, "true" if value else "false")
        else:
            minimum, maximum = NATIVE_POLICY_BOUNDS[name]
            value = _bounded_integer(request[name], name=name, minimum=minimum, maximum=maximum)
            if name == "call_window_seconds" and value not in {120, 240}:
                raise HTTPException(422, "call_window_seconds must be 120 or 240")
            if name == "engaged_completion_grace_seconds":
                value = ((value + 14) // 15) * 15
            parser.set(section, key, str(value))

    # A partial API request that selects filter dimensions is an intent to use
    # the matrix. Preserve an explicitly supplied false as an intentional pause.
    filter_policy_keys = {
        "filter_new", "filter_new_on_band", "filter_continents", "filter_lotw_only",
    }
    if "filter_matrix_enabled" not in request and filter_policy_keys.intersection(request):
        if not parser.has_section("Eligibility"):
            parser.add_section("Eligibility")
        parser.set("Eligibility", "FilterMatrixEnabled", "true")

    dimension_keys = {
        "call": "Call", "dxcc": "Dxcc", "continent": "Continent",
        "grid": "Grid", "cq_zone": "CqZone", "itu_zone": "ItuZone",
    }
    for request_key, prefix in (("filter_new", "FilterNew"), ("filter_new_on_band", "FilterBand")):
        if request_key not in request:
            continue
        values = _validated_filter_dimensions(
            request[request_key], name=request_key, current=current[request_key],
        )
        if not parser.has_section("Eligibility"):
            parser.add_section("Eligibility")
        for name, enabled in values.items():
            parser.set("Eligibility", prefix + dimension_keys[name], "true" if enabled else "false")
    if "filter_continents" in request:
        enabled_continents = set(_validated_continents(request["filter_continents"]))
        if not parser.has_section("Eligibility"):
            parser.add_section("Eligibility")
        parser.set("Eligibility", "FilterContinents", ",".join(
            continent for continent in CONTINENTS if continent in enabled_continents
        ))
    if "selection_order" in request:
        if not parser.has_section("Selection"):
            parser.add_section("Selection")
        parser.set("Selection", "Order", _validated_selection_order(request["selection_order"]))

    min_snr = _bounded_integer(request.get("min_snr", current["min_snr"]), name="min_snr", minimum=-30, maximum=0)
    if not parser.has_section("SpotSources"):
        parser.add_section("SpotSources")
    parser.set("SpotSources", "MinSNR", str(min_snr))
    if not parser.has_section("Eligibility"):
        parser.add_section("Eligibility")
    parser.set("Eligibility", "MinSignal", str(min_snr))

    if not parser.has_section("GridChase"):
        parser.add_section("GridChase")
    parser.set("GridChase", "Enabled", "true")
    if "grid_chase_us_only" in request:
        parser.set("GridChase", "USOnly", "true" if _strict_boolean(request["grid_chase_us_only"], name="grid_chase_us_only") else "false")
    if "spot_sources_us_only" in request:
        parser.set("SpotSources", "UsOnlyFilter", "true" if _strict_boolean(request["spot_sources_us_only"], name="spot_sources_us_only") else "false")

    if "callsign" in request:
        callsign = str(request["callsign"]).strip().upper()
        if not CALLSIGN_RE.fullmatch(callsign):
            raise HTTPException(422, "callsign is invalid")
        parser.set("SpotSources", "Callsign", callsign)
    if "grid" in request:
        grid = str(request["grid"]).strip().upper()
        if not GRID_RE.fullmatch(grid):
            raise HTTPException(422, "grid is invalid")
        parser.set("SpotSources", "Grid", grid)

    if "band_switching_enabled" in request:
        if not parser.has_section("BandSwitching"):
            parser.add_section("BandSwitching")
        band_switching_enabled = _strict_boolean(
            request["band_switching_enabled"], name="band_switching_enabled",
        )
        parser.set("BandSwitching", "Enabled", "true" if band_switching_enabled else "false")
    if "automation_timing" in request:
        timing = _validated_automation_timing(request["automation_timing"], current["automation_timing"])
        if not parser.has_section("AutomationTiming"):
            parser.add_section("AutomationTiming")
        for name, value in timing.items():
            if isinstance(value, bool):
                encoded = "true" if value else "false"
            else:
                encoded = str(value)
            parser.set("AutomationTiming", AUTOMATION_TIMING_INI_KEYS[name], encoded)
    if "band_schedules" in request:
        schedules = _validated_band_schedules(request["band_schedules"], current["band_schedules"])
        if not parser.has_section("BandSchedules"):
            parser.add_section("BandSchedules")
        for band, schedule in schedules.items():
            parser.set("BandSchedules", f"Band{band}Restricted", "true" if schedule["restricted"] else "false")
            parser.set("BandSchedules", f"Band{band}Start", schedule["start"])
            parser.set("BandSchedules", f"Band{band}End", schedule["end"])
    if "enabled_bands" in request:
        if not parser.has_section("BandSelection"):
            parser.add_section("BandSelection")
        parser.set("BandSelection", "EnabledBands", ",".join(str(item) for item in _validated_bands(request["enabled_bands"])))
    if "auto_dx_modes" in request:
        if not parser.has_section("AutoDx"):
            parser.add_section("AutoDx")
        parser.set("AutoDx", "Modes", ",".join(_validated_modes(request["auto_dx_modes"])))
    if "atno_chase_type" in request or "scarce_threshold" in request:
        if not parser.has_section("AutoDx"):
            parser.add_section("AutoDx")
        if "atno_chase_type" in request:
            parser.set("AutoDx", "ATNOChaseType", str(_bounded_integer(request["atno_chase_type"], name="atno_chase_type", minimum=0, maximum=3)))
        if "scarce_threshold" in request:
            parser.set("AutoDx", "ScarceThreshold", str(_bounded_integer(request["scarce_threshold"], name="scarce_threshold", minimum=0, maximum=20)))

    if "us_states" in request:
        raw_states = request["us_states"]
        if not isinstance(raw_states, dict):
            raise HTTPException(422, "us_states must be an object")
        unknown = set(raw_states) - {*US_STATE_DEFAULTS, "bands"}
        if unknown:
            raise HTTPException(422, f"Unknown us_states setting: {sorted(unknown)[0]}")
        current_states = current["us_states"]
        values = {**current_states, **raw_states}
        if not parser.has_section("USStates"):
            parser.add_section("USStates")
        for name, key in (
            ("enabled", "Enabled"), ("require_confirmation", "RequireConfirmation"),
            ("prefer_lotw", "PreferLotw"),
        ):
            value = _strict_boolean(values[name], name=f"us_states.{name}")
            parser.set("USStates", key, "true" if value else "false")
        for name, key, low, high in (
            ("minimum_worked", "MinimumWorked", 1, 10),
            ("missing_confirmation_weight", "MissingConfirmationWeight", 0, 100000),
            ("under_quota_weight", "UnderQuotaWeight", 0, 100000),
        ):
            parser.set("USStates", key, str(_bounded_integer(
                values[name], name=f"us_states.{name}", minimum=low, maximum=high,
            )))
        state_bands = _validated_bands(values["bands"])
        if 14 in state_bands:
            raise HTTPException(422, "US States chase supports 160m through 10m; 6m is excluded")
        parser.set("USStates", "Bands", ",".join(str(band) for band in state_bands))

    if "dxpedition" in request:
        raw = request["dxpedition"]
        if not isinstance(raw, dict):
            raise HTTPException(422, "dxpedition must be an object")
        unknown = set(raw) - set(DXPEDITION_DEFAULTS)
        if unknown:
            raise HTTPException(422, f"Unknown dxpedition setting: {sorted(unknown)[0]}")
        values = {**current["dxpedition"], **raw}
        if not parser.has_section("Dxpedition"):
            parser.add_section("Dxpedition")
        for name, key in (
            ("enabled", "Enabled"),
            ("allow_same_band_off_standard_qsy", "AllowSameBandOffStandardQsy"),
            ("allow_cross_band_qsy", "AllowCrossBandQsy"),
            ("return_to_standard", "ReturnToStandard"),
        ):
            parser.set("Dxpedition", key, "true" if _strict_boolean(values[name], name=f"dxpedition.{name}") else "false")
        scope = str(values["chase_scope"]).strip().lower()
        if scope not in {"needed-only", "any-active"}:
            raise HTTPException(422, "dxpedition.chase_scope must be needed-only or any-active")
        parser.set("Dxpedition", "ChaseScope", scope)
        for name, key, low, high in (
            ("min_spotters", "MinSpotters", 1, 20),
            ("max_spot_age_seconds", "MaxSpotAgeSeconds", 15, 1800),
            ("rx_audio_hz", "RxAudioHz", 300, 2700),
            ("tx_offset_hz", "TxOffsetHz", 0, 2400),
        ):
            parser.set("Dxpedition", key, str(_bounded_integer(
                values[name], name=f"dxpedition.{name}", minimum=low, maximum=high,
            )))

    if "cluster_chase" in request:
        raw = request["cluster_chase"]
        if not isinstance(raw, dict):
            raise HTTPException(422, "cluster_chase must be an object")
        writable = set(CLUSTER_CHASE_DEFAULTS)
        unknown = set(raw) - writable - {"continent_filter_override_for_needed_targets"}
        if unknown:
            raise HTTPException(422, f"Unknown cluster_chase setting: {sorted(unknown)[0]}")
        values = {**current["cluster_chase"], **raw}
        if not parser.has_section("ClusterChase"):
            parser.add_section("ClusterChase")
        for name, key in (
            ("enabled", "Enabled"), ("chase_new_dxcc", "ChaseNewDxcc"),
            ("chase_band_dxcc", "ChaseBandDxcc"),
            ("chase_us_states", "ChaseUsStates"),
            ("chase_dxpeditions", "ChaseDxpeditions"),
            ("chase_unconfirmed_continents", "ChaseUnconfirmedContinents"),
            ("chase_unconfirmed_cq_zones", "ChaseUnconfirmedCqZones"),
            ("chase_unconfirmed_itu_zones", "ChaseUnconfirmedItuZones"),
        ):
            parser.set("ClusterChase", key, "true" if _strict_boolean(values[name], name=f"cluster_chase.{name}") else "false")
        minimum = _bounded_integer(values["min_spotters"], name="cluster_chase.min_spotters", minimum=1, maximum=20)
        consensus = _bounded_integer(values["consensus_spotters"], name="cluster_chase.consensus_spotters", minimum=1, maximum=20)
        if consensus < minimum:
            raise HTTPException(422, "cluster_chase.consensus_spotters must be at least min_spotters")
        parser.set("ClusterChase", "MinSpotters", str(minimum))
        parser.set("ClusterChase", "ConsensusSpotters", str(consensus))
        parser.set("ClusterChase", "QueueLimit", str(_bounded_integer(
            values["queue_limit"], name="cluster_chase.queue_limit", minimum=1, maximum=50,
        )))

    _write_flat_policy(
        parser,
        request=request,
        current=current["award_hunting"],
        request_key="award_hunting",
        section="AwardHunting",
        defaults=AWARD_HUNTING_DEFAULTS,
        ini_keys=AWARD_HUNTING_INI_KEYS,
        bounds={name: (0, 100000) for name in AWARD_HUNTING_DEFAULTS if name.endswith("_weight")},
    )
    _write_flat_policy(
        parser,
        request=request,
        current=current["reference_hunting"],
        request_key="reference_hunting",
        section="ReferenceHunting",
        defaults=REFERENCE_HUNTING_DEFAULTS,
        ini_keys=REFERENCE_HUNTING_INI_KEYS,
        bounds={
            **{name: (0, 100000) for name in REFERENCE_HUNTING_DEFAULTS if name.endswith("_weight")},
            "max_activation_age_seconds": (60, 86400),
        },
    )
    _write_flat_policy(
        parser,
        request=request,
        current=current["propagation_adaptation"],
        request_key="propagation_adaptation",
        section="PropagationAdaptation",
        defaults=PROPAGATION_ADAPTATION_DEFAULTS,
        ini_keys=PROPAGATION_ADAPTATION_INI_KEYS,
        bounds={
            "window_seconds": (60, 86400),
            "unique_decode_weight": (0, 100000),
            "distant_decode_weight": (0, 100000),
            "successful_qso_weight": (0, 100000),
            "max_band_boost": (0, 100000),
        },
    )
    _write_flat_policy(
        parser,
        request=request,
        current=current["directed_callers"],
        request_key="directed_callers",
        section="DirectedCallers",
        defaults=DIRECTED_CALLERS_DEFAULTS,
        ini_keys=DIRECTED_CALLERS_INI_KEYS,
        bounds={"inbox_size": (1, 100), "max_age_seconds": (15, 3600)},
    )

    if "pileup_strategy" in request:
        raw = request["pileup_strategy"]
        if not isinstance(raw, dict):
            raise HTTPException(422, "pileup_strategy must be an object")
        unknown = set(raw) - set(PILEUP_STRATEGY_DEFAULTS)
        if unknown:
            raise HTTPException(422, f"Unknown pileup_strategy setting: {sorted(unknown)[0]}")
        values = {**current["pileup_strategy"], **raw}
        if not parser.has_section("PileupStrategy"):
            parser.add_section("PileupStrategy")
        parser.set(
            "PileupStrategy", "Enabled",
            "true" if _strict_boolean(values["enabled"], name="pileup_strategy.enabled") else "false",
        )
        offsets = values["audio_offsets_hz"]
        if not isinstance(offsets, list) or not offsets or len(offsets) > 16:
            raise HTTPException(422, "pileup_strategy.audio_offsets_hz must contain 1 to 16 offsets")
        normalized_offsets: list[int] = []
        for raw_offset in offsets:
            offset = _bounded_integer(
                raw_offset, name="pileup_strategy.audio_offsets_hz", minimum=-2400, maximum=2400,
            )
            if offset not in normalized_offsets:
                normalized_offsets.append(offset)
        parser.set("PileupStrategy", "AudioOffsetsHz", ",".join(str(value) for value in normalized_offsets))
        parser.set("PileupStrategy", "RotateAfterAttempts", str(_bounded_integer(
            values["rotate_after_attempts"], name="pileup_strategy.rotate_after_attempts", minimum=1, maximum=20,
        )))
        parser.set("PileupStrategy", "RevisitDelaySeconds", str(_bounded_integer(
            values["revisit_delay_seconds"], name="pileup_strategy.revisit_delay_seconds", minimum=0, maximum=86400,
        )))

    if "campaign" in request:
        raw = request["campaign"]
        if not isinstance(raw, dict):
            raise HTTPException(422, "campaign must be an object")
        unknown = set(raw) - set(CAMPAIGN_DEFAULTS)
        if unknown:
            raise HTTPException(422, f"Unknown campaign setting: {sorted(unknown)[0]}")
        values = {**current["campaign"], **raw}
        profile = str(values["profile"]).strip().lower().replace("_", "-")
        if "profile" not in raw and set(raw).intersection(CAMPAIGN_WEIGHT_NAMES):
            profile = "custom"
        if profile not in {*CAMPAIGN_PRESETS, "custom"}:
            raise HTTPException(422, f"campaign.profile must be one of: {', '.join([*CAMPAIGN_PRESETS, 'custom'])}")
        if profile in CAMPAIGN_PRESETS:
            values.update(dict(zip(CAMPAIGN_WEIGHT_NAMES, CAMPAIGN_PRESETS[profile], strict=True)))
        if not parser.has_section("Campaign"):
            parser.add_section("Campaign")
        parser.set("Campaign", "Profile", profile)
        for name, key in CAMPAIGN_INI_KEYS.items():
            parser.set("Campaign", key, str(_bounded_integer(
                values[name], name=f"campaign.{name}", minimum=0, maximum=500,
            )))

    if "outcome_learning" in request:
        raw = request["outcome_learning"]
        if not isinstance(raw, dict):
            raise HTTPException(422, "outcome_learning must be an object")
        unknown = set(raw) - set(OUTCOME_LEARNING_DEFAULTS)
        if unknown:
            raise HTTPException(422, f"Unknown outcome_learning setting: {sorted(unknown)[0]}")
        values = {**current["outcome_learning"], **raw}
        telemetry = str(values["telemetry_file"]).strip().replace("\\", "/")
        telemetry_path = Path(telemetry)
        if not telemetry or telemetry_path.is_absolute() or ".." in telemetry_path.parts:
            raise HTTPException(422, "outcome_learning.telemetry_file must be a relative runtime path")
        if not parser.has_section("OutcomeLearning"):
            parser.add_section("OutcomeLearning")
        parser.set(
            "OutcomeLearning", "Enabled",
            "true" if _strict_boolean(values["enabled"], name="outcome_learning.enabled") else "false",
        )
        parser.set("OutcomeLearning", "TelemetryFile", telemetry)

    sources = request.get("spot_sources")
    if sources is not None:
        if not isinstance(sources, dict):
            raise HTTPException(422, "spot_sources must be an object")
        if not parser.has_section("SpotSources"):
            parser.add_section("SpotSources")
        if "us_only" in sources:
            if "spot_sources_us_only" in request:
                alias_value = _strict_boolean(request["spot_sources_us_only"], name="spot_sources_us_only")
                canonical_value = _strict_boolean(sources["us_only"], name="spot_sources.us_only")
                if alias_value != canonical_value:
                    raise HTTPException(422, "spot_sources.us_only conflicts with deprecated spot_sources_us_only")
            parser.set("SpotSources", "UsOnlyFilter", "true" if _strict_boolean(sources["us_only"], name="spot_sources.us_only") else "false")
        rbn = sources.get("rbn")
        if rbn is not None:
            if not isinstance(rbn, dict):
                raise HTTPException(422, "spot_sources.rbn must be an object")
            if "enabled" in rbn:
                parser.set("SpotSources", "RbnEnabled", "true" if _strict_boolean(rbn["enabled"], name="spot_sources.rbn.enabled") else "false")
            if "host" in rbn:
                host = str(rbn["host"]).strip()
                if not HOST_RE.fullmatch(host):
                    raise HTTPException(422, "spot_sources.rbn.host is invalid")
                parser.set("SpotSources", "RbnHost", host)
            if "port" in rbn:
                parser.set("SpotSources", "RbnPort", str(_bounded_integer(rbn["port"], name="spot_sources.rbn.port", minimum=1, maximum=65535)))
        pskr = sources.get("psk_reporter")
        if pskr is not None:
            if not isinstance(pskr, dict):
                raise HTTPException(422, "spot_sources.psk_reporter must be an object")
            if "enabled" in pskr:
                parser.set("SpotSources", "PskEnabled", "true" if _strict_boolean(pskr["enabled"], name="spot_sources.psk_reporter.enabled") else "false")
            if "poll_interval_seconds" in pskr:
                parser.set("SpotSources", "PskPollInterval", str(_bounded_integer(pskr["poll_interval_seconds"], name="spot_sources.psk_reporter.poll_interval_seconds", minimum=60, maximum=600)))
        cluster = sources.get("dx_cluster")
        if cluster is not None:
            if not isinstance(cluster, dict):
                raise HTTPException(422, "spot_sources.dx_cluster must be an object")
            if "enabled" in cluster:
                parser.set("SpotSources", "DxcEnabled", "true" if _strict_boolean(cluster["enabled"], name="spot_sources.dx_cluster.enabled") else "false")
            if "use_default_servers" in cluster:
                use_defaults = _strict_boolean(cluster["use_default_servers"], name="spot_sources.dx_cluster.use_default_servers")
                parser.set("SpotSources", "UseDefaultDxClusterServers", "true" if use_defaults else "false")
            if "servers" in cluster:
                servers = _validated_servers(cluster["servers"])
                if not parser.has_section("DxClusterServers"):
                    parser.add_section("DxClusterServers")
                for key in list(parser["DxClusterServers"]):
                    parser.remove_option("DxClusterServers", key)
                parser.set("DxClusterServers", "Count", str(len(servers)))
                for index, server in enumerate(servers):
                    parser.set("DxClusterServers", f"Server{index}", "|".join((server["name"], server["host"], str(server["port"]), "true" if server["enabled"] else "false")))

    # Migrate away from the obsolete independent budget on any explicit save.
    # Attempt/CallWindowSeconds and MaxConsecutiveWindows are the sole source.
    if parser.has_section("AutomationTiming"):
        parser.remove_option("AutomationTiming", "NormalCallSeconds")
    output = StringIO()
    parser.write(output, space_around_delimiters=False)
    _write_settings_text(path, output.getvalue())
    if auto_dx_enabled is not None:
        atomic_write_json(STARTUP_SAFETY_PATH, {
            "desired_enabled": auto_dx_enabled,
            "staged_off": False,
        })
    return {
        **read_mshv_auto_dx_settings(engine_running=engine_running),
        "saved": True,
        "message": (
            "MSHV Auto DX settings saved; native hot reload applies them within 2 seconds "
            "or safely after the active QSO releases ownership"
            if engine_running else
            "MSHV Auto DX runtime settings saved"
        ),
    }
