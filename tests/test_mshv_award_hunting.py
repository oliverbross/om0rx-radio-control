from datetime import UTC, datetime, timedelta
import json

import duckdb
import pytest
from fastapi import HTTPException

from activity_intelligence.repository import ActivityRepository
from activity_intelligence.services import ActivityIntelligenceService
from services.mshv_award_hunting import (
    build_award_hunting_watch,
    publish_repository_award_hunting_watch,
    record_acknowledged_award_qso,
    write_award_hunting_watch,
)
from services.mshv_configuration import (
    read_mshv_auto_dx_settings,
    update_mshv_auto_dx_settings,
)


NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def _attestation(**overrides):
    value = {
        "status": "healthy",
        "historical_novelty_allowed": True,
        "generated_at": NOW.isoformat(),
        "max_age_seconds": 10,
        "snapshot": {"generation": "a" * 64},
        "deltas": {"count": 2, "pending_outbox": 1},
        "reasons": [],
    }
    value.update(overrides)
    return value


def _activation(program, reference, **overrides):
    row = {
        "program": program,
        "type": "ACTIVE_SPOT",
        "activator_call": "K1ABC/P",
        "references": [reference],
        "frequency_khz": 14074.0,
        "mode": "FT8",
        "source_id": f"{program}_SPOTS",
        "last_seen_utc": (NOW - timedelta(seconds=30)).isoformat(),
    }
    row.update(overrides)
    return row


def test_award_watch_keeps_programs_additive_and_dedupes_exact_slots():
    history = [
        {"pota_ref": "K-1234", "band": "40m", "mode": "FT8"},
        {"wwff_ref": "KFF-0999", "band": "20m", "mode": "FT8"},
    ]
    activations = [
        _activation("POTA", "K-1234"),
        _activation("POTA", "K-1234", last_seen_utc=(NOW - timedelta(seconds=10)).isoformat()),
        _activation("SOTA", "W1/AM-001", activator_call="W1XYZ/P"),
        _activation("WWFF", "KFF-0999", activator_call="K2XYZ"),
        _activation("POTA", "K-9999", mode="SSB"),
        _activation("POTA", "K-8888", last_seen_utc=(NOW - timedelta(hours=1)).isoformat()),
    ]

    watch = build_award_hunting_watch(activations, history_rows=history, now=NOW)

    assert watch["schema"] == 1
    assert watch["enabled_programs"] == ["POTA", "SOTA", "WWFF"]
    assert len(watch["activations"]) == 3
    by_slot = {entry["slot_key"]: entry for entry in watch["activations"]}
    pota = by_slot["POTA:K-1234@20m@FT8"]
    assert pota["spotted_at_utc"] == "2026-10-07T11:59:50Z"
    assert pota["gaps"] == {
        "new_reference": False,
        "new_reference_on_band": True,
        "new_reference_on_band_mode": True,
    }
    assert by_slot["SOTA:W1/AM-001@20m@FT8"]["gaps"] == {
        "new_reference": True,
        "new_reference_on_band": True,
        "new_reference_on_band_mode": True,
    }
    assert not any(by_slot["WWFF:KFF-0999@20m@FT8"]["gaps"].values())


def test_activation_identity_uses_base_call_but_slot_key_stays_award_slot():
    watch = build_award_hunting_watch(
        [
            _activation("POTA", "K-1234", activator_call="K1ABC/P"),
            _activation("POTA", "K-1234", activator_call="EA8/K1ABC/P", last_seen_utc=(NOW - timedelta(seconds=5)).isoformat()),
            _activation("POTA", "K-1234", activator_call="K2XYZ/P"),
        ],
        now=NOW,
    )
    assert len(watch["activations"]) == 2
    assert {entry["base_call"] for entry in watch["activations"]} == {"K1ABC", "K2XYZ"}
    assert {entry["slot_key"] for entry in watch["activations"]} == {"POTA:K-1234@20m@FT8"}


