from datetime import UTC, datetime, timedelta
import json

from services.mshv_cluster_watch import (
    build_dxpedition_watch,
    classify_cluster_spot,
    publish_repository_dxpedition_watch,
    write_dxpedition_watch,
)


NOW = datetime(2026, 10, 5, 20, 0, tzinfo=UTC)


def _active(**overrides):
    row = {
        "callsign": "A31WW",
        "aliases": ["A31WW", "A31DX"],
        "status": "ACTIVE",
        "start_date_utc": "2026-10-01",
        "end_date_utc": "2026-10-10",
        "bands": ["20m", "15"],
        "modes": ["FT8", "CW"],
        "source_id": "NG3K_ADXO",
    }
    row.update(overrides)
    return row


def test_watch_contract_filters_dates_modes_and_deduplicates_aliases():
    payload = build_dxpedition_watch([
        _active(),
        _active(callsign="A31DX", aliases=["A31DX"], source_id="DXCAL_ICS"),
        _active(callsign="OLD1AA", aliases=[], status="EXPIRED"),
        _active(callsign="CW1AA", aliases=[], modes=["CW"]),
        _active(callsign="FUT1AA", aliases=[], status="UPCOMING", start_date_utc="2026-11-01"),
    ], now=NOW, max_spot_age_seconds=120)

    assert payload["schema"] == 1
    assert payload["spot_max_age_seconds"] == 120
    assert payload["watch_max_age_seconds"] == 86400
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["aliases"] == ["A31WW", "A31DX"]
    assert payload["entries"][0]["bands"] == ["20m", "15m"]
    assert payload["entries"][0]["modes"] == ["FT8"]


def test_cluster_spot_requires_explicit_ft8_freshness_band_and_exact_frequency_key():
    watch = build_dxpedition_watch([_active()], now=NOW)
    base = {
        "callsign": "A31DX",
        "mode": "FT8",
        "frequency_hz": 14_090_000,
        "timestamp_utc": (NOW - timedelta(seconds=119)).isoformat(),
    }

    accepted = classify_cluster_spot(base, watch, now=NOW)
    assert accepted["accepted"] is True
    assert accepted["dedupe_key"] == "A31DX@20m@140900"
    assert classify_cluster_spot({**base, "mode": ""}, watch, now=NOW)["reason"] == "mode-not-explicit-ft8-ft4"
    assert classify_cluster_spot(
        {**base, "timestamp_utc": (NOW - timedelta(seconds=121)).isoformat()}, watch, now=NOW,
    )["reason"] == "spot-stale"
    assert classify_cluster_spot({**base, "frequency_hz": 7_056_000}, watch, now=NOW)["reason"] == "dxpedition-band-mismatch"

    nearby = classify_cluster_spot({**base, "frequency_hz": 14_090_049}, watch, now=NOW)
    other_operation = classify_cluster_spot({**base, "frequency_hz": 14_095_000}, watch, now=NOW)
    assert nearby["dedupe_key"] == accepted["dedupe_key"]
    assert other_operation["dedupe_key"] != accepted["dedupe_key"]

    stale_watch = {**watch, "generated_at_utc": (NOW - timedelta(days=2)).isoformat()}
    assert classify_cluster_spot(base, stale_watch, now=NOW)["reason"] == "watch-stale"
    assert classify_cluster_spot(base, {**watch, "schema": 2}, now=NOW)["reason"] == "watch-schema-invalid"


def test_watch_and_spot_contract_accepts_ft4_as_a_distinct_mode():
    watch = build_dxpedition_watch([
        _active(modes=["FT4"], bands=["40m"]),
    ], now=NOW)
    assert watch["entries"][0]["modes"] == ["FT4"]
    accepted = classify_cluster_spot({
        "callsign": "A31DX",
        "mode": "FT4",
        "frequency_hz": 7_047_000,
        "timestamp_utc": NOW.isoformat(),
    }, watch, now=NOW)
    assert accepted["accepted"] is True
    assert accepted["band"] == "40m"
    assert classify_cluster_spot({
        "callsign": "A31DX",
        "mode": "FT8",
        "frequency_hz": 7_047_000,
        "timestamp_utc": NOW.isoformat(),
    }, watch, now=NOW)["reason"] == "dxpedition-mode-mismatch"


def test_watch_publish_is_atomic_json(tmp_path):
    target = tmp_path / "settings" / "database" / "dxpedition_watch.json"
    payload = write_dxpedition_watch(target, [_active()], now=NOW)
    assert json.loads(target.read_text(encoding="utf-8")) == payload
    assert not list(target.parent.glob("*.tmp"))


def test_repository_publish_uses_canonical_mutable_path_and_trusted_sources(tmp_path):
    class Repository:
        def active_dxpeditions(self, limit):
            assert limit == 500
            return [_active(), _active(callsign="BAD1AA", source_id="UNREVIEWED_WEB")]

    published = publish_repository_dxpedition_watch(Repository(), tmp_path, now=NOW)
    target = tmp_path / "settings" / "database" / "dxpedition_watch.json"
    assert published["path"] == str(target)
    assert [entry["callsign"] for entry in published["watch"]["entries"]] == ["A31WW"]
    assert json.loads(target.read_text(encoding="utf-8")) == published["watch"]
