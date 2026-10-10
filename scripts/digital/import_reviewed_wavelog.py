"""Safely submit explicitly reviewed WSJT forensic candidates to Wavelog.

The script is dry-run by default. It reads Wavelog in one repeatable, read-only
snapshot, never writes a database directly, and submits the original ADIF only
through Wavelog's API. Ambiguous/near/existing candidates are always excluded.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, time, timezone
import hashlib
import json
from pathlib import Path
import sys

import pymysql
from pymysql.cursors import DictCursor

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from radio_control import config
from radio_control.persistence import atomic_write_json, read_json_object
from radio_control.wavelog_api import WavelogClient
from scripts.digital.export_history import create_snapshot, parse_adif, serialize_original_records

ALLOWED_MODES = {"FT8", "FT4"}


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d%H%M%S")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    if isinstance(value, time):
        return value.strftime("%H%M%S")
    return str(value)


def _date_text(value) -> str:
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y%m%d")
    return _text(value)


def _time_text(value) -> str:
    if isinstance(value, (datetime, time)):
        return value.strftime("%H%M%S")
    return _text(value)


def authoritative_wavelog_records(station_id: int) -> list[dict]:
    """Take one fresh consistent read-only snapshot from Wavelog MySQL."""
    connection = pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASS,
        database=config.DB_NAME,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
            cursor.execute(
                """
                SELECT COL_PRIMARY_KEY, COL_CALL, COL_QSO_DATE, COL_TIME_ON,
                       COL_TIME_OFF, COL_BAND, COL_FREQ, COL_MODE, COL_SUBMODE,
                       COL_STATION_CALLSIGN
                FROM TABLE_HRD_CONTACTS_V01
                WHERE station_id = %s
                ORDER BY COL_PRIMARY_KEY
                """,
                (station_id,),
            )
            rows = cursor.fetchall()
        connection.rollback()
    finally:
        connection.close()
    return [
        {
            "_SOURCE_ID": _text(row.get("COL_PRIMARY_KEY")),
            "CALL": _text(row.get("COL_CALL")),
            "QSO_DATE": _date_text(row.get("COL_QSO_DATE")),
            "TIME_ON": _time_text(row.get("COL_TIME_ON")),
            "TIME_OFF": _time_text(row.get("COL_TIME_OFF")),
            "BAND": _text(row.get("COL_BAND")),
            "FREQ": _text(row.get("COL_FREQ")),
            "MODE": _text(row.get("COL_MODE")),
            "SUBMODE": _text(row.get("COL_SUBMODE")),
            "STATION_CALLSIGN": _text(row.get("COL_STATION_CALLSIGN")),
        }
        for row in rows
    ]


def _candidate_key(record: dict) -> str:
    adif = serialize_original_records([record])
    return hashlib.sha256(adif.encode("utf-8")).hexdigest()


def _identity(record: dict) -> dict:
    return {
        "call": str(record.get("CALL") or "").upper(),
        "qso_date": str(record.get("QSO_DATE") or ""),
        "time_on": str(record.get("TIME_ON") or ""),
        "band": str(record.get("BAND") or "").lower(),
        "mode": str(record.get("SUBMODE") or record.get("MODE") or "").upper(),
        "frequency_mhz": record.get("FREQ") or "",
    }


def compare_now(candidates: list[dict], station: str, station_id: int) -> tuple[dict, dict[str, dict]]:
    audit: list[dict] = []
    _, comparison = create_snapshot(
        [
            ("postgres-wavelog-mirror", authoritative_wavelog_records(station_id)),
            ("reviewed-candidates", candidates),
        ],
        station,
        all_modes=True,
        audit_output=audit,
    )
    if comparison.get("rejected_by_source", {}).get("postgres-wavelog-mirror"):
        raise RuntimeError("Authoritative Wavelog snapshot contained rejected records; duplicate preflight is unsafe")
    classifications: dict[str, dict] = {}
    for entry in audit:
        if entry.get("source") == "postgres-wavelog-mirror" or "record" not in entry:
            continue
        record = entry["record"]
        key = _candidate_key(entry.get("raw") or record)
        classifications[key] = {
            "classification": entry["classification"],
            "identity": _identity(record),
            "matched_wavelog_primary_ids": entry.get("matched_wavelog_primary_ids", []),
            "matched_times": entry.get("matched_times", []),
        }
    return comparison, classifications


async def run(args) -> dict:
    text = args.candidate.read_text(encoding="utf-8-sig")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    provenance = read_json_object(args.candidate.with_suffix(".report.json"))
    candidates = list(parse_adif(text))
    modes = {str(row.get("SUBMODE") or row.get("MODE") or "").upper() for row in candidates}
    if (
        provenance.get("canonical_source") != "wsjt_forensic_candidates"
        or provenance.get("sha256") != digest
        or provenance.get("preserves_original_adif_fields") is not True
        or set(provenance.get("allowed_modes") or []) != ALLOWED_MODES
        or int(provenance.get("records") or -1) != len(candidates)
    ):
        raise SystemExit("Candidate provenance/digest invalid")
    if len(candidates) != args.expected_count or not modes.issubset(ALLOWED_MODES):
        raise SystemExit(f"Expected exactly {args.expected_count} FT8/FT4 candidates; found {len(candidates)} {sorted(modes)}")
    if args.apply and args.reviewed_sha256.lower() != digest:
        raise SystemExit("--apply requires the exact user-reviewed candidate SHA256")

    args.report_dir.mkdir(parents=True, exist_ok=True)
    comparison, classifications = compare_now(candidates, str(config.MY_STATION).upper(), int(config.WAVELOG_STATION_ID))
    candidate_map = {_candidate_key(row): row for row in candidates}
    if len(candidate_map) != len(candidates):
        raise SystemExit("Candidate file contains duplicate original ADIF records")
    eligible = [key for key in candidate_map if classifications.get(key, {}).get("classification") == "genuinely_absent"]
    excluded = {key: classifications.get(key, {"classification": "unclassified"}) for key in candidate_map if key not in eligible}
    preflight = {
        "schema": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dry_run": not args.apply,
        "candidate_sha256": digest,
        "candidate_records": len(candidates),
        "eligible_now": len(eligible),
        "eligible": [{"key": key, "identity": _identity(candidate_map[key])} for key in eligible],
        "excluded_now": len(excluded),
        "excluded": excluded,
        "comparison": comparison["reconciliation"],
        "comparison_tolerance": comparison["reconciliation_tolerance"],
        "wavelog_snapshot_rows": comparison["sources"].get("postgres-wavelog-mirror"),
        "wavelog_read": "repeatable-read read-only authoritative MySQL snapshot",
        "write_path": "Wavelog API submit_adif_string only",
    }
    atomic_write_json(args.report_dir / "preflight.json", preflight)
    if not args.apply:
        return preflight

    journal_path = args.report_dir / "import-journal.json"
    journal = read_json_object(journal_path)
    if journal and (journal.get("schema") != 1 or journal.get("candidate_sha256") != digest):
        raise SystemExit("Existing import journal does not match this candidate set")
    journal.setdefault("schema", 1)
    journal.setdefault("candidate_sha256", digest)
    journal.setdefault("entries", {})
    unresolved = [key for key, entry in journal["entries"].items() if entry.get("state") in {"submitting", "failed"}]
    if unresolved:
        raise SystemExit(f"Journal contains unresolved submissions; refusing blind retry: {unresolved}")

    client = WavelogClient()
    results = []
    try:
        for ordinal, key in enumerate(eligible, start=1):
            record = candidate_map[key]
            prior = journal["entries"].get(key)
            if prior and prior.get("state") == "accepted":
                results.append({"key": key, "state": "already-accepted", "identity": _identity(record), "response": prior.get("response")})
                continue
            journal["entries"][key] = {
                "state": "submitting",
                "ordinal": ordinal,
                "identity": _identity(record),
                "started_utc": datetime.now(timezone.utc).isoformat(),
            }
            atomic_write_json(journal_path, journal)
            response = await client.submit_adif_string(serialize_original_records([record]))
            if not response.get("success"):
                journal["entries"][key].update({"state": "failed", "response": response, "finished_utc": datetime.now(timezone.utc).isoformat()})
                atomic_write_json(journal_path, journal)
                atomic_write_json(args.report_dir / "import-results.json", {"success": False, "results": results, "failed": journal["entries"][key]})
                raise SystemExit(f"Wavelog rejected candidate {ordinal}/{len(eligible)}; import stopped")
            journal["entries"][key].update({"state": "accepted", "response": response, "finished_utc": datetime.now(timezone.utc).isoformat()})
            atomic_write_json(journal_path, journal)
            results.append({"key": key, "state": "accepted", "identity": _identity(record), "response": response})
            atomic_write_json(args.report_dir / "import-results.json", {"success": True, "accepted": sum(row["state"] == "accepted" for row in results), "results": results})
    finally:
        await WavelogClient.close_session()

    post_comparison, post_classifications = compare_now(candidates, str(config.MY_STATION).upper(), int(config.WAVELOG_STATION_ID))
    accepted_keys = [key for key, entry in journal["entries"].items() if entry.get("state") == "accepted"]
    unverified_after = [key for key in accepted_keys if post_classifications.get(key, {}).get("classification") != "exact"]
    verification = {
        "schema": 1,
        "verified_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_sha256": digest,
        "accepted": len(accepted_keys),
        "unverified": unverified_after,
        "verified": not unverified_after,
        "classifications": {key: post_classifications.get(key, {"classification": "unclassified"}) for key in accepted_keys},
        "wavelog_snapshot_rows": post_comparison["sources"].get("postgres-wavelog-mirror"),
    }
    atomic_write_json(args.report_dir / "post-verify.json", verification)
    return {"success": verification["verified"], "preflight": preflight, "results": results, "post_verify": verification}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, default=50)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reviewed-sha256", default="")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args)), indent=2))


if __name__ == "__main__":
    main()