def test_history_uses_adif_submode_and_exact_comment_references():
    history = [
        {"band": "20m", "mode": "MFSK", "submode": "FT8", "comment": "CQ POTA K-1234"},
        {"band": "20m", "mode": "FT8", "comment": "CQ POTA K-12345"},
    ]
    watch = build_award_hunting_watch(
        [
            _activation("POTA", "K-1234", mode="MFSK+FT8"),
            _activation("POTA", "K-12345", activator_call="K2XYZ"),
        ],
        history_rows=history,
        now=NOW,
    )
    by_ref = {entry["reference"]: entry for entry in watch["activations"]}
    assert not any(by_ref["K-1234"]["gaps"].values())
    assert not any(by_ref["K-12345"]["gaps"].values())
    false_prefix = build_award_hunting_watch(
        [_activation("POTA", "K-1234")],
        history_rows=[{"band": "20m", "mode": "FT8", "comment": "CQ POTA K-12345"}],
        now=NOW,
    )
    assert all(false_prefix["activations"][0]["gaps"].values())


def test_activity_status_uses_submode_and_does_not_match_reference_prefix(tmp_path):
    qso_path = tmp_path / "status.duckdb"
    conn = duckdb.connect(str(qso_path))
    conn.execute(
        """
        CREATE TABLE qso_records (
            qso_datetime TIMESTAMP, time_on TIMESTAMP, band VARCHAR,
            mode VARCHAR, submode VARCHAR, pota_ref VARCHAR,
            sig VARCHAR, sig_info VARCHAR, comment VARCHAR
        )
        """
    )
    conn.execute(
        "INSERT INTO qso_records VALUES (current_timestamp, current_timestamp, '20m', "
        "'MFSK', 'FT8', '', '', '', 'worked CQ POTA K-12345')"
    )
    conn.execute(
        "INSERT INTO qso_records VALUES (current_timestamp, current_timestamp, '20m', "
        "'MFSK', 'FT8', '', '', '', 'worked CQ POTA K-1234')"
    )
    conn.close()
    service = ActivityIntelligenceService(
        repository=ActivityRepository(tmp_path / "ai.duckdb"), qso_db_path=qso_path,
    )
    exact = service.portable_reference_status("POTA", "K-1234", band="20m", mode="MFSK+FT8")
    assert exact["count"] == 1
    assert exact["workedOnBandMode"] is True


def test_program_switches_filter_independently_not_exclusively():
    watch = build_award_hunting_watch(
        [_activation("POTA", "K-1234"), _activation("SOTA", "W1/AM-001")],
        now=NOW,
        enabled_programs=["POTA"],
    )
    assert watch["enabled_programs"] == ["POTA"]
    assert [entry["program"] for entry in watch["activations"]] == ["POTA"]


def test_repository_publish_writes_atomic_runtime_sidecar_with_qso_slots(tmp_path):
    qso_path = tmp_path / "qso.duckdb"
    conn = duckdb.connect(str(qso_path))
    conn.execute(
        """
        CREATE TABLE qso_records (
            band VARCHAR, mode VARCHAR, submode VARCHAR,
            pota_ref VARCHAR, sota_ref VARCHAR, wwff_ref VARCHAR,
            sig VARCHAR, sig_info VARCHAR, comment VARCHAR
        )
        """
    )
    conn.execute("INSERT INTO qso_records VALUES ('20m', 'FT8', '', 'K-1234', '', '', 'POTA', 'K-1234', '')")
    conn.close()

    class Repository:
        def portable_activations(self, limit):
            assert limit == 1000
            return [_activation("POTA", "K-1234")]

    result = publish_repository_award_hunting_watch(
        Repository(), tmp_path / "runtime", qso_db_path=qso_path, now=NOW,
        history_attestation=_attestation(),
    )
    payload = json.loads((tmp_path / "runtime/settings/database/award_hunting.json").read_text(encoding="utf-8"))
    assert payload == result["watch"]
    assert payload["history_authoritative"] is True
    assert payload["history_authority"]["pending_outbox_count"] == 1
    assert payload["activations"][0]["gaps"] == {
        "new_reference": False,
        "new_reference_on_band": False,
        "new_reference_on_band_mode": False,
    }


