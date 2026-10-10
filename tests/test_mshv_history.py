import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from services import digital_logging
from services import mshv_history
from radio_control.wavelog_api import WavelogClient


ADIF = (
    "<STATION_CALLSIGN:5>OM0RX <CALL:5>OM1AA <BAND:3>20m <FREQ:6>14.074 "
    "<MODE:3>FT8 <QSO_DATE:8>20261004 <TIME_ON:6>120000 <TIME_OFF:6>120045 <EOR>\n"
)


def _request(adif=ADIF, *, event_id="a" * 64, client_id="MSHV-OM0RX-AUTO-DX"):
    return {
        "provider": "mshv_auto_dx", "station_callsign": "OM0RX",
        "client_id": client_id, "event_id": event_id, "adif_text": adif,
    }


def _outbox_adif(adif=ADIF, *, event_id="a" * 64, client_id="MSHV-OM0RX-AUTO-DX"):
    record = adif.replace("<EOR>", "")
    fields = {
        "APP_OM0RX_PROVIDER": "mshv_auto_dx", "APP_OM0RX_STATION": "OM0RX",
        "APP_OM0RX_CLIENT_ID": client_id, "APP_OM0RX_EVENT_ID": event_id,
        "APP_OM0RX_TIME_ON": "120000", "APP_OM0RX_TIME_OFF": "120045",
        "APP_OM0RX_FREQUENCY_HZ": "14074000",
    }
    return record + "".join(f"<{name}:{len(value)}>{value}" for name, value in fields.items()) + "<EOR>"


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _attested_runtime(tmp_path):
    runtime = tmp_path / "runtime"
    (runtime / "log").mkdir(parents=True)
    (runtime / "settings/database").mkdir(parents=True)
    source = tmp_path / "wavelog-canonical.adi"
    source.write_text(ADIF, encoding="utf-8")
    report_path = source.with_suffix(source.suffix + ".report.json")
    report_path.write_text(json.dumps({
        "schema": 1,
        "canonical_source": "wavelog_postgres",
        "station_callsign": "OM0RX",
        "configured_station_id": 1,
        "canonical_sha256": _sha(source),
        "total_records": 1,
        "digital_records": 1,
    }), encoding="utf-8")
    native = runtime / "log/mshvlog.edim"
    mirror = runtime / "log/mshvlog.adi"
    tracker = runtime / "settings/database/worked.db"
    native.write_bytes(b"native-history")
    mirror.write_bytes(source.read_bytes())
    with sqlite3.connect(tracker) as connection:
        connection.execute(
            "CREATE TABLE wavelog_applied_deltas (delta_key TEXT PRIMARY KEY, applied_utc TEXT NOT NULL)"
        )
        connection.execute("CREATE TABLE fixture_worked (id INTEGER PRIMARY KEY, value TEXT)")
    marker = {
        "schema": 1,
        "provider": "mshv_auto_dx",
        "applied": True,
        "canonical_source": mshv_history.CANONICAL_SOURCE,
        "production_policy": mshv_history.PRODUCTION_POLICY,
        "station_callsign": "OM0RX",
        "configured_station_id": 1,
        "records": 1,
        "native_records": 1,
        "tracker_coverage_verified": True,
        "canonical_sha256": _sha(source),
        "native_sha256": _sha(native),
        "adif_sha256": _sha(mirror),
        "tracker_sha256": _sha(tracker),
        "provenance_report_sha256": _sha(report_path),
        "source": str(source),
        "backup": "history-backups/test",
        "imported_utc": datetime.now(timezone.utc).isoformat(),
    }
    (runtime / "history-import.json").write_text(json.dumps(marker), encoding="utf-8")
    return runtime, source, report_path


def test_attested_snapshot_metadata_hash_count_age_and_station(tmp_path):
    runtime, _, _ = _attested_runtime(tmp_path)
    result = mshv_history.history_status(runtime=runtime, delta_path=tmp_path / "deltas.json")
    assert result["status"] == "healthy"
    assert result["historical_novelty_allowed"] is True
    assert result["authority"] == "wavelog"
    assert result["snapshot"]["station_callsign"] == "OM0RX"
    assert result["snapshot"]["station_id"] == 1
    assert result["snapshot"]["records"] == 1
    assert result["snapshot"]["age_seconds"] >= 0
    assert all(result["snapshot"]["store_checks"].values())
    assert result["max_age_seconds"] == 10
    assert datetime.fromisoformat(result["generated_at"]).tzinfo is not None


def test_history_status_single_flight_shares_one_validation(tmp_path, monkeypatch):
    runtime, _, _ = _attested_runtime(tmp_path)
    delta_path = tmp_path / "deltas.json"
    original = mshv_history._history_status_unlocked
    calls = 0
    calls_lock = threading.Lock()
    start = threading.Barrier(6)

    def slow_validation(**kwargs):
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.1)
        return original(**kwargs)

    monkeypatch.setattr(mshv_history, "_history_status_unlocked", slow_validation)
    mshv_history.invalidate_history_status_cache()

    def fetch():
        start.wait()
        return mshv_history.history_status(
            runtime=runtime, delta_path=delta_path, cache_ttl_seconds=30,
        )

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(lambda _index: fetch(), range(6)))

    assert calls == 1
    assert all(result["status"] == "healthy" for result in results)
    assert all(result["historical_novelty_allowed"] is True for result in results)


