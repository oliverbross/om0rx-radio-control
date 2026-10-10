"""Read-only canonical station history snapshot for MSHV native/tracker import.

Database rows precede supplemental ADIF, so Wavelog wins field conflicts.
No source log or database is modified. Output is stable for identical inputs.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import csv
import io
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from radio_control.persistence import atomic_write_json, atomic_write_text

FIELDS = ("CALL", "QSO_DATE", "TIME_ON", "TIME_OFF", "BAND", "MODE", "SUBMODE", "FREQ", "DXCC", "GRIDSQUARE", "RST_SENT", "RST_RCVD", "STATION_CALLSIGN", "OPERATOR", "MY_GRIDSQUARE", "COUNTRY", "CQZ", "ITUZ", "NAME", "QTH", "COMMENT", "QSL_RCVD", "LOTW_QSL_RCVD", "EQSL_QSL_RCVD", "POTA_REF", "SOTA_REF", "IOTA", "WWFF_REF")


def parse_adif(text: str):
    """Respect field length so literal '<' in values cannot truncate records."""
    position = 0
    record = {}
    tag = re.compile(r"<([^:>]+)(?::(\d+)(?::[^>]*)?)?>", re.I)
    while match := tag.search(text, position):
        name = match[1].strip().upper()
        position = match.end()
        if name == "EOH":
            record = {}
        elif name == "EOR":
            if record:
                yield record
            record = {}
        elif match[2] is not None:
            length = int(match[2])
            if position + length > len(text):
                raise ValueError("Truncated ADIF field")
            record[name] = text[position:position + length].strip()
            position += length
    if record:
        raise ValueError("ADIF ends with an incomplete QSO (missing EOR)")


def normalize(record: dict, station: str) -> dict | None:
    data = {str(key).upper(): str(value).strip() for key, value in record.items() if value is not None}
    for key in ("CALL", "MODE", "SUBMODE", "GRIDSQUARE", "STATION_CALLSIGN"):
        if key in data:
            data[key] = data[key].upper()
    data["CALL"] = re.sub(r"\s+", "", data.get("CALL", ""))
    data["STATION_CALLSIGN"] = data.get("STATION_CALLSIGN") or station
    if data["STATION_CALLSIGN"] != station:
        return None
    data["BAND"] = data.get("BAND", "").lower()
    if data.get("MODE") == "MFSK" and data.get("SUBMODE") in {"FT4", "FT8"}:
        data["MODE"] = data.pop("SUBMODE")
    date = re.sub(r"\D", "", data.get("QSO_DATE", ""))[:8]
    time_on = re.sub(r"\D", "", data.get("TIME_ON", ""))
    if len(time_on) == 4:
        time_on += "00"
    if len(time_on) != 6 or len(date) != 8 or not data.get("CALL") or not data.get("MODE"):
        raise ValueError("Missing/invalid QSO identity fields")
    datetime.strptime(date + time_on, "%Y%m%d%H%M%S")
    data["QSO_DATE"], data["TIME_ON"] = date, time_on
    if data.get("FREQ"):
        frequency = float(data["FREQ"])
        if frequency > 1000:
            frequency /= 1_000_000
        if frequency <= 0:
            raise ValueError("Invalid frequency")
        data["FREQ"] = f"{frequency:.6f}".rstrip("0").rstrip(".")
        if not data["BAND"]:
            from radio_control.flex_radio import FlexCtl
            data["BAND"] = FlexCtl.band_for_frequency(frequency) or ""
    if not data["BAND"]:
        raise ValueError("Missing band")
    if data.get("FREQ"):
        from radio_control.flex_radio import FlexCtl
        derived = FlexCtl.band_for_frequency(float(data["FREQ"]))
        if derived and derived != data["BAND"]:
            data["_BAND_FREQUENCY_MISMATCH"] = "true"
    return data


def utc_log_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def postgres_records(station_id: int):
    from radio_control.postgres_store import connect
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cur.execute("SELECT * FROM qso_records WHERE station_id = %s ORDER BY qso_datetime, wavelog_id", (station_id,))
            columns = [column.name for column in cur.description]
            for values in cur.fetchall():
                row = dict(zip(columns, values))
                data = {key.upper(): value for key, value in row.items() if key.upper() in FIELDS}
                data["_SOURCE_ID"] = row.get("wavelog_id") or row.get("id")
                data["FREQ"] = row.get("frequency")
                date = row.get("qso_datetime") or row.get("time_on")
                if isinstance(date, datetime):
                    date = utc_log_datetime(date)
                    data["QSO_DATE"] = date.strftime("%Y%m%d")
                    data["TIME_ON"] = date.strftime("%H%M%S")
                if isinstance(row.get("time_off"), datetime):
                    data["TIME_OFF"] = row["time_off"].strftime("%H%M%S")
                yield data
        conn.rollback()


def serialize_records(ordered):
    lines = ["OM0RX canonical migration snapshot", "<ADIF_VER:5>3.1.0 <PROGRAMID:5>OM0RX <EOH>"]
    for record in ordered:
        lines.append(" ".join(f"<{key}:{len(record[key])}>{record[key]}" for key in FIELDS if record.get(key)) + " <EOR>")
    return "\n".join(lines) + "\n"


def serialize_original_records(ordered):
    """Serialize complete source fields without inventing or dropping ADIF tags."""
    lines = ["OM0RX forensic review candidates", "<ADIF_VER:5>3.1.0 <PROGRAMID:5>OM0RX <EOH>"]
    for record in ordered:
        fields = []
        for raw_key, raw_value in record.items():
            key = str(raw_key).strip().upper()
            if not key or key.startswith("_") or key in {"EOH", "EOR"} or raw_value is None:
                continue
            value = str(raw_value)
            fields.append(f"<{key}:{len(value)}>{value}")
        lines.append(" ".join(fields) + " <EOR>")
    return "\n".join(lines) + "\n"


def create_snapshot(sources, station: str, *, all_modes=False, union_output=None, audit_output=None):
    records = {}
    counts = {}
    rejected = Counter()
    duplicates = 0
    provenance = {}
    raw_modes = {}
    raw_fields = {}
    canonical_ids = {}
    rejection_records = []
    seen_by_source = {}
    duplicate_rows_by_source = Counter()
    for name, values in sources:
        counts[name] = 0
        raw_modes[name] = Counter()
        seen_by_source[name] = set()
        for raw in values:
            counts[name] += 1
            raw_modes[name][str(raw.get("SUBMODE") or raw.get("MODE") or "UNKNOWN").upper()] += 1
            try:
                record = normalize(raw, station)
            except (ValueError, OverflowError) as exc:
                rejected[name] += 1
                rejection_records.append({"classification": "rejected", "reason": str(exc), "source": name, "raw": {key: str(value) for key, value in raw.items()}})
                continue
            if record is None:
                rejected[name] += 1
                rejection_records.append({"classification": "rejected", "reason": "station-callsign-mismatch", "source": name, "raw": {key: str(value) for key, value in raw.items()}})
                continue
            key = tuple(record.get(field, "") for field in ("STATION_CALLSIGN", "CALL", "QSO_DATE", "TIME_ON", "BAND", "MODE", "SUBMODE"))
            if key in seen_by_source[name]:
                duplicate_rows_by_source[name] += 1
            seen_by_source[name].add(key)
            if key in records:
                duplicates += 1
                if "postgres-wavelog-mirror" not in provenance.get(key, set()):
                    for field, value in record.items():
                        if not records[key].get(field):
                            records[key][field] = value
            else:
                records[key] = record
            provenance.setdefault(key, set()).add(name)
            if name != "postgres-wavelog-mirror" or key not in raw_fields:
                raw_fields[key] = {str(field).upper(): str(value) for field, value in raw.items() if value is not None}
            if name == "postgres-wavelog-mirror":
                canonical_ids.setdefault(key, []).append(record.get("_SOURCE_ID"))
    ordered = sorted(records.values(), key=lambda item: (item["QSO_DATE"], item["TIME_ON"], item["CALL"], item["BAND"], item["MODE"]))
    union_text = serialize_records(ordered)
    if union_output is not None:
        union_output.append(union_text)
    groups = {}
    for key, record in records.items():
        group = (record["CALL"], record["BAND"], record["MODE"], record.get("SUBMODE", ""))
        groups.setdefault(group, []).append((key, record))
    diagnostics = Counter()
    samples = []
    production = []
    audit = []
    base_index = {}
    base_mode_index = {}
    def basecall(call):
        return max(call.split("/"), key=len)
    for key, record in records.items():
        if "postgres-wavelog-mirror" in provenance[key]:
            base_index.setdefault((basecall(record["CALL"]), record["BAND"], record["MODE"]), []).append(record)
            base_mode_index.setdefault((basecall(record["CALL"]), record["MODE"]), []).append(record)
    def near_time(a, b):
        first = datetime.strptime(a["QSO_DATE"] + a["TIME_ON"], "%Y%m%d%H%M%S")
        second = datetime.strptime(b["QSO_DATE"] + b["TIME_ON"], "%Y%m%d%H%M%S")
        return abs((first - second).total_seconds()) <= 180
    def close(a, b):
        return near_time(a, b) and (not a.get("FREQ") or not b.get("FREQ") or abs(float(a["FREQ"]) - float(b["FREQ"])) <= .005000001)
    for entries in groups.values():
        canonical = [(key, row) for key, row in entries if "postgres-wavelog-mirror" in provenance[key]]
        supplementary = [(key, row) for key, row in entries if "postgres-wavelog-mirror" not in provenance[key]]
        production.extend(row for _, row in canonical)
        for key, row in canonical:
            diagnostics["exact_shared" if len(provenance[key]) > 1 else "wavelog_only"] += 1
            if len(provenance[key]) > 1:
                audit.append({"classification": "exact", "record": row, "matched_times": [row["QSO_DATE"] + row["TIME_ON"]], "matched_wavelog_primary_ids": canonical_ids[key]})
        for key, row in supplementary:
            matches = [candidate for _, candidate in canonical if close(row, candidate)]
            any_near = [candidate for _, candidate in canonical if near_time(row, candidate)]
            near_supplementary = [candidate for other, candidate in supplementary if other != key and near_time(row, candidate)]
            portable_matches = [candidate for candidate in base_index.get((basecall(row["CALL"]), row["BAND"], row["MODE"]), []) if candidate["CALL"] != row["CALL"] and near_time(row, candidate)]
            cross_band_or_portable = [candidate for candidate in base_mode_index.get((basecall(row["CALL"]), row["MODE"]), []) if (candidate["BAND"] != row["BAND"] or candidate["CALL"] != row["CALL"]) and near_time(row, candidate)]
            if len(matches) == 1:
                diagnostics["likely_duplicate"] += 1
                reason = "likely_duplicate"
            elif len(matches) > 1 or any_near or near_supplementary or portable_matches or cross_band_or_portable or row.get("_BAND_FREQUENCY_MISMATCH"):
                diagnostics["ambiguous"] += 1
                reason = "ambiguous"
            else:
                diagnostics["source_only_unambiguous"] += 1
                audit.append({"classification": "genuinely_absent", "record": row, "matched_times": []})
                continue
            forensic_matches = list({id(candidate): candidate for candidate in [*any_near, *cross_band_or_portable]}.values())
            audit.append({"classification": reason, "record": row, "matched_times": [candidate["QSO_DATE"] + candidate["TIME_ON"] for candidate in forensic_matches], "matched_wavelog_primary_ids": [candidate.get("_SOURCE_ID") for candidate in forensic_matches]})
            if len(samples) < 30:
                samples.append({"call": row["CALL"], "date": row["QSO_DATE"], "time": row["TIME_ON"], "band": row["BAND"], "mode": row["MODE"], "reason": reason, "candidate_times": [candidate["TIME_ON"] for candidate in matches]})
    production = [row for row in production if all_modes or row["MODE"] in {"FT8", "FT4"}]
    ordered = sorted(production, key=lambda item: (item["QSO_DATE"], item["TIME_ON"], item["CALL"], item["BAND"], item["MODE"]))
    text = serialize_records(ordered)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    canonical_mismatches = [
        {
            "wavelog_primary_ids": canonical_ids.get(key, []),
            "call": row["CALL"],
            "qso_date": row["QSO_DATE"],
            "time_on": row["TIME_ON"],
            "mode": row["MODE"],
            "stored_band": row["BAND"],
            "stored_frequency_mhz": row.get("FREQ"),
        }
        for key, row in records.items()
        if "postgres-wavelog-mirror" in provenance[key] and row.get("_BAND_FREQUENCY_MISMATCH")
    ]
    canonical_scope_mismatches = [
        mismatch for mismatch in canonical_mismatches
        if mismatch["mode"] in {"FT8", "FT4"}
    ]
    report = {"canonical_source": "wavelog_postgres", "station_callsign": station, "canonical_sha256": digest, "migration_eligible": not all_modes, "station": station, "sources": counts, "rejected_by_source": dict(rejected), "duplicates_merged": duplicates, "raw_union_records": len(records), "reconciliation": dict(diagnostics), "reconciliation_tolerance": {"seconds": 180, "frequency_hz": 5000, "crosses_utc_midnight": True}, "ambiguity_samples": samples, "production_policy": "Wavelog sole authority; WSJT inputs diagnostic only; FT8/FT4 only" if not all_modes else "Wavelog sole authority; WSJT inputs diagnostic only; all modes", "total_records": len(ordered), "by_mode": dict(sorted(Counter(row["MODE"] for row in ordered).items())), "by_band": dict(sorted(Counter(row["BAND"] for row in ordered).items())), "digital_records": sum(row["MODE"] in {"FT8", "FT4"} for row in ordered), "sha256": digest, "raw_union_sha256": hashlib.sha256(union_text.encode("utf-8")).hexdigest(), "canonical_band_frequency_mismatch_count": len(canonical_mismatches), "canonical_band_frequency_mismatches": canonical_mismatches, "migration_scope_band_frequency_mismatch_count": len(canonical_scope_mismatches), "migration_scope_band_frequency_mismatches": canonical_scope_mismatches}
    report["raw_source_modes"] = {name: dict(value) for name, value in raw_modes.items()}
    report["exact_identity_rows_merged"] = duplicates
    report["duplicate_rows_within_source"] = {name: duplicate_rows_by_source.get(name, 0) for name in counts}
    report["cross_source_shared_identities"] = diagnostics.get("exact_shared", 0)
    report["wavelog_unique_all_modes"] = len(canonical_ids)
    report["wavelog_duplicate_group_distribution"] = dict(Counter(len(ids) for ids in canonical_ids.values()))
    report["wavelog_duplicate_examples"] = [{"identity": list(key), "primary_ids": ids} for key, ids in canonical_ids.items() if len(ids) > 1][:20]
    report["exact_shared_by_mode"] = dict(Counter(records[key]["MODE"] for key in canonical_ids if len(provenance[key]) > 1))
    report["comparison_by_mode"] = {mode: dict(Counter(entry["classification"] for entry in audit if entry["record"]["MODE"] == mode)) for mode in sorted({entry["record"]["MODE"] for entry in audit})}
    mappings = Counter(str(entry["matched_wavelog_primary_ids"][0]) for entry in audit if entry["classification"] in {"exact", "likely_duplicate"} and entry.get("matched_wavelog_primary_ids") and entry["matched_wavelog_primary_ids"][0] is not None)
    report["mapping_cardinality"] = {"one_to_one_wavelog_identities": sum(count == 1 for count in mappings.values()), "many_to_one_wavelog_identities": sum(count > 1 for count in mappings.values()), "many_to_one_wsjt_records": sum(count for count in mappings.values() if count > 1)}
    report["count_denominators"] = "Source totals count all physical rows across all modes. Cross-source classes count unique normalized WSJT identities across all modes, not only FT8/FT4. Production counts only unique Wavelog FT8/FT4 identities. Near-time classifications are diagnostics, never merged into production."
    report["postgres_timestamp_semantics"] = "Wavelog sync copies UTC COL_TIME_ON without timezone; naive mirror timestamps are treated as UTC, aware timestamps converted to UTC"
    report["migration_eligible"] = not all_modes and not rejected.get("postgres-wavelog-mirror") and not canonical_scope_mismatches
    for entry in audit:
        row = entry["record"]
        key = tuple(row.get(field, "") for field in ("STATION_CALLSIGN", "CALL", "QSO_DATE", "TIME_ON", "BAND", "MODE", "SUBMODE"))
        entry["raw"] = raw_fields[key]
        entry["wavelog_primary_ids"] = canonical_ids.get(key, [])
        entry["reason"] = entry["classification"]
    audit.extend(rejection_records)
    if audit_output is not None:
        audit_output.extend(audit)
    return text, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres", action="store_true", help="Use canonical PostgreSQL Wavelog mirror first (read-only)")
    parser.add_argument("--adif", action="append", type=Path, default=[])
    parser.add_argument("--station")
    parser.add_argument("--station-id", type=int)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--all-modes", action="store_true")
    parser.add_argument("--union-output", type=Path, help="Separate raw union audit (never the production import)")
    parser.add_argument("--audit-dir", type=Path)
    parser.add_argument("--qualify-migration", action="store_true", help="Mark Wavelog-only snapshot eligible after count/dedupe review")
    args = parser.parse_args()
    from radio_control import config
    args.station = args.station or str(getattr(config, "MY_STATION"))
    if not args.postgres:
        parser.error("Production history requires --postgres; optional ADIF inputs are diagnostic only")
    sources = []
    if args.postgres:
        if args.station_id is None:
            from radio_control import config
            args.station_id = int(getattr(config, "WAVELOG_STATION_ID"))
        sources.append(("postgres-wavelog-mirror", postgres_records(args.station_id)))
    for source in args.adif:
        if source.resolve() == args.output.resolve():
            parser.error("Output must not overwrite a source log")
        sources.append((str(source.resolve()), parse_adif(source.read_text(encoding="utf-8-sig", errors="strict"))))
    union = []
    audit = []
    text, report = create_snapshot(sources, args.station.upper(), all_modes=args.all_modes, union_output=union, audit_output=audit)
    report["configured_station_id"] = args.station_id
    report["migration_eligible"] = bool(args.qualify_migration and report["migration_eligible"])
    report["qualification_review_required"] = not args.qualify_migration
    if not report["total_records"]:
        raise SystemExit("No valid records; existing output preserved")
    atomic_write_text(args.output, text, backup=True)
    atomic_write_json(args.output.with_suffix(args.output.suffix + ".report.json"), report)
    if args.union_output:
        if args.union_output.resolve() == args.output.resolve() or args.union_output.resolve() in [source.resolve() for source in args.adif]:
            raise SystemExit("Union output must be separate from production/source logs")
        atomic_write_text(args.union_output, union[0], backup=True)
        atomic_write_json(args.union_output.with_suffix(".report.json"), {"migration_eligible": False, "canonical_source": "diagnostic_raw_union", "sha256": report["raw_union_sha256"]})
    if args.adif:
        audit_dir = args.audit_dir or args.output.parent / "forensics"
        atomic_write_json(audit_dir / "record-comparison.json", {"migration_eligible": False, "thresholds": report["reconciliation_tolerance"], "records": audit})
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(["classification", "call", "qso_date", "time_on", "band", "mode", "frequency_mhz", "matched_times"])
        for entry in audit:
            if "record" not in entry:
                writer.writerow([entry["classification"], entry.get("raw", {}).get("CALL", ""), "", "", "", "", "", entry["reason"]])
                continue
            row = entry["record"]
            writer.writerow([entry["classification"], row["CALL"], row["QSO_DATE"], row["TIME_ON"], row["BAND"], row["MODE"], row.get("FREQ", ""), "|".join(entry["matched_times"])])
        atomic_write_text(audit_dir / "record-comparison.csv", stream.getvalue())
        candidate_entries = [entry for entry in audit if entry["classification"] == "genuinely_absent"]
        candidates = [entry["raw"] for entry in candidate_entries if entry["record"]["MODE"] in {"FT8", "FT4"}]
        candidate_text = serialize_original_records(candidates)
        atomic_write_text(audit_dir / "wavelog-review-candidates-not-for-mshv.adi", candidate_text)
        atomic_write_json(audit_dir / "wavelog-review-candidates-not-for-mshv.report.json", {"migration_eligible": False, "requires_user_review": True, "canonical_source": "wsjt_forensic_candidates", "records": len(candidates), "allowed_modes": ["FT4", "FT8"], "preserves_original_adif_fields": True, "sha256": hashlib.sha256(candidate_text.encode("utf-8")).hexdigest()})
        nondigital = [entry["raw"] for entry in candidate_entries if entry["record"]["MODE"] not in {"FT8", "FT4"}]
        nondigital_text = serialize_original_records(nondigital)
        atomic_write_text(audit_dir / "wavelog-nondigital-review-candidates-not-authorized.adi", nondigital_text)
        atomic_write_json(audit_dir / "wavelog-nondigital-review-candidates-not-authorized.report.json", {"migration_eligible": False, "authorized": False, "records": len(nondigital), "sha256": hashlib.sha256(nondigital_text.encode("utf-8")).hexdigest()})
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