def test_acknowledged_reference_delta_stays_closed_until_mirror_catches_up(tmp_path):
    qso_path = tmp_path / "qso.duckdb"
    conn = duckdb.connect(str(qso_path))
    conn.execute(
        "CREATE TABLE qso_records (band VARCHAR, mode VARCHAR, submode VARCHAR, pota_ref VARCHAR, "
        "sota_ref VARCHAR, wwff_ref VARCHAR, sig VARCHAR, sig_info VARCHAR, comment VARCHAR)"
    )
    conn.close()
    delta_path = tmp_path / "award-deltas.json"
    qso = {"callsign": "K1ABC", "band": "20m", "mode": "MFSK", "submode": "FT8", "pota_ref": "K-1234"}
    assert record_acknowledged_award_qso(qso, path=delta_path)["recorded"] is True

    class Repository:
        def portable_activations(self, limit):
            return [_activation("POTA", "K-1234")]

    first = publish_repository_award_hunting_watch(
        Repository(), tmp_path / "runtime", qso_db_path=qso_path,
        award_delta_path=delta_path, history_attestation=_attestation(), now=NOW,
    )["watch"]
    assert first["history_authoritative"] is True
    assert first["history_authority"]["award_delta_pending"] == 1
    assert not any(first["activations"][0]["gaps"].values())

    # A later publisher invocation has no in-memory supplemental row.  It must
    # reconstruct the acknowledgement from disk just as it would after a
    # backend restart or ordinary periodic refresh.
    second = publish_repository_award_hunting_watch(
        Repository(), tmp_path / "runtime", qso_db_path=qso_path,
        award_delta_path=delta_path, history_attestation=_attestation(),
        now=NOW + timedelta(seconds=5),
    )["watch"]
    assert second["history_authority"]["award_delta_pending"] == 1
    assert not any(second["activations"][0]["gaps"].values())
    assert len(json.loads(delta_path.read_text(encoding="utf-8"))["records"]) == 1

    conn = duckdb.connect(str(qso_path))
    conn.execute(
        "INSERT INTO qso_records VALUES ('20m', 'MFSK', 'FT8', 'K-1234', '', '', 'POTA', 'K-1234', '')"
    )
    conn.close()
    mirrored = publish_repository_award_hunting_watch(
        Repository(), tmp_path / "runtime", qso_db_path=qso_path,
        award_delta_path=delta_path, history_attestation=_attestation(),
        now=NOW + timedelta(seconds=6),
    )["watch"]
    assert mirrored["history_authority"]["award_delta_pending"] == 0
    assert mirrored["history_authority"]["award_delta_retired"] == 1
    assert not any(mirrored["activations"][0]["gaps"].values())
    assert json.loads(delta_path.read_text(encoding="utf-8"))["records"] == {}


def test_repository_publish_fails_closed_when_history_is_unavailable(tmp_path):
    class Repository:
        def portable_activations(self, limit):
            return [_activation("POTA", "K-1234")]

    result = publish_repository_award_hunting_watch(
        Repository(), tmp_path / "runtime", qso_db_path=tmp_path / "missing.duckdb", now=NOW,
    )
    watch = result["watch"]
    assert watch["history_authoritative"] is False
    assert watch["activations"][0]["history_status"] == "unavailable"
    assert not any(watch["activations"][0]["gaps"].values())


def test_stale_attestation_fails_closed_even_with_available_qso_cache(tmp_path):
    qso_path = tmp_path / "qso.duckdb"
    conn = duckdb.connect(str(qso_path))
    conn.execute(
        "CREATE TABLE qso_records (band VARCHAR, mode VARCHAR, submode VARCHAR, pota_ref VARCHAR, "
        "sota_ref VARCHAR, wwff_ref VARCHAR, sig VARCHAR, sig_info VARCHAR, comment VARCHAR)"
    )
    conn.close()

    class Repository:
        def portable_activations(self, limit):
            return [_activation("POTA", "K-1234")]

    stale = _attestation(generated_at=(NOW - timedelta(seconds=11)).isoformat())
    watch = publish_repository_award_hunting_watch(
        Repository(), tmp_path / "runtime", qso_db_path=qso_path,
        history_attestation=stale, now=NOW,
    )["watch"]
    assert watch["history_authoritative"] is False
    assert watch["history_authority"]["fresh"] is False
    assert not any(watch["activations"][0]["gaps"].values())