def test_history_status_refresh_failure_returns_unfreshened_last_validation(tmp_path, monkeypatch):
    runtime, _, _ = _attested_runtime(tmp_path)
    delta_path = tmp_path / "deltas.json"
    mshv_history.invalidate_history_status_cache()
    first = mshv_history.history_status(
        runtime=runtime, delta_path=delta_path, cache_ttl_seconds=0.01,
    )
    time.sleep(0.02)

    def failed_validation(**_kwargs):
        raise RuntimeError("fixture refresh failure")

    monkeypatch.setattr(mshv_history, "_history_status_unlocked", failed_validation)
    stale = mshv_history.history_status(
        runtime=runtime, delta_path=delta_path, cache_ttl_seconds=0.01,
    )

    assert stale["status"] == "healthy"
    assert stale["generated_at"] == first["generated_at"]
    assert stale["snapshot"]["age_seconds"] == first["snapshot"]["age_seconds"]


def test_single_flight_stale_fallback_is_identical_for_owner_and_waiters(tmp_path, monkeypatch):
    runtime, _, _ = _attested_runtime(tmp_path)
    delta_path = tmp_path / "deltas.json"
    mshv_history.invalidate_history_status_cache()
    first = mshv_history.history_status(
        runtime=runtime, delta_path=delta_path, cache_ttl_seconds=0.01,
    )
    time.sleep(0.02)

    refresh_entered = threading.Event()
    release_refresh = threading.Event()
    all_waiters_blocked = threading.Event()
    waiter_count = 3
    wait_count = 0
    wait_count_lock = threading.Lock()

    class CountingEvent:
        def __init__(self):
            self._event = threading.Event()

        def wait(self, timeout=None):
            nonlocal wait_count
            with wait_count_lock:
                wait_count += 1
                if wait_count == waiter_count:
                    all_waiters_blocked.set()
            return self._event.wait(timeout)

        def set(self):
            self._event.set()

    def failed_validation(**_kwargs):
        refresh_entered.set()
        assert release_refresh.wait(2)
        raise RuntimeError("fixture refresh failure")

    monkeypatch.setattr(mshv_history, "Event", CountingEvent)
    monkeypatch.setattr(mshv_history, "_history_status_unlocked", failed_validation)

    def fetch():
        return mshv_history.history_status(
            runtime=runtime, delta_path=delta_path, cache_ttl_seconds=0.01,
        )

    with ThreadPoolExecutor(max_workers=waiter_count + 1) as executor:
        owner = executor.submit(fetch)
        assert refresh_entered.wait(2)
        # Make the cached signature temporarily unusable so these callers wait
        # on the in-flight refresh instead of taking the immediate stale path.
        delta_path.write_text('{"schema":1,"next_sequence":1,"records":{},"pending":{}}')
        waiters = [executor.submit(fetch) for _ in range(waiter_count)]
        assert all_waiters_blocked.wait(2)
        delta_path.unlink()
        release_refresh.set()
        results = [owner.result(timeout=2)] + [future.result(timeout=2) for future in waiters]

    assert all(result == first for result in results)
    assert all(result["generated_at"] == first["generated_at"] for result in results)


def test_history_status_failure_without_cached_validation_is_not_hidden(tmp_path, monkeypatch):
    runtime, _, _ = _attested_runtime(tmp_path)
    mshv_history.invalidate_history_status_cache()
    monkeypatch.setattr(
        mshv_history, "_history_status_unlocked",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("fixture refresh failure")),
    )
    with pytest.raises(RuntimeError, match="fixture refresh failure"):
        mshv_history.history_status(
            runtime=runtime, delta_path=tmp_path / "deltas.json", cache_ttl_seconds=30,
        )


def test_changed_inputs_never_fall_back_to_prechange_cached_authority(tmp_path, monkeypatch):
    runtime, source, _ = _attested_runtime(tmp_path)
    delta_path = tmp_path / "deltas.json"
    mshv_history.invalidate_history_status_cache()
    first = mshv_history.history_status(
        runtime=runtime, delta_path=delta_path, cache_ttl_seconds=30,
    )
    assert first["historical_novelty_allowed"] is True
    source.write_text(ADIF + "changed", encoding="utf-8")
    monkeypatch.setattr(
        mshv_history, "_history_status_unlocked",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("fixture refresh failure")),
    )

    with pytest.raises(RuntimeError, match="fixture refresh failure"):
        mshv_history.history_status(
            runtime=runtime, delta_path=delta_path, cache_ttl_seconds=30,
        )


def test_mutation_during_validation_is_retried_before_result_is_cached(tmp_path, monkeypatch):
    runtime, _, _ = _attested_runtime(tmp_path)
    delta_path = tmp_path / "deltas.json"
    original = mshv_history._history_status_unlocked
    calls = 0

    def mutate_after_first_validation(**kwargs):
        nonlocal calls
        calls += 1
        result = original(**kwargs)
        if calls == 1:
            delta_path.write_text('{"schema":99,"records":{}}', encoding="utf-8")
        return result

    mshv_history.invalidate_history_status_cache()
    monkeypatch.setattr(
        mshv_history, "_history_status_unlocked", mutate_after_first_validation,
    )
    result = mshv_history.history_status(
        runtime=runtime, delta_path=delta_path, cache_ttl_seconds=30,
    )
    cached = mshv_history.history_status(
        runtime=runtime, delta_path=delta_path, cache_ttl_seconds=30,
    )

    assert calls == 2
    assert result["historical_novelty_allowed"] is False
    assert "acknowledged-delta-journal-invalid" in result["reasons"]
    assert cached["historical_novelty_allowed"] is False


