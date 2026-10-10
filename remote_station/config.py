"""Configuration for the independent Windows remote-station agent."""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
BANDS = ("160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m")


class AgentConfigError(ValueError):
    """Raised when an agent configuration is incomplete or unsafe."""


def default_config_path() -> Path:
    override = os.environ.get("OM0RX_REMOTE_AGENT_CONFIG", "").strip()
    if override:
        return Path(override).expanduser()
    app_data = os.environ.get("APPDATA", "").strip()
    base = Path(app_data) if app_data else Path.home() / ".config"
    return base / "OM0RX Remote Station" / "agent.json"


def _band_map(value: Any, name: str, *, minimum: int, maximum: int) -> dict[str, int]:
    if not isinstance(value, dict):
        raise AgentConfigError(f"{name} must be an object with one value per band")
    result: dict[str, int] = {}
    for band in BANDS:
        raw = value.get(band)
        if isinstance(raw, bool):
            raise AgentConfigError(f"{name}.{band} must be an integer")
        try:
            parsed = int(raw)
        except (TypeError, ValueError) as exc:
            raise AgentConfigError(f"{name}.{band} must be an integer") from exc
        if not minimum <= parsed <= maximum:
            raise AgentConfigError(f"{name}.{band} must be between {minimum} and {maximum}")
        result[band] = parsed
    return result


def _band_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list):
        raise AgentConfigError(f"{name} must be a list")
    unknown = sorted({str(item) for item in value} - set(BANDS))
    if unknown:
        raise AgentConfigError(f"{name} contains unsupported bands: {', '.join(unknown)}")
    selected = {str(item) for item in value}
    return [band for band in BANDS if band in selected]


