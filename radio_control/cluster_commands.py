"""DX cluster command helpers."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


DEFAULT_RBL_COMMAND_PROFILES: dict[str, dict[str, Any]] = {
    "dxspider": {
        "name": "DXSpider",
        "enable": "set/skimmer",
        "disable": "unset/skimmer",
        "modes": {},
        "supports_mode_commands": False,
        "mode_note": "Mode filtering is handled in the spot table unless custom commands are configured.",
    },
    "cccluster": {
        "name": "CC Cluster",
        "enable": "set/skimmer",
        "disable": "unset/skimmer",
        "modes": {},
        "supports_mode_commands": False,
        "mode_note": "Built-in profile only toggles skimmer feed; add custom profile modes for server-side mode commands.",
    },
    "ve7cc": {
        "name": "VE7CC",
        "enable": "set/skimmer",
        "disable": "unset/skimmer",
        "modes": {},
        "supports_mode_commands": False,
        "mode_note": "Built-in profile only toggles skimmer feed; add custom profile modes for server-side mode commands.",
    },
}


def _normalize_profile_name(profile_name: str | None) -> str:
    name = str(profile_name or "dxspider").strip().lower()
    return name or "dxspider"


def merged_rbl_profiles(configured_profiles: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Merge user-defined command profiles over built-in profile names."""
    profiles = {key: dict(value) for key, value in DEFAULT_RBL_COMMAND_PROFILES.items()}
    for key, value in (configured_profiles or {}).items():
        if not isinstance(value, Mapping):
            continue
        normalized = _normalize_profile_name(key)
        base = dict(profiles.get(normalized, {}))
        base.update(dict(value))
        base["modes"] = dict(base.get("modes") or {})
        base["supports_mode_commands"] = bool(base.get("supports_mode_commands") or base["modes"])
        profiles[normalized] = base
    return profiles


def build_rbl_command_plan(
    enabled: bool,
    modes: Sequence[str] | None = None,
    profile_name: str | None = None,
    configured_profiles: Mapping[str, Any] | None = None,
    legacy_enable_command: str | None = None,
    legacy_disable_command: str | None = None,
    legacy_mode_commands: Mapping[str, str] | None = None,
) -> tuple[str, list[str]]:
    """Return the selected profile name and cluster commands to toggle RBL/skimmer spots."""
    profiles = merged_rbl_profiles(configured_profiles)
    normalized_profile = _normalize_profile_name(profile_name)
    profile = profiles.get(normalized_profile) or profiles["dxspider"]

    command = profile.get("enable" if enabled else "disable")
    if enabled and legacy_enable_command:
        command = legacy_enable_command
    elif not enabled and legacy_disable_command:
        command = legacy_disable_command
    command = str(command or "").strip()
    commands = [command] if command else []

    mode_commands = dict(profile.get("modes") or {})
    mode_commands.update({str(key).upper(): value for key, value in (legacy_mode_commands or {}).items()})
    if enabled and modes:
        for mode in modes:
            mode_command = mode_commands.get(str(mode).upper())
            if mode_command:
                commands.append(str(mode_command).strip())

    return normalized_profile if normalized_profile in profiles else "dxspider", [cmd for cmd in commands if cmd]