def test_identical_watch_publication_is_a_noop_until_freshness_renewal(tmp_path):
    target = tmp_path / "award_hunting.json"
    first = write_award_hunting_watch(target, [_activation("POTA", "K-1234")], now=NOW)
    second = write_award_hunting_watch(
        target, [_activation("POTA", "K-1234")], now=NOW + timedelta(seconds=30),
    )
    assert second == first
    renewed = write_award_hunting_watch(
        target, [_activation("POTA", "K-1234")], now=NOW + timedelta(seconds=1801),
    )
    assert renewed["generated_at_utc"] != first["generated_at_utc"]


def test_composable_settings_defaults_and_running_hot_update(tmp_path, monkeypatch):
    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(tmp_path / "runtime"))
    initial = read_mshv_auto_dx_settings(engine_running=True)
    assert initial["editable"] is True
    assert initial["restart_required_after_save"] is False
    assert initial["reference_hunting"]["pota_enabled"] is True
    assert initial["reference_hunting"]["sota_enabled"] is True
    assert initial["reference_hunting"]["wwff_enabled"] is True
    assert initial["reference_hunting"]["pota_weight"] == 1800
    assert initial["award_hunting"]["stack_scores"] is True

    saved = update_mshv_auto_dx_settings(
        {
            "award_hunting": {"new_cq_zone_weight": 2300},
            "reference_hunting": {"pota_enabled": False, "sota_enabled": True, "pota_weight": 1900},
            "propagation_adaptation": {"window_seconds": 1200},
            "campaign": {"profile": "dxcc-challenge"},
            "pileup_strategy": {"audio_offsets_hz": [0, -100, 100]},
            "directed_callers": {"inbox_size": 12},
            "outcome_learning": {"telemetry_file": "logs/learn.jsonl"},
        },
        engine_running=True,
    )
    assert saved["saved"] is True
    assert saved["reference_hunting"]["pota_enabled"] is False
    assert saved["reference_hunting"]["sota_enabled"] is True
    assert saved["reference_hunting"]["wwff_enabled"] is True
    assert saved["award_hunting"]["new_cq_zone_weight"] == 2300
    assert saved["propagation_adaptation"]["window_seconds"] == 1200
    assert saved["campaign"]["reference_weight_percent"] == 75
    assert saved["campaign"]["dxcc_weight_percent"] == 175
    assert saved["pileup_strategy"]["audio_offsets_hz"] == [0, -100, 100]
    assert saved["directed_callers"]["inbox_size"] == 12
    assert saved["outcome_learning"]["telemetry_file"] == "logs/learn.jsonl"
    assert "hot reload" in saved["message"].lower()

    custom = update_mshv_auto_dx_settings(
        {"campaign": {"state_weight_percent": 135}}, engine_running=True,
    )
    assert custom["campaign"]["profile"] == "custom"
    assert custom["campaign"]["state_weight_percent"] == 135


def test_rejects_unsafe_outcome_path_and_invalid_offset(tmp_path, monkeypatch):
    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(tmp_path / "runtime"))
    with pytest.raises(HTTPException, match="relative runtime path"):
        update_mshv_auto_dx_settings(
            {"outcome_learning": {"telemetry_file": "../outside.jsonl"}}, engine_running=True,
        )
    with pytest.raises(HTTPException, match="audio_offsets_hz"):
        update_mshv_auto_dx_settings(
            {"pileup_strategy": {"audio_offsets_hz": [2500]}}, engine_running=True,
        )


def test_authoritative_portable_qso_triggers_sidecar_republish(monkeypatch):
    import services.mshv_award_hunting as award_hunting
    import services.qso_logging as qso_logging

    calls = []
    monkeypatch.setattr(qso_logging, "_record_qso_status", lambda qso: None)
    monkeypatch.setattr(qso_logging, "write_qso_to_postgres_read_cache", lambda qso: True)
    monkeypatch.setattr(
        award_hunting,
        "record_acknowledged_award_qso",
        lambda qso: {"recorded": True, "keys": ["test"]},
    )
    monkeypatch.setattr(
        award_hunting,
        "republish_after_authoritative_history_change",
        lambda reason, **kwargs: calls.append((reason, kwargs)),
    )

    qso = {"callsign": "K1ABC", "band": "20m", "mode": "FT8", "pota_ref": "K-1234"}
    qso_logging.record_qso_in_local_read_cache(qso)
    assert calls == [("wavelog-qso-acknowledged", {"acknowledged_qso": qso})]


