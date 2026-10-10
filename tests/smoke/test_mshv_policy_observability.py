import hashlib
import json

import pytest
from fastapi import HTTPException

from services import mshv_configuration as configuration
from services.mshv_observability import daily_summaries, normalize_status, record_qso, record_selection
from services.mshv_history import reconcile_source_backed_pending, stage_pending_delta
from radio_control.persistence import atomic_write_json


def test_native_policy_schema_round_trips_exact_ini_keys(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(runtime))
    monkeypatch.setattr(configuration, "STARTUP_SAFETY_PATH", tmp_path / "startup.json")

    result = configuration.update_mshv_auto_dx_settings({
        "prefer_non_europe": False,
        "filter_matrix_enabled": True,
        "filter_new": {"call": True, "dxcc": True, "continent": True, "grid": False, "cq_zone": True, "itu_zone": False},
        "filter_new_on_band": {"call": True, "dxcc": False, "continent": True, "grid": True, "cq_zone": False, "itu_zone": True},
        "filter_continents": ["AF", "AS", "NA"],
        "allow_band_dxcc_outside_continent": False,
        "filter_lotw_only": True,
        "min_snr": -17,
        "treat_73_as_cq": True,
        "watch_unconfirmed_dxcc": False,
        "selection_order": "last",
        "call_window_seconds": 120,
        "max_consecutive_windows": 1,
        "same_target_revisit_delay_seconds": 120,
        "recent_qso_cooldown_seconds": 7200,
        "min_band_dwell_seconds": 180,
        "engaged_completion_grace_seconds": 76,
        "target_priority": {"non_europe": 7777},
    }, engine_running=False)

    assert result["filter_new"]["continent"] is True
    assert result["filter_new_on_band"]["itu_zone"] is True
    assert result["filter_continents"] == ["AF", "AS", "NA"]
    assert result["filter_lotw_only_effective"] is False
    assert result["engaged_completion_grace_seconds"] == 90
    assert result["native_policy_capabilities"]["backend_planner_active"] is False
    text = (runtime / "settings" / "autodx.ini").read_text(encoding="utf-8")
    for expected in (
        "PreferNonEurope=false", "NonEuropeBoost=7777",
        "FilterMatrixEnabled=true", "FilterNewContinent=true",
        "FilterBandItuZone=true", "FilterContinents=AF,AS,NA",
        "AllowBandDxccOutsideContinent=false",
        "FilterLotwOnly=true", "MinSignal=-17", "Treat73AsCq=true",
        "WatchUnconfirmedDxcc=false", "Order=last",
        "CallWindowSeconds=120", "MaxConsecutiveWindows=1",
        "SameTargetRetrySeconds=120", "MinimumDwellSeconds=180",
        "RecentQsoCooldownSeconds=7200",
        "EngagedCompletionGraceSeconds=90",
    ):
        assert expected in text
    parsed = configuration._parser(runtime / "settings" / "autodx.ini")
    assert parsed.getint("Attempt", "EngagedCompletionGraceSeconds") == 90
    assert parsed.getint("Attempt", "RecentQsoCooldownSeconds") == 7200
    assert not parsed.has_option("AutoDX", "EngagedCompletionGraceSeconds")


