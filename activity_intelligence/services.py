"""Activity Intelligence orchestration and spot enrichment."""

from __future__ import annotations

import asyncio
import logging
import math
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import httpx

from radio_control import config
from radio_control.activity_references import extract_activity_references
from radio_control.postgres_store import connect as connect_postgres
from radio_control.postgres_store import should_use_postgres
from radio_control.rotor_math import bearing_from_coordinates, grid_to_latlon
from radio_control.spot_intelligence import score_spot as base_score_spot

from .adapters import adapter_from_settings, iso_utc, parse_datetime, parse_rbn_line, stable_id
from .models import ActivityTag, PropagationAssessment, SourceSyncState, SpotAction, StationStateSample, compact_dict
from .repository import ActivityRepository
from .settings import get_settings

logger = logging.getLogger(__name__)


def _parse_iso(value: str | None) -> datetime | None:
    return parse_datetime(value)


def _normalize_call(value: Any) -> str:
    return "".join(ch for ch in str(value or "").upper().strip() if ch.isalnum() or ch == "/")


def _spot_frequency_khz(spot: dict[str, Any]) -> float:
    if spot.get("frequency_mhz") is not None:
        try:
            return float(spot["frequency_mhz"]) * 1000.0
        except (TypeError, ValueError):
            pass
    try:
        return float(spot.get("frequency") or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_comment_refs(text: str) -> list[str]:
    refs: list[str] = []
    for pattern in (
        r"\b[A-Z]{1,3}-\d{3,5}\b",
        r"\b[A-Z0-9]{1,3}/[A-Z]{1,3}-\d{3}\b",
        r"\b[A-Z0-9]{1,4}FF-\d{3,5}\b",
    ):
        refs.extend(match.group(0).upper() for match in re.finditer(pattern, text or "", re.IGNORECASE))
    return list(dict.fromkeys(refs))


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class ActivityIntelligenceService:
    """Coordinates source sync, matching, scoring, and dashboards."""

    def __init__(self, repository: ActivityRepository | None = None, qso_db_path: str | Path | None = None):
        self.settings = get_settings()
        self.repository = repository or ActivityRepository()
        self._explicit_qso_db_path = qso_db_path is not None
        self.qso_db_path = Path(qso_db_path) if qso_db_path else config.DATA_DIR / "qso_log.duckdb"
        self.adapters = adapter_from_settings(self.settings)
        self._sync_lock = asyncio.Lock()
        self._settings_signature = repr(self.settings)
        self._selected_contest_id: str | None = None

    def reload_settings(self) -> None:
        settings = get_settings()
        signature = repr(settings)
        if signature != self._settings_signature:
            self.settings = settings
            self.adapters = adapter_from_settings(self.settings)
            self._settings_signature = signature

    async def refresh_due_sources(self, force: bool = False) -> dict[str, Any]:
        self.reload_settings()
        if not self.settings.get("enabled", True):
            return {"ok": True, "disabled": True, "sources": []}
        async with self._sync_lock:
            results = []
            timeout = httpx.Timeout(15.0, connect=5.0)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                for adapter in self.adapters:
                    if not adapter.enabled():
                        continue
                    state = self.repository.get_source_state(adapter.source_id)
                    if not force and state.next_allowed_at_utc:
                        next_allowed = _parse_iso(state.next_allowed_at_utc)
                        if next_allowed and next_allowed > datetime.now(UTC):
                            results.append({"sourceId": adapter.source_id, "skipped": True, "nextAllowedAtUtc": state.next_allowed_at_utc})
                            continue
                    result = await self._refresh_adapter(client, adapter, state)
                    results.append(result)
            try:
                self.repository.prune_raw_payloads(int(self.settings.get("keepRawPayloadsDays", 14)))
                self.repository.prune_operational_history(int(self.settings.get("keepOperationalHistoryDays", 30)))
            except Exception:
                logger.debug("Activity history pruning failed", exc_info=True)
            return {"ok": True, "sources": results}

    async def _refresh_adapter(self, client: httpx.AsyncClient, adapter: Any, state: SourceSyncState) -> dict[str, Any]:
        state.last_attempt_at_utc = iso_utc()
        try:
            raw = await adapter.fetch_raw(client, state.etag, state.last_modified)
            state.last_http_status = raw.http_status
            state.etag = raw.etag or state.etag
            state.last_modified = raw.last_modified or state.last_modified
            if raw.http_status == 304:
                state.last_success_at_utc = raw.fetched_at_utc
                state.last_error = None
                state.consecutive_failures = 0
                state.next_allowed_at_utc = iso_utc(datetime.now(UTC) + timedelta(seconds=adapter.get_recommended_poll_interval_seconds()))
                self.repository.upsert_source_state(state)
                return {"sourceId": adapter.source_id, "ok": True, "notModified": True}
            if raw.http_status and raw.http_status >= 400:
                raise RuntimeError(f"HTTP {raw.http_status}")
            parsed = adapter.parse(raw)
            state.last_success_at_utc = raw.fetched_at_utc
            state.last_error = None
            state.consecutive_failures = 0
            state.next_allowed_at_utc = iso_utc(datetime.now(UTC) + timedelta(seconds=adapter.get_recommended_poll_interval_seconds()))
            with self.repository.transaction():
                self.repository.store_raw_payload(adapter.source_id, raw.content_type, raw.body, raw.fetched_at_utc)
                self.repository.delete_current_source_records(adapter.source_id)
                self.repository.upsert_dxpeditions(parsed.get("dxpeditions", []))
                self.repository.upsert_contests(parsed.get("contests", []))
                self.repository.upsert_portable_activations(parsed.get("portable_activations", []))
                self.repository.upsert_portable_references(parsed.get("portable_references", []))
                self.repository.upsert_space_weather(parsed.get("space_weather", []))
                self.repository.upsert_source_state(state)
            return {
                "sourceId": adapter.source_id,
                "ok": True,
                "counts": {key: len(value) for key, value in parsed.items()},
                "nextAllowedAtUtc": state.next_allowed_at_utc,
            }
        except Exception as exc:
            state.consecutive_failures += 1
            state.last_error = str(exc)
            backoff_minutes = [0, 5, 15, 60][min(state.consecutive_failures - 1, 3)]
            normal_seconds = adapter.get_recommended_poll_interval_seconds()
            state.next_allowed_at_utc = iso_utc(datetime.now(UTC) + timedelta(seconds=normal_seconds, minutes=backoff_minutes))
            self.repository.upsert_source_state(state)
            logger.warning("Activity source %s failed: %s", adapter.source_id, exc)
            return {"sourceId": adapter.source_id, "ok": False, "error": str(exc), "nextAllowedAtUtc": state.next_allowed_at_utc}

    def ingest_rbn_from_spot(self, spot: dict[str, Any]) -> None:
        self.reload_settings()
        rbn_settings = self.settings.get("rbn", {})
        if not rbn_settings.get("enabled", True) or not rbn_settings.get("ingestFromExistingCluster", True):
            return
        if (spot.get("spot_source") or "cluster") != "rbl":
            return
        own_calls = {_normalize_call(call) for call in rbn_settings.get("stationCalls") or [] if _normalize_call(call)}
        call = _normalize_call(spot.get("callsign"))
        if rbn_settings.get("ownCallOnlyProcessing", True) and call not in own_calls:
            return
        raw_line = f"DX de {spot.get('spotter') or 'RBN'}: {_spot_frequency_khz(spot):.1f} {call} {spot.get('comment') or ''}"
        timestamp = None
        if spot.get("timestamp"):
            try:
                timestamp = datetime.fromtimestamp(float(spot["timestamp"]), UTC)
            except (TypeError, ValueError, OSError):
                timestamp = None
        parsed = parse_rbn_line(raw_line, timestamp=timestamp)
        if parsed:
            parsed.id = stable_id(parsed.raw_line, parsed.timestamp_utc, spot.get("aggregate_count") or "")
            skimmer_lat = _parse_float(
                spot.get("spotter_latitude")
                or spot.get("skimmer_lat")
                or spot.get("skimmer_latitude")
                or spot.get("latitude_spotter")
            )
            skimmer_lon = _parse_float(
                spot.get("spotter_longitude")
                or spot.get("skimmer_lon")
                or spot.get("skimmer_longitude")
                or spot.get("longitude_spotter")
            )
            if skimmer_lat is not None and skimmer_lon is not None:
                parsed.skimmer_lat = skimmer_lat
                parsed.skimmer_lon = skimmer_lon
                home_lat = float(getattr(config, "ROTOR_HOME_LAT", 48.17))
                home_lon = float(getattr(config, "ROTOR_HOME_LON", 17.08))
                parsed.bearing_from_station_deg = bearing_from_coordinates(home_lat, home_lon, skimmer_lat, skimmer_lon)
                parsed.distance_km = _distance_km(home_lat, home_lon, skimmer_lat, skimmer_lon)
            try:
                self._store_station_state_sample(spot, parsed.timestamp_utc)
                self.repository.upsert_rbn_spot(parsed)
            except Exception:
                logger.debug("Could not store RBN spot", exc_info=True)

    def _store_station_state_sample(self, spot: dict[str, Any], timestamp_utc: str | None = None) -> None:
        timestamp_utc = timestamp_utc or iso_utc()
        frequency_khz = _spot_frequency_khz(spot) or None
        mode = str(spot.get("mode") or spot.get("rbl_mode_group") or "").upper() or None
        bearing = _parse_float(
            spot.get("rotatorBearingDeg")
            or spot.get("rotator_bearing_deg")
            or spot.get("current_bearing")
            or spot.get("bearing")
        )
        antenna_name = spot.get("antennaName") or spot.get("antenna_name") or spot.get("antenna")
        power_watts = _parse_float(spot.get("powerWatts") or spot.get("power_watts") or spot.get("rfpower"))
        tx_state_raw = spot.get("txState", spot.get("tx_state"))
        tx_state = bool(tx_state_raw) if tx_state_raw is not None else None
        if frequency_khz is None and mode is None and bearing is None and antenna_name is None and power_watts is None:
            return
        self.repository.upsert_station_state_sample(
            StationStateSample(
                id=stable_id("STATION_STATE", timestamp_utc, frequency_khz, mode, bearing, antenna_name, power_watts, tx_state),
                timestamp_utc=timestamp_utc,
                frequency_khz=frequency_khz,
                mode=mode,
                rotator_bearing_deg=bearing,
                antenna_name=str(antenna_name) if antenna_name else None,
                power_watts=power_watts,
                tx_state=tx_state,
            )
        )

    def enrich_spot(self, spot: dict[str, Any]) -> dict[str, Any]:
        self.reload_settings()
        if not self.settings.get("enabled", True) or not self.settings.get("enrichExistingSpots", True):
            return spot
        call = _normalize_call(spot.get("callsign"))
        if not call:
            return spot

        self.ingest_rbn_from_spot(spot)
        tags: list[ActivityTag] = []
        actions: list[SpotAction] = []
        reasons: list[str] = list(spot.get("spot_score_reasons") or [])
        base_score = int(spot.get("spot_score") or 0)
        if not base_score:
            base_score, reasons = base_score_spot(spot)

        weights = self.settings.get("spotPriority", {})
        ai_score = int(weights.get("base", 20))

        dx_match = self.repository.find_dxpedition_by_call(call)
        if dx_match:
            label = f"DX {dx_match.get('callsign')}"
            if dx_match.get("dxcc_entity"):
                label = f"{label} {dx_match.get('dxcc_entity')}"
            tags.append(ActivityTag("DXPEDITION", label, 0.9, dx_match.get("source_id", "DX"), dx_match.get("id")))
            ai_score += int(weights.get("dxpeditionActive", 30) if dx_match.get("status") == "ACTIVE" else weights.get("dxpeditionUpcomingWithin24h", 10))
            reasons.append("DXpedition")
            actions.append(SpotAction("open-dxpedition", "Open DXpedition details", "OPEN_DETAILS", {"id": dx_match.get("id"), "type": "dxpedition"}))

        portable_matches = self.repository.find_portable_by_call_or_ref(call, " ".join(_extract_comment_refs(spot.get("comment") or "")))
        seen_refs: set[str] = set()
        reference_statuses: dict[tuple[str, str], dict[str, Any]] = {}
        for portable in portable_matches[:3]:
            for ref in portable.get("references") or []:
                if ref in seen_refs:
                    continue
                seen_refs.add(ref)
                program = self._portable_program_for_ref(portable.get("program", "POTA"), ref)
                tag_type = {
                    "POTA": "POTA_ACTIVE",
                    "SOTA": "SOTA_ACTIVE" if portable.get("type") == "ACTIVE_SPOT" else "SOTA_ALERT",
                    "WWFF": "WWFF_ACTIVE" if portable.get("type") == "ACTIVE_SPOT" else "WWFF_AGENDA",
                }.get(program, "POTA_ACTIVE")
                tags.append(ActivityTag(tag_type, f"{program} {ref}", 0.82, portable.get("source_id", program), ref))
                ai_score += int(weights.get("portableActive", 20))
                reasons.append(f"{program} {ref}")
                ref_status = self.portable_reference_status(program, ref, callsign=call)
                reference_statuses[(program, str(ref).upper())] = ref_status
                if ref_status.get("worked"):
                    tags.append(ActivityTag("DUPLICATE", f"Worked {ref}", 0.88, "WAVELOG", ref))
                    reasons.append(f"worked {program} ref")
                else:
                    tags.append(ActivityTag("NEW_REFERENCE", f"New {ref}", 0.8, "WAVELOG", ref))
                    ai_score += int(weights.get("newPortableReference", 25))
                    reasons.append(f"new {program} ref")
                actions.append(
                    SpotAction(
                        f"fill-{program.lower()}-{ref}",
                        f"Fill {program} {ref}",
                        "FILL_LOG_FIELDS",
                        self._portable_fill_payload(program, ref),
                    )
                )

        propagation = self.assess_propagation(spot)
        if propagation:
            spot["propagation"] = compact_dict(propagation)
            tag_type = {
                "EXCELLENT": "PROPAGATION_GOOD",
                "GOOD": "PROPAGATION_GOOD",
                "FAIR": "PROPAGATION_MARGINAL",
                "MARGINAL": "PROPAGATION_MARGINAL",
                "POOR": "PROPAGATION_POOR",
            }.get(propagation.label, "PROPAGATION_MARGINAL")
            tags.append(ActivityTag(tag_type, f"PROP {propagation.label}", propagation.confidence, "NOAA_SWPC"))
            ai_score += int(weights.get(f"propagation{propagation.label.title()}", 0))
            reasons.extend(propagation.reasons[:2])

        if spot.get("dxcc_status") == "ATNO":
            ai_score += int(weights.get("neededAtno", 40))
        elif "Band+Mode" in str(spot.get("dxcc_status") or spot.get("tag") or ""):
            ai_score += int(weights.get("neededBandSlot", 25))
        if str(spot.get("call_status") or "").startswith("Worked") or str(spot.get("dxcc_status") or "").startswith("Worked"):
            tags.append(ActivityTag("WORKED_BEFORE", "Worked before", 0.9, "WAVELOG"))
        if spot.get("aggregate_count", 1) and int(spot.get("aggregate_count") or 1) > 1:
            ai_score += int(weights.get("duplicate", -35))
            tags.append(ActivityTag("DUPLICATE", f"Seen x{spot.get('aggregate_count')}", 0.8, "CLUSTER"))

        self._add_bearing_fields(spot, actions)

        priority = max(0, min(100, max(base_score, ai_score)))
        spot["activity_tags"] = [compact_dict(tag) for tag in tags]
        references = extract_activity_references(spot)
        for reference in references:
            program = str(reference.get("type") or "").upper()
            ref_id = str(reference.get("reference_id") or "").upper()
            status = reference_statuses.get((program, ref_id))
            if status is None:
                status = self.portable_reference_status(program, ref_id, callsign=call)
            if status.get("worked"):
                reference["status"] = "worked"
                reference.pop("need_reason", None)
            else:
                reference["status"] = "needed"
                reference["need_reason"] = program.lower()
        spot["reference_items"] = references
        spot["priority_score"] = priority
        spot["spot_score"] = priority
        spot["spot_score_reasons"] = list(dict.fromkeys([str(reason) for reason in reasons if reason]))[:5]
        spot["recommended_actions"] = [compact_dict(action) for action in actions]
        return spot

    def _portable_program_for_ref(self, program: str, reference: str) -> str:
        program = str(program or "").upper()
        reference = str(reference or "").upper()
        if program != "PARKSNPEAKS":
            return program
        if "/" in reference and re.search(r"/[A-Z]{1,3}-\d{3}$", reference):
            return "SOTA"
        if "FF-" in reference:
            return "WWFF"
        if re.match(r"^[A-Z]{1,3}-\d{3,5}$", reference):
            return "POTA"
        return program

    def assess_propagation(self, spot: dict[str, Any]) -> PropagationAssessment | None:
        if not self.settings.get("propagation", {}).get("enabled", True):
            return None
        snapshot = self.repository.latest_space_weather()
        if not snapshot:
            return PropagationAssessment(score=50, label="UNKNOWN", confidence=0.2, reasons=["No current SWPC snapshot"])
        kp = snapshot.get("kp")
        freq_khz = _spot_frequency_khz(spot)
        score = 70
        reasons: list[str] = []
        if isinstance(kp, (int, float)):
            reasons.append(f"Kp {kp:g}")
            if kp <= 2:
                score += 12
            elif kp <= 4:
                score += 0
            elif kp <= 6:
                score -= 20
            else:
                score -= 35
        band = spot.get("band")
        freq_mhz = freq_khz / 1000.0 if freq_khz else 0.0
        hour = datetime.now(UTC).hour
        path_type = "UNKNOWN"
        daylight_path = False
        target_lat = spot.get("latitude")
        target_lon = spot.get("longitude")
        if (target_lat is None or target_lon is None) and spot.get("gridsquare"):
            try:
                target_lat, target_lon = grid_to_latlon(str(spot["gridsquare"]))
            except Exception:
                target_lat, target_lon = None, None
        if target_lat is not None and target_lon is not None:
            try:
                daylight = self._path_daylight_assessment(float(target_lat), float(target_lon))
                daylight_path = bool(daylight.get("sunlit"))
                if daylight["grayline"]:
                    score += 10
                    reasons.append("grayline path")
                    path_type = "GRAYLINE"
                elif daylight["polar"]:
                    reasons.append("polar path")
                    path_type = "POLAR"
                    if isinstance(kp, (int, float)) and kp >= 4:
                        score -= 12
                        reasons.append("disturbed polar path")
            except Exception:
                logger.debug("Propagation path daylight assessment failed", exc_info=True)
        if band in {"10m", "12m", "15m"} and 7 <= hour <= 18:
            score += 8
            reasons.append("daylight high-band window")
        if band in {"80m", "160m", "40m"} and not (16 <= hour or hour <= 7):
            score -= 10
            reasons.append("low band daylight")
        if freq_khz >= 28000 and isinstance(kp, (int, float)) and kp >= 5:
            score -= 8
            reasons.append("disturbed high-band path")
        xray_class = str(snapshot.get("xray_class") or "").upper()
        xray_penalty = self._xray_penalty(xray_class)
        if xray_penalty:
            penalty = xray_penalty + (8 if daylight_path and freq_mhz >= 10 else 0)
            score -= penalty
            reasons.append(f"{xray_class} X-ray flux")
        drap_freq = _parse_float(snapshot.get("drap_affected_frequency_mhz"))
        if drap_freq and freq_mhz and drap_freq >= freq_mhz:
            score -= 28 if daylight_path else 16
            reasons.append(f"D-RAP affected to {drap_freq:g} MHz")
        wind_speed = _parse_float(snapshot.get("solar_wind_speed_kms"))
        bz = _parse_float(snapshot.get("solar_wind_bz_nt"))
        if wind_speed and wind_speed >= 650:
            score -= 8
            reasons.append(f"solar wind {wind_speed:g} km/s")
        if bz is not None and bz <= -8:
            score -= 10
            reasons.append(f"Bz {bz:g} nT")
        solar_flux = _parse_float(snapshot.get("solar_flux_sfu"))
        if solar_flux:
            if band in {"10m", "12m", "15m"} and solar_flux >= 150:
                score += 10
                reasons.append(f"SFI {solar_flux:g}")
            elif band in {"10m", "12m"} and solar_flux < 90:
                score -= 8
                reasons.append(f"low SFI {solar_flux:g}")
        if self.settings.get("propagation", {}).get("useRbnEvidence", True) and band:
            evidence = self._rbn_band_evidence(str(band))
            if evidence:
                score += min(12, 4 + evidence * 2)
                reasons.append(f"RBN own-call evidence on {band}")
        score = max(0, min(100, score))
        if score >= 85:
            label = "EXCELLENT"
        elif score >= 70:
            label = "GOOD"
        elif score >= 52:
            label = "FAIR"
        elif score >= 35:
            label = "MARGINAL"
        else:
            label = "POOR"
        return PropagationAssessment(
            score=score,
            label=label,
            confidence=0.7 if path_type != "UNKNOWN" else (0.62 if reasons else 0.25),
            reasons=reasons or ["Heuristic band/time score"],
            path_type=path_type,
        )

    def _xray_penalty(self, xray_class: str) -> int:
        if not xray_class:
            return 0
        letter = xray_class[0]
        try:
            level = float(xray_class[1:] or "1")
        except ValueError:
            level = 1
        if letter == "X":
            return 35 + min(15, int(level * 3))
        if letter == "M":
            return 18 + min(12, int(level * 2))
        if letter == "C" and level >= 5:
            return 6
        return 0

    def _rbn_band_evidence(self, band: str) -> int:
        station_calls = [_normalize_call(call) for call in self.settings.get("rbn", {}).get("stationCalls") or []]
        try:
            return self.repository.rbn_band_report_count(station_calls, band, minutes=30)
        except Exception:
            logger.debug("RBN propagation evidence lookup failed", exc_info=True)
            return 0

    def _path_daylight_assessment(self, target_lat: float, target_lon: float) -> dict[str, bool]:
        now = datetime.now(UTC)
        home_lat = float(getattr(config, "ROTOR_HOME_LAT", 48.17))
        home_lon = float(getattr(config, "ROTOR_HOME_LON", 17.08))
        home_alt = self._solar_altitude_deg(now, home_lat, home_lon)
        target_alt = self._solar_altitude_deg(now, target_lat, target_lon)
        grayline = abs(home_alt) <= 8 or abs(target_alt) <= 8
        polar = max(abs(home_lat), abs(target_lat)) >= 60
        sunlit = home_alt > 0 or target_alt > 0
        return {"grayline": grayline, "polar": polar, "sunlit": sunlit}

    def _solar_altitude_deg(self, when: datetime, lat: float, lon: float) -> float:
        day = when.timetuple().tm_yday
        hour = when.hour + when.minute / 60 + when.second / 3600
        gamma = 2.0 * 3.141592653589793 / 365.0 * (day - 1 + (hour - 12) / 24)
        decl = (
            0.006918
            - 0.399912 * math.cos(gamma)
            + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma)
            + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma)
            + 0.00148 * math.sin(3 * gamma)
        )
        eqtime = 229.18 * (
            0.000075
            + 0.001868 * math.cos(gamma)
            - 0.032077 * math.sin(gamma)
            - 0.014615 * math.cos(2 * gamma)
            - 0.040849 * math.sin(2 * gamma)
        )
        minutes = when.hour * 60 + when.minute + when.second / 60
        true_solar_time = (minutes + eqtime + 4 * lon) % 1440
        hour_angle = true_solar_time / 4 - 180
        lat_rad = math.radians(lat)
        ha_rad = math.radians(hour_angle)
        altitude_arg = (
            math.sin(lat_rad) * math.sin(decl)
            + math.cos(lat_rad) * math.cos(decl) * math.cos(ha_rad)
        )
        altitude = math.asin(max(-1.0, min(1.0, altitude_arg)))
        return math.degrees(altitude)

    def _add_bearing_fields(self, spot: dict[str, Any], actions: list[SpotAction]) -> None:
        try:
            home_lat = float(getattr(config, "ROTOR_HOME_LAT", 48.17))
            home_lon = float(getattr(config, "ROTOR_HOME_LON", 17.08))
            target_lat = spot.get("latitude")
            target_lon = spot.get("longitude")
            if (target_lat is None or target_lon is None) and spot.get("gridsquare"):
                target_lat, target_lon = grid_to_latlon(str(spot["gridsquare"]))
            if target_lat is None or target_lon is None:
                return
            bearing = bearing_from_coordinates(home_lat, home_lon, float(target_lat), float(target_lon))
            long_path = (bearing + 180.0) % 360.0
            spot["bearingShortPathDeg"] = round(bearing)
            spot["bearingLongPathDeg"] = round(long_path)
            actions.append(SpotAction("beam-sp", f"Beam {round(bearing):03d} SP", "BEAM", {"bearing": round(bearing), "path": "SHORT_PATH"}))
            actions.append(SpotAction("beam-lp", f"Beam {round(long_path):03d} LP", "BEAM", {"bearing": round(long_path), "path": "LONG_PATH"}))
        except Exception:
            logger.debug("Could not add activity bearing fields", exc_info=True)

    def dashboard(self) -> dict[str, Any]:
        self.reload_settings()
        station_calls = self.settings.get("rbn", {}).get("stationCalls") or []
        return {
            "ok": True,
            "settings": {
                "enabled": self.settings.get("enabled", True),
                "showPriorityScore": self.settings.get("showPriorityScore", True),
                "autoSortByPriority": self.settings.get("autoSortByPriority", False),
                "stationCalls": station_calls,
            },
            "sourceStatus": self.repository.list_source_states(),
            "sourceCatalog": self.source_catalog(),
            "dxpeditions": self.repository.active_dxpeditions(limit=80),
            "contests": self.repository.upcoming_contests(limit=80),
            "contestContext": self.contest_context(),
            "portableActivations": self.repository.portable_activations(limit=150),
            "spaceWeather": self.repository.latest_space_weather(),
            "rbn": self.rbn_summary(station_calls),
        }

    def source_catalog(self) -> list[dict[str, Any]]:
        self.reload_settings()
        return [
            {
                "sourceId": adapter.source_id,
                "url": getattr(adapter, "url", ""),
                "pollSeconds": adapter.get_recommended_poll_interval_seconds(),
                "enabled": adapter.enabled(),
                "label": self._source_label(adapter.source_id),
            }
            for adapter in self.adapters
        ]

    def _source_label(self, source_id: str) -> str:
        labels = {
            "NG3K_ADXO": "NG3K ADXO",
            "DXCAL_ICS": "DXCAL iCal",
            "WA7BNM_RSS": "WA7BNM Contest Calendar",
            "LOCAL_CONTEST_DEFINITIONS": "Local contest definitions",
            "POTA_ACTIVE": "POTA active spots",
            "SOTA_SPOTS": "SOTA spots",
            "SOTA_ALERTS": "SOTA alerts",
            "WWFF_SPOTS": "WWFF Spotline",
            "WWFF_AGENDAS": "WWFF agendas",
            "PARKSNPEAKS_ALL": "ParksnPeaks",
            "NOAA_SWPC_KP": "NOAA Kp",
            "NOAA_SWPC_XRAY": "NOAA X-ray",
            "NOAA_SWPC_SOLAR_WIND": "NOAA solar wind",
            "NOAA_SWPC_SOLAR_FLUX": "NOAA solar flux",
            "NOAA_SWPC_DRAP": "NOAA D-RAP",
        }
        return labels.get(source_id, source_id.replace("_", " ").title())

    def set_contest_context(self, contest_id: str | None) -> dict[str, Any]:
        self.reload_settings()
        if not contest_id:
            self._selected_contest_id = None
            return {"ok": True, "contestContext": self.contest_context()}
        contest = self.repository.get_contest(contest_id)
        if not contest:
            return {"ok": False, "error": "Contest not found"}
        self._selected_contest_id = contest_id
        return {"ok": True, "contestContext": self.contest_context()}

    def contest_context(self, band: str | None = None, mode: str | None = None) -> dict[str, Any]:
        self.reload_settings()
        selected = self.repository.get_contest(self._selected_contest_id) if self._selected_contest_id else None
        current = self.repository.current_contests(limit=20)
        candidates = []
        if selected and self._contest_matches_band_mode(selected, band, mode):
            candidates.append({**selected, "selected": True})
        for contest in current:
            if selected and contest.get("id") == selected.get("id"):
                continue
            if self._contest_matches_band_mode(contest, band, mode):
                candidates.append(contest)
        return {
            "selectedContestId": self._selected_contest_id,
            "selected": selected,
            "candidates": candidates[:8],
            "runningCount": len(current),
            "banner": self._contest_banner(candidates[:3], band, mode),
        }

    def _contest_banner(self, contests: list[dict[str, Any]], band: str | None, mode: str | None) -> dict[str, Any] | None:
        if not contests or not self.settings.get("contests", {}).get("showRunningContestBanner", True):
            return None
        contest = contests[0]
        pieces = [contest.get("name", "Contest active")]
        if band:
            pieces.append(str(band))
        if mode:
            pieces.append(str(mode).upper())
        exchange = contest.get("exchange")
        return {
            "contestId": contest.get("id"),
            "name": contest.get("name"),
            "label": " · ".join(pieces),
            "exchange": exchange,
            "rulesUrl": contest.get("rules_url") or contest.get("rulesUrl"),
            "sourceId": contest.get("source_id"),
            "selected": bool(contest.get("selected")),
        }

    def _contest_matches_band_mode(self, contest: dict[str, Any], band: str | None, mode: str | None) -> bool:
        bands = [str(item).lower() for item in contest.get("bands") or [] if item]
        modes = [self._normalize_contest_mode(item) for item in contest.get("modes") or [] if item]
        if band and bands and str(band).lower() not in bands:
            return False
        if mode and modes:
            normalized_mode = self._normalize_contest_mode(mode)
            if normalized_mode not in modes:
                return False
        return True

    def _normalize_contest_mode(self, mode: Any) -> str:
        text = str(mode or "").upper()
        if text in {"USB", "LSB", "AM", "FM"}:
            return "SSB"
        if text in {"DIGU", "DIGL", "FT4", "FT8", "RTTY", "PSK", "DIGI"}:
            return "DIGI" if text in {"DIGU", "DIGL", "PSK", "DIGI"} else text
        return text

    def rbn_summary(self, station_calls: list[str] | None = None, minutes: int = 60) -> dict[str, Any]:
        self.reload_settings()
        station_calls = station_calls or self.settings.get("rbn", {}).get("stationCalls") or []
        reports = self.repository.rbn_reports([_normalize_call(call) for call in station_calls], minutes=minutes)
        for report in reports:
            state = self.repository.nearest_station_state(str(report.get("timestamp_utc") or ""), window_seconds=120)
            if state:
                report["stationState"] = state
        snrs = [float(report["snr_db"]) for report in reports if isinstance(report.get("snr_db"), (int, float))]
        unique_skimmers = {report.get("skimmer_call") for report in reports if report.get("skimmer_call")}
        band_counts: dict[str, int] = {}
        for report in reports:
            band = report.get("band") or "?"
            band_counts[band] = band_counts.get(band, 0) + 1
        analytics = self._build_rbn_analytics(reports, minutes)
        return {
            "stationCalls": station_calls,
            "minutes": minutes,
            "totalReports": len(reports),
            "uniqueSkimmers": len(unique_skimmers),
            "maxSnrDb": max(snrs) if snrs else None,
            "medianSnrDb": sorted(snrs)[len(snrs) // 2] if snrs else None,
            "bestBand": max(band_counts, key=band_counts.get) if band_counts else None,
            **analytics,
            "reports": reports[:80],
        }

    def _build_rbn_analytics(self, reports: list[dict[str, Any]], minutes: int) -> dict[str, Any]:
        now = datetime.now(UTC)
        last_report_at = None
        by_band: dict[str, dict[str, Any]] = {}
        by_mode: dict[str, int] = {}
        snr_buckets: dict[tuple[str, str], list[float]] = {}
        skimmer_buckets: dict[str, set[str]] = {}
        heatmap: dict[tuple[str, str], int] = {}
        headings: dict[str, dict[str, Any]] = {}
        antenna: dict[str, dict[str, Any]] = {}

        for report in reports:
            timestamp = _parse_iso(report.get("timestamp_utc"))
            if timestamp and (last_report_at is None or timestamp > last_report_at):
                last_report_at = timestamp
            band = str(report.get("band") or "?")
            mode = str(report.get("mode") or "?")
            snr = _parse_float(report.get("snr_db"))
            band_row = by_band.setdefault(band, {"band": band, "reports": 0, "uniqueSkimmers": set(), "snrs": []})
            band_row["reports"] += 1
            if report.get("skimmer_call"):
                band_row["uniqueSkimmers"].add(report.get("skimmer_call"))
            if snr is not None:
                band_row["snrs"].append(snr)
            by_mode[mode] = by_mode.get(mode, 0) + 1

            if timestamp:
                bucket_5 = timestamp.replace(minute=(timestamp.minute // 5) * 5, second=0, microsecond=0)
                key_5 = iso_utc(bucket_5)
                if snr is not None:
                    snr_buckets.setdefault((key_5, band), []).append(snr)
                skimmer_buckets.setdefault(key_5, set()).add(str(report.get("skimmer_call") or ""))
                bucket_15 = timestamp.replace(minute=(timestamp.minute // 15) * 15, second=0, microsecond=0)
                heatmap[(iso_utc(bucket_15), band)] = heatmap.get((iso_utc(bucket_15), band), 0) + 1

            bearing = _parse_float(report.get("bearing_from_station_deg"))
            if bearing is not None:
                sector_start = int(bearing // 30) * 30
                sector = f"{sector_start:03d}-{(sector_start + 29) % 360:03d}"
                sector_row = headings.setdefault(sector, {"sector": sector, "reports": 0, "snrs": []})
                sector_row["reports"] += 1
                if snr is not None:
                    sector_row["snrs"].append(snr)

            state = report.get("stationState") or {}
            antenna_key = state.get("antenna_name") or state.get("antennaName")
            rotor = _parse_float(state.get("rotator_bearing_deg") or state.get("rotatorBearingDeg"))
            if not antenna_key and rotor is not None:
                antenna_key = f"Beam {round(rotor):03d}"
            if antenna_key:
                row = antenna.setdefault(str(antenna_key), {"label": str(antenna_key), "reports": 0, "snrs": [], "bands": {}})
                row["reports"] += 1
                row["bands"][band] = row["bands"].get(band, 0) + 1
                if snr is not None:
                    row["snrs"].append(snr)

        def summarize_snrs(values: list[float]) -> dict[str, Any]:
            if not values:
                return {"maxSnrDb": None, "medianSnrDb": None}
            ordered = sorted(values)
            return {"maxSnrDb": max(ordered), "medianSnrDb": ordered[len(ordered) // 2]}

        band_rows = []
        for row in by_band.values():
            snr_summary = summarize_snrs(row["snrs"])
            band_rows.append(
                {
                    "band": row["band"],
                    "reports": row["reports"],
                    "uniqueSkimmers": len(row["uniqueSkimmers"]),
                    **snr_summary,
                }
            )
        band_rows.sort(key=lambda item: (-item["reports"], item["band"]))

        heading_rows = []
        for row in headings.values():
            heading_rows.append({"sector": row["sector"], "reports": row["reports"], **summarize_snrs(row["snrs"])})
        heading_rows.sort(key=lambda item: (-item["reports"], item["sector"]))

        antenna_rows = []
        for row in antenna.values():
            antenna_rows.append(
                {
                    "label": row["label"],
                    "reports": row["reports"],
                    "bestBand": max(row["bands"], key=row["bands"].get) if row["bands"] else None,
                    **summarize_snrs(row["snrs"]),
                }
            )
        antenna_rows.sort(key=lambda item: (-item["reports"], item["label"]))

        no_reports_minutes = None
        if last_report_at:
            no_reports_minutes = max(0, int((now - last_report_at).total_seconds() // 60))

        return {
            "lastReportAtUtc": iso_utc(last_report_at) if last_report_at else None,
            "noReportsMinutes": no_reports_minutes,
            "noReportsWarning": no_reports_minutes is None or no_reports_minutes >= min(15, max(5, minutes // 4)),
            "bandSummary": band_rows[:10],
            "modeSummary": [{"mode": mode, "reports": count} for mode, count in sorted(by_mode.items(), key=lambda item: -item[1])],
            "snrSeries": [
                {
                    "bucketUtc": bucket,
                    "band": band,
                    "reports": len(values),
                    **summarize_snrs(values),
                }
                for (bucket, band), values in sorted(snr_buckets.items())
            ][-80:],
            "uniqueSkimmerSeries": [
                {"bucketUtc": bucket, "uniqueSkimmers": len({skimmer for skimmer in skimmers if skimmer})}
                for bucket, skimmers in sorted(skimmer_buckets.items())
            ][-80:],
            "azimuthSectors": heading_rows[:12],
            "bestHeading": heading_rows[0]["sector"] if heading_rows else None,
            "bandOpeningHeatmap": [
                {"bucketUtc": bucket, "band": band, "reports": count}
                for (bucket, band), count in sorted(heatmap.items())
            ][-120:],
            "antennaComparisons": antenna_rows[:8],
        }

    def lookup_reference(self, query: str) -> dict[str, Any]:
        if not query.strip():
            return {"ok": True, "results": []}
        return {"ok": True, "results": self._with_portable_status(self.repository.lookup_reference(query, limit=25))}

    async def lookup_reference_extended(self, query: str) -> dict[str, Any]:
        self.reload_settings()
        local_results = self.repository.lookup_reference(query, limit=25) if query.strip() else []
        remote_results = []
        if query.strip() and self.settings.get("portable", {}).get("pota", {}).get("enabled", True):
            remote_results.extend(await self._lookup_pota_reference(query))
        if query.strip() and self.settings.get("portable", {}).get("sota", {}).get("enabled", True):
            remote_results.extend(await self._lookup_sota_reference(query))
        if query.strip() and self.settings.get("portable", {}).get("wwff", {}).get("enabled", True):
            remote_results.extend(await self._lookup_wwff_reference(query))
        merged = []
        seen = set()
        for item in [*local_results, *remote_results]:
            key = (item.get("program"), item.get("reference"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return {"ok": True, "results": self._with_portable_status(merged[:25]), "localCount": len(local_results), "remoteCount": len(remote_results)}

    def _with_portable_status(self, refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        enriched = []
        for ref in refs:
            status = self.portable_reference_status(str(ref.get("program") or ""), str(ref.get("reference") or ""))
            enriched.append({**ref, "workedState": status})
        return enriched

    def portable_reference_status(self, program: str, reference: str, callsign: str | None = None) -> dict[str, Any]:
        program = str(program or "").upper()
        reference = str(reference or "").upper().strip()
        if not reference:
            return {"worked": False, "count": 0, "status": "unknown"}
        use_postgres = should_use_postgres() and not self._explicit_qso_db_path
        if not use_postgres and not self.qso_db_path.exists():
            return {"worked": False, "count": 0, "status": "no-cache"}
        field = {"POTA": "pota_ref", "SOTA": "sota_ref", "IOTA": "iota", "WWFF": "wwff_ref"}.get(program)
        clauses = []
        params: list[Any] = []
        placeholder = "%s" if use_postgres else "?"
        if field:
            clauses.append(f"upper(coalesce({field}, '')) = {placeholder}")
            params.append(reference)
        clauses.append(
            f"(upper(coalesce(sig, '')) = {placeholder} AND upper(coalesce(sig_info, '')) = {placeholder})"
        )
        params.extend([program, reference])
        clauses.append(f"upper(coalesce(comment, '')) LIKE {placeholder}")
        params.append(f"%{reference}%")
        call_clause = ""
        if callsign:
            call_clause = f" AND upper(coalesce(call, '')) = {placeholder}"
            params.append(_normalize_call(callsign))
        query = f"""
            SELECT COUNT(*) AS count, MAX(coalesce(qso_datetime, time_on)) AS last_worked
            FROM qso_records
            WHERE ({' OR '.join(clauses)}){call_clause}
        """
        try:
            if use_postgres:
                with connect_postgres() as conn:
                    with conn.cursor() as cur:
                        cur.execute(query, params)
                        row = cur.fetchone()
            else:
                conn = duckdb.connect(str(self.qso_db_path), read_only=True)
                try:
                    row = conn.execute(query, params).fetchone()
                finally:
                    conn.close()
        except Exception:
            logger.debug("Portable reference status lookup failed for %s %s", program, reference, exc_info=True)
            return {"worked": False, "count": 0, "status": "unavailable"}
        count = int(row[0] or 0) if row else 0
        return {
            "worked": count > 0,
            "count": count,
            "status": "worked" if count else "new",
            "lastWorkedUtc": str(row[1]) if row and row[1] else None,
        }

    def _portable_fill_payload(self, program: str, reference: str) -> dict[str, Any]:
        program = str(program or "").upper()
        reference = str(reference or "").upper()
        payload: dict[str, Any] = {"program": program, "reference": reference, "sig": program, "sig_info": reference}
        if program == "POTA":
            payload["pota"] = reference
            payload["pota_ref"] = reference
        elif program == "SOTA":
            payload["sota"] = reference
            payload["sota_ref"] = reference
        elif program == "WWFF":
            payload["wwff"] = reference
            payload["wwff_ref"] = reference
        return payload

    async def _lookup_pota_reference(self, query: str) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(6.0, connect=3.0), follow_redirects=True) as client:
                response = await client.get(
                    "https://api.pota.app/lookup",
                    params={"search": query, "size": 10},
                    headers={"User-Agent": "OM0RX-Radio-Control/2.0 activity-intelligence"},
                )
                if response.status_code >= 400:
                    return []
                payload = response.json()
        except Exception:
            logger.debug("POTA remote lookup failed", exc_info=True)
            return []
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = payload.get("results") or payload.get("data") or []
        else:
            rows = []
        results = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            reference = row.get("reference") or row.get("referenceCode") or row.get("parkId")
            if not reference:
                continue
            results.append(
                {
                    "program": "POTA",
                    "reference": str(reference).upper(),
                    "name": row.get("name") or row.get("parkName"),
                    "region": row.get("locationName") or row.get("entityName"),
                    "latitude": row.get("latitude"),
                    "longitude": row.get("longitude"),
                    "grid": row.get("grid"),
                    "officialUrl": f"https://pota.app/#/park/{str(reference).upper()}",
                    "sourceId": "POTA_LOOKUP",
                }
            )
        return results

    async def _lookup_sota_reference(self, query: str) -> list[dict[str, Any]]:
        match = re.search(r"\b([A-Z0-9]{1,3})/([A-Z]{1,3}-\d{3})\b", query.strip().upper())
        if not match:
            return []
        association, summit = match.group(1), match.group(2)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(6.0, connect=3.0), follow_redirects=True) as client:
                response = await client.get(
                    f"https://api-db2.sota.org.uk/api/summits/{association}/{summit}",
                    headers={"User-Agent": "OM0RX-Radio-Control/2.0 activity-intelligence"},
                )
                if response.status_code >= 400:
                    return []
                row = response.json()
        except Exception:
            logger.debug("SOTA remote lookup failed", exc_info=True)
            return []
        if not isinstance(row, dict):
            return []
        reference = row.get("summitCode") or f"{association}/{summit}"
        return [
            {
                "program": "SOTA",
                "reference": str(reference).upper() if "/" in str(reference) else f"{association}/{reference}".upper(),
                "name": row.get("name") or row.get("summitName"),
                "association": row.get("associationName") or association,
                "region": row.get("regionName"),
                "latitude": row.get("latitude"),
                "longitude": row.get("longitude"),
                "elevationM": row.get("altM") or row.get("elevation"),
                "sourceId": "SOTA_LOOKUP",
            }
        ]

    async def _lookup_wwff_reference(self, query: str) -> list[dict[str, Any]]:
        match = re.search(r"\b([A-Z0-9]{1,4}FF-\d{3,5})\b", query.strip().upper())
        if not match:
            return []
        reference = match.group(1)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(6.0, connect=3.0), follow_redirects=True) as client:
                response = await client.get(
                    f"http://parksnpeaks.org/api/PARK/WWFF/{reference}",
                    headers={"User-Agent": "OM0RX-Radio-Control/2.0 activity-intelligence"},
                )
                if response.status_code >= 400:
                    return []
                payload = response.json()
        except Exception:
            logger.debug("WWFF ParksnPeaks remote lookup failed", exc_info=True)
            return []
        row = payload[0] if isinstance(payload, list) and payload else payload
        if not isinstance(row, dict):
            return []
        return [
            {
                "program": "WWFF",
                "reference": reference,
                "name": row.get("name") or row.get("Name") or row.get("parkName"),
                "region": row.get("region") or row.get("state") or row.get("State"),
                "latitude": row.get("lat") or row.get("latitude") or row.get("Latitude"),
                "longitude": row.get("lon") or row.get("longitude") or row.get("Longitude"),
                "sourceId": "PARKSNPEAKS_LOOKUP",
            }
        ]

    async def dxpedition_detail(self, dxpedition_id: str, classifier: Any = None) -> dict[str, Any]:
        item = self.repository.get_dxpedition(dxpedition_id)
        if not item:
            return {"ok": False, "error": "DXpedition not found"}
        matrix = []
        bands = ["160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m"]
        modes = ["CW", "SSB", "RTTY", "FT8"]
        callsign = item.get("callsign")
        if classifier and callsign:
            async def cell_status(band: str, mode: str) -> dict[str, str]:
                status = "Unknown"
                try:
                    worked, confirmed, new_band, new_mode, bandmode_confirmed = await asyncio.wait_for(
                        classifier.call_status_flags(callsign, band, mode),
                        timeout=0.35,
                    )
                    if not worked:
                        status = "Needed"
                    elif bandmode_confirmed:
                        status = "Confirmed"
                    elif new_band or new_mode:
                        status = "Needed slot"
                    else:
                        status = "Worked"
                except Exception:
                    logger.debug("DXpedition worked matrix lookup failed for %s %s %s", callsign, band, mode, exc_info=True)
                return {"band": band, "mode": mode, "status": status}

            cells = await asyncio.gather(*(cell_status(band, mode) for band in bands for mode in modes))
            by_band_mode = {(cell["band"], cell["mode"]): cell for cell in cells}
            for band in bands:
                row = {"band": band, "modes": []}
                for mode in modes:
                    row["modes"].append(by_band_mode.get((band, mode), {"mode": mode, "status": "Unknown"}))
                matrix.append(row)
        return {"ok": True, "dxpedition": item, "workedMatrix": matrix, "matrixBands": bands, "matrixModes": modes}

    async def run_direct_rbn_telnet(self) -> None:
        self.reload_settings()
        rbn = self.settings.get("rbn", {})
        if not rbn.get("enabled", True) or not rbn.get("directTelnet", False):
            return
        await asyncio.gather(
            self._run_rbn_telnet_reader(
                str(rbn.get("directTelnetHost") or "telnet.reversebeacon.net"),
                int(rbn.get("directTelnetPort") or 7000),
                7000,
            ),
            self._run_rbn_telnet_reader(
                str(rbn.get("directFt8TelnetHost") or "telnet.reversebeacon.net"),
                int(rbn.get("directFt8TelnetPort") or 7001),
                7001,
            ),
        )

    async def _run_rbn_telnet_reader(self, host: str, port: int, source_port: int) -> None:
        backoff = 5
        while True:
            self.reload_settings()
            rbn = self.settings.get("rbn", {})
            if not rbn.get("directTelnet", False):
                await asyncio.sleep(60)
                continue
            try:
                reader, writer = await asyncio.open_connection(host, port)
                station_call = (rbn.get("stationCalls") or [getattr(config, "MY_STATION", "N0CALL")])[0]
                writer.write((str(station_call).upper() + "\r\n").encode("ascii", errors="ignore"))
                await writer.drain()
                backoff = 5
                while rbn.get("directTelnet", False):
                    raw = await asyncio.wait_for(reader.readline(), timeout=90)
                    if not raw:
                        break
                    line = raw.decode("utf-8", errors="replace").strip()
                    parsed = parse_rbn_line(line, source_port=source_port)
                    if not parsed:
                        continue
                    calls = {_normalize_call(call) for call in rbn.get("stationCalls") or []}
                    if rbn.get("ownCallOnlyProcessing", True) and parsed.spotted_call not in calls:
                        continue
                    self.repository.upsert_rbn_spot(parsed)
                    rbn = self.settings.get("rbn", {})
                writer.close()
                await writer.wait_closed()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Direct RBN telnet %s:%s failed: %s", host, port, exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 120)


_service: ActivityIntelligenceService | None = None


def get_activity_intelligence_service() -> ActivityIntelligenceService:
    global _service
    if _service is None:
        _service = ActivityIntelligenceService()
    return _service