def test_offline_replay_preserves_reference_fields_and_durably_closes_slots(tmp_path, monkeypatch):
    import asyncio

    from radio_control.qso_outbox import QSOOutbox
    import services.mshv_award_hunting as award_hunting
    import services.qso_logging as qso_logging

    def field(name, value):
        return f"<{name}:{len(value)}>{value}"

    values = {
        "CALL": "K1ABC",
        "QSO_DATE": "20261007",
        "TIME_ON": "120000",
        "TIME_OFF": "120045",
        "BAND": "20m",
        "FREQ": "14.074",
        "MODE": "MFSK",
        "SUBMODE": "FT8",
        "POTA_REF": "K-1234",
        "SOTA_REF": "W1/AM-001",
        "WWFF_REF": "KFF-0999",
        "SIG": "POTA",
        "SIG_INFO": "K-1234",
        "COMMENT": "CQ POTA K-1234 SOTA W1/AM-001 WWFF KFF-0999",
    }
    adif = "".join(field(name, value) for name, value in values.items()) + "<EOR>"
    parsed = qso_logging._qso_data_from_adif_record(adif)
    assert parsed["pota_ref"] == values["POTA_REF"]
    assert parsed["sota_ref"] == values["SOTA_REF"]
    assert parsed["wwff_ref"] == values["WWFF_REF"]
    assert parsed["sig"] == values["SIG"]
    assert parsed["sig_info"] == values["SIG_INFO"]
    assert parsed["comment"] == values["COMMENT"]
    assert parsed["mode"] == "FT8"

    delta_path = tmp_path / "award-deltas.json"
    monkeypatch.setattr(award_hunting, "AWARD_DELTA_PATH", delta_path)
    monkeypatch.setattr(award_hunting, "republish_after_authoritative_history_change", lambda *args, **kwargs: {})
    monkeypatch.setattr(qso_logging, "_record_qso_status", lambda qso: None)
    monkeypatch.setattr(qso_logging, "write_qso_to_postgres_read_cache", lambda qso: False)
    monkeypatch.setattr(qso_logging, "_record_dedupe_entries", lambda *args, **kwargs: None)

    class Wavelog:
        async def submit_adif_string(self, record):
            return {"success": True}

    outbox = QSOOutbox(tmp_path / "outbox.adif")
    monkeypatch.setattr(outbox, "_acknowledge_mshv_history", lambda record: None)
    assert outbox.enqueue_adif(adif)
    result = asyncio.run(outbox.replay(Wavelog(), on_resolved_record=qso_logging.record_qso_status_from_adif))
    assert result["success"] is True
    assert result["remaining"] == 0
    records = list(json.loads(delta_path.read_text(encoding="utf-8"))["records"].values())
    assert {(row["program"], row["reference"], row["band"], row["mode"]) for row in records} == {
        ("POTA", "K-1234", "20m", "FT8"),
        ("SOTA", "W1/AM-001", "20m", "FT8"),
        ("WWFF", "KFF-0999", "20m", "FT8"),
    }


def test_outbox_retains_record_when_durable_reference_promotion_fails(tmp_path, monkeypatch):
    import asyncio

    from radio_control.qso_outbox import QSOOutbox

    class Wavelog:
        async def submit_adif_string(self, record):
            return {"success": True}

    outbox = QSOOutbox(tmp_path / "outbox.adif")
    monkeypatch.setattr(outbox, "_acknowledge_mshv_history", lambda record: None)
    assert outbox.enqueue_adif("<CALL:5>K1ABC<BAND:3>20m<MODE:3>FT8<EOR>")

    def failed_promotion(record):
        raise OSError("journal unavailable")

    result = asyncio.run(outbox.replay(Wavelog(), on_resolved_record=failed_promotion))
    assert result["success"] is False
    assert result["remaining"] == 1
    assert "history acknowledgement failed" in result["failures"][0].lower()