def test_nondefault_attempt_budget_matches_real_native_runtime_shape(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    (runtime / "settings").mkdir(parents=True)
    (runtime / "settings/autodx.ini").write_text(
        "[AutomationTiming]\nNormalCallSeconds=150\n", encoding="utf-8",
    )
    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(runtime))
    monkeypatch.setattr(configuration, "STARTUP_SAFETY_PATH", tmp_path / "startup.json")
    saved = configuration.update_mshv_auto_dx_settings({
        "call_window_seconds": 240,
        "max_consecutive_windows": 2,
    }, engine_running=False)
    assert saved["automation_timing"]["normal_call_seconds"] == 480
    assert "NormalCallSeconds" not in (runtime / "settings/autodx.ini").read_text(encoding="utf-8")

    desired = json.loads(json.dumps(saved["desired"]))
    native = json.loads(json.dumps(desired))
    native["schema_version"] = 1
    native["lotw_membership_capability"] = True
    native["confirmed_dxcc_data_available"] = True
    native["desired_enabled"] = native.pop("enabled")
    native.pop("enabled_band_names", None)
    timing = native["automation_timing"]
    timing["normal_call_seconds"] = 999  # obsolete native field is ignored
    timing.update({
        "call_window_seconds": native.pop("call_window_seconds"),
        "max_consecutive_windows": native.pop("max_consecutive_windows"),
        "same_target_retry_seconds": native.pop("same_target_revisit_delay_seconds"),
        "recent_qso_cooldown_seconds": native.pop("recent_qso_cooldown_seconds"),
        "minimum_band_dwell_seconds": native.pop("min_band_dwell_seconds"),
        "engaged_completion_grace_seconds": native.pop("engaged_completion_grace_seconds"),
    })
    eligibility = native["eligibility"]
    eligibility.update({
        "filter_matrix_enabled": native.pop("filter_matrix_enabled"),
        **{f"filter_new_{name}": value for name, value in native.pop("filter_new").items()},
        **{f"filter_band_{name}": value for name, value in native.pop("filter_new_on_band").items()},
        "continents": native.pop("filter_continents"),
        "lotw_only": native.pop("filter_lotw_only"),
        "treat_73_as_cq": native.pop("treat_73_as_cq"),
        "watch_unconfirmed_dxcc": native.pop("watch_unconfirmed_dxcc"),
        "allow_band_dxcc_outside_continent": native.pop("allow_band_dxcc_outside_continent"),
    })
    eligibility["continents"] = list(reversed(eligibility["continents"]))
    native["target_priority"]["non_europe_boost"] = native["target_priority"].pop("non_europe")

    matched = configuration.read_mshv_auto_dx_settings(
        engine_running=True, engine_state={"autodx_config": native},
    )
    assert matched["runtime_parity"] == {"status": "match", "drift": []}
    assert matched["lotw_membership_capability"] is True
    assert matched["confirmed_dxcc_data_available"] is True
    removed_continent = native["eligibility"]["continents"].pop()
    continent_drift = configuration.read_mshv_auto_dx_settings(
        engine_running=True, engine_state={"autodx_config": native},
    )
    assert continent_drift["runtime_parity"] == {
        "status": "drift", "drift": ["filter_continents"],
    }
    native["eligibility"]["continents"].append(removed_continent)
    native["eligibility"]["filter_new_grid"] = not native["eligibility"]["filter_new_grid"]
    drifted = configuration.read_mshv_auto_dx_settings(
        engine_running=True, engine_state={"autodx_config": native},
    )
    assert drifted["runtime_parity"] == {"status": "drift", "drift": ["filter_new"]}


def test_runtime_parity_ignores_reference_and_directed_caller_observations():
    desired = {key: {} for key, _ in configuration._PARITY_PATHS}
    desired["spot_sources"] = {"dx_cluster": {}}
    desired["reference_hunting"] = {
        "enabled": True,
        "pota_enabled": True,
        "sota_enabled": True,
        "wwff_enabled": True,
        "max_activation_age_seconds": 900,
    }
    desired["directed_callers"] = {
        "enabled": True,
        "inbox_size": 8,
        "max_age_seconds": 90,
    }
    effective = {
        "schema_version": 1,
        **{
            effective_key: desired[desired_key]
            for desired_key, effective_key in configuration._PARITY_PATHS
        },
        "reference_hunting": {
            **desired["reference_hunting"],
            "activation_count": 17,
            "index_valid": True,
        },
        "directed_callers": {
            **desired["directed_callers"],
            "queued": 3,
        },
    }

    assert configuration._runtime_parity(desired, effective) == {
        "status": "match", "drift": [],
    }

    effective["reference_hunting"]["pota_enabled"] = False
    assert configuration._runtime_parity(desired, effective) == {
        "status": "drift", "drift": ["reference_hunting"],
    }
    effective["reference_hunting"]["pota_enabled"] = True
    effective["directed_callers"]["inbox_size"] = 9
    assert configuration._runtime_parity(desired, effective) == {
        "status": "drift", "drift": ["directed_callers"],
    }


@pytest.mark.parametrize("payload,match", [
    ({"filter_new": {"award": True}}, "Unknown filter_new"),
    ({"filter_continents": ["EU", "XX"]}, "Unknown continent"),
    ({"selection_order": "new_dxcc"}, "score or last"),
    ({"call_window_seconds": 121}, "120 or 240"),
    ({"max_consecutive_windows": 21}, "between 1 and 20"),
    ({"recent_qso_cooldown_seconds": 86401}, "between 0 and 86400"),
    ({"engaged_completion_grace_seconds": 121}, "between 15 and 120"),
])
def test_native_policy_rejects_unknown_or_unsafe_values(tmp_path, monkeypatch, payload, match):
    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(tmp_path / "runtime"))
    with pytest.raises(HTTPException, match=match):
        configuration.update_mshv_auto_dx_settings(payload, engine_running=False)