def _port(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise AgentConfigError(f"{name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AgentConfigError(f"{name} must be an integer") from exc
    if not 1 <= parsed <= 65535:
        raise AgentConfigError(f"{name} must be between 1 and 65535")
    return parsed


def _integer(value: Any, name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise AgentConfigError(f"{name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AgentConfigError(f"{name} must be an integer") from exc
    if not minimum <= parsed <= maximum:
        raise AgentConfigError(f"{name} must be between {minimum} and {maximum}")
    return parsed


@dataclass(frozen=True)
class AgentConfig:
    path: Path
    bind_host: str
    bind_port: int
    control_token: str
    flex_host: str
    flex_port: int
    flex_slice_id: int
    flex_station_name: str
    kpa_enabled: bool
    kpa_port: str
    kpa_baudrate: int
    kat_enabled: bool
    kat_port: str
    kat_baudrate: int
    follow_radio: bool
    digital_kpa_policy: str
    commissioned: bool
    flex_antenna_policy: dict[str, Any]
    kat_antenna_policy: dict[str, int]
    kat_antenna_names: dict[str, str]
    amplifier_allowed_bands: list[str]
    amplifier_drive_w: dict[str, int]
    barefoot_drive_w: dict[str, int]
    digital_amplifier_allowed_bands: list[str]
    digital_amplifier_drive_w: dict[str, int]
    tune_power_w: int
    tune_target_swr: float
    tune_abort_swr: float
    tune_timeout_seconds: float

    def public_summary(self) -> dict[str, Any]:
        """Return configuration safe to expose to an authenticated client."""
        return {
            "schema_version": SCHEMA_VERSION,
            "server": {"bind_host": self.bind_host, "bind_port": self.bind_port},
            "flex": {
                "model": "FLEX-8400",
                "host": self.flex_host,
                "port": self.flex_port,
                "slice_id": self.flex_slice_id,
                "station_name": self.flex_station_name,
            },
            "kpa500": {
                "enabled": self.kpa_enabled,
                "port": self.kpa_port,
                "baudrate": self.kpa_baudrate,
            },
            "kat500": {
                "enabled": self.kat_enabled,
                "port": self.kat_port,
                "baudrate": self.kat_baudrate,
            },
            "commissioned": self.commissioned,
            "policy": {
                "follow_radio": self.follow_radio,
                "digital_kpa_policy": self.digital_kpa_policy,
                "flex_antenna": self.flex_antenna_policy,
                "kat_antenna": self.kat_antenna_policy,
                "kat_antenna_names": self.kat_antenna_names,
                "amplifier_allowed_bands": self.amplifier_allowed_bands,
                "amplifier_drive_w": self.amplifier_drive_w,
                "barefoot_drive_w": self.barefoot_drive_w,
                "digital_amplifier_allowed_bands": self.digital_amplifier_allowed_bands,
                "digital_amplifier_drive_w": self.digital_amplifier_drive_w,
                "tune_power_w": self.tune_power_w,
                "tune_target_swr": self.tune_target_swr,
                "tune_abort_swr": self.tune_abort_swr,
                "tune_timeout_seconds": self.tune_timeout_seconds,
            },
        }

    def apply_to_radio_config(self) -> None:
        """Apply the isolated agent policy to the shared drivers in this process."""
        from radio_control import config

        values = {
            "FLEX_TCP_HOST": self.flex_host,
            "FLEX_TCP_PORT": self.flex_port,
            "FLEX_SLICE_ID": self.flex_slice_id,
            "FLEX_ANTENNA_POLICY": self.flex_antenna_policy,
            "KPA500_ENABLED": self.kpa_enabled,
            "KPA500_PORT": self.kpa_port,
            "KPA500_BAUDRATE": self.kpa_baudrate,
            "KAT500_ENABLED": self.kat_enabled,
            "KAT500_PORT": self.kat_port,
            "KAT500_BAUDRATE": self.kat_baudrate,
            "ELECRAFT_FOLLOW_RADIO": self.follow_radio,
            "STATION_COORDINATOR_COMMISSIONED": self.commissioned,
            "STATION_AMPLIFIER_ALLOWED_BANDS": self.amplifier_allowed_bands,
            "STATION_AMPLIFIER_DRIVE_W": self.amplifier_drive_w,
            "STATION_BAREFOOT_DRIVE_W": self.barefoot_drive_w,
            "STATION_DIGITAL_AMPLIFIER_ALLOWED_BANDS": self.digital_amplifier_allowed_bands,
            "STATION_DIGITAL_AMPLIFIER_DRIVE_W": self.digital_amplifier_drive_w,
            "DIGITAL_KPA_POLICY": self.digital_kpa_policy,
            "KAT500_ANTENNA_POLICY": self.kat_antenna_policy,
            "KAT500_ANTENNA_NAMES": self.kat_antenna_names,
            "STATION_TUNE_POWER_W": self.tune_power_w,
            "STATION_TUNE_TARGET_SWR": self.tune_target_swr,
            "STATION_TUNE_ABORT_SWR": self.tune_abort_swr,
            "STATION_TUNE_TIMEOUT_SECONDS": self.tune_timeout_seconds,
        }
        for name, value in values.items():
            setattr(config, name, value)


def default_config_document(*, control_token: str | None = None) -> dict[str, Any]:
    """Return a clean station profile matching the currently documented route."""
    return {
        "schema_version": SCHEMA_VERSION,
        "server": {
            "bind_host": "127.0.0.1",
            "bind_port": 8840,
            "control_token": control_token or secrets.token_urlsafe(32),
        },
        "flex": {
            "model": "FLEX-8400",
            "host": "192.168.0.199",
            "port": 4992,
            "slice_id": 0,
            "station_name": "Maestro",
            "antenna_policy": {
                "enabled": True,
                "bands": {
                    "160m": "ANT1",
                    "80m": "ANT1",
                    "60m": "ANT1",
                    "40m": "ANT1",
                    "30m": "ANT1",
                    "20m": "ANT1",
                    "17m": "ANT1",
                    "15m": "ANT1",
                    "12m": "ANT1",
                    "10m": "ANT1",
                    "6m": "ANT1",
                },
            },
        },
        "kpa500": {"enabled": True, "port": "COM17", "baudrate": 38400},
        "kat500": {"enabled": True, "port": "COM15", "baudrate": 38400},
        "station": {
            "commissioned": False,
            "follow_radio": True,
            "digital_kpa_policy": "operate",
            "kat_antenna_policy": {
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
            },
            "kat_antenna_names": {"1": "KAT ANT1", "2": "KAT ANT2", "3": "KAT ANT3"},
            "amplifier_allowed_bands": [
                "160m",
                "80m",
                "40m",
                "30m",
                "15m",
                "12m",
                "10m",
            ],
            "amplifier_drive_w": {band: 25 for band in BANDS},
            "barefoot_drive_w": {
                "160m": 90,
                "80m": 90,
                "60m": 25,
                "40m": 100,
                "30m": 90,
                "20m": 65,
                "17m": 70,
                "15m": 90,
                "12m": 90,
                "10m": 90,
                "6m": 25,
            },
            "digital_amplifier_allowed_bands": ["160m", "80m", "40m", "30m", "15m", "10m"],
            "digital_amplifier_drive_w": {
                "160m": 25,
                "80m": 25,
                "60m": 25,
                "40m": 15,
                "30m": 25,
                "20m": 25,
                "17m": 25,
                "15m": 25,
                "12m": 25,
                "10m": 25,
                "6m": 25,
            },
            "tune_power_w": 25,
            "tune_target_swr": 1.5,
            "tune_abort_swr": 3.0,
            "tune_timeout_seconds": 30.0,
        },
    }


def write_default_config(path: Path | None = None) -> Path:
    target = (path or default_config_path()).expanduser().resolve()
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite existing configuration: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(default_config_document(), indent=2) + "\n", encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(target)
    return target


def load_agent_config(path: Path | None = None) -> AgentConfig:
    source = (path or default_config_path()).expanduser().resolve()
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AgentConfigError(f"Agent configuration does not exist: {source}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentConfigError(f"Agent configuration could not be read: {exc}") from exc

    if not isinstance(document, dict):
        raise AgentConfigError("Agent configuration must contain a JSON object")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise AgentConfigError(f"schema_version must be {SCHEMA_VERSION}")
    server = document.get("server") or {}
    flex = document.get("flex") or {}
    kpa = document.get("kpa500") or {}
    kat = document.get("kat500") or {}
    station = document.get("station") or {}
    token = str(server.get("control_token") or "").strip()
    if len(token) < 32 or any(character.isspace() for character in token):
        raise AgentConfigError("server.control_token must contain at least 32 characters")
    bind_host = str(server.get("bind_host") or "127.0.0.1").strip().lower()
    if bind_host not in {"127.0.0.1", "localhost", "::1"}:
        raise AgentConfigError(
            "server.bind_host must be loopback; publish the agent privately with Tailscale Serve"
        )
    flex_host = str(flex.get("host") or "").strip()
    if not flex_host:
        raise AgentConfigError("flex.host is required")
    flex_station_name = str(flex.get("station_name") or "").strip()
    if not flex_station_name:
        raise AgentConfigError("flex.station_name is required")
    kpa_port = str(kpa.get("port") or "").strip()
    kat_port = str(kat.get("port") or "").strip()
    if not kpa_port or not kat_port:
        raise AgentConfigError("kpa500.port and kat500.port are required")

    antenna_policy = flex.get("antenna_policy") or {}
    antenna_bands = antenna_policy.get("bands") or {}
    normalized_flex_bands: dict[str, str] = {}
    for band in BANDS:
        antenna = str(antenna_bands.get(band) or "").upper()
        if antenna not in {"ANT1", "ANT2", "XVTR"}:
            raise AgentConfigError(f"flex.antenna_policy.bands.{band} must be ANT1, ANT2, or XVTR")
        normalized_flex_bands[band] = antenna

    names = station.get("kat_antenna_names") or {}
    normalized_names = {str(index): str(names.get(str(index)) or "").strip() for index in (1, 2, 3)}
    if any(not value for value in normalized_names.values()):
        raise AgentConfigError("station.kat_antenna_names must name outputs 1, 2, and 3")

    slice_id = _integer(flex.get("slice_id", 0), "flex.slice_id", minimum=0, maximum=7)
    commissioned = station.get("commissioned", False)
    if type(commissioned) is not bool:
        raise AgentConfigError("station.commissioned must be true or false")
    kpa_enabled = kpa.get("enabled", True)
    if type(kpa_enabled) is not bool:
        raise AgentConfigError("kpa500.enabled must be true or false")
    kat_enabled = kat.get("enabled", True)
    if type(kat_enabled) is not bool:
        raise AgentConfigError("kat500.enabled must be true or false")
    follow_radio = station.get("follow_radio", True)
    if type(follow_radio) is not bool:
        raise AgentConfigError("station.follow_radio must be true or false")
    digital_kpa_policy = str(station.get("digital_kpa_policy") or "operate").strip().lower()
    if digital_kpa_policy not in {"operate", "standby"}:
        raise AgentConfigError("station.digital_kpa_policy must be operate or standby")
    antenna_enabled = antenna_policy.get("enabled", True)
    if type(antenna_enabled) is not bool:
        raise AgentConfigError("flex.antenna_policy.enabled must be true or false")
    if commissioned and not kpa_enabled:
        raise AgentConfigError("a commissioned station requires kpa500.enabled=true")
    if commissioned and not kat_enabled:
        raise AgentConfigError("a commissioned station requires kat500.enabled=true")
    if commissioned and not follow_radio:
        raise AgentConfigError("a commissioned station requires station.follow_radio=true")
    if commissioned and not antenna_enabled:
        raise AgentConfigError(
            "a commissioned station requires flex.antenna_policy.enabled=true"
        )

    def positive_float(name: str, default: float) -> float:
        try:
            value = float(station.get(name, default))
        except (TypeError, ValueError) as exc:
            raise AgentConfigError(f"station.{name} must be numeric") from exc
        if value <= 0:
            raise AgentConfigError(f"station.{name} must be positive")
        return value

    target_swr = positive_float("tune_target_swr", 1.5)
    abort_swr = positive_float("tune_abort_swr", 3.0)
    if abort_swr <= target_swr:
        raise AgentConfigError("station.tune_abort_swr must be greater than tune_target_swr")

    return AgentConfig(
        path=source,
        bind_host=bind_host,
        bind_port=_port(server.get("bind_port", 8840), "server.bind_port"),
        control_token=token,
        flex_host=flex_host,
        flex_port=_port(flex.get("port", 4992), "flex.port"),
        flex_slice_id=slice_id,
        flex_station_name=flex_station_name,
        kpa_enabled=kpa_enabled,
        kpa_port=kpa_port,
        kpa_baudrate=_integer(
            kpa.get("baudrate", 38400),
            "kpa500.baudrate",
            minimum=300,
            maximum=1_000_000,
        ),
        kat_enabled=kat_enabled,
        kat_port=kat_port,
        kat_baudrate=_integer(
            kat.get("baudrate", 38400),
            "kat500.baudrate",
            minimum=300,
            maximum=1_000_000,
        ),
        follow_radio=follow_radio,
        digital_kpa_policy=digital_kpa_policy,
        commissioned=commissioned,
        flex_antenna_policy={"enabled": antenna_enabled, "bands": normalized_flex_bands},
        kat_antenna_policy=_band_map(
            station.get("kat_antenna_policy"), "station.kat_antenna_policy", minimum=1, maximum=3
        ),
        kat_antenna_names=normalized_names,
        amplifier_allowed_bands=_band_list(
            station.get("amplifier_allowed_bands"), "station.amplifier_allowed_bands"
        ),
        amplifier_drive_w=_band_map(
            station.get("amplifier_drive_w"), "station.amplifier_drive_w", minimum=1, maximum=100
        ),
        barefoot_drive_w=_band_map(
            station.get("barefoot_drive_w"), "station.barefoot_drive_w", minimum=1, maximum=100
        ),
        digital_amplifier_allowed_bands=_band_list(
            station.get("digital_amplifier_allowed_bands"),
            "station.digital_amplifier_allowed_bands",
        ),
        digital_amplifier_drive_w=_band_map(
            station.get("digital_amplifier_drive_w"),
            "station.digital_amplifier_drive_w",
            minimum=1,
            maximum=100,
        ),
        tune_power_w=_integer(
            station.get("tune_power_w", 25),
            "station.tune_power_w",
            minimum=1,
            maximum=100,
        ),
        tune_target_swr=target_swr,
        tune_abort_swr=abort_swr,
        tune_timeout_seconds=positive_float("tune_timeout_seconds", 30.0),
    )
