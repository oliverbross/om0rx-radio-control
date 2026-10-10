"""Apply the two operator-authorized Wavelog band corrections safely.

Dry-run is the default. Apply uses one narrowly scoped transaction, exact
optimistic guards for every identifying field, and verifies that only COL_BAND
changed. This is intentionally not a general-purpose Wavelog editor.
"""
from __future__ import annotations

import argparse
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
from radio_control.persistence import atomic_write_json


CORRECTIONS = (
    {
        "id": 171175,
        "call": "ON3QRP",
        "qso_date": "20260527",
        "time_on": "231128",
        "mode": "FT8",
        "frequency_hz": 1_840_000,
        "old_band": "40m",
        "new_band": "160m",
    },
    {
        "id": 148686,
        "call": "DL0SOP",
        "qso_date": "20250724",
        "time_on": "174440",
        "mode": "CW",
        "frequency_hz": 7_015_064,
        "old_band": "20m",
        "new_band": "40m",
    },
)


def _json_value(value):
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def _stable_row(row: dict) -> dict:
    return {key: _json_value(row[key]) for key in sorted(row)}


def _row_hash(row: dict) -> str:
    payload = json.dumps(_stable_row(row), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _summary(row: dict) -> dict:
    return {
        "id": int(row["COL_PRIMARY_KEY"]),
        "station_id": int(row["station_id"]),
        "call": str(row.get("COL_CALL") or ""),
        "qso_date": row["COL_QSO_DATE"].strftime("%Y%m%d"),
        "time_on": row["COL_TIME_ON"].strftime("%H%M%S"),
        "mode": str(row.get("COL_SUBMODE") or row.get("COL_MODE") or ""),
        "frequency_hz": int(row["COL_FREQ"]),
        "band": str(row.get("COL_BAND") or "").lower(),
        "full_row_sha256": _row_hash(row),
    }


def _changed_columns(before: dict, after: dict) -> list[str]:
    keys = set(before) | set(after)
    return sorted(key for key in keys if _json_value(before.get(key)) != _json_value(after.get(key)))


def _connect():
    return pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASS,
        database=config.DB_NAME,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )


def _read_row(cursor, correction: dict) -> dict:
    cursor.execute(
        "SELECT * FROM TABLE_HRD_CONTACTS_V01 WHERE COL_PRIMARY_KEY = %s AND station_id = %s FOR UPDATE",
        (correction["id"], int(config.WAVELOG_STATION_ID)),
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError(f"Wavelog row {correction['id']} was not found in station {config.WAVELOG_STATION_ID}")
    return row


def _expected_summary(correction: dict) -> dict:
    return {
        "id": correction["id"],
        "station_id": int(config.WAVELOG_STATION_ID),
        "call": correction["call"],
        "qso_date": correction["qso_date"],
        "time_on": correction["time_on"],
        "mode": correction["mode"],
        "frequency_hz": correction["frequency_hz"],
        "band": correction["old_band"],
    }


def run(*, apply: bool, report: Path) -> dict:
    connection = _connect()
    evidence = {
        "schema": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "apply": apply,
        "table": "TABLE_HRD_CONTACTS_V01",
        "authorized_columns": ["COL_BAND"],
        "untouched_id": 144533,
        "corrections": [],
        "committed": False,
    }
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            cursor.execute("START TRANSACTION")
            before_rows = []
            for correction in CORRECTIONS:
                row = _read_row(cursor, correction)
                actual = _summary(row)
                comparable = {key: value for key, value in actual.items() if key != "full_row_sha256"}
                expected = _expected_summary(correction)
                if comparable != expected:
                    raise RuntimeError(
                        f"Wavelog row {correction['id']} no longer matches the authorized precondition: "
                        f"expected={expected!r} actual={comparable!r}"
                    )
                before_rows.append(row)
                evidence["corrections"].append({"authorized": correction, "before": actual})

            if not apply:
                connection.rollback()
                evidence["result"] = "dry-run-exact-preconditions-passed"
                atomic_write_json(report, evidence)
                return evidence

            for correction in CORRECTIONS:
                cursor.execute(
                    """
                    UPDATE TABLE_HRD_CONTACTS_V01
                    SET COL_BAND = %s
                    WHERE COL_PRIMARY_KEY = %s
                      AND station_id = %s
                      AND UPPER(TRIM(COL_CALL)) = %s
                      AND DATE_FORMAT(COL_QSO_DATE, '%%Y%%m%%d') = %s
                      AND TIME_FORMAT(COL_TIME_ON, '%%H%%i%%s') = %s
                      AND UPPER(TRIM(COALESCE(NULLIF(COL_SUBMODE, ''), COL_MODE))) = %s
                      AND CAST(COL_FREQ AS DECIMAL(18, 3)) = %s
                      AND LOWER(TRIM(COL_BAND)) = %s
                    """,
                    (
                        correction["new_band"], correction["id"], int(config.WAVELOG_STATION_ID),
                        correction["call"], correction["qso_date"], correction["time_on"],
                        correction["mode"], correction["frequency_hz"], correction["old_band"].lower(),
                    ),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(f"Exact guarded update matched {cursor.rowcount} rows for {correction['id']}")

            for index, correction in enumerate(CORRECTIONS):
                after = _read_row(cursor, correction)
                changed = _changed_columns(before_rows[index], after)
                after_summary = _summary(after)
                if changed != ["COL_BAND"] or after_summary["band"].lower() != correction["new_band"].lower():
                    raise RuntimeError(
                        f"Post-update verification failed for {correction['id']}: "
                        f"changed={changed!r} after_band={after_summary['band']!r}"
                    )
                evidence["corrections"][index].update({"after": after_summary, "changed_columns": changed})

            connection.commit()
            evidence["committed"] = True
            evidence["result"] = "committed-and-verified"
    except Exception as exc:
        connection.rollback()
        evidence["result"] = "rolled-back"
        evidence["error"] = str(exc)
        atomic_write_json(report, evidence)
        raise
    finally:
        connection.close()

    atomic_write_json(report, evidence)
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(apply=args.apply, report=args.report), indent=2))


if __name__ == "__main__":
    main()