def test_filter_matrix_defaults_active_but_preserves_explicit_false(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    settings = runtime / "settings" / "autodx.ini"
    settings.parent.mkdir(parents=True)
    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(runtime))
    monkeypatch.setattr(configuration, "STARTUP_SAFETY_PATH", tmp_path / "startup.json")

    defaults = configuration.read_mshv_auto_dx_settings(engine_running=False)
    assert defaults["filter_matrix_enabled"] is True
    assert defaults["filter_new"]["call"] is True
    assert defaults["filter_new_on_band"]["call"] is True
    assert defaults["engaged_completion_grace_seconds"] == 120
    assert defaults["recent_qso_cooldown_seconds"] == 3600
    assert defaults["allow_band_dxcc_outside_continent"] is True

    settings.write_text(
        "[Eligibility]\nFilterMatrixEnabled=false\nFilterNewCall=true\n",
        encoding="utf-8",
    )
    explicit = configuration.read_mshv_auto_dx_settings(engine_running=False)
    assert explicit["filter_matrix_enabled"] is False


def test_partial_filter_update_activates_matrix_and_grace_rounds_to_slots(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(runtime))
    monkeypatch.setattr(configuration, "STARTUP_SAFETY_PATH", tmp_path / "startup.json")

    saved = configuration.update_mshv_auto_dx_settings({
        "filter_new": {"continent": True},
        "engaged_completion_grace_seconds": 16,
    }, engine_running=False)
    assert saved["filter_matrix_enabled"] is True
    assert saved["filter_new"]["continent"] is True
    assert saved["engaged_completion_grace_seconds"] == 30
    text = (runtime / "settings" / "autodx.ini").read_text(encoding="utf-8")
    assert "FilterMatrixEnabled=true" in text
    assert "EngagedCompletionGraceSeconds=30" in text
    parsed = configuration._parser(runtime / "settings" / "autodx.ini")
    assert parsed.getint("Attempt", "EngagedCompletionGraceSeconds") == 30
    assert not parsed.has_option("AutoDX", "EngagedCompletionGraceSeconds")


