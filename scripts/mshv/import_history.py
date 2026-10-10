"""Explicit, offline MSHV history migration; never called during normal launch."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone
from contextlib import closing

TAG = re.compile(r"<([^:>]+)(?::(\d+)(?::[^>]+)?)?>", re.I)


def read_adif(path: Path):
    text = path.read_text(encoding="utf-8-sig", errors="strict")
    fields = {}
    offset = 0
    while match := TAG.search(text, offset):
        name = match[1].upper()
        offset = match.end()
        if name == "EOH":
            fields = {}
        elif name == "EOR":
            if fields:
                yield fields
            fields = {}
        elif match[2] is not None:
            length = int(match[2])
            if offset + length > len(text):
                raise ValueError(f"Truncated ADIF field {name}: {path}")
            fields[name] = text[offset:offset + length].strip()
            offset += length
    if fields:
        raise ValueError(f"Unterminated ADIF record: {path}")


def canonical(records):
    unique = {}
    rejected = 0
    for record in records:
        record = dict(record)
        mode = record.get("MODE", "").upper()
        if mode == "MFSK" and record.get("SUBMODE", "").upper() == "FT4":
            mode = "FT4"
        if mode not in ("FT8", "FT4"):
            rejected += 1
            continue
        record["MODE"] = mode
        record.pop("SUBMODE", None)
        record["CALL"] = record.get("CALL", "").upper()
        record["BAND"] = record.get("BAND", "").lower()
        for key in ("CALL", "BAND", "QSO_DATE", "TIME_ON"):
            if not record.get(key):
                raise ValueError(f"Required history field missing: {key}")
        if not re.fullmatch(r"\d{8}", record["QSO_DATE"]) or not re.fullmatch(r"\d{4}(\d{2})?", record["TIME_ON"]):
            raise ValueError("Invalid history date/time")
        record["TIME_ON"] = record["TIME_ON"].ljust(6, "0")
        key = tuple(record[k] for k in ("CALL", "QSO_DATE", "TIME_ON", "BAND", "MODE"))
        unique[key] = {**unique.get(key, {}), **record}
    lines = ["OM0RX canonical MSHV history <ADIF_VER:5>3.1.4<EOH>"]
    for key in sorted(unique):
        fields = unique[key]
        lines.append("".join(f"<{name}:{len(value)}>{value}" for name, value in sorted(fields.items())) + "<EOR>")
    return ("\n".join(lines) + "\n").encode("utf-8"), len(unique), rejected


def mshv_running(executable: Path):
    """Return whether the exact packaged executable is running.

    A broad process-name match can both block an unrelated MSHV installation and
    miss a renamed packaged process.  Win32 exposes the image path for an exact,
    case-insensitive identity check.
    """
    if os.name != "nt":
        raise RuntimeError("Production migration requires Windows process inspection")
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    target = os.path.normcase(os.path.realpath(executable))
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    result = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {executable.name}", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, check=True)
    import csv
    import io
    for row in csv.reader(io.StringIO(result.stdout)):
        if len(row) < 2 or row[0].lower() != executable.name.lower() or not row[1].isdigit():
            continue
        handle = kernel32.OpenProcess(process_query_limited_information, False, int(row[1]))
        if not handle:
            # Fail closed when an exact-name candidate cannot be identified.
            return True
        try:
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return True
            if os.path.normcase(os.path.realpath(buffer.value)) == target:
                return True
        finally:
            kernel32.CloseHandle(handle)
    return False


def history_keys(records):
    keys = set()
    for record in records:
        mode = record.get("MODE", "").upper()
        if mode == "MFSK" and record.get("SUBMODE", "").upper() == "FT4":
            mode = "FT4"
        if mode in ("FT8", "FT4"):
            keys.add((record.get("CALL", "").upper(), record.get("QSO_DATE", ""),
                      record.get("TIME_ON", "").ljust(6, "0"), record.get("BAND", "").lower(), mode))
    return keys


BAND_INDEX = {"160m":3,"80m":4,"60m":5,"40m":6,"30m":7,"20m":8,"17m":9,"15m":10,"12m":11,"10m":12,"6m":14,"2m":17}
NATIVE_BANDS = {"1.8M":"160m","3.5M":"80m","5M":"60m","7M":"40m","10M":"30m","14M":"20m","18M":"17m","21M":"15m","24M":"12m","28M":"10m","50M":"6m","144M":"2m"}


def tracker_base_call(callsign: str) -> str:
    """Mirror MSHV HvDxccTracker::extractBaseCall for worked_calls keys.

    The native log deliberately preserves the full portable callsign.  MSHV's
    dupe tracker, however, keys worked calls by its normalized base call while
    DXCC lookup continues to use the full call.  Validation must compare the
    tracker against that documented native representation, not require a value
    the tracker intentionally does not store.
    """
    call = callsign.upper().strip()
    slash = call.rfind("/")
    if 0 < slash < len(call) - 1 and len(call[slash + 1:]) <= 3:
        call = call[:slash]
    slash = call.find("/")
    if 0 < slash < len(call) - 1:
        prefix, main_call = call[:slash], call[slash + 1:]
        if len(prefix) <= 3 and len(main_call) > len(prefix):
            call = main_call
    return call


def validate_stores(native, database, expected_keys):
    actual_keys = []
    for line in native.read_text(encoding="utf-8-sig").splitlines():
        if not line or line.startswith("["):
            continue
        fields = line.split(";")
        if len(fields) < 21 or fields[5] not in {"22", "24"} or fields[9] not in NATIVE_BANDS:
            raise RuntimeError("Unsupported/malformed native history record")
        actual_keys.append((fields[4].upper(), fields[0], fields[1] + fields[18], NATIVE_BANDS[fields[9]],
                            "FT8" if fields[5] == "22" else "FT4"))
    if len(actual_keys) != len(expected_keys) or set(actual_keys) != expected_keys:
        raise RuntimeError("Native history count/identity coverage differs from canonical Wavelog")
    expected_tracker = {
        (tracker_base_call(call), BAND_INDEX[band], mode)
        for call, date, time, band, mode in expected_keys
    }
    with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Staged tracker failed SQLite integrity check")
        if db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='wavelog_applied_deltas'"
        ).fetchone() is None:
            raise RuntimeError("Staged tracker lacks the Wavelog acknowledged-delta ledger")
        actual_tracker = set(db.execute("SELECT callsign,band_index,mode FROM worked_calls"))
    if actual_tracker != expected_tracker:
        missing = sorted(expected_tracker - actual_tracker)[:10]
        unexpected = sorted(actual_tracker - expected_tracker)[:10]
        raise RuntimeError(
            "Tracker call/band/mode coverage differs from canonical Wavelog: "
            f"expected={len(expected_tracker)} actual={len(actual_tracker)} "
            f"missing_sample={missing!r} unexpected_sample={unexpected!r}"
        )
    return {"native_records": len(actual_keys), "tracker_unique_calls": len(actual_tracker), "tracker_coverage_verified": True}


TARGETS = (
    "log/mshvlog.edim",
    "log/mshvlog.adi",
    "settings/database/worked.db",
    "settings/database/wavelog_delta_state.json",
    "history-import.json",
)


def _atomic_json(path: Path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def recover_interrupted(runtime: Path):
    """Rollback an interrupted commit from the durable history journal."""
    runtime = runtime.resolve(strict=True)
    lock = runtime / ".history-import.lock"
    if not lock.exists():
        return {"recovered": False, "reason": "no_journal"}
    exe = runtime / "MSHV_OM0RX.exe"
    if mshv_running(exe):
        raise RuntimeError("Stop the packaged MSHV runtime before history recovery")
    try:
        journal = json.loads(lock.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"History recovery journal is unreadable: {lock}") from exc
    if (journal.get("schema") != 1 or journal.get("runtime") != str(runtime) or
            journal.get("phase") not in {"preparing", "committing", "rolling_back"} or
            set(journal.get("originals", {})) != set(TARGETS)):
        raise RuntimeError("History recovery journal identity/schema is invalid")
    backup = (runtime / "history-backups" / journal.get("backup", "")).resolve()
    backup_root = (runtime / "history-backups").resolve()
    if backup.parent != backup_root:
        raise RuntimeError("History recovery backup path escapes the runtime")
    originals = journal["originals"]
    backup_hashes = journal.get("backup_sha256", {})
    if journal["phase"] == "preparing":
        # The phase changes only after every backup is durable and before the
        # first replacement, so no runtime store can have changed yet.
        lock.unlink()
        return {"recovered": True, "phase": "preparing", "restored": 0}
    for relative in TARGETS:
        if originals[relative] is not True:
            continue
        saved = backup / relative
        expected = backup_hashes.get(relative, "").lower()
        if not saved.is_file() or not expected or hashlib.sha256(saved.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"History recovery backup is missing or corrupt: {relative}")
    journal["phase"] = "rolling_back"
    _atomic_json(lock, journal)
    restored = 0
    for relative in TARGETS:
        target = runtime / relative
        if originals[relative] is True:
            target.parent.mkdir(parents=True, exist_ok=True)
            rollback = target.with_suffix(target.suffix + ".rollback.tmp")
            shutil.copy2(backup / relative, rollback)
            os.replace(rollback, target)
            restored += 1
        elif target.exists():
            target.unlink()
    lock.unlink()
    return {"recovered": True, "phase": "committing", "restored": restored}


def migrate(args):
    runtime = args.runtime.resolve(strict=True)
    source = args.adif.resolve(strict=True)
    provenance_path = source.with_suffix(source.suffix + ".report.json")
    if not provenance_path.exists():
        raise ValueError("Wavelog canonical provenance report is required")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8-sig"))
    source_bytes = source.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    if (provenance.get("canonical_source") != "wavelog_postgres" or
            provenance.get("station_callsign") != "OM0RX" or
            provenance.get("migration_eligible") is not True or
            provenance.get("qualification_review_required") is not False or
            provenance.get("production_policy") != "Wavelog sole authority; WSJT inputs diagnostic only; FT8/FT4 only" or
            provenance.get("canonical_sha256", "").lower() != source_hash):
        raise ValueError("Only the verified Wavelog-canonical OM0RX export may be migrated")
    exe = runtime / "MSHV_OM0RX.exe"
    if mshv_running(exe):
        raise RuntimeError("Stop MSHV before history migration")
    native = runtime / "log/mshvlog.edim"
    mirror = runtime / "log/mshvlog.adi"
    database = runtime / "settings/database/worked.db"
    if any(Path(str(database) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise RuntimeError("SQLite sidecars exist; close/recover the tracker before migration")
    lock = runtime / ".history-import.lock"
    if lock.exists():
        raise RuntimeError(f"Migration lock/journal exists; run --recover before proceeding: {lock}")
    if native.exists() and not mirror.exists():
        raise RuntimeError("Existing native MSHV log has no ADIF mirror; export it before migration")
    records = list(read_adif(source))
    data, count, rejected = canonical(records)
    if (provenance.get("total_records") != len(records) or
            provenance.get("digital_records") != len(records) or rejected != 0):
        raise ValueError("Wavelog provenance/source record counts do not match exactly")
    if any(band not in BAND_INDEX for call, date, time, band, mode in history_keys(records)):
        raise ValueError("Canonical history contains a band unsupported by the qualified tracker")
    if mirror.exists():
        previous_records = list(read_adif(mirror))
        canonical(previous_records)  # validate native identities without merging fields
        if not history_keys(previous_records).issubset(history_keys(records)):
            raise ValueError("Native MSHV history contains records absent from Wavelog; sync them before migration")
    if count == 0 or count > 500000:
        raise ValueError("History is empty or exceeds MSHV's 500000-QSO limit")
    # The exact Wavelog export is the authoritative artifact attested by its
    # provenance report.  Normalized serialization is private input to the
    # native derived-store importer; it must not replace the canonical bytes
    # or identity recorded by the marker.
    digest = source_hash
    report = {"schema": 1, "provider": "mshv_auto_dx", "dry_run": not args.apply,
              "records": count, "skipped_other_modes": rejected, "canonical_sha256": digest,
              "source": str(source), "runtime": str(runtime),
              "canonical_source": provenance["canonical_source"],
              "production_policy": provenance["production_policy"],
              "station_callsign": provenance["station_callsign"],
              "configured_station_id": provenance.get("configured_station_id"),
              "provenance_report_sha256": hashlib.sha256(provenance_path.read_bytes()).hexdigest()}
    marker = runtime / "history-import.json"
    if marker.exists():
        previous = json.loads(marker.read_text())
        delta_state_path = runtime / "settings/database/wavelog_delta_state.json"
        delta_state = json.loads(delta_state_path.read_text()) if delta_state_path.is_file() else {}
        if (previous.get("canonical_sha256") == digest and
                delta_state.get("snapshot_generation") == digest and
                all(path.exists() and previous.get(key) == hashlib.sha256(path.read_bytes()).hexdigest()
                    for path, key in ((native, "native_sha256"), (mirror, "adif_sha256"), (database, "tracker_sha256")))):
            report["unchanged"] = True
            return report
    if not args.apply:
        return report
    if not exe.exists():
        raise FileNotFoundError(exe)
    build = json.loads((runtime / "om0rx-build.json").read_text(encoding="utf-8-sig"))
    if (build.get("provider") != "mshv_auto_dx" or
            "wavelog_history_delta_v2" not in build.get("capabilities", []) or
            build.get("executable_sha256", "").lower() != hashlib.sha256(exe.read_bytes()).hexdigest()):
        raise RuntimeError("Offline importer executable lacks the qualified Wavelog delta-ledger capability")
    backup = runtime / "history-backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    targets = [runtime / relative for relative in TARGETS]
    originals = {relative: (runtime / relative).exists() for relative in TARGETS}
    journal = {"schema": 1, "phase": "preparing", "runtime": str(runtime),
               "backup": backup.name, "originals": originals, "backup_sha256": {}}
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, json.dumps(journal, sort_keys=True).encode("utf-8"))
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        lock.unlink()
        raise
    os.close(fd)
    commit_started = False
    try:
        backup.mkdir(parents=True)
        for relative, path in zip(TARGETS, targets):
            if path.exists():
                saved = backup / relative
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, saved)
                journal["backup_sha256"][relative] = hashlib.sha256(saved.read_bytes()).hexdigest()
        if mshv_running(exe):
            raise RuntimeError("MSHV was started during migration preparation")
        with tempfile.TemporaryDirectory(prefix="mshv-history-", dir=runtime.parent) as temp:
            staging = Path(temp)
            (staging / "log").mkdir()
            shutil.copytree(runtime / "settings/database", staging / "settings/database",
                            ignore=shutil.ignore_patterns("worked.db", "worked.db-*", "wavelog_delta_state.json"))
            history = staging / "canonical.adi"
            history.write_bytes(data)
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
            subprocess.run([str(exe), f"--om0rx-import-history={history}", f"--om0rx-import-root={staging}"],
                           env=env, check=True, timeout=1800)
            staged_native = staging / "log/mshvlog.edim"
            staged_db = staging / "settings/database/worked.db"
            if not staged_native.exists() or not staged_db.exists():
                raise RuntimeError("Offline importer did not create both stores")
            report.update(validate_stores(staged_native, staged_db, history_keys(records)))
            # Canonical ADIF preserves every field, including fields MSHV cannot export.
            staged_mirror = staging / "log/mshvlog.adi"
            staged_mirror.write_bytes(source_bytes)
            staged_marker = staging / "history-import.json"
            report.update(applied=True, backup=str(backup), imported_utc=datetime.now(timezone.utc).isoformat())
            report.update(native_sha256=hashlib.sha256(staged_native.read_bytes()).hexdigest(),
                          adif_sha256=hashlib.sha256(staged_mirror.read_bytes()).hexdigest(),
                          tracker_sha256=hashlib.sha256(staged_db.read_bytes()).hexdigest())
            staged_delta_state = staging / "settings/database/wavelog_delta_state.json"
            staged_delta_state.write_text(json.dumps({
                "schema": 1,
                "snapshot_generation": report["canonical_sha256"],
                "last_sequence": 0,
                "applied_keys": [],
                "tracker_sha256": report["tracker_sha256"],
            }, indent=2), encoding="utf-8")
            staged_marker.write_text(json.dumps(report, indent=2), encoding="utf-8")
            journal["phase"] = "committing"
            _atomic_json(lock, journal)
            commit_started = True
            for path, staged in zip(targets, [staged_native, staged_mirror, staged_db, staged_delta_state, staged_marker]):
                path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged, path)
    except BaseException:
        if commit_started:
            recover_interrupted(runtime)
        elif lock.exists():
            lock.unlink()
        raise
    lock.unlink()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--adif", type=Path)
    parser.add_argument("--apply", action="store_true", help="Commit staged migration after backups; default is dry-run")
    parser.add_argument("--recover", action="store_true", help="Rollback an interrupted journal and exit")
    args = parser.parse_args()
    if args.recover:
        if args.apply or args.adif:
            parser.error("--recover cannot be combined with --apply or --adif")
        print(json.dumps(recover_interrupted(args.runtime), indent=2))
        return
    if args.adif is None:
        parser.error("--adif is required unless --recover is used")
    print(json.dumps(migrate(args), indent=2))


if __name__ == "__main__":
    main()