def test_history_status_etag_excludes_only_volatile_freshness_fields(tmp_path):
    runtime, _, _ = _attested_runtime(tmp_path)
    payload = mshv_history.history_status(runtime=runtime, delta_path=tmp_path / "deltas.json")
    same_semantics = json.loads(json.dumps(payload))
    same_semantics["generated_at"] = "2099-01-01T00:00:00+00:00"
    same_semantics["snapshot"]["age_seconds"] += 100
    changed_semantics = json.loads(json.dumps(payload))
    changed_semantics["historical_novelty_allowed"] = False

    assert mshv_history.history_status_etag(same_semantics) == mshv_history.history_status_etag(payload)
    assert mshv_history.history_status_etag(changed_semantics) != mshv_history.history_status_etag(payload)


def test_mshv_history_endpoint_honors_semantic_etag(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from services import digital_engine

    payload = {
        "status": "healthy", "historical_novelty_allowed": True,
        "snapshot": {"age_seconds": 12.5},
        "generated_at": "2026-10-06T12:00:00+00:00", "max_age_seconds": 10,
    }
    monkeypatch.setattr(mshv_history, "history_status", lambda: deepcopy(payload))
    app = FastAPI()
    digital_engine.register_digital_endpoints(app)

    with TestClient(app) as client:
        first = client.get("/api/digital/mshv-history")
        unchanged = client.get(
            "/api/digital/mshv-history", headers={"If-None-Match": first.headers["etag"]},
        )

    assert first.status_code == 200
    assert unchanged.status_code == 304
    assert unchanged.content == b""
    assert unchanged.headers["etag"] == first.headers["etag"]
    assert unchanged.headers["x-om0rx-history-generated-at"] == payload["generated_at"]
    assert unchanged.headers["x-om0rx-history-max-age"] == "10"


def test_temporary_source_outage_uses_embedded_attestation_and_acknowledged_deltas(tmp_path):
    runtime, source, report = _attested_runtime(tmp_path)
    delta_path = tmp_path / "deltas.json"
    acknowledged = mshv_history.record_acknowledged_delta(
        _request(),
        {"success": True, "wavelog": {"success": True}},
        path=delta_path,
    )
    assert acknowledged["recorded"]
    source.unlink()
    report.unlink()
    result = mshv_history.history_status(runtime=runtime, delta_path=delta_path)
    assert result["status"] == "offline-attested"
    assert result["historical_novelty_allowed"] is True
    assert result["deltas"]["count"] == 1
    assert result["outage_policy"] == "last-attested-snapshot-plus-acknowledged-deltas"


@pytest.mark.parametrize("mutation", ["source", "tracker", "provenance", "marker"])
def test_absent_or_invalid_snapshot_blocks_historical_novelty(tmp_path, mutation):
    runtime, source, report = _attested_runtime(tmp_path)
    if mutation == "source":
        source.write_text(ADIF + "changed", encoding="utf-8")
    elif mutation == "tracker":
        (runtime / "settings/database/worked.db").write_bytes(b"changed")
    elif mutation == "provenance":
        report.write_text("{}", encoding="utf-8")
    else:
        (runtime / "history-import.json").unlink()
    result = mshv_history.history_status(runtime=runtime, delta_path=tmp_path / "deltas.json")
    assert result["status"] == "blocked-diverged"
    assert result["historical_novelty_allowed"] is False


def test_outbox_is_pending_until_wavelog_replay_then_exactly_once(tmp_path):
    delta_path = tmp_path / "deltas.json"
    request = _request()
    pending = mshv_history.record_pending_delta(
        request, {"success": True, "outbox_queued": True}, path=delta_path,
    )
    assert pending["pending"]
    payload = json.loads(delta_path.read_text())
    assert payload["records"] == {}
    assert len(payload["pending"]) == 1
    assert mshv_history.record_acknowledged_delta(
        request, {"success": True, "outbox_queued": True}, path=delta_path,
    )["recorded"] is False

    first = mshv_history.acknowledge_outbox_delta(_outbox_adif(), path=delta_path)
    second = mshv_history.acknowledge_outbox_delta(_outbox_adif(), path=delta_path)
    assert first["recorded"] is True
    assert second["recorded"] is True
    assert second["duplicate_receipt"] is True
    payload = json.loads(delta_path.read_text())
    assert payload["pending"] == {}
    assert len(payload["records"]) == 1
    assert next(iter(payload["records"].values()))["outcome"] == "outbox-replay"


def test_duplicate_of_outbox_only_dedupe_does_not_promote_history(tmp_path):
    delta_path = tmp_path / "deltas.json"
    request = _request()
    mshv_history.record_pending_delta(
        request, {"success": True, "outbox_queued": True}, path=delta_path,
    )
    result = mshv_history.record_acknowledged_delta(request, {
        "success": True,
        "duplicate": True,
        "outbox_queued": True,
        "wavelog": {"success": False},
        "dedupe": {"wavelog_success": False, "outbox_queued": True},
    }, path=delta_path)
    assert result["recorded"] is False
    journal = json.loads(delta_path.read_text())
    assert journal["records"] == {}
    assert len(journal["pending"]) == 1


def test_acknowledged_delta_sequence_is_contiguous_unique_and_hash_chained(tmp_path):
    runtime, _, _ = _attested_runtime(tmp_path)
    delta_path = tmp_path / "deltas.json"
    result1 = mshv_history.record_acknowledged_delta(
        _request(),
        {"success": True, "wavelog": {"success": True}}, path=delta_path,
    )
    second_adif = ADIF.replace("OM1AA", "OM2BB").replace("120000", "120015")
    result2 = mshv_history.record_acknowledged_delta(
        _request(second_adif, event_id="b" * 64),
        {"success": True, "wavelog": {"success": True}}, path=delta_path,
    )
    duplicate = mshv_history.record_acknowledged_delta(
        _request(),
        {"success": True, "wavelog": {"success": True}}, path=delta_path,
    )
    journal = json.loads(delta_path.read_text())
    first = journal["records"][result1["delta_key"]]
    second = journal["records"][result2["delta_key"]]
    assert (first["sequence"], second["sequence"], journal["next_sequence"]) == (1, 2, 3)
    assert second["previous_hash"] == first["entry_hash"]
    assert duplicate["duplicate_receipt"] is True
    assert len(journal["records"]) == 2

    second["call"] = "TAMPER"
    delta_path.write_text(json.dumps(journal), encoding="utf-8")
    status = mshv_history.history_status(runtime=runtime, delta_path=delta_path)
    assert status["historical_novelty_allowed"] is False
    assert "unacknowledged-live-delta" in status["reasons"]


def test_common_wavelog_success_publishes_provider_neutral_delta_once(tmp_path):
    delta_path = tmp_path / "deltas.json"
    adif = (
        "<CALL:5>9T0MD <GRIDSQUARE:6>JI75SS <MODE:3>FT8 "
        "<QSO_DATE:8>20261005 <TIME_ON:6>005345 <TIME_OFF:6>005445 "
        "<BAND:3>40m <FREQ:7>7.06048 <STATION_CALLSIGN:5>OM0RX <EOR>"
    )
    qso = {
        "callsign": "9T0MD", "gridsquare": "JI75SS", "mode": "FT8",
        "band": "40m", "frequency": 7.06048, "provider": "wsjtz",
        "station_callsign": "OM0RX", "client_id": "WSJT-X - OM0RX-WSJT-Z",
    }
    accepted = {"success": True, "data": {"status": "created", "id": 178170}}

    first = mshv_history.record_successful_wavelog_upload(
        qso, accepted, adif_text=adif, path=delta_path,
    )
    second = mshv_history.record_successful_wavelog_upload(
        qso, accepted, adif_text=adif, path=delta_path,
    )

    journal = json.loads(delta_path.read_text())
    row = next(iter(journal["records"].values()))
    assert first["recorded"] is True
    assert second["duplicate_receipt"] is True
    assert len(journal["records"]) == 1
    assert row["provider"] == "wsjtz"
    assert row["wavelog_id"] == 178170
    assert (row["call"], row["grid"], row["band"], row["mode"]) == (
        "9T0MD", "JI75SS", "40m", "FT8",
    )


def test_bridge_iso_times_preserve_wavelog_interval_and_promote_pending_delta(tmp_path):
    delta_path = tmp_path / "deltas.json"
    source_adif = (
        "<STATION_CALLSIGN:5>OM0RX <CALL:5>OM3SX <GRIDSQUARE:4>KN08 "
        "<BAND:4>160m <FREQ:4>1.84 <MODE:3>FT8 <QSO_DATE:8>20261005 "
        "<TIME_ON:6>162400 <QSO_DATE_OFF:8>20261005 <TIME_OFF:6>162600 <EOR>"
    )
    request = _request(source_adif, event_id="d" * 64)
    pending = mshv_history.stage_pending_delta(request, path=delta_path)

    qso_data = {
        "callsign": "OM3SX",
        "gridsquare": "KN08",
        "frequency": 1.84,
        "frequency_hz": 1_840_000,
        "band": "160m",
        "mode": "FT8",
        "date": "20261005",
        "date_time": "2026-10-05T16:24:00.000Z",
        "time_on": "2026-10-05T16:24:00.000Z",
        "time_off": "2026-10-05T16:26:00.000Z",
        "provider": "mshv_auto_dx",
        "station_callsign": "OM0RX",
        "client_id": "MSHV-OM0RX-AUTO-DX",
        "event_id": "d" * 64,
    }
    upload_adif = WavelogClient().build_adif_string(qso_data).upper()
    assert "<QSO_DATE:8>20261005" in upload_adif
    assert "<TIME_ON:6>162400" in upload_adif
    assert "<QSO_DATE_OFF:8>20261005" in upload_adif
    assert "<TIME_OFF:6>162600" in upload_adif

    acknowledged = mshv_history.record_successful_wavelog_upload(
        qso_data,
        {"success": True, "data": {"status": "created", "id": 178199}},
        adif_text=upload_adif,
        path=delta_path,
    )
    journal = json.loads(delta_path.read_text(encoding="utf-8"))
    row = journal["records"][acknowledged["delta_key"]]

    assert acknowledged["delta_key"] == pending["delta_key"]
    assert journal["pending"] == {}
    assert (row["time_on"], row["time_off"]) == ("162400", "162600")


def test_type5_remains_pending_during_outage_and_clears_only_on_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(digital_logging, "PROVISIONAL_PATH", tmp_path / "provisional.json")
    monkeypatch.setattr(mshv_history, "DELTA_PATH", tmp_path / "deltas.json")

    async def queued(_request):
        return {"success": True, "outbox_queued": True, "wavelog": {"success": False}}

    provisional = {
        "provider": "mshv_auto_dx", "event_type": "QSO_LOGGED", "call": "OM1AA",
        "event_id": "a" * 64, "station_callsign": "OM0RX", "client_id": "MSHV-OM0RX-AUTO-DX",
        "mode": "FT8", "frequency_hz": 14_074_000,
        "date_time": "2026-10-04T12:00:45+00:00", "time_off": "2026-10-04T12:00:45+00:00",
    }
    asyncio.run(digital_logging.log_digital_qso(provisional, SimpleNamespace(log_qso=queued)))
    result = asyncio.run(digital_logging.log_digital_qso({
        **provisional, "event_type": "LOGGED_ADIF", "adif_text": ADIF,
    }, SimpleNamespace(log_qso=queued)))
    assert result["provisional_upgrade"] == "pending-outbox"
    assert result["history_delta"]["pending"] is True
    assert len(digital_logging.provisional_records()) == 1

    replay = digital_logging.acknowledge_outbox_resolution(_outbox_adif())
    assert replay["history_delta"]["recorded"] is True
    assert replay["provisional_upgrade"] == "matched"
    assert digital_logging.provisional_records() == {}


def test_type5_pairs_to_adif_time_off_while_delta_identity_keeps_time_on(tmp_path, monkeypatch):
    monkeypatch.setattr(digital_logging, "PROVISIONAL_PATH", tmp_path / "provisional.json")
    monkeypatch.setattr(mshv_history, "DELTA_PATH", tmp_path / "deltas.json")

    async def accepted(_request):
        return {"success": True, "wavelog": {"success": True}}

    receipt = {
        "provider": "mshv_auto_dx", "event_type": "QSO_LOGGED",
        "event_id": "a" * 64, "station_callsign": "OM0RX", "call": "OM1AA",
        "client_id": "MSHV-OM0RX-AUTO-DX",
        "mode": "FT8", "frequency_hz": 14_074_000,
        "date_time": "2026-10-04T12:10:00+00:00",
        "time_off": "2026-10-04T12:10:00+00:00",
    }
    asyncio.run(digital_logging.log_digital_qso(receipt, SimpleNamespace(log_qso=accepted)))
    authoritative = ADIF.replace(
        "<TIME_ON:6>120000 <TIME_OFF:6>120045",
        "<TIME_ON:6>120000 <TIME_OFF:6>121000",
    )
    result = asyncio.run(digital_logging.log_digital_qso({
        **receipt, "event_type": "LOGGED_ADIF", "adif_text": authoritative,
    }, SimpleNamespace(log_qso=accepted)))
    assert result["provisional_upgrade"] == "matched"
    journal = json.loads((tmp_path / "deltas.json").read_text())
    delta = next(iter(journal["records"].values()))
    assert delta["time_on"] == "120000"
    assert delta["key"] != receipt["event_id"]


def test_pending_journal_is_durable_before_logger_can_enqueue(tmp_path, monkeypatch):
    delta_path = tmp_path / "deltas.json"
    monkeypatch.setattr(mshv_history, "DELTA_PATH", delta_path)
    monkeypatch.setattr(digital_logging, "PROVISIONAL_PATH", tmp_path / "provisional.json")
    observed = []

    async def logger(_request):
        journal = json.loads(delta_path.read_text())
        observed.append(len(journal["pending"]))
        return {"success": True, "outbox_queued": True, "wavelog": {"success": False}}

    request = {
        **_request(), "event_type": "LOGGED_ADIF", "call": "OM1AA",
        "mode": "FT8", "frequency_hz": 14_074_000,
    }
    result = asyncio.run(digital_logging.log_digital_qso(
        request, SimpleNamespace(log_qso=logger),
    ))
    assert observed == [1]
    assert result["history_pending_staged"]["pending"] is True


def test_outbox_ack_reconstructs_missing_pending_from_rich_identity(tmp_path):
    delta_path = tmp_path / "deltas.json"
    result = mshv_history.acknowledge_outbox_delta(_outbox_adif(), path=delta_path)
    assert result["recorded"] is True
    assert result["pending_reconstructed"] is True
    journal = json.loads(delta_path.read_text())
    assert journal["pending"] == {}
    row = next(iter(journal["records"].values()))
    assert row["client_id"] == "MSHV-OM0RX-AUTO-DX"
    assert row["event_id"] == "a" * 64


def test_outbox_ack_with_missing_correlation_is_retained_blocked(tmp_path):
    result = mshv_history.acknowledge_outbox_delta(ADIF, path=tmp_path / "deltas.json")
    assert result["recorded"] is False
    assert result["reason"] == "outbox-reconstruction-identity-incomplete"


def test_type5_type12_pairing_is_bound_to_client_and_event(tmp_path, monkeypatch):
    monkeypatch.setattr(digital_logging, "PROVISIONAL_PATH", tmp_path / "provisional.json")
    monkeypatch.setattr(mshv_history, "DELTA_PATH", tmp_path / "deltas.json")

    async def accepted(_request):
        return {"success": True, "wavelog": {"success": True}}

    common = {
        "provider": "mshv_auto_dx", "event_type": "QSO_LOGGED",
        "station_callsign": "OM0RX", "call": "OM1AA", "mode": "FT8",
        "frequency_hz": 14_074_000, "date_time": "2026-10-04T12:00:45+00:00",
        "time_off": "2026-10-04T12:00:45+00:00",
    }
    first = {**common, "client_id": "MSHV-OM0RX-AUTO-DX", "event_id": "a" * 64}
    other = {**common, "client_id": "OTHER-CLIENT", "event_id": "b" * 64}
    asyncio.run(digital_logging.log_digital_qso(first, SimpleNamespace(log_qso=accepted)))
    asyncio.run(digital_logging.log_digital_qso(other, SimpleNamespace(log_qso=accepted)))
    result = asyncio.run(digital_logging.log_digital_qso({
        **first, "event_type": "LOGGED_ADIF", "adif_text": ADIF,
    }, SimpleNamespace(log_qso=accepted)))
    assert result["provisional_upgrade"] == "matched"
    remaining = digital_logging.provisional_records()
    assert set(remaining) == {"b" * 64}
    assert remaining["b" * 64]["client_id"] == "OTHER-CLIENT"


def test_invalid_delta_journal_blocks_otherwise_attested_snapshot(tmp_path):
    runtime, _, _ = _attested_runtime(tmp_path)
    delta_path = tmp_path / "deltas.json"
    delta_path.write_text('{"schema":99,"records":{}}', encoding="utf-8")
    result = mshv_history.history_status(runtime=runtime, delta_path=delta_path)
    assert result["status"] == "blocked-diverged"
    assert result["historical_novelty_allowed"] is False
    assert "acknowledged-delta-journal-invalid" in result["reasons"]


def test_malformed_orphan_outbox_identity_is_not_promoted(tmp_path):
    malformed = _outbox_adif(event_id="legacy-event")
    result = mshv_history.acknowledge_outbox_delta(
        malformed, path=tmp_path / "deltas.json",
    )
    assert result["recorded"] is False
    assert result["reason"] == "outbox-reconstruction-identity-incomplete"
    assert not (tmp_path / "deltas.json").exists()


def test_invalid_acknowledged_identity_blocks_history_status(tmp_path):
    runtime, _, _ = _attested_runtime(tmp_path)
    delta_path = tmp_path / "deltas.json"
    acknowledged = mshv_history.record_acknowledged_delta(
        _request(), {"success": True, "wavelog": {"success": True}}, path=delta_path,
    )
    journal = json.loads(delta_path.read_text(encoding="utf-8"))
    row = journal["records"][acknowledged["delta_key"]]
    row["event_id"] = "legacy-event"
    content = {key: value for key, value in row.items() if key != "entry_hash"}
    row["entry_hash"] = hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    delta_path.write_text(json.dumps(journal), encoding="utf-8")
    result = mshv_history.history_status(runtime=runtime, delta_path=delta_path)
    assert result["historical_novelty_allowed"] is False
    assert "unacknowledged-live-delta" in result["reasons"]
    assert acknowledged["delta_key"] in result["deltas"]["invalid"]


def test_tracker_hash_evolves_only_with_persisted_monotonic_acknowledged_state(tmp_path):
    runtime, _, _ = _attested_runtime(tmp_path)
    delta_path = tmp_path / "deltas.json"
    acknowledged = mshv_history.record_acknowledged_delta(
        _request(),
        {"success": True, "wavelog": {"success": True}},
        path=delta_path,
    )
    journal = json.loads(delta_path.read_text())
    row = journal["records"][acknowledged["delta_key"]]
    tracker = runtime / "settings/database/worked.db"
    with sqlite3.connect(tracker) as connection:
        connection.execute("INSERT INTO fixture_worked(value) VALUES ('acknowledged-delta')")
        connection.execute(
            "INSERT INTO wavelog_applied_deltas(delta_key, applied_utc) VALUES (?, ?)",
            (acknowledged["delta_key"], datetime.now(timezone.utc).isoformat()),
        )
    state = {
        "schema": 1,
        "snapshot_generation": json.loads((runtime / "history-import.json").read_text())["canonical_sha256"],
        "last_sequence": row["sequence"],
        "applied_keys": [acknowledged["delta_key"]],
        "tracker_sha256": _sha(tracker),
    }
    state_path = runtime / "settings/database/wavelog_delta_state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    accepted = mshv_history.history_status(runtime=runtime, delta_path=delta_path)
    assert accepted["historical_novelty_allowed"] is True
    assert accepted["snapshot"]["delta_state"]["valid"] is True

    state["last_sequence"] += 1
    state_path.write_text(json.dumps(state), encoding="utf-8")
    rejected = mshv_history.history_status(runtime=runtime, delta_path=delta_path)
    assert rejected["historical_novelty_allowed"] is False
    assert "derived-tracker-diverged" in rejected["reasons"]


def test_sqlite_commit_before_json_cursor_status_is_strictly_read_only(tmp_path):
    runtime, _, _ = _attested_runtime(tmp_path)
    delta_path = tmp_path / "deltas.json"
    acknowledged = mshv_history.record_acknowledged_delta(
        _request(),
        {"success": True, "wavelog": {"success": True}}, path=delta_path,
    )
    tracker = runtime / "settings/database/worked.db"
    with sqlite3.connect(tracker) as connection:
        connection.execute("INSERT INTO fixture_worked(value) VALUES ('native-commit')")
        connection.execute(
            "INSERT INTO wavelog_applied_deltas(delta_key, applied_utc) VALUES (?, ?)",
            (acknowledged["delta_key"], datetime.now(timezone.utc).isoformat()),
        )

    state_path = runtime / "settings/database/wavelog_delta_state.json"
    assert not state_path.exists()
    result = mshv_history.history_status(runtime=runtime, delta_path=delta_path)
    assert not state_path.exists()
    assert result["historical_novelty_allowed"] is False
    assert result["snapshot"]["delta_state"]["recovery_available"] is True
    assert "delta-state-recovery-available-via-stopped-engine-post" in result["warnings"]


def test_strict_journal_error_returns_blocked_telemetry_not_500(tmp_path):
    runtime, _, _ = _attested_runtime(tmp_path)
    delta_path = tmp_path / "deltas.json"
    delta_path.write_text("not json", encoding="utf-8")
    result = mshv_history.history_status(runtime=runtime, delta_path=delta_path)
    assert result["status"] == "blocked-diverged"
    assert result["historical_novelty_allowed"] is False
    assert result["deltas"]["journal_error"]


def test_pending_identity_is_exposed_only_as_negative_inhibition(tmp_path):
    runtime, _, _ = _attested_runtime(tmp_path)
    delta_path = tmp_path / "deltas.json"
    mshv_history.record_pending_delta(
        _request(),
        {"success": True, "outbox_queued": True}, path=delta_path,
    )
    result = mshv_history.history_status(runtime=runtime, delta_path=delta_path)
    assert result["historical_novelty_allowed"] is True
    assert result["deltas"]["count"] == 0
    assert result["deltas"]["pending_records"] == [{
        "key": result["deltas"]["pending_keys"][0],
        "call": "OM1AA", "band": "20m", "frequency_hz": 14_074_000,
        "mode": "FT8", "grid": "",
        "qso_date": "20261004", "time_on": "120000", "time_off": "120045",
        "provider": "mshv_auto_dx", "client_id": "MSHV-OM0RX-AUTO-DX",
        "event_id": "a" * 64,
    }]
    assert result["derived_logs_policy"]["authoritative"] is False


def test_native_history_is_fail_closed_and_applies_only_acknowledged_deltas():
    source_root = Path(os.environ.get(
        "OM0RX_MSHV_TEST_SOURCE_ROOT",
        mshv_history.ROOT / "data/build/mshv-auto-dx/src",
    )).resolve()
    source = source_root / "MSHV_2762/src"
    assert source.is_dir(), f"Attested native source fixture is missing: {source}"
    core = (source / "HvAutoDxer/autodxercore.cpp").read_text(encoding="utf-8")
    scorer_h = (source / "HvAutoDxer/targetscorer.h").read_text(encoding="utf-8")
    scorer_cpp = (source / "HvAutoDxer/targetscorer.cpp").read_text(encoding="utf-8")
    main = (source / "main_ms.cpp").read_text(encoding="utf-8")
    assert 'm_historicalNoveltyAllowed(false)' in core
    assert '"/api/digital/mshv-history"' in core
    assert 'value("historical_novelty_allowed").toBool(false)' in core
    assert 'value("acknowledged_records")' in core
    assert 'value("generated_at")' in core
    assert 'status = "stale-history-response"' in core
    assert "noteTransientHistoryFailure" in core
    assert "HISTORY_TRANSIENT_FAILURE_LIMIT" in core
    assert "pendingCrossBandHistoryAllowed" in core
    assert "CROSSBAND-RETRY-DEFERRED" in core
    assert "m_historyTransientGraceTimer->setSingleShot(true)" in core
    assert "expireTransientHistoryGrace" in core
    assert "historyReplyIsStale(requestGeneration)" in core
    assert "m_historyIgnoreRepliesThroughGeneration" in core
    assert "m_historyTransientTerminalized" in core
    assert "applyWavelogAcknowledgedQso" in core
    assert "setHistoricalNoveltyAllowed" in scorer_h
    assert scorer_cpp.count("m_historicalNoveltyAllowed &&") >= 3
    assert "CROSSBAND-BLOCKED: Wavelog history authority unavailable" in core
    assert "NONSTD-BLOCKED: Wavelog history authority unavailable" in core
    logged = core.split("void AutoDxerCore::onMSHVQsoLogged", 1)[1].split(
        "void AutoDxerCore::onDialFrequencyChanged", 1
    )[0]
    assert "recordQSO(" not in logged
    assert "m_hvDxccTracker->onQsoLogged" not in main
    assert "QTimer::singleShot(4000" in core
    assert "QUEUE-BLOCKED: %1 historical authority unavailable" in core
    assert "Historical authority revoked; deferred target cancelled" in core
    assert "historicalActionAllowed" in core
    assert "cancelPendingWavelogPaths();" in core
    assert "QUEUE-BLOCKED: %1 historical authority unavailable" in core
    assert "SLOT-ANALYSIS: Pending Wavelog QSO; deferred target cancelled" in core
    assert "WAVELOG-PENDING: cancelled cross-band target" in core
    assert "WAVELOG-PENDING: cancelled non-standard target" in core
    assert core.count("historicalActionAllowed(spot.callsign, false)") >= 2
    band_complete = core.split("void AutoDxerCore::onBandChangeComplete", 1)[1].split(
        "void AutoDxerCore::onQSOComplete", 1
    )[0]
    guard = band_complete.index("pendingCrossBandHistoryAllowed(m_pendingCrossBandCallsign)")
    assert guard < band_complete.index("emit requestDialFreqChange")
    assert guard < band_complete.index("emit requestTxFreqChange")
    # Canonical cleanup owns every pending-verification field. The completion
    # path must return/dequeue through it before any dial or TX-frequency edge;
    # a callsign-only clear would leave stale source/reason telemetry behind.
    before_dial = band_complete[:band_complete.index("emit requestDialFreqChange")]
    assert "returnFromPendingCrossBandVerification" in before_dial
    cleanup = core.split("void AutoDxerCore::clearPendingCrossBandVerification()", 1)[1].split(
        "bool AutoDxerCore::returnFromPendingCrossBandVerification", 1
    )[0]
    assert "m_pendingCrossBandCallsign.clear();" in cleanup


@pytest.mark.parametrize("date,time_on,time_off", [
    ("", "120000", "120045"),
    ("20261340", "120000", "120045"),
    ("20261004", "", "120045"),
    ("20261004", "1200", "120045"),
    ("20261004", "246000", "120045"),
    ("20261004", "120000", ""),
    ("20261004", "120000", "1200"),
    ("20261004", "120000", "126060"),
])
def test_mshv_type12_rejects_missing_or_invalid_canonical_times(
    tmp_path, monkeypatch, date, time_on, time_off,
):
    monkeypatch.setattr(mshv_history, "DELTA_PATH", tmp_path / "deltas.json")
    adif = (
        f"<STATION_CALLSIGN:5>OM0RX <CALL:5>OM1AA <BAND:3>20m <FREQ:6>14.074 "
        f"<MODE:3>FT8 <QSO_DATE:{len(date)}>{date} <TIME_ON:{len(time_on)}>{time_on} "
        f"<TIME_OFF:{len(time_off)}>{time_off} <EOR>"
    )
    with pytest.raises(ValueError, match="identity is incomplete"):
        mshv_history.stage_pending_delta(_request(adif))
    assert not (tmp_path / "deltas.json").exists()


def test_provisional_recovery_reuses_durable_identity_and_requires_unique_adif(
    tmp_path, monkeypatch,
):
    runtime = tmp_path / "runtime"
    (runtime / "log").mkdir(parents=True)
    provisional_path = tmp_path / "provisional.json"
    delta_path = tmp_path / "deltas.json"
    monkeypatch.setenv("OM0RX_MSHV_RUNTIME", str(runtime))
    monkeypatch.setattr(digital_logging, "PROVISIONAL_PATH", provisional_path)
    monkeypatch.setattr(mshv_history, "DELTA_PATH", delta_path)
    import services.digital_engine as digital_engine
    monkeypatch.setattr(digital_engine, "selected_provider", lambda: "mshv_auto_dx")

    receipt = {
        "provider": "mshv_auto_dx", "station_callsign": "OM0RX",
        "client_id": "MSHV-OM0RX-AUTO-DX", "event_id": "e" * 64,
        "call": "OM1AA", "mode": "FT8", "frequency_hz": 14_074_000,
        "date_time": "2026-10-04T12:00:45+00:00", "event_type": "QSO_LOGGED",
    }

    async def accepted(request):
        return {"success": True, "wavelog": {"success": True}, "request": request}

    logger = SimpleNamespace(log_qso=accepted)
    asyncio.run(digital_logging.log_digital_qso(receipt, logger))
    (runtime / "log/mshvlog.adi").write_text(ADIF, encoding="utf-8")
    unique = asyncio.run(digital_logging.reconcile_provisional(logger))
    assert unique["recovered"] == 1
    journal = json.loads(delta_path.read_text(encoding="utf-8"))
    acknowledged = next(iter(journal["records"].values()))
    assert acknowledged["event_id"] == "e" * 64
    assert acknowledged["client_id"] == "MSHV-OM0RX-AUTO-DX"

    # Recreate the receipt as if after restart. Two equally matching native
    # rows are ambiguous and cannot retire it.
    delta_path.unlink()
    asyncio.run(digital_logging.log_digital_qso(receipt, logger))
    (runtime / "log/mshvlog.adi").write_text(ADIF + ADIF, encoding="utf-8")
    ambiguous = asyncio.run(digital_logging.reconcile_provisional(logger))
    assert ambiguous["recovered"] == 0
    assert ambiguous["ambiguous"] == 1
    assert digital_logging.provisional_health()["pending_authoritative_adif"] == 1


def test_invalid_type12_is_rejected_before_wavelog_and_preserves_provisional_audit(
    tmp_path, monkeypatch,
):
    from fastapi import HTTPException

    monkeypatch.setattr(digital_logging, "PROVISIONAL_PATH", tmp_path / "provisional.json")
    monkeypatch.setattr(mshv_history, "DELTA_PATH", tmp_path / "deltas.json")
    request = {
        "provider": "mshv_auto_dx", "station_callsign": "OM0RX",
        "client_id": "MSHV-OM0RX-AUTO-DX", "event_id": "f" * 64,
        "call": "OM1AA", "mode": "FT8", "frequency_hz": 14_074_000,
        "date_time": "2026-10-04T12:00:45+00:00",
    }
    calls = 0

    async def should_not_log(_request):
        nonlocal calls
        calls += 1
        return {"success": True, "wavelog": {"success": True}}

    logger = SimpleNamespace(log_qso=should_not_log)
    asyncio.run(digital_logging.log_digital_qso(
        {**request, "event_type": "QSO_LOGGED"}, logger,
    ))
    invalid = (
        "<STATION_CALLSIGN:5>OM0RX <CALL:5>OM1AA <BAND:3>20m "
        "<FREQ:6>14.074 <MODE:3>FT8 <QSO_DATE:8>20261004 "
        "<TIME_ON:6>120000 <EOR>"
    )
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(digital_logging.log_digital_qso(
            {**request, "event_type": "LOGGED_ADIF", "adif_text": invalid}, logger,
        ))
    assert rejected.value.status_code == 400
    assert calls == 0
    records = digital_logging.provisional_records()
    assert list(records) == ["f" * 64]
    assert records["f" * 64]["lifecycle_state"] in {"type5_received", "type12_paired"}
    assert not (tmp_path / "deltas.json").exists()