def test_legacy_autodx_completion_grace_reads_and_migrates_to_attempt(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    settings = runtime / "settings" / "autodx.ini"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        "[AutoDX]\nEngagedCompletionGraceSeconds=46\n"
        "[Attempt]\nRecentQsoCooldownSeconds=4321\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(runtime))
    monkeypatch.setattr(configuration, "STARTUP_SAFETY_PATH", tmp_path / "startup.json")

    observed = configuration.read_mshv_auto_dx_settings(engine_running=False)
    assert observed["engaged_completion_grace_seconds"] == 60
    assert observed["recent_qso_cooldown_seconds"] == 4321
    configuration.update_mshv_auto_dx_settings({"min_snr": -20}, engine_running=False)

    migrated = configuration._parser(settings)
    assert migrated.getint("Attempt", "EngagedCompletionGraceSeconds") == 60
    assert migrated.getint("Attempt", "RecentQsoCooldownSeconds") == 4321
    assert not migrated.has_option("AutoDX", "EngagedCompletionGraceSeconds")


def test_observability_normalizes_missing_fields_without_inventing_live_state():
    result = normalize_status({"selection_score": 42, "skipped_reasons": ["LoTW-only"]}, fresh=False)
    assert result["reported"] is True
    assert result["fresh"] is False
    assert result["target"] is None
    assert result["selection_score"] == 42
    assert result["budget"]["call_window_seconds"] == 120
    assert result["next_retry"]["utc"] is None
    assert result["audit"]["event_counter"] == 0


def test_daily_summary_is_exact_once_by_selection_and_qso_ids(tmp_path):
    path = tmp_path / "summaries.json"
    selection = {
        "selection_id": "selection-1", "timestamp": "2026-10-06T12:00:00+00:00",
        "target": {"call": "VK9AA", "band": "20m"},
    }
    qso = {"event_id": "a" * 64, "last_acknowledged_utc": "2026-10-06T12:05:00+00:00"}
    record_selection(selection, path=path)
    record_selection(selection, path=path)
    record_qso(qso, path=path)
    record_qso(qso, path=path)
    row = daily_summaries(path=path)["days"][0]
    assert row["bands"] == {"20m": 1}
    assert row["targets"] == {"VK9AA": 1}
    assert row["qsos"] == 1


def test_legacy_pending_reconciliation_is_preview_only_until_explicitly_applied(tmp_path):
    runtime = tmp_path / "runtime"
    source = tmp_path / "canonical.adi"
    delta = tmp_path / "deltas.json"
    adif = (
        "<CALL:5>VK9AA<QSO_DATE:8>20261006<TIME_ON:6>120000<TIME_OFF:6>120115"
        "<BAND:3>20m<FREQ:6>14.074<MODE:3>FT8<STATION_CALLSIGN:5>OM0RX"
        f"<APP_OM0RX_EVENT_ID:64>{'b' * 64}<APP_OM0RX_CLIENT_ID:21>MSHV-OM0RX-AUTO-DX"
        "<APP_OM0RX_PROVIDER:12>mshv_auto_dx<EOR>"
    )
    source.write_text(adif, encoding="utf-8")
    runtime.mkdir(parents=True)
    atomic_write_json(runtime / "history-import.json", {
        "applied": True, "canonical_source": "wavelog_postgres",
        "canonical_sha256": hashlib.sha256(adif.encode()).hexdigest(), "source": str(source),
    })
    staged = stage_pending_delta({
        "adif_text": adif, "provider": "mshv_auto_dx",
        "client_id": "MSHV-OM0RX-AUTO-DX", "event_id": "b" * 64,
    }, path=delta)
    assert staged["pending"] is True
    preview = reconcile_source_backed_pending(runtime=runtime, delta_path=delta, apply=False)
    assert preview["promotable_count"] == 1
    assert preview["promoted_count"] == 0
    applied = reconcile_source_backed_pending(runtime=runtime, delta_path=delta, apply=True)
    assert applied["promoted_count"] == 1


def test_pending_reconciliation_rejects_weak_identity_collision(tmp_path):
    runtime = tmp_path / "runtime"
    source = tmp_path / "canonical.adi"
    delta = tmp_path / "deltas.json"
    event_id = "c" * 64
    pending = (
        "<CALL:5>VK9AA<QSO_DATE:8>20261006<TIME_ON:6>120000<TIME_OFF:6>120115"
        "<BAND:3>20m<FREQ:6>14.074<MODE:3>FT8<STATION_CALLSIGN:5>OM0RX"
        f"<APP_OM0RX_EVENT_ID:64>{event_id}<APP_OM0RX_CLIENT_ID:21>MSHV-OM0RX-AUTO-DX"
        "<APP_OM0RX_PROVIDER:12>mshv_auto_dx<EOR>"
    )
    # Same former weak identity, but no event id and different TIME_OFF/FREQ.
    canonical = (
        "<CALL:5>VK9AA<QSO_DATE:8>20261006<TIME_ON:6>120000<TIME_OFF:6>120116"
        "<BAND:3>20m<FREQ:6>14.075<MODE:3>FT8<STATION_CALLSIGN:5>OM0RX<EOR>"
    )
    source.write_text(canonical, encoding="utf-8")
    runtime.mkdir(parents=True)
    atomic_write_json(runtime / "history-import.json", {
        "applied": True, "canonical_source": "wavelog_postgres",
        "canonical_sha256": hashlib.sha256(canonical.encode()).hexdigest(), "source": str(source),
    })
    assert stage_pending_delta({
        "adif_text": pending, "provider": "mshv_auto_dx",
        "client_id": "MSHV-OM0RX-AUTO-DX", "event_id": event_id,
    }, path=delta)["pending"] is True
    result = reconcile_source_backed_pending(runtime=runtime, delta_path=delta, apply=True)
    assert result["promotable_count"] == 0
    assert result["promoted_count"] == 0


def test_pending_reconciliation_reports_ambiguous_exact_fallback(tmp_path):
    runtime = tmp_path / "runtime"
    source = tmp_path / "canonical.adi"
    delta = tmp_path / "deltas.json"
    event_id = "d" * 64
    base = (
        "<CALL:5>VK9AA<QSO_DATE:8>20261006<TIME_ON:6>120000<TIME_OFF:6>120115"
        "<BAND:3>20m<FREQ:6>14.074<MODE:3>FT8<STATION_CALLSIGN:5>OM0RX"
    )
    pending = (
        base + f"<APP_OM0RX_EVENT_ID:64>{event_id}"
        "<APP_OM0RX_CLIENT_ID:21>MSHV-OM0RX-AUTO-DX"
        "<APP_OM0RX_PROVIDER:12>mshv_auto_dx<EOR>"
    )
    canonical = base + "<EOR>" + base + "<EOR>"
    source.write_text(canonical, encoding="utf-8")
    runtime.mkdir(parents=True)
    atomic_write_json(runtime / "history-import.json", {
        "applied": True, "canonical_source": "wavelog_postgres",
        "canonical_sha256": hashlib.sha256(canonical.encode()).hexdigest(), "source": str(source),
    })
    staged = stage_pending_delta({
        "adif_text": pending, "provider": "mshv_auto_dx",
        "client_id": "MSHV-OM0RX-AUTO-DX", "event_id": event_id,
    }, path=delta)
    result = reconcile_source_backed_pending(runtime=runtime, delta_path=delta, apply=True)
    assert result["promoted_count"] == 0
    assert result["ambiguous"] == [{
        "key": staged["delta_key"], "reason": "ambiguous-canonical-match", "candidate_count": 2,
    }]
