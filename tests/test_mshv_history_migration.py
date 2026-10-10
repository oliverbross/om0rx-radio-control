import importlib.util
import json
from pathlib import Path
import hashlib
from types import SimpleNamespace
from unittest.mock import patch

import pytest

MODULE = Path(__file__).resolve().parents[1] / "scripts/mshv/import_history.py"
spec = importlib.util.spec_from_file_location("mshv_history", MODULE)
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)


def setup_history(tmp_path):
    runtime = tmp_path / "runtime"
    (runtime / "log").mkdir(parents=True)
    (runtime / "settings/database").mkdir(parents=True)
    source = tmp_path / "canonical.adi"
    source.write_text("<CALL:5>OM1AA<BAND:3>20m<MODE:4>MFSK<SUBMODE:3>FT4<QSO_DATE:8>20261001<TIME_ON:6>120000<EOR>\n")
    source.with_suffix(".adi.report.json").write_text(json.dumps({
        "canonical_source": "wavelog_postgres", "station_callsign": "OM0RX",
        "migration_eligible": True, "canonical_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "qualification_review_required": False,
        "production_policy": "Wavelog sole authority; WSJT inputs diagnostic only; FT8/FT4 only",
        "total_records": 1, "digital_records": 1,
    }))
    return SimpleNamespace(runtime=runtime, adif=source, apply=False)


def test_dry_run_has_no_runtime_mutation(tmp_path):
    args = setup_history(tmp_path)
    with patch.object(history, "mshv_running", return_value=False):
        report = history.migrate(args)
    assert report["records"] == 1
    assert report["dry_run"]
    assert not list(args.runtime.rglob("*.db"))
    assert not (args.runtime / ".history-import.lock").exists()


@pytest.mark.parametrize(("callsign", "expected"), [
    ("OM1AA/P", "OM1AA"),
    ("FS/W1NA", "W1NA"),
    ("6W/DB1RUL", "DB1RUL"),
    ("EA8/OM0RX/P", "OM0RX"),
    ("KH6ABC", "KH6ABC"),
])
def test_tracker_base_call_matches_native_portable_normalization(callsign, expected):
    assert history.tracker_base_call(callsign) == expected


def test_source_provenance_and_hash_required(tmp_path):
    args = setup_history(tmp_path)
    args.adif.write_text(args.adif.read_text() + "changed")
    with pytest.raises(ValueError, match="Wavelog-canonical"):
        history.migrate(args)


def test_ineligible_or_audit_only_provenance_is_rejected(tmp_path):
    args = setup_history(tmp_path)
    report_path = args.adif.with_suffix(".adi.report.json")
    report = json.loads(report_path.read_text())
    report["migration_eligible"] = False
    report_path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="Wavelog-canonical"):
        history.migrate(args)
    report["migration_eligible"] = True
    report["canonical_source"] = "wsjt_forensic_candidates"
    report_path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="Wavelog-canonical"):
        history.migrate(args)


def test_active_process_and_sidecars_refused(tmp_path):
    args = setup_history(tmp_path)
    with patch.object(history, "mshv_running", return_value=True), pytest.raises(RuntimeError, match="Stop MSHV"):
        history.migrate(args)
    (args.runtime / "settings/database/worked.db-wal").touch()
    with patch.object(history, "mshv_running", return_value=False), pytest.raises(RuntimeError, match="sidecars"):
        history.migrate(args)


def test_unsynced_native_records_refused(tmp_path):
    args = setup_history(tmp_path)
    (args.runtime / "log/mshvlog.edim").write_text("native")
    (args.runtime / "log/mshvlog.adi").write_text("<CALL:5>OM2BB<BAND:3>20m<MODE:3>FT8<QSO_DATE:8>20261001<TIME_ON:6>130000<EOR>")
    with patch.object(history, "mshv_running", return_value=False), pytest.raises(ValueError, match="absent from Wavelog"):
        history.migrate(args)


def test_actual_wavelog_export_report_is_accepted(tmp_path):
    exporter_path = MODULE.parents[1] / "digital/export_history.py"
    exporter_spec = importlib.util.spec_from_file_location("canonical_exporter", exporter_path)
    exporter = importlib.util.module_from_spec(exporter_spec)
    exporter_spec.loader.exec_module(exporter)
    args = setup_history(tmp_path)
    text, report = exporter.create_snapshot([("postgres-wavelog-mirror", [{
        "CALL": "OM1AA", "STATION_CALLSIGN": "OM0RX", "BAND": "20m", "MODE": "FT8",
        "FREQ": "14.074", "QSO_DATE": "20261001", "TIME_ON": "120000",
    }])], "OM0RX")
    # Mirrors the explicit --qualify-migration CLI gate after count review.
    report["migration_eligible"] = True
    report["qualification_review_required"] = False
    exporter.atomic_write_text(args.adif, text)
    args.adif.with_suffix(".adi.report.json").write_text(json.dumps(report), encoding="utf-8")
    with patch.object(history, "mshv_running", return_value=False):
        accepted = history.migrate(args)
    assert accepted["records"] == report["total_records"] == 1