def test_online_mshv_logged_adif_journal_survives_restart_and_closes_duckdb_gap(tmp_path, monkeypatch):
    import asyncio

    from services import digital_logging, mshv_history
    import services.mshv_award_hunting as award_hunting
    import services.qso_logging as qso_logging
    from services.wsjtx import WSJTXService

    def field(name, value):
        return f"<{name}:{len(value)}>{value}"

    adif = "".join((
        field("CALL", "K1ABC"), field("STATION_CALLSIGN", "OM0RX"),
        field("QSO_DATE", "20261007"), field("TIME_ON", "120000"),
        field("TIME_OFF", "120045"), field("BAND", "20m"),
        field("FREQ", "14.074"), field("MODE", "MFSK"),
        field("SUBMODE", "FT8"), field("POTA_REF", "K-1234"), "<EOR>",
    ))
    delta_path = tmp_path / "award-deltas.json"
    monkeypatch.setattr(award_hunting, "AWARD_DELTA_PATH", delta_path)
    monkeypatch.setattr(award_hunting, "republish_after_authoritative_history_change", lambda *args, **kwargs: {})
    monkeypatch.setattr(digital_logging, "PROVISIONAL_PATH", tmp_path / "provisional.json")
    monkeypatch.setattr(mshv_history, "DELTA_PATH", tmp_path / "history-deltas.json")
    monkeypatch.setattr(qso_logging, "_dedupe_ledger_path", tmp_path / "qso-dedupe.json")
    monkeypatch.setattr(qso_logging, "_pending_dedupe_claims", {})
    monkeypatch.setattr(qso_logging, "_recent_wavelog_duplicate_entry", lambda qso: None)
    monkeypatch.setattr(qso_logging, "write_qso_to_postgres_read_cache", lambda qso: False)

    class Wavelog:
        async def log_qso(self, qso):
            return {"success": True, "message": "accepted", "data": {"id": 123}}

    service = WSJTXService()
    service.set_dependencies(Wavelog(), None, None)
    request = {
        "provider": "mshv_auto_dx", "event_type": "LOGGED_ADIF",
        "event_id": "a" * 64, "station_callsign": "OM0RX",
        "client_id": "MSHV-OM0RX-AUTO-DX", "call": "K1ABC",
        "mode": "FT8", "frequency_hz": 14_074_000,
        "date_time": "2026-10-07T12:00:45+00:00", "async_upload": True,
        "adif_text": adif,
    }
    accepted = asyncio.run(digital_logging.log_digital_qso(request, service))
    assert accepted["wavelog"]["success"] is True
    assert accepted["history_delta"]["recorded"] is True
    durable = json.loads(delta_path.read_text(encoding="utf-8"))
    assert {(row["program"], row["reference"], row["band"], row["mode"]) for row in durable["records"].values()} == {
        ("POTA", "K-1234", "20m", "FT8"),
    }

    qso_path = tmp_path / "offline.duckdb"
    conn = duckdb.connect(str(qso_path))
    conn.execute(
        "CREATE TABLE qso_records (band VARCHAR, mode VARCHAR, submode VARCHAR, pota_ref VARCHAR, "
        "sota_ref VARCHAR, wwff_ref VARCHAR, sig VARCHAR, sig_info VARCHAR, comment VARCHAR)"
    )
    conn.close()

    class Repository:
        def portable_activations(self, limit):
            return [_activation("POTA", "K-1234")]

    first = publish_repository_award_hunting_watch(
        Repository(), tmp_path / "runtime", qso_db_path=qso_path,
        award_delta_path=delta_path, history_attestation=_attestation(), now=NOW,
    )["watch"]
    restarted = publish_repository_award_hunting_watch(
        Repository(), tmp_path / "runtime-after-restart", qso_db_path=qso_path,
        award_delta_path=delta_path, history_attestation=_attestation(),
        now=NOW + timedelta(seconds=5),
    )["watch"]
    assert first["history_authority"]["award_delta_pending"] == 1
    assert restarted["history_authority"]["award_delta_pending"] == 1
    assert not any(first["activations"][0]["gaps"].values())
    assert not any(restarted["activations"][0]["gaps"].values())


