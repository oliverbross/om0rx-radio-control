"""Portable/special-activity reference extraction and log-field mapping.

The spot feeds are inconsistent: some provide structured activity tags, while
others put only a reference in the free-form comment.  Keep the normalisation
in one dependency-light module so spot enrichment, Digital automation, and QSO
logging all agree on the same program and reference identity.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping


REFERENCE_PROGRAM_ALIASES = {
    "POTA": "POTA",
    "SOTA": "SOTA",
    "IOTA": "IOTA",
    "WWFF": "WWFF",
    "BOTA": "WWBOTA",
    "UKBOTA": "WWBOTA",
    "WWBOTA": "WWBOTA",
    "BUNKER": "WWBOTA",
    "BUNKERS": "WWBOTA",
    "ARLHS": "ARLHS",
    "ILLW": "ARLHS",
    "LIGHTHOUSE": "ARLHS",
    "LIGHTHOUSES": "ARLHS",
}

HUNTER_PROGRAMS = {"POTA", "SOTA", "IOTA", "WWFF", "WWBOTA", "ARLHS"}

_SOTA_RE = re.compile(r"\b[A-Z0-9]{1,3}/[A-Z0-9]{1,3}-\d{3}\b", re.I)
_IOTA_RE = re.compile(r"\b(?:AF|AN|AS|EU|NA|OC|SA)-\d{3}\b", re.I)
_WWFF_RE = re.compile(r"\b[A-Z0-9]{1,4}FF-\d{3,5}\b", re.I)
_WWBOTA_RE = re.compile(r"\bB/[A-Z0-9]{1,4}-\d{4}\b", re.I)
_POTA_RE = re.compile(r"\b[A-Z0-9]{1,4}-\d{4,5}(?:@[A-Z0-9-]{4,6})?\b", re.I)
_ARLHS_RE = re.compile(r"\b[A-Z]{2,4}-\d{3}\b", re.I)

_EXACT_REFERENCE_PATTERNS = {
    "POTA": re.compile(r"^[A-Z0-9]{1,4}-\d{4,5}(?:@[A-Z0-9-]{4,6})?$", re.I),
    "SOTA": re.compile(r"^[A-Z0-9]{1,3}/[A-Z0-9]{1,3}-\d{3}$", re.I),
    "IOTA": re.compile(r"^(?:AF|AN|AS|EU|NA|OC|SA)-\d{3}$", re.I),
    "WWFF": re.compile(r"^[A-Z0-9]{1,4}FF-\d{3,5}$", re.I),
    "WWBOTA": re.compile(r"^B/[A-Z0-9]{1,4}-\d{4}$", re.I),
    "ARLHS": re.compile(r"^[A-Z]{2,4}-\d{3}$", re.I),
}


def canonical_reference_program(value: Any) -> str:
    text = str(value or "").strip().upper().replace("-ACTIVE", "_ACTIVE")
    for suffix in ("_ACTIVE", "_ALERT", "_AGENDA", "_REFERENCE"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return REFERENCE_PROGRAM_ALIASES.get(text, text)


def normalize_activity_reference(program: Any, reference: Any) -> tuple[str, str]:
    """Return one exact program/reference identity or an empty pair.

    Program context is mandatory for broad hyphenated references.  This keeps
    prefixes such as IOTA ``EU-123`` and generic callsign/comment fragments
    from being reinterpreted as POTA references.
    """
    program_text = canonical_reference_program(program)
    reference_text = str(reference or "").strip().upper().strip(".,;:()[]{}")
    pattern = _EXACT_REFERENCE_PATTERNS.get(program_text)
    if pattern is None or not pattern.fullmatch(reference_text):
        return "", ""
    # A POTA spot may append @grid metadata.  The award identity is the park.
    if program_text == "POTA":
        reference_text = reference_text.split("@", 1)[0]
    return program_text, reference_text


def _reference_item(
    program: Any,
    reference: Any,
    *,
    status: Any = "",
    need_reason: Any = "",
) -> dict[str, str] | None:
    program_text = canonical_reference_program(program)
    reference_text = str(reference or "").strip().upper().strip(".,;:()[]{}")
    if not program_text or not reference_text:
        return None
    if program_text in _EXACT_REFERENCE_PATTERNS:
        program_text, reference_text = normalize_activity_reference(program_text, reference_text)
        if not program_text:
            return None
    item = {"type": program_text, "reference_id": reference_text}
    if status not in (None, ""):
        item["status"] = str(status).strip().lower()
    if need_reason not in (None, ""):
        item["need_reason"] = str(need_reason).strip().lower()
    return item


def _iter_values(value: Any) -> Iterable[Any]:
    if isinstance(value, str):
        yield from (token.strip() for token in re.split(r"[,;]", value) if token.strip())
    elif isinstance(value, Iterable) and not isinstance(value, (str, bytes, Mapping)):
        yield from value
    elif value not in (None, ""):
        yield value


def extract_activity_references(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    """Return de-duplicated canonical activity references from a spot/target."""
    items: list[dict[str, str]] = []

    raw_items = payload.get("reference_items") or payload.get("references") or []
    if isinstance(raw_items, str):
        raw_items = [token.strip() for token in raw_items.split(",") if token.strip()]
    for raw in raw_items if isinstance(raw_items, Iterable) else []:
        if isinstance(raw, Mapping):
            item = _reference_item(
                raw.get("type") or raw.get("program") or raw.get("reference_type") or raw.get("kind"),
                raw.get("reference_id") or raw.get("reference") or raw.get("id") or raw.get("ref"),
                status=raw.get("status") or raw.get("reference_status"),
                need_reason=raw.get("need_reason") or raw.get("reference_need_reason"),
            )
        else:
            item = _reference_item("CUSTOM", raw)
        if item:
            items.append(item)

    direct_fields = {
        "POTA": ("pota", "pota_ref", "pota_reference"),
        "SOTA": ("sota", "sota_ref", "sota_reference"),
        "IOTA": ("iota", "iota_ref", "iota_reference"),
        "WWFF": ("wwff", "wwff_ref", "wwff_reference"),
        "WWBOTA": ("wwbota", "bota", "bunker", "bunker_ref"),
        "ARLHS": ("arlhs", "lighthouse", "lighthouse_ref"),
    }
    for program, keys in direct_fields.items():
        value = next((payload.get(key) for key in keys if payload.get(key) not in (None, "")), None)
        for reference in _iter_values(value):
            item = _reference_item(program, reference)
            if item:
                items.append(item)

    sig_program = canonical_reference_program(payload.get("sig"))
    if sig_program in HUNTER_PROGRAMS:
        for reference in _iter_values(payload.get("sig_info")):
            item = _reference_item(sig_program, reference)
            if item:
                items.append(item)

    tags = payload.get("activity_tags") or []
    if isinstance(tags, Iterable) and not isinstance(tags, (str, bytes, Mapping)):
        for tag in tags:
            if not isinstance(tag, Mapping):
                continue
            program = canonical_reference_program(tag.get("type"))
            reference = tag.get("ref_id") or tag.get("reference")
            if program not in HUNTER_PROGRAMS or not reference:
                continue
            item = _reference_item(program, reference)
            if item:
                items.append(item)

    comment = str(payload.get("comment") or payload.get("message") or payload.get("notes") or "").upper()
    special_text = " ".join(
        str(value or "").upper()
        for value in (payload.get("special"), payload.get("special_tags"), comment)
    )
    patterns: list[tuple[str, re.Pattern[str], bool]] = [
        ("SOTA", _SOTA_RE, True),
        ("IOTA", _IOTA_RE, True),
        ("WWFF", _WWFF_RE, True),
        ("WWBOTA", _WWBOTA_RE, True),
        ("POTA", _POTA_RE, "POTA" in special_text),
        ("ARLHS", _ARLHS_RE, "ARLHS" in special_text or "LIGHTHOUSE" in special_text or "ILLW" in special_text),
    ]
    occupied: set[str] = set()
    for program, pattern, enabled in patterns:
        if not enabled:
            continue
        for match in pattern.findall(comment):
            reference = str(match).upper()
            # EU-123 is IOTA, XXFF-1234 is WWFF, and B/XX-1234 is WWBOTA;
            # do not let the deliberately broad POTA/ARLHS patterns steal them.
            if reference in occupied:
                continue
            item = _reference_item(program, reference)
            if item:
                items.append(item)
                occupied.add(reference)

    deduped: dict[tuple[str, str], dict[str, str]] = {}
    for item in items:
        key = (item["type"], item["reference_id"])
        existing = deduped.get(key, {})
        deduped[key] = {**existing, **item}
    return list(deduped.values())


def reference_items_to_qso_fields(reference_items: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Map hunted references to Wavelog/ADIF fields for the contacted station."""
    grouped: dict[str, list[str]] = {}
    for raw in reference_items or []:
        program = canonical_reference_program(raw.get("type") or raw.get("program"))
        reference = str(raw.get("reference_id") or raw.get("reference") or raw.get("id") or "").strip().upper()
        if program and reference and reference not in grouped.setdefault(program, []):
            grouped[program].append(reference)

    fields: dict[str, str] = {}
    for program, field in (("POTA", "pota"), ("SOTA", "sota"), ("IOTA", "iota"), ("WWFF", "wwff")):
        if grouped.get(program):
            fields[field] = ",".join(grouped[program])

    for program in ("WWBOTA", "ARLHS"):
        if grouped.get(program):
            fields["sig"] = program
            fields["sig_info"] = ",".join(grouped[program])
            break
    return fields
