"""PostgreSQL-backed DX spot persistence."""

from __future__ import annotations

import csv
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional

from radio_control.postgres_store import connect, initialize_schema
from radio_control.spot_intelligence import enrich_spot_intelligence, extract_rbl_snr
from radio_control.spot_processor import (
    band_from_khz,
    classify_spot_source,
    clean_comment,
    extract_special,
    infer_mode,
)

logger = logging.getLogger(__name__)


def _epoch(value: Any) -> float:
    if not value:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.timestamp()
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.timestamp()
    except ValueError:
        return 0.0


class PostgresSpotsLogger:
    """PostgreSQL logger for DX cluster spots."""

    def __init__(self, *_args: Any, **_kwargs: Any):
        initialize_schema()

    def _execute_rows(self, query: str, params: list[Any] | tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchall()

    def log_spot(
        self,
        spot_data: Dict[str, Any],
        call_status: str = "Unknown",
        dxcc_status: str = "Unknown",
    ) -> bool:
        try:
            from radio_control.spots_logger import get_country_and_zone

            spotter = str(spot_data.get("spotter", "")).upper().strip()
            dxcall = str(spot_data.get("dxcall", "")).upper().strip()
            freq_khz = float(spot_data.get("freq_khz") or 0.0)
            comment = clean_comment(spot_data.get("comment", ""))
            received_at = spot_data.get("timestamp") or datetime.now(UTC)
            if not spotter or not dxcall or freq_khz <= 0:
                logger.warning("Invalid spot data: spotter=%s call=%s freq=%s", spotter, dxcall, freq_khz)
                return False
            if isinstance(received_at, str):
                received_at = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
            if received_at.tzinfo is None:
                received_at = received_at.replace(tzinfo=UTC)

            band = band_from_khz(freq_khz)
            mode = infer_mode(comment, band, freq_khz)
            spot_source = spot_data.get("spot_source")
            rbl_group = spot_data.get("rbl_mode_group")
            if not spot_source:
                spot_source, rbl_group = classify_spot_source(spotter, comment, mode)
            special_tags = extract_special(comment) or None
            country_info = get_country_and_zone(dxcall) or {}

            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO spots (
                            received_at, date_utc, time_utc,
                            frequency_khz, callsign, spotter, comment,
                            band, mode, spot_source, rbl_mode_group,
                            country, zone_cq, zone_itu, continent,
                            special_tags, call_status, dxcc_status
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            received_at,
                            received_at.date(),
                            received_at.time(),
                            freq_khz,
                            dxcall,
                            spotter,
                            comment,
                            band,
                            mode,
                            spot_source,
                            rbl_group,
                            country_info.get("country"),
                            country_info.get("cq_zone"),
                            country_info.get("itu_zone"),
                            country_info.get("continent"),
                            special_tags,
                            call_status,
                            dxcc_status,
                        ),
                    )
                conn.commit()
            return True
        except Exception:
            logger.error("Error logging PostgreSQL spot", exc_info=True)
            return False

    def get_spot_count(self, date_filter: Optional[str] = None) -> int:
        if date_filter:
            rows = self._execute_rows("SELECT COUNT(*) FROM spots WHERE date_utc = %s", [date_filter])
        else:
            rows = self._execute_rows("SELECT COUNT(*) FROM spots")
        return int(rows[0][0] or 0) if rows else 0

    def repair_spot_metadata(
        self,
        limit: Optional[int] = None,
        dry_run: bool = False,
        vacuum: bool = False,
    ) -> Dict[str, Any]:
        del vacuum
        query = """
            SELECT id, frequency_khz, callsign, spotter, comment
            FROM spots
            ORDER BY received_at DESC
        """
        params: list[Any] = []
        if limit and limit > 0:
            query += " LIMIT %s"
            params.append(limit)
        try:
            rows = self._execute_rows(query, params)
            updated = 0
            rbl_count = 0
            ft2_count = 0
            examples = []
            with connect() as conn:
                with conn.cursor() as cur:
                    for rowid, frequency_khz, callsign, spotter, comment in rows:
                        clean = clean_comment(comment or "")
                        band = band_from_khz(float(frequency_khz))
                        mode = infer_mode(clean, band, float(frequency_khz))
                        spot_source, rbl_group = classify_spot_source(spotter or "", clean, mode)
                        special_tags = extract_special(clean) or None
                        from radio_control.spots_logger import get_country_and_zone

                        country_info = get_country_and_zone(callsign or "") or {}
                        if spot_source == "rbl":
                            rbl_count += 1
                        if mode == "FT2":
                            ft2_count += 1
                        if len(examples) < 5:
                            examples.append(
                                {
                                    "callsign": callsign,
                                    "band": band,
                                    "mode": mode,
                                    "spot_source": spot_source,
                                    "rbl_mode_group": rbl_group,
                                }
                            )
                        if not dry_run:
                            cur.execute(
                                """
                                UPDATE spots
                                SET comment = %s, band = %s, mode = %s, spot_source = %s,
                                    rbl_mode_group = %s, special_tags = %s, country = %s,
                                    zone_cq = %s, zone_itu = %s, continent = %s
                                WHERE id = %s
                                """,
                                (
                                    clean,
                                    band,
                                    mode,
                                    spot_source,
                                    rbl_group,
                                    special_tags,
                                    country_info.get("country"),
                                    country_info.get("cq_zone"),
                                    country_info.get("itu_zone"),
                                    country_info.get("continent"),
                                    rowid,
                                ),
                            )
                            updated += 1
                conn.commit()
            return {
                "ok": True,
                "dry_run": dry_run,
                "scanned": len(rows),
                "updated": 0 if dry_run else updated,
                "rbl_rows": rbl_count,
                "ft2_rows": ft2_count,
                "examples": examples,
            }
        except Exception as exc:
            logger.error("Error repairing PostgreSQL spot metadata", exc_info=True)
            return {"ok": False, "error": str(exc), "dry_run": dry_run}

    def get_stats_by_band(self, date_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        where = "WHERE date_utc = %s" if date_filter else ""
        params = [date_filter] if date_filter else []
        rows = self._execute_rows(
            f"""
            SELECT band, COUNT(*), COUNT(DISTINCT callsign), COUNT(DISTINCT spotter),
                   COUNT(DISTINCT country), MIN(frequency_khz), MAX(frequency_khz)
            FROM spots
            {where}
            GROUP BY band
            ORDER BY band
            """,
            params,
        )
        columns = ["band", "total_spots", "unique_callsigns", "spotters", "countries", "min_freq", "max_freq"]
        return [dict(zip(columns, row)) for row in rows]

    def get_stats_by_mode(self, date_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        where = "WHERE date_utc = %s" if date_filter else ""
        params = [date_filter] if date_filter else []
        rows = self._execute_rows(
            f"""
            SELECT mode, COUNT(*), COUNT(DISTINCT callsign), COUNT(DISTINCT country)
            FROM spots
            {where}
            GROUP BY mode
            ORDER BY COUNT(*) DESC
            """,
            params,
        )
        columns = ["mode", "total_spots", "unique_callsigns", "countries"]
        return [dict(zip(columns, row)) for row in rows]

    def get_stats_by_country(self, limit: int = 20, date_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        if date_filter:
            where = "WHERE date_utc = %s"
            params: list[Any] = [date_filter, limit]
        else:
            where = "WHERE country IS NOT NULL"
            params = [limit]
        rows = self._execute_rows(
            f"""
            SELECT country, COUNT(*), COUNT(DISTINCT callsign), COUNT(DISTINCT band),
                   MIN(frequency_khz), MAX(frequency_khz)
            FROM spots
            {where}
            GROUP BY country
            ORDER BY COUNT(*) DESC
            LIMIT %s
            """,
            params,
        )
        columns = ["country", "total_spots", "unique_callsigns", "bands", "min_freq", "max_freq"]
        return [dict(zip(columns, row)) for row in rows]

    def get_recent_spots(self, limit: int = 100, before: str | None = None) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        where = "WHERE received_at < %s" if before else ""
        params: list[Any] = [before, limit] if before else [limit]
        rows = self._execute_rows(
            f"""
            SELECT received_at::text, date_utc::text, time_utc::text,
                   frequency_khz, band, mode, COALESCE(spot_source, 'cluster'),
                   COALESCE(rbl_mode_group, ''), callsign, spotter, country, zone_cq,
                   comment, special_tags
            FROM spots
            {where}
            ORDER BY received_at DESC
            LIMIT %s
            """,
            params,
        )
        columns = [
            "received_at",
            "date_utc",
            "time_utc",
            "frequency_khz",
            "band",
            "mode",
            "spot_source",
            "rbl_mode_group",
            "callsign",
            "spotter",
            "country",
            "cq",
            "comment",
            "special_tags",
        ]
        return [dict(zip(columns, row)) for row in rows]

    def get_spots_by_callsign(self, callsign: str, limit: int = 100) -> List[Dict[str, Any]]:
        rows = self._execute_rows(
            """
            SELECT received_at::text, date_utc::text, time_utc::text,
                   frequency_khz, band, mode, spotter, country, comment
            FROM spots
            WHERE upper(callsign) = upper(%s)
            ORDER BY received_at DESC
            LIMIT %s
            """,
            [callsign, limit],
        )
        columns = ["received_at", "date_utc", "time_utc", "frequency_khz", "band", "mode", "spotter", "country", "comment"]
        return [dict(zip(columns, row)) for row in rows]

    def get_special_event_spots(self, limit: int = 100) -> List[Dict[str, Any]]:
        rows = self._execute_rows(
            """
            SELECT received_at::text, date_utc::text, time_utc::text, frequency_khz,
                   band, mode, callsign, spotter, country, special_tags, comment
            FROM spots
            WHERE special_tags IS NOT NULL AND special_tags != ''
            ORDER BY received_at DESC
            LIMIT %s
            """,
            [limit],
        )
        columns = ["received_at", "date_utc", "time_utc", "frequency_khz", "band", "mode", "callsign", "spotter", "country", "special_tags", "comment"]
        return [dict(zip(columns, row)) for row in rows]

    def get_filtered_spots(
        self,
        limit: int = 100,
        callsign: Optional[str] = None,
        bands: Optional[List[str]] = None,
        modes: Optional[List[str]] = None,
        zones_cq: Optional[List[int]] = None,
        continents: Optional[List[str]] = None,
        special_tags_filter: Optional[List[str]] = None,
        spot_sources: Optional[List[str]] = None,
        rbl_mode_groups: Optional[List[str]] = None,
        rbl_min_snr: Optional[float] = None,
        rbl_dedupe_minutes: Optional[int] = None,
        max_age_minutes: Optional[int] = None,
        sort_by: str = "time",
    ) -> List[Dict[str, Any]]:
        where = []
        params: list[Any] = []
        if callsign:
            where.append("upper(callsign) LIKE %s")
            params.append(f"{callsign.upper()}%")
        if bands:
            where.append("band = ANY(%s)")
            params.append(list(bands))
        if modes:
            where.append("mode = ANY(%s)")
            params.append(list(modes))
        if spot_sources:
            where.append("COALESCE(spot_source, 'cluster') = ANY(%s)")
            params.append([str(source).lower() for source in spot_sources])
        if max_age_minutes and max_age_minutes > 0:
            where.append("received_at >= %s")
            params.append(datetime.now(UTC) - timedelta(minutes=max_age_minutes))
        if rbl_mode_groups:
            where.append("(COALESCE(spot_source, 'cluster') <> 'rbl' OR rbl_mode_group = ANY(%s))")
            params.append([str(group).upper() for group in rbl_mode_groups])
        if zones_cq:
            where.append("zone_cq = ANY(%s)")
            params.append([int(zone) for zone in zones_cq])
        if continents:
            where.append("continent = ANY(%s)")
            params.append(list(continents))
        if special_tags_filter:
            tag_clauses = []
            for tag in special_tags_filter:
                tag_clauses.append("special_tags ILIKE %s")
                params.append(f"%{tag}%")
            where.append("(" + " OR ".join(tag_clauses) + ")")

        query_limit = max(limit * 5, limit + 50) if rbl_min_snr is not None or rbl_dedupe_minutes or sort_by == "score" else limit
        where_sql = "WHERE " + " AND ".join(where) if where else ""
        rows = self._execute_rows(
            f"""
            SELECT EXTRACT(EPOCH FROM received_at), time_utc::text, frequency_khz / 1000.0,
                   frequency_khz::text, band, mode, COALESCE(spot_source, 'cluster'),
                   COALESCE(rbl_mode_group, ''), callsign, spotter, country, zone_cq, zone_itu,
                   continent, special_tags, comment, call_status, dxcc_status
            FROM spots
            {where_sql}
            ORDER BY received_at DESC
            LIMIT %s
            """,
            [*params, query_limit],
        )
        columns = [
            "timestamp",
            "time",
            "frequency_mhz",
            "frequency",
            "band",
            "mode",
            "spot_source",
            "rbl_mode_group",
            "callsign",
            "spotter",
            "country",
            "cq",
            "zone_itu",
            "continent",
            "special_tags",
            "comment",
            "call_status",
            "dxcc_status",
        ]
        spots = []
        for row in rows:
            spot = dict(zip(columns, row))
            spot["tag"] = None
            spot["special"] = spot.get("special_tags", "")
            spot["spotter_continent"] = spot.get("continent", "")
            spot["call_status"] = spot.get("call_status") or "-"
            spot["dxcc_status"] = spot.get("dxcc_status") or "-"
            enrich_spot_intelligence(spot)
            spots.append(spot)

        if rbl_min_snr is not None:
            spots = [
                spot
                for spot in spots
                if spot.get("spot_source") != "rbl"
                or (
                    (spot.get("rbl_snr") if spot.get("rbl_snr") is not None else extract_rbl_snr(spot.get("comment")))
                    is not None
                    and float(
                        spot.get("rbl_snr")
                        if spot.get("rbl_snr") is not None
                        else extract_rbl_snr(spot.get("comment"))
                    )
                    >= float(rbl_min_snr)
                )
            ]
        if rbl_dedupe_minutes and rbl_dedupe_minutes > 0:
            deduped = []
            latest_by_key: dict[tuple[Any, Any, Any], float] = {}
            window_seconds = rbl_dedupe_minutes * 60
            for spot in spots:
                if spot.get("spot_source") != "rbl":
                    deduped.append(spot)
                    continue
                key = (spot.get("callsign"), spot.get("band"), spot.get("mode"))
                timestamp = float(spot.get("timestamp") or 0)
                previous = latest_by_key.get(key)
                if previous is not None and abs(previous - timestamp) <= window_seconds:
                    continue
                latest_by_key[key] = timestamp
                deduped.append(spot)
            spots = deduped
        if sort_by == "score":
            spots.sort(key=lambda spot: (spot.get("spot_score", 0), spot.get("timestamp", 0)), reverse=True)
        return spots[:limit]

    def get_source_stats(self, windows_minutes: Optional[List[int]] = None) -> Dict[str, Any]:
        windows = windows_minutes or [5, 15, 60]
        try:
            total = self._execute_rows(
                """
                SELECT COUNT(*),
                       SUM(CASE WHEN COALESCE(spot_source, 'cluster') = 'cluster' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN COALESCE(spot_source, 'cluster') = 'rbl' THEN 1 ELSE 0 END),
                       EXTRACT(EPOCH FROM MAX(received_at)),
                       EXTRACT(EPOCH FROM MAX(CASE WHEN COALESCE(spot_source, 'cluster') = 'cluster' THEN received_at ELSE NULL END)),
                       EXTRACT(EPOCH FROM MAX(CASE WHEN COALESCE(spot_source, 'cluster') = 'rbl' THEN received_at ELSE NULL END))
                FROM spots
                """
            )[0]
            all_time = {
                "total": int(total[0] or 0),
                "cluster": int(total[1] or 0),
                "rbl": int(total[2] or 0),
                "other": 0,
                "last_any": float(total[3] or 0),
                "last_cluster": float(total[4] or 0),
                "last_rbl": float(total[5] or 0),
            }
            all_time["other"] = max(0, all_time["total"] - all_time["cluster"] - all_time["rbl"])

            window_stats = []
            for minutes in windows:
                cutoff = datetime.now(UTC) - timedelta(minutes=minutes)
                rows = self._execute_rows(
                    """
                    SELECT lower(COALESCE(spot_source, 'cluster')),
                           upper(COALESCE(rbl_mode_group, '')),
                           upper(COALESCE(mode, '')),
                           COUNT(*),
                           EXTRACT(EPOCH FROM MAX(received_at))
                    FROM spots
                    WHERE received_at >= %s
                    GROUP BY 1, 2, 3
                    """,
                    [cutoff],
                )
                stats = {
                    "minutes": minutes,
                    "label": f"{minutes}m" if minutes < 60 else f"{minutes // 60}h",
                    "total": 0,
                    "cluster": 0,
                    "rbl": 0,
                    "other": 0,
                    "modes": {},
                    "rbl_modes": {},
                    "last_any": 0,
                    "last_cluster": 0,
                    "last_rbl": 0,
                }
                for source, rbl_group, mode, count, last_seen in rows:
                    count_int = int(count or 0)
                    last_seen_float = float(last_seen or 0)
                    stats["total"] += count_int
                    stats["last_any"] = max(stats["last_any"], last_seen_float)
                    stats["modes"][mode or "UNKNOWN"] = stats["modes"].get(mode or "UNKNOWN", 0) + count_int
                    if source == "cluster":
                        stats["cluster"] += count_int
                        stats["last_cluster"] = max(stats["last_cluster"], last_seen_float)
                    elif source == "rbl":
                        stats["rbl"] += count_int
                        stats["last_rbl"] = max(stats["last_rbl"], last_seen_float)
                        group = rbl_group or "OTHER"
                        stats["rbl_modes"][group] = stats["rbl_modes"].get(group, 0) + count_int
                    else:
                        stats["other"] += count_int
                window_stats.append(stats)
            return {"ok": True, "all_time": all_time, "windows": window_stats}
        except Exception as exc:
            logger.error("Error getting PostgreSQL source stats", exc_info=True)
            return {"ok": False, "error": str(exc), "all_time": {}, "windows": []}

    def export_csv(self, output_path: str, date_filter: Optional[str] = None):
        where = "WHERE date_utc = %s" if date_filter else ""
        params = [date_filter] if date_filter else []
        rows = self._execute_rows(
            f"""
            SELECT received_at, date_utc, time_utc, frequency_khz, band, mode,
                   callsign, spotter, country, zone_cq, zone_itu, continent, special_tags, comment
            FROM spots
            {where}
            ORDER BY received_at DESC
            """,
            params,
        )
        with open(output_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "received_at",
                    "date_utc",
                    "time_utc",
                    "frequency_khz",
                    "band",
                    "mode",
                    "callsign",
                    "spotter",
                    "country",
                    "zone_cq",
                    "zone_itu",
                    "continent",
                    "special_tags",
                    "comment",
                ]
            )
            writer.writerows(rows)
        return len(rows)

    def close(self) -> None:
        return None

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        self.close()