def test_online_mshv_award_journal_failure_invalidates_sidecar(tmp_path, monkeypatch):
    import asyncio

    import services.mshv_award_hunting as award_hunting
    import services.qso_logging as qso_logging
    from services.mshv_award_hunting import WATCH_RELATIVE_PATH
    from services.wsjtx import WSJTXService

    runtime = tmp_path / "runtime"
    target = runtime / WATCH_RELATIVE_PATH
    write_award_hunting_watch(target, [_activation("POTA", "K-1234")], now=NOW)
    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(runtime))
    monkeypatch.setattr(qso_logging, "_dedupe_ledger_path", tmp_path / "qso-dedupe.json")
    monkeypatch.setattr(qso_logging, "_pending_dedupe_claims", {})
    monkeypatch.setattr(qso_logging, "_recent_wavelog_duplicate_entry", lambda qso: None)
    monkeypatch.setattr(qso_logging, "write_qso_to_postgres_read_cache", lambda qso: False)
    monkeypatch.setattr(
        award_hunting, "record_acknowledged_award_qso",
        lambda qso: (_ for _ in ()).throw(OSError("disk unavailable")),
    )

    class Wavelog:
        async def log_qso(self, qso):
            return {"success": True, "message": "accepted"}

    service = WSJTXService()
    service.set_dependencies(Wavelog(), None, None)
    with pytest.raises(HTTPException, match="not durably journaled"):
        asyncio.run(service.log_qso({
            "provider": "mshv_auto_dx", "async_upload": True, "call": "K1ABC",
            "mode": "FT8", "frequency_hz": 14_074_000,
            "adif_text": (
                "<CALL:5>K1ABC<QSO_DATE:8>20261007<TIME_ON:6>120000"
                "<BAND:3>20m<FREQ:6>14.074<MODE:3>FT8<POTA_REF:6>K-1234<EOR>"
            ),
        }))
    invalidated = json.loads(target.read_text(encoding="utf-8"))
    assert invalidated["history_authoritative"] is False
    assert invalidated["history_authority"]["status"] == "invalidated"
    assert invalidated["history_authority"]["reasons"] == [
        "mshv-award-acknowledgement-persistence-failed",
    ]
    assert not any(invalidated["activations"][0]["gaps"].values())


def test_online_mshv_verified_duplicate_is_durably_journaled(tmp_path, monkeypatch):
    import asyncio

    import services.mshv_award_hunting as award_hunting
    import services.qso_logging as qso_logging
    from services.wsjtx import WSJTXService

    delta_path = tmp_path / "award-deltas.json"
    monkeypatch.setattr(award_hunting, "AWARD_DELTA_PATH", delta_path)
    monkeypatch.setattr(award_hunting, "republish_after_authoritative_history_change", lambda *args, **kwargs: {})
    monkeypatch.setattr(qso_logging, "_dedupe_ledger_path", tmp_path / "qso-dedupe.json")
    monkeypatch.setattr(qso_logging, "_pending_dedupe_claims", {})
    monkeypatch.setattr(qso_logging, "_recent_wavelog_duplicate_entry", lambda qso: None)
    monkeypatch.setattr(qso_logging, "write_qso_to_postgres_read_cache", lambda qso: False)

    class Wavelog:
        async def log_qso(self, qso):
            return {
                "success": False, "duplicate": True, "identity_verified": True,
                "message": "exact QSO already present",
            }

    service = WSJTXService()
    service.set_dependencies(Wavelog(), None, None)
    result = asyncio.run(service.log_qso({
        "provider": "mshv_auto_dx", "async_upload": True, "call": "K1ABC",
        "mode": "FT8", "frequency_hz": 14_074_000,
        "adif_text": (
            "<CALL:5>K1ABC<QSO_DATE:8>20261007<TIME_ON:6>120000"
            "<BAND:3>20m<FREQ:6>14.074<MODE:3>FT8<SOTA_REF:9>W1/AM-001<EOR>"
        ),
    }))
    assert result["success"] is True
    assert result["duplicate"] is True
    assert result["readback_verified"] is True
    assert result["readback_identity_exact"] is True
    records = list(json.loads(delta_path.read_text(encoding="utf-8"))["records"].values())
    assert [(row["program"], row["reference"]) for row in records] == [("SOTA", "W1/AM-001")]
