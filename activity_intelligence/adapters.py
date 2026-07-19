"""External source adapters and tolerant parsers."""

from __future__ import annotations

import hashlib
import html
import json
import logging
import re
from defusedxml import ElementTree as ET
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx

from radio_control.spot_processor import band_from_khz

from .models import (
    ContestEvent,
    Dxpedition,
    PortableActivation,
    PortableReference,
    RawFetchResult,
    RbnSpot,
    SpaceWeatherSnapshot,
)

logger = logging.getLogger(__name__)
MAX_FEED_BYTES = 5 * 1024 * 1024


def _bounded_text(response: httpx.Response, max_bytes: int = MAX_FEED_BYTES) -> str:
    content_type = (response.headers.get("content-type") or "").lower()
    if content_type and not any(kind in content_type for kind in ("xml", "json", "text", "calendar", "octet-stream")):
        raise ValueError(f"Unsupported feed content type: {content_type.split(';', 1)[0]}")
    if len(response.content) > max_bytes:
        raise ValueError("External feed exceeded the allowed size")
    return response.text

CALL_RE = re.compile(r"\b[A-Z0-9]{1,3}\d[A-Z0-9/]{1,10}\b", re.IGNORECASE)
MONTH_RE = re.compile(
    r"\b(?P<m1>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*"
    r"(?P<d1>\d{1,2})"
    r"(?:\s*[-/]\s*(?:(?P<m2>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*)?(?P<d2>\d{1,2}))?",
    re.IGNORECASE,
)
MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}
PORTABLE_REFS = {
    "POTA": re.compile(r"\b[A-Z]{1,3}-\d{3,5}\b", re.IGNORECASE),
    "SOTA": re.compile(r"\b[A-Z0-9]{1,3}/[A-Z]{1,3}-\d{3}\b", re.IGNORECASE),
    "WWFF": re.compile(r"\b[A-Z0-9]{1,4}FF-\d{3,5}\b", re.IGNORECASE),
}
RBN_RE = re.compile(
    r"DX\s+de\s+(?P<skimmer>[A-Z0-9/#-]+):\s+"
    r"(?P<freq>\d+(?:\.\d+)?)\s+"
    r"(?P<call>[A-Z0-9/]+)\s+"
    r"(?P<rest>.*)",
    re.IGNORECASE,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_utc(value: datetime | None = None) -> str:
    return (value or utc_now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_id(*parts: Any) -> str:
    return hashlib.sha1("|".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()


def normalize_call(value: Any) -> str:
    text = str(value or "").strip().upper()
    text = text.split()[0] if text else ""
    return "".join(ch for ch in text if ch.isalnum() or ch == "/")


def candidate_calls(text: str) -> list[str]:
    """Return plausible amateur calls from source text while rejecting dates/units."""
    candidates: list[str] = []
    for raw in CALL_RE.findall(text or ""):
        call = normalize_call(raw)
        if len(call) < 3:
            continue
        if not any(ch.isalpha() for ch in call) or not any(ch.isdigit() for ch in call):
            continue
        if re.fullmatch(r"\d{4,8}", call):
            continue
        if re.fullmatch(r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\d{1,2}", call):
            continue
        if re.fullmatch(r"\d+(?:M|CM|MM|W|KW)", call):
            continue
        if call not in candidates:
            candidates.append(call)
    return candidates


def looks_like_date_cell(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "").strip()).upper()
    if not normalized:
        return False
    if MONTH_RE.search(normalized):
        return True
    return bool(re.fullmatch(r"(?:\d{4}\s+)?(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\d{1,2}", normalized))


def parse_datetime(value: Any, default_tz=UTC) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=default_tz)
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M %Z"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=UTC)
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=default_tz)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(text)
    except Exception:
        return None


def parse_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def text_from_html(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def extract_refs(text: str, program: str | None = None) -> list[str]:
    refs: list[str] = []
    patterns = [PORTABLE_REFS[program]] if program else PORTABLE_REFS.values()
    for pattern in patterns:
        refs.extend(match.group(0).upper() for match in pattern.finditer(text or ""))
    return list(dict.fromkeys(refs))


def status_from_dates(start: datetime | None, end: datetime | None) -> str:
    now = utc_now()
    if start and start > now:
        return "UPCOMING"
    if start and end and start <= now <= end + timedelta(days=1):
        return "ACTIVE"
    if end and end < now:
        return "EXPIRED"
    return "UNKNOWN"


def parse_month_day_range(text: str) -> tuple[datetime | None, datetime | None]:
    """Parse common ADXO month/day ranges such as May 23-Jun 6."""
    match = MONTH_RE.search(text or "")
    if not match:
        return None, None
    now = utc_now()
    month1 = MONTHS.get(match.group("m1")[:3].upper())
    day1 = int(match.group("d1"))
    month2 = MONTHS.get((match.group("m2") or match.group("m1"))[:3].upper())
    day2 = int(match.group("d2") or day1)
    if not month1 or not month2:
        return None, None
    start = datetime(now.year, month1, day1, tzinfo=UTC)
    end_year = now.year + (1 if month2 < month1 else 0)
    end = datetime(end_year, month2, day2, 23, 59, 59, tzinfo=UTC)
    if end < now - timedelta(days=180):
        start = start.replace(year=start.year + 1)
        end = end.replace(year=end.year + 1)
    return start, end


class SourceAdapter(ABC):
    source_id: str
    url: str
    poll_seconds: int = 3600

    def __init__(self, enabled: bool = True, poll_seconds: int | None = None, url: str | None = None):
        self._enabled = enabled
        if poll_seconds:
            self.poll_seconds = int(poll_seconds)
        if url:
            self.url = url

    def enabled(self) -> bool:
        return self._enabled

    def get_recommended_poll_interval_seconds(self) -> int:
        return self.poll_seconds

    async def fetch_raw(
        self,
        client: httpx.AsyncClient,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> RawFetchResult:
        headers = {"User-Agent": "OM0RX-Radio-Control/2.0 activity-intelligence"}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        response = await client.get(self.url, headers=headers)
        return RawFetchResult(
            source_id=self.source_id,
            url=str(response.url),
            fetched_at_utc=iso_utc(),
            http_status=response.status_code,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
            content_type=response.headers.get("content-type"),
            body=_bounded_text(response) if response.status_code != 304 else "",
        )

    @abstractmethod
    def parse(self, raw: RawFetchResult) -> dict[str, list[Any]]:
        raise NotImplementedError


class Ng3kAdxoAdapter(SourceAdapter):
    source_id = "NG3K_ADXO"
    url = "https://www.ng3k.com/misc/adxo.html"
    poll_seconds = 12 * 3600

    def parse(self, raw: RawFetchResult) -> dict[str, list[Any]]:
        events: list[Dxpedition] = []
        row_chunks = re.findall(r"<tr[^>]*>(.*?)</tr>", raw.body, re.DOTALL | re.IGNORECASE)
        chunks = row_chunks or raw.body.splitlines()
        for chunk in chunks:
            text = text_from_html(chunk)
            if not text or len(text) < 8:
                continue
            cells = [text_from_html(cell) for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", chunk, re.DOTALL | re.IGNORECASE)]
            cell_calls = [(cell, candidate_calls(cell)) for cell in cells]
            calls = []
            call_cell_index: int | None = None
            for index, (cell, found) in enumerate(cell_calls):
                if found and ("spot" in cell.lower() or len(cell.split()) <= 3):
                    calls = found
                    call_cell_index = index
                    break
            if not calls:
                calls = candidate_calls(text)
            if not calls:
                continue
            start, end = parse_month_day_range(text)
            call = calls[0]
            if len(call) < 3:
                continue
            entity_text = text
            if cells and call_cell_index is not None:
                if call_cell_index == 0 and len(cells) > 1:
                    entity_text = cells[1]
                else:
                    preceding = [cell for cell in cells[:call_cell_index] if not looks_like_date_cell(cell)]
                    entity_text = preceding[-1] if preceding else text
            entity_text = re.sub(re.escape(call), "", entity_text, flags=re.IGNORECASE).strip(" -:")
            if start:
                entity_text = MONTH_RE.sub("", entity_text, count=1).strip(" -:")
            aliases = [alias for alias in calls[1:] if alias != call]
            events.append(
                Dxpedition(
                    id=stable_id(self.source_id, call, start, end, text),
                    source_id=self.source_id,
                    callsign=call,
                    aliases=aliases,
                    dxcc_entity=entity_text[:80] or None,
                    start_date_utc=iso_utc(start) if start else None,
                    end_date_utc=iso_utc(end) if end else None,
                    status=status_from_dates(start, end),
                    source_url=raw.url,
                    notes=text[:500],
                    last_updated_utc=raw.fetched_at_utc,
                )
            )
        return {"dxpeditions": events}


class DxCalIcsAdapter(SourceAdapter):
    source_id = "DXCAL_ICS"
    url = "https://www.danplanet.com/dxcal.ics"
    poll_seconds = 6 * 3600

    def parse(self, raw: RawFetchResult) -> dict[str, list[Any]]:
        events: list[Dxpedition] = []
        for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", raw.body, re.DOTALL | re.IGNORECASE):
            fields: dict[str, str] = {}
            for line in block.replace("\r\n ", "").splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                fields[key.split(";", 1)[0].upper()] = value.strip()
            summary = fields.get("SUMMARY") or ""
            description = fields.get("DESCRIPTION") or ""
            calls = CALL_RE.findall(summary)
            if not calls:
                calls = CALL_RE.findall(description)
            if not calls:
                continue
            start = parse_datetime(fields.get("DTSTART"))
            end = parse_datetime(fields.get("DTEND")) or start
            call = normalize_call(calls[0])
            entity = re.sub(r"\b" + re.escape(call) + r"\b", "", summary, flags=re.IGNORECASE).strip(" -:")
            events.append(
                Dxpedition(
                    id=stable_id(self.source_id, call, start, end, summary),
                    source_id=self.source_id,
                    callsign=call,
                    aliases=[normalize_call(c) for c in calls[1:]],
                    dxcc_entity=entity or None,
                    start_date_utc=iso_utc(start) if start else None,
                    end_date_utc=iso_utc(end) if end else None,
                    status=status_from_dates(start, end),
                    source_url=fields.get("URL") or raw.url,
                    notes=description or summary,
                    last_updated_utc=raw.fetched_at_utc,
                )
            )
        return {"dxpeditions": events}


class Wa7bnmRssAdapter(SourceAdapter):
    source_id = "WA7BNM_RSS"
    url = "https://www.contestcalendar.com/calendar.rss"
    poll_seconds = 6 * 3600

    def parse(self, raw: RawFetchResult) -> dict[str, list[Any]]:
        contests: list[ContestEvent] = []
        try:
            if len(raw.body.encode("utf-8")) > MAX_FEED_BYTES:
                raise ValueError("XML feed exceeded the allowed size")
            root = ET.fromstring(raw.body)
        except ET.ParseError:
            logger.debug("Could not parse WA7BNM RSS")
            return {"contests": []}
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            description = text_from_html(item.findtext("description") or "")
            link = (item.findtext("link") or raw.url).strip()
            if not title:
                continue
            start = parse_datetime(item.findtext("pubDate")) or utc_now()
            end = start + timedelta(days=1)
            date_match = re.search(
                r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}).*?(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2})",
                description,
            )
            if date_match:
                start = parse_datetime(date_match.group(1)) or start
                end = parse_datetime(date_match.group(2)) or end
            modes = sorted({mode for mode in ("CW", "SSB", "RTTY", "FT8", "DIGI") if mode in (title + description).upper()})
            contests.append(
                ContestEvent(
                    id=stable_id(self.source_id, title, start, link),
                    source_id=self.source_id,
                    name=title,
                    start_utc=iso_utc(start),
                    end_utc=iso_utc(end),
                    modes=modes,
                    source_url=link,
                    rules_url=link,
                    exchange=description[:500] if description else None,
                    rule_confidence="LOW",
                    last_updated_utc=raw.fetched_at_utc,
                )
            )
        return {"contests": contests}


def _parse_list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip().upper() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return [item.strip().strip("'\"").upper() for item in text.split(",") if item.strip()]


def _parse_simple_contest_yaml(body: str) -> list[dict[str, Any]]:
    """Parse a small YAML subset used by config/contest_definitions.yaml."""
    contests: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_contests = False
    for raw_line in body.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped in {"contests:", "contestDefinitions:"}:
            in_contests = True
            continue
        if not in_contests and not stripped.startswith("- "):
            continue
        if stripped.startswith("- "):
            if current:
                contests.append(current)
            current = {}
            stripped = stripped[2:].strip()
            if not stripped:
                continue
        if ":" not in stripped or current is None:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        current[key] = _parse_list_value(value) if key in {"modes", "bands", "classes"} else value
    if current:
        contests.append(current)
    return contests


class LocalContestDefinitionsAdapter(SourceAdapter):
    source_id = "LOCAL_CONTEST_DEFINITIONS"
    url = "config/contest_definitions.yaml"
    poll_seconds = 5 * 60

    async def fetch_raw(
        self,
        client: httpx.AsyncClient,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> RawFetchResult:
        path = Path(self.url)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            return RawFetchResult(
                source_id=self.source_id,
                url=str(path),
                fetched_at_utc=iso_utc(),
                http_status=204,
                content_type="text/plain",
                body="",
            )
        stat = path.stat()
        return RawFetchResult(
            source_id=self.source_id,
            url=str(path),
            fetched_at_utc=iso_utc(),
            http_status=200,
            etag=stable_id(path, stat.st_mtime_ns, stat.st_size),
            last_modified=iso_utc(datetime.fromtimestamp(stat.st_mtime, UTC)),
            content_type="text/yaml",
            body=path.read_text(encoding="utf-8", errors="replace"),
        )

    def parse(self, raw: RawFetchResult) -> dict[str, list[Any]]:
        if not raw.body.strip():
            return {"contests": []}
        rows: list[dict[str, Any]] = []
        try:
            payload = json.loads(raw.body)
            rows = payload if isinstance(payload, list) else payload.get("contests") or []
        except Exception:
            try:
                import yaml  # type: ignore

                payload = yaml.safe_load(raw.body)
                rows = payload if isinstance(payload, list) else payload.get("contests") or []
            except Exception:
                rows = _parse_simple_contest_yaml(raw.body)
        contests: list[ContestEvent] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or row.get("contest") or "").strip()
            start = parse_datetime(row.get("startUtc") or row.get("start_utc") or row.get("start"))
            end = parse_datetime(row.get("endUtc") or row.get("end_utc") or row.get("end"))
            if not name or not start or not end:
                continue
            contest_id = str(row.get("id") or stable_id(self.source_id, name, start, end))
            contests.append(
                ContestEvent(
                    id=contest_id,
                    source_id=self.source_id,
                    name=name,
                    start_utc=iso_utc(start),
                    end_utc=iso_utc(end),
                    modes=_parse_list_value(row.get("modes")),
                    bands=_parse_list_value(row.get("bands")),
                    geographic_focus=row.get("geographicFocus") or row.get("geographic_focus"),
                    participation=row.get("participation"),
                    classes=_parse_list_value(row.get("classes")),
                    exchange=row.get("exchange"),
                    work_stations_rule=row.get("workStationsRule") or row.get("work_stations_rule"),
                    qso_points_rule=row.get("qsoPointsRule") or row.get("qso_points_rule"),
                    multipliers_rule=row.get("multipliersRule") or row.get("multipliers_rule"),
                    score_calculation=row.get("scoreCalculation") or row.get("score_calculation"),
                    log_due_utc=iso_utc(parse_datetime(row.get("logDueUtc") or row.get("log_due_utc"))) if parse_datetime(row.get("logDueUtc") or row.get("log_due_utc")) else None,
                    log_upload_url=row.get("logUploadUrl") or row.get("log_upload_url"),
                    rules_url=row.get("rulesUrl") or row.get("rules_url") or raw.url,
                    cabrillo_name=row.get("cabrilloName") or row.get("cabrillo_name"),
                    source_url=row.get("sourceUrl") or row.get("source_url") or raw.url,
                    rule_confidence=str(row.get("ruleConfidence") or row.get("rule_confidence") or "HIGH").upper(),
                    last_updated_utc=raw.fetched_at_utc,
                )
            )
        return {"contests": contests}


class JsonPortableAdapter(SourceAdapter):
    program = "POTA"
    activation_type = "ACTIVE_SPOT"
    source_id = "PORTABLE_JSON"
    url = ""
    poll_seconds = 60

    def parse(self, raw: RawFetchResult) -> dict[str, list[Any]]:
        try:
            payload = json.loads(raw.body)
        except json.JSONDecodeError:
            return {"portable_activations": [], "portable_references": []}
        rows = payload if isinstance(payload, list) else payload.get("spots") or payload.get("activations") or payload.get("alerts") or payload.get("data") or []
        activations: list[PortableActivation] = []
        references: list[PortableReference] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            text = " ".join(str(row.get(key, "")) for key in row)
            call = normalize_call(
                row.get("activator")
                or row.get("activatorCallsign")
                or row.get("activatingCallsign")
                or row.get("callsign")
                or row.get("call")
            )
            refs = extract_refs(text, self.program if self.program in PORTABLE_REFS else None)
            explicit_ref = row.get("reference") or row.get("referenceCode")
            summit_code = row.get("summitCode")
            association_code = row.get("associationCode")
            if summit_code and association_code:
                explicit_ref = f"{association_code}/{summit_code}"
            elif summit_code:
                explicit_ref = summit_code
            if explicit_ref:
                refs = [str(explicit_ref).upper(), *refs]
            refs = list(dict.fromkeys(refs))
            if not call or not refs:
                continue
            freq = parse_float(row.get("frequency")) or parse_float(row.get("freq"))
            if freq and freq < 200:
                freq *= 1000
            seen = parse_datetime(row.get("spotTime") or row.get("timeStamp") or row.get("lastSeen") or row.get("date")) or utc_now()
            start = parse_datetime(row.get("start") or row.get("startDate") or row.get("startTime"))
            end = parse_datetime(row.get("end") or row.get("endDate") or row.get("endTime"))
            raw_hash = stable_id(json.dumps(row, sort_keys=True, default=str))
            activations.append(
                PortableActivation(
                    id=stable_id(self.source_id, self.program, call, refs, freq, seen, raw_hash),
                    program=self.program,
                    type=self.activation_type,
                    activator_call=call,
                    references=refs,
                    frequency_khz=freq,
                    mode=(row.get("mode") or row.get("modeCode") or "").upper() or None,
                    spotter_call=normalize_call(row.get("spotter") or row.get("spotterCallsign")),
                    comments=row.get("comments") or row.get("comment") or row.get("text"),
                    start_utc=iso_utc(start) if start else None,
                    end_utc=iso_utc(end) if end else None,
                    source_id=self.source_id,
                    source_url=raw.url,
                    raw_payload_hash=raw_hash,
                    last_seen_utc=iso_utc(seen),
                )
            )
            for ref in refs:
                references.append(
                    PortableReference(
                        program=self.program,
                        reference=ref,
                        name=row.get("name") or row.get("parkName") or row.get("summitName") or row.get("summitDetails"),
                        association=row.get("associationCode"),
                        region=row.get("region") or row.get("associationName"),
                        grid=row.get("grid") or row.get("gridSquare"),
                        latitude=parse_float(row.get("latitude") or row.get("lat")),
                        longitude=parse_float(row.get("longitude") or row.get("lon") or row.get("lng")),
                        official_url=row.get("url"),
                        source_id=self.source_id,
                        source_payload_hash=raw_hash,
                        last_verified_utc=raw.fetched_at_utc,
                    )
                )
        return {"portable_activations": activations, "portable_references": references}


class PotaSpotsAdapter(JsonPortableAdapter):
    source_id = "POTA_ACTIVE"
    program = "POTA"
    url = "https://api.pota.app/spot/activator"


class SotaSpotsAdapter(JsonPortableAdapter):
    source_id = "SOTA_SPOTS"
    program = "SOTA"
    url = "https://api-db2.sota.org.uk/api/spots/10/all"


class SotaAlertsAdapter(JsonPortableAdapter):
    source_id = "SOTA_ALERTS"
    program = "SOTA"
    activation_type = "ALERT"
    url = "https://api-db2.sota.org.uk/api/alerts/10/all/all"
    poll_seconds = 300


class WwffSpotsAdapter(JsonPortableAdapter):
    source_id = "WWFF_SPOTS"
    program = "WWFF"
    url = "https://spots.wwff.co/static/spots.json"


class WwffAgendasAdapter(JsonPortableAdapter):
    source_id = "WWFF_AGENDAS"
    program = "WWFF"
    activation_type = "AGENDA"
    url = "https://spots.wwff.co/static/agendas_active.json"
    poll_seconds = 300


class ParksnPeaksAllAdapter(JsonPortableAdapter):
    source_id = "PARKSNPEAKS_ALL"
    program = "PARKSNPEAKS"
    url = "http://www.parksnpeaks.org/api/ALL"


class SwpcKpAdapter(SourceAdapter):
    source_id = "NOAA_SWPC_KP"
    url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
    poll_seconds = 15 * 60

    def parse(self, raw: RawFetchResult) -> dict[str, list[Any]]:
        try:
            rows = json.loads(raw.body)
        except json.JSONDecodeError:
            rows = []
        latest = None
        if isinstance(rows, list):
            data_rows = rows[1:] if rows and isinstance(rows[0], list) else rows
            for row in data_rows:
                if not isinstance(row, list) or len(row) < 2:
                    continue
                latest = row
        if not latest:
            return {"space_weather": []}
        timestamp = parse_datetime(latest[0]) or utc_now()
        return {
            "space_weather": [
                SpaceWeatherSnapshot(
                    id=stable_id(self.source_id, timestamp, latest),
                    timestamp_utc=iso_utc(timestamp),
                    kp=parse_float(latest[1]),
                    source_ids=[self.source_id],
                    raw_json={"row": latest},
                )
            ]
        }


def xray_class_from_flux(flux: float | None) -> str | None:
    if flux is None or flux <= 0:
        return None
    classes = [("X", 1e-4), ("M", 1e-5), ("C", 1e-6), ("B", 1e-7), ("A", 1e-8)]
    for label, base in classes:
        if flux >= base:
            return f"{label}{flux / base:.1f}"
    return f"A{flux / 1e-8:.1f}"


class SwpcXrayAdapter(SourceAdapter):
    source_id = "NOAA_SWPC_XRAY"
    url = "https://services.swpc.noaa.gov/json/goes/primary/xrays-6-hour.json"
    poll_seconds = 5 * 60

    def parse(self, raw: RawFetchResult) -> dict[str, list[Any]]:
        try:
            rows = json.loads(raw.body)
        except json.JSONDecodeError:
            rows = []
        latest = None
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            energy = str(row.get("energy") or row.get("observed_flux") or "")
            if "0.1-0.8" in energy or latest is None:
                latest = row
        if not latest:
            return {"space_weather": []}
        timestamp = parse_datetime(latest.get("time_tag") or latest.get("time")) or utc_now()
        flux = parse_float(latest.get("flux"))
        return {
            "space_weather": [
                SpaceWeatherSnapshot(
                    id=stable_id(self.source_id, timestamp, flux),
                    timestamp_utc=iso_utc(timestamp),
                    xray_class=xray_class_from_flux(flux),
                    source_ids=[self.source_id],
                    raw_json={"row": latest},
                )
            ]
        }


class SwpcSolarWindAdapter(SourceAdapter):
    source_id = "NOAA_SWPC_SOLAR_WIND"
    url = "https://services.swpc.noaa.gov/products/solar-wind/mag-1-day.json"
    poll_seconds = 5 * 60

    async def fetch_raw(
        self,
        client: httpx.AsyncClient,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> RawFetchResult:
        headers = {"User-Agent": "OM0RX-Radio-Control/2.0 activity-intelligence"}
        mag_response = await client.get(self.url, headers=headers)
        plasma_url = "https://services.swpc.noaa.gov/products/solar-wind/plasma-1-day.json"
        plasma_response = await client.get(plasma_url, headers=headers)
        return RawFetchResult(
            source_id=self.source_id,
            url=f"{self.url};{plasma_url}",
            fetched_at_utc=iso_utc(),
            http_status=max(mag_response.status_code, plasma_response.status_code),
            content_type="application/json",
            body=json.dumps({"mag": _bounded_text(mag_response), "plasma": _bounded_text(plasma_response)}),
        )

    def parse(self, raw: RawFetchResult) -> dict[str, list[Any]]:
        try:
            payload = json.loads(raw.body)
            mag_rows = json.loads(payload.get("mag") or "[]")
            plasma_rows = json.loads(payload.get("plasma") or "[]")
        except Exception:
            return {"space_weather": []}
        latest_mag = self._latest_array_row(mag_rows)
        latest_plasma = self._latest_array_row(plasma_rows)
        if not latest_mag and not latest_plasma:
            return {"space_weather": []}
        timestamp = parse_datetime((latest_mag or latest_plasma)[0]) or utc_now()
        bz = parse_float(self._row_value(mag_rows, latest_mag, "bz_gsm", fallback_index=3))
        speed = parse_float(self._row_value(plasma_rows, latest_plasma, "speed", fallback_index=2))
        return {
            "space_weather": [
                SpaceWeatherSnapshot(
                    id=stable_id(self.source_id, timestamp, bz, speed),
                    timestamp_utc=iso_utc(timestamp),
                    solar_wind_bz_nt=bz,
                    solar_wind_speed_kms=speed,
                    source_ids=[self.source_id],
                    raw_json={"mag": latest_mag, "plasma": latest_plasma},
                )
            ]
        }

    def _latest_array_row(self, rows: Any) -> list[Any] | None:
        latest = None
        if isinstance(rows, list):
            for row in rows[1:] if rows and isinstance(rows[0], list) else rows:
                if isinstance(row, list) and row:
                    latest = row
        return latest

    def _row_value(self, rows: Any, row: list[Any] | None, column: str, fallback_index: int) -> Any:
        if not row:
            return None
        if isinstance(rows, list) and rows and isinstance(rows[0], list):
            header = [str(item).lower() for item in rows[0]]
            if column in header:
                index = header.index(column)
                if index < len(row):
                    return row[index]
        return row[fallback_index] if len(row) > fallback_index else None


class SwpcSolarFluxAdapter(SourceAdapter):
    source_id = "NOAA_SWPC_SOLAR_FLUX"
    url = "https://services.swpc.noaa.gov/json/solar-cycle/observed-solar-cycle-indices.json"
    poll_seconds = 6 * 3600

    def parse(self, raw: RawFetchResult) -> dict[str, list[Any]]:
        try:
            rows = json.loads(raw.body)
        except json.JSONDecodeError:
            rows = []
        latest = None
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict):
                latest = row
        if not latest:
            return {"space_weather": []}
        timestamp = parse_datetime(latest.get("time-tag") or latest.get("time_tag") or latest.get("date")) or utc_now()
        flux = parse_float(latest.get("f10.7") or latest.get("f10_7") or latest.get("observed_flux"))
        return {
            "space_weather": [
                SpaceWeatherSnapshot(
                    id=stable_id(self.source_id, timestamp, flux),
                    timestamp_utc=iso_utc(timestamp),
                    solar_flux_sfu=flux,
                    source_ids=[self.source_id],
                    raw_json={"row": latest},
                )
            ]
        }


class SwpcDrapAdapter(SourceAdapter):
    source_id = "NOAA_SWPC_DRAP"
    url = "https://services.swpc.noaa.gov/text/drap_global_frequencies.txt"
    poll_seconds = 5 * 60

    def parse(self, raw: RawFetchResult) -> dict[str, list[Any]]:
        if raw.body.lstrip().startswith("# DRAP"):
            return self._parse_text(raw)
        try:
            payload = json.loads(raw.body)
        except json.JSONDecodeError:
            payload = {}
        row = payload[-1] if isinstance(payload, list) and payload else payload
        if not isinstance(row, dict):
            return {"space_weather": []}
        timestamp = parse_datetime(row.get("time_tag") or row.get("time") or row.get("timestamp")) or utc_now()
        freq = (
            parse_float(row.get("drap_affected_frequency_mhz"))
            or parse_float(row.get("affected_frequency_mhz"))
            or parse_float(row.get("highest_affected_frequency"))
            or parse_float(row.get("haf"))
        )
        return {
            "space_weather": [
                SpaceWeatherSnapshot(
                    id=stable_id(self.source_id, timestamp, freq),
                    timestamp_utc=iso_utc(timestamp),
                    drap_affected_frequency_mhz=freq,
                    source_ids=[self.source_id],
                    raw_json={"row": row},
                )
            ]
        }

    def _parse_text(self, raw: RawFetchResult) -> dict[str, list[Any]]:
        valid_match = re.search(r"Product Valid At\s*:\s*([0-9-]+\s+[0-9:]+\s+UTC)", raw.body, re.IGNORECASE)
        timestamp = parse_datetime(valid_match.group(1)) if valid_match else utc_now()
        frequencies: list[float] = []
        for line in raw.body.splitlines():
            if not re.match(r"\s*-?\d+\s*\|", line):
                continue
            _, values = line.split("|", 1)
            for value in re.findall(r"\b\d+(?:\.\d+)?\b", values):
                parsed = parse_float(value)
                if parsed is not None:
                    frequencies.append(parsed)
        freq = max(frequencies) if frequencies else None
        return {
            "space_weather": [
                SpaceWeatherSnapshot(
                    id=stable_id(self.source_id, timestamp, freq),
                    timestamp_utc=iso_utc(timestamp),
                    drap_affected_frequency_mhz=freq,
                    source_ids=[self.source_id],
                    raw_json={
                        "product": "D-Region Absorption",
                        "source_url": raw.url,
                        "max_grid_frequency_mhz": freq,
                    },
                )
            ]
        }


def parse_rbn_line(raw_line: str, timestamp: datetime | None = None, source_port: int | None = None) -> RbnSpot | None:
    line = (raw_line or "").strip()
    match = RBN_RE.search(line)
    if not match:
        return None
    rest = match.group("rest") or ""
    freq = parse_float(match.group("freq"))
    if not freq:
        return None
    snr = None
    speed = None
    snr_match = re.search(r"([+-]?\d+(?:\.\d+)?)\s*dB\b", rest, re.IGNORECASE)
    wpm_match = re.search(r"(\d+(?:\.\d+)?)\s*WPM\b", rest, re.IGNORECASE)
    if snr_match:
        snr = parse_float(snr_match.group(1))
    if wpm_match:
        speed = parse_float(wpm_match.group(1))
    rest_upper = rest.upper()
    mode = "FT8" if source_port == 7001 else "CW"
    if "FT4" in rest_upper:
        mode = "FT4"
    elif "FT8" in rest_upper:
        mode = "FT8"
    elif "RTTY" in rest_upper:
        mode = "RTTY"
    return RbnSpot(
        id=stable_id("RBN", line, timestamp or utc_now()),
        timestamp_utc=iso_utc(timestamp),
        spotted_call=normalize_call(match.group("call")),
        skimmer_call=normalize_call(match.group("skimmer").replace("-#", "")),
        frequency_khz=float(freq),
        band=band_from_khz(float(freq)),
        mode=mode,
        snr_db=snr,
        speed_wpm=speed,
        cq_flag=bool(re.search(r"\b(?:CQ|TEST)\b", rest, re.IGNORECASE)),
        spot_comment=rest.strip(),
        source_port=source_port,
        raw_line=line,
    )


def adapter_from_settings(settings: dict[str, Any]) -> list[SourceAdapter]:
    adapters: list[SourceAdapter] = []
    if not settings.get("enabled", True):
        return adapters
    dx = settings.get("dxpeditions", {})
    if dx.get("enabled", True) and dx.get("ng3kAdxoEnabled", True):
        adapters.append(Ng3kAdxoAdapter(poll_seconds=int(dx.get("ng3kPollHours", 12)) * 3600))
    if dx.get("enabled", True) and dx.get("dxcalIcsEnabled", True):
        adapters.append(DxCalIcsAdapter(poll_seconds=int(dx.get("ng3kPollHours", 12)) * 3600))
    contests = settings.get("contests", {})
    if contests.get("enabled", True) and contests.get("wa7bnmEnabled", True):
        adapters.append(Wa7bnmRssAdapter(poll_seconds=int(contests.get("wa7bnmFeedPollHours", 6)) * 3600))
    if contests.get("enabled", True) and contests.get("localContestDefinitionsPath"):
        adapters.append(LocalContestDefinitionsAdapter(url=str(contests.get("localContestDefinitionsPath"))))
    portable = settings.get("portable", {})
    if portable.get("enabled", True):
        if portable.get("pota", {}).get("enabled", True) and portable.get("pota", {}).get("useUndocumentedApi", True):
            adapters.append(PotaSpotsAdapter(poll_seconds=int(portable.get("pota", {}).get("activeSpotIntervalSeconds", 60))))
        if portable.get("sota", {}).get("enabled", True):
            adapters.append(SotaSpotsAdapter(poll_seconds=int(portable.get("sota", {}).get("activeSpotIntervalSeconds", 60))))
            adapters.append(SotaAlertsAdapter(poll_seconds=int(portable.get("sota", {}).get("alertsIntervalSeconds", 300))))
        if portable.get("wwff", {}).get("enabled", True):
            adapters.append(WwffSpotsAdapter(poll_seconds=int(portable.get("wwff", {}).get("minRefreshSeconds", 30))))
            adapters.append(WwffAgendasAdapter(poll_seconds=max(300, int(portable.get("wwff", {}).get("minRefreshSeconds", 30)))))
        if portable.get("parksnpeaks", {}).get("enabled", True):
            adapters.append(ParksnPeaksAllAdapter(poll_seconds=int(portable.get("parksnpeaks", {}).get("spotsIntervalSeconds", 60))))
    propagation = settings.get("propagation", {})
    if propagation.get("enabled", True) and propagation.get("swpcEnabled", True):
        adapters.append(SwpcKpAdapter())
        adapters.append(SwpcXrayAdapter())
        adapters.append(SwpcSolarWindAdapter())
        adapters.append(SwpcSolarFluxAdapter())
        adapters.append(SwpcDrapAdapter())
    return adapters