def test_authoritative_marker_hash_retains_exact_attested_wavelog_bytes(tmp_path):
    args = setup_history(tmp_path)
    exact_hash = hashlib.sha256(args.adif.read_bytes()).hexdigest()
    normalized, _, _ = history.canonical(list(history.read_adif(args.adif)))
    assert hashlib.sha256(normalized).hexdigest() != exact_hash

    with patch.object(history, "mshv_running", return_value=False):
        report = history.migrate(args)

    assert report["canonical_sha256"] == exact_hash
    source = MODULE.read_text(encoding="utf-8")
    assert "staged_mirror.write_bytes(source_bytes)" in source


def test_failed_import_restores_original_stores(tmp_path):
    args = setup_history(tmp_path)
    args.apply = True
    native = args.runtime / "log/mshvlog.edim"
    mirror = args.runtime / "log/mshvlog.adi"
    native.write_bytes(b"original native")
    mirror.write_bytes(args.adif.read_bytes())
    exe = args.runtime / "MSHV_OM0RX.exe"
    exe.write_bytes(b"test executable")
    (args.runtime / "om0rx-build.json").write_text(json.dumps({
        "provider": "mshv_auto_dx", "capabilities": ["offline_history_v1", "wavelog_history_delta_v2"],
        "executable_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
    }))
    with patch.object(history, "mshv_running", return_value=False), patch.object(history.subprocess, "run", side_effect=RuntimeError("import failed")):
        with pytest.raises(RuntimeError, match="import failed"):
            history.migrate(args)
    assert native.read_bytes() == b"original native"
    assert mirror.read_bytes() == args.adif.read_bytes()
    assert not (args.runtime / ".history-import.lock").exists()
    assert list((args.runtime / "history-backups").iterdir())


def test_backup_failure_does_not_leave_invalid_lock(tmp_path):
    args = setup_history(tmp_path)
    args.apply = True
    native = args.runtime / "log/mshvlog.edim"
    native.write_bytes(b"original native")
    (args.runtime / "log/mshvlog.adi").write_bytes(args.adif.read_bytes())
    exe = args.runtime / "MSHV_OM0RX.exe"
    exe.write_bytes(b"test executable")
    (args.runtime / "om0rx-build.json").write_text(json.dumps({
        "provider": "mshv_auto_dx", "capabilities": ["offline_history_v1", "wavelog_history_delta_v2"],
        "executable_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
    }))
    with patch.object(history, "mshv_running", return_value=False), patch.object(history.shutil, "copy2", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            history.migrate(args)
    assert native.read_bytes() == b"original native"
    assert not (args.runtime / ".history-import.lock").exists()


def test_legacy_importer_without_delta_ledger_capability_is_rejected(tmp_path):
    args = setup_history(tmp_path)
    args.apply = True
    exe = args.runtime / "MSHV_OM0RX.exe"
    exe.write_bytes(b"legacy executable")
    (args.runtime / "om0rx-build.json").write_text(json.dumps({
        "provider": "mshv_auto_dx", "capabilities": ["offline_history_v1"],
        "executable_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
    }))
    with patch.object(history, "mshv_running", return_value=False), pytest.raises(
        RuntimeError, match="delta-ledger capability"
    ):
        history.migrate(args)
    assert not (args.runtime / ".history-import.lock").exists()


def test_interrupted_commit_journal_restores_exact_originals(tmp_path):
    args = setup_history(tmp_path)
    runtime = args.runtime.resolve()
    native = runtime / "log/mshvlog.edim"
    mirror = runtime / "log/mshvlog.adi"
    native.write_bytes(b"replacement")
    mirror.write_bytes(b"replacement")
    backup = runtime / "history-backups/crash"
    (backup / "log").mkdir(parents=True)
    (backup / "settings/database").mkdir(parents=True)
    (backup / "log/mshvlog.edim").write_bytes(b"original native")
    (backup / "log/mshvlog.adi").write_bytes(b"original adif")
    originals = {relative: relative in {"log/mshvlog.edim", "log/mshvlog.adi"} for relative in history.TARGETS}
    hashes = {
        relative: hashlib.sha256((backup / relative).read_bytes()).hexdigest()
        for relative in history.TARGETS if originals[relative]
    }
    (runtime / ".history-import.lock").write_text(json.dumps({
        "schema": 1, "phase": "committing", "runtime": str(runtime), "backup": "crash",
        "originals": originals, "backup_sha256": hashes,
    }))
    with patch.object(history, "mshv_running", return_value=False):
        result = history.recover_interrupted(runtime)
    assert result["recovered"] and result["restored"] == 2
    assert native.read_bytes() == b"original native"
    assert mirror.read_bytes() == b"original adif"
    assert not (runtime / "settings/database/worked.db").exists()
    assert not (runtime / "history-import.json").exists()
    assert not (runtime / ".history-import.lock").exists()
