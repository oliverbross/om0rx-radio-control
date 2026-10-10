"""Qualification of the packaged offline mode; no station or radio services."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
from contextlib import closing
from types import SimpleNamespace

import pytest


def test_packaged_native_import_and_idempotency(tmp_path):
    project = Path(__file__).resolve().parents[1]
    configured_runtime = os.environ.get("OM0RX_MSHV_TEST_RUNTIME")
    packaged = Path(configured_runtime).resolve() if configured_runtime else (
        project / "data/build/mshv-auto-dx/phase2-runtime"
    )
    if not (packaged / "om0rx-build.json").exists():
        if configured_runtime:
            pytest.fail(f"Explicit MSHV test candidate is missing its manifest: {packaged}")
        pytest.skip("Build/package MSHV before native offline qualification")
    manifest = json.loads((packaged / "om0rx-build.json").read_text(encoding="utf-8-sig"))
    if configured_runtime:
        assert "wavelog_history_delta_v2" in set(manifest.get("capabilities") or [])
    runtime = tmp_path / "runtime"
    shutil.copytree(packaged, runtime, ignore=shutil.ignore_patterns("history-backups", "history-import.json", ".history-import.lock", "mshvlog.*", "worked.db*"))
    source = tmp_path / "canonical.adi"
    source.write_bytes(
        b"<ADIF_VER:5>3.1.4<EOH>\n"
        b"<CALL:5>OM1AA<BAND:3>20m<MODE:3>FT8<FREQ:6>14.074<QSO_DATE:8>20261001<TIME_ON:6>120000<EOR>\n"
        b"<CALL:5>OK1BB<BAND:3>40m<MODE:4>MFSK<SUBMODE:3>FT4<FREQ:5>7.047<QSO_DATE:8>20261001<TIME_ON:6>130000<EOR>\n")
    source.with_suffix(".adi.report.json").write_text(json.dumps({
        "canonical_source": "wavelog_postgres", "station_callsign": "OM0RX", "migration_eligible": True,
        "canonical_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "qualification_review_required": False,
        "production_policy": "Wavelog sole authority; WSJT inputs diagnostic only; FT8/FT4 only",
        "total_records": 2, "digital_records": 2,
    }))
    spec = importlib.util.spec_from_file_location("mshv_import_native", project / "scripts/mshv/import_history.py")
    importer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(importer)
    args = SimpleNamespace(runtime=runtime, adif=source, apply=True)
    first = importer.migrate(args)
    assert first["applied"] and first["records"] == 2
    assert (runtime / "log/mshvlog.edim").exists()
    with closing(sqlite3.connect(runtime / "settings/database/worked.db")) as db:
        assert db.execute("SELECT COUNT(*) FROM worked_calls").fetchone()[0] == 2
        assert {row[0] for row in db.execute("SELECT DISTINCT mode FROM worked_calls")} == {"FT8", "FT4"}
    before = hashlib.sha256((runtime / "log/mshvlog.edim").read_bytes()).hexdigest()
    second = importer.migrate(args)
    assert second["unchanged"]
    assert hashlib.sha256((runtime / "log/mshvlog.edim").read_bytes()).hexdigest() == before
    assert not (runtime / ".history-import.lock").exists()
