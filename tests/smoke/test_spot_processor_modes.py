import _bootstrap  # noqa: F401

from datetime import UTC, datetime, timedelta

from radio_control.spot_processor import band_from_khz, classify_spot_source, infer_mode
from radio_control.spot_intelligence import extract_rbl_snr, score_spot
from radio_control.spots_logger import SpotsLogger
from radio_control.cluster_commands import build_rbl_command_plan
from radio_control.spot_aggregation import live_spot_key, upsert_live_spot
from radio_control.local_heard import correlate_local_heard


def test_infer_mode_keeps_ft4_spots_visible():
    assert infer_mode("FT4 +03dB from JN53", "20m", 14080.0) == "FT4"
    assert infer_mode("", "40m", 7047.5) == "FT4"


def test_infer_mode_detects_ft2_from_comment_and_frequency():
    assert infer_mode("Trying FT2", "6m", 50320.0) == "FT2"
    assert infer_mode("", "6m", 50320.0) == "FT2"


def test_infer_mode_does_not_let_ft2_comment_override_explicit_ft8():
    assert infer_mode("FT8 Anyone want to try FT2 in ES", "6m", 50313.0) == "FT8"


def test_band_from_khz_keeps_six_meter_ft2_in_band():
    assert band_from_khz(50320.0) == "6m"


def test_rbl_spots_are_classified_from_skimmer_spotter():
    assert classify_spot_source("OM0RX-#", "CQ", "CW") == ("rbl", "CW")
    assert classify_spot_source("OM0RX", "RBN FT8 -12 dB", "FT8") == ("rbl", "DIGI")
    assert classify_spot_source("OM0RX", "normal comment", "SSB") == ("cluster", "")


def test_rbl_mode_filter_does_not_hide_cluster_spots(tmp_path):
    db_path = tmp_path / "spots.duckdb"
    now = datetime.now(UTC)

    with SpotsLogger(str(db_path)) as logger:
        assert logger.log_spot({
            "spotter": "OM0RX",
            "dxcall": "K1ABC",
            "freq_khz": 14025.0,
            "comment": "CQ",
            "timestamp": now,
        })
        assert logger.log_spot({
            "spotter": "OM0RX-#",
            "dxcall": "K1RBL",
            "freq_khz": 14026.0,
            "comment": "CQ",
            "timestamp": now + timedelta(seconds=1),
        })
        assert logger.log_spot({
            "spotter": "OM0RX-#",
            "dxcall": "N1DIGI",
            "freq_khz": 14074.0,
            "comment": "FT8",
            "timestamp": now + timedelta(seconds=2),
        })

        visible = logger.get_filtered_spots(
            limit=10,
            spot_sources=["cluster", "rbl"],
            rbl_mode_groups=["CW"],
        )

    calls = {spot["callsign"] for spot in visible}
    assert calls == {"K1ABC", "K1RBL"}


def test_filtered_spots_can_limit_to_recent_window(tmp_path):
    db_path = tmp_path / "spots.duckdb"
    now = datetime.now(UTC)

    with SpotsLogger(str(db_path)) as logger:
        assert logger.log_spot({
            "spotter": "OM0RX",
            "dxcall": "K1OLD",
            "freq_khz": 14025.0,
            "comment": "CW",
            "timestamp": now - timedelta(hours=3),
        })
        assert logger.log_spot({
            "spotter": "OM0RX",
            "dxcall": "K1NEW",
            "freq_khz": 14026.0,
            "comment": "CW",
            "timestamp": now - timedelta(minutes=10),
        })

        visible = logger.get_filtered_spots(
            limit=10,
            spot_sources=["cluster"],
            max_age_minutes=60,
        )

    calls = {spot["callsign"] for spot in visible}
    assert calls == {"K1NEW"}


def test_spot_intelligence_scores_and_extracts_snr():
    assert extract_rbl_snr("CW 13dB Q:9") == 13
    assert extract_rbl_snr("RBN FT8 -12 dB") == -12

    score, reasons = score_spot({
        "call_status": "New Call",
        "dxcc_status": "ATNO",
        "spot_source": "rbl",
        "comment": "CW 18dB",
    })
    assert score == 100
    assert "ATNO" in reasons
    assert "new call" in reasons


def test_rbl_noise_filters_keep_cluster_and_trim_rbl(tmp_path):
    db_path = tmp_path / "spots.duckdb"
    now = datetime.now(UTC)

    with SpotsLogger(str(db_path)) as logger:
        assert logger.log_spot({
            "spotter": "OM0RX",
            "dxcall": "K1CLUSTER",
            "freq_khz": 14200.0,
            "comment": "SSB",
            "timestamp": now,
        })
        assert logger.log_spot({
            "spotter": "OM0RX-#",
            "dxcall": "K1WEAK",
            "freq_khz": 14025.0,
            "comment": "CW -5dB Q:1",
            "timestamp": now + timedelta(seconds=1),
        })
        assert logger.log_spot({
            "spotter": "OM0RX-#",
            "dxcall": "K1STRONG",
            "freq_khz": 14026.0,
            "comment": "CW 12dB Q:8",
            "timestamp": now + timedelta(seconds=2),
        })
        assert logger.log_spot({
            "spotter": "K1TTT-#",
            "dxcall": "K1STRONG",
            "freq_khz": 14026.2,
            "comment": "CW 15dB Q:8",
            "timestamp": now + timedelta(seconds=30),
        })

        visible = logger.get_filtered_spots(
            limit=10,
            rbl_min_snr=10,
            rbl_dedupe_minutes=5,
        )

    calls = [spot["callsign"] for spot in visible]
    assert "K1CLUSTER" in calls
    assert "K1WEAK" not in calls
    assert calls.count("K1STRONG") == 1


def test_cluster_rbl_command_profiles_support_custom_modes():
    profile, commands = build_rbl_command_plan(
        True,
        modes=["CW", "DIGI"],
        profile_name="custom",
        configured_profiles={
            "custom": {
                "enable": "set/skimmer",
                "disable": "unset/skimmer",
                "modes": {"CW": "accept/skimmer cw", "DIGI": "accept/skimmer digi"},
            }
        },
    )
    assert profile == "custom"
    assert commands == ["set/skimmer", "accept/skimmer cw", "accept/skimmer digi"]


def test_repair_spot_metadata_recomputes_rbl_and_ft2(tmp_path):
    db_path = tmp_path / "spots.duckdb"
    now = datetime.now(UTC)

    with SpotsLogger(str(db_path)) as logger:
        assert logger.log_spot({
            "spotter": "OM0RX-#",
            "dxcall": "K1FT2",
            "freq_khz": 50320.0,
            "comment": "Trying FT2",
            "timestamp": now,
        })
        logger.conn.execute(
            "UPDATE spots SET band = '20m', mode = 'SSB', spot_source = 'cluster', rbl_mode_group = NULL"
        )
        logger.conn.commit()

        dry_run = logger.repair_spot_metadata(limit=1, dry_run=True)
        repaired = logger.repair_spot_metadata(limit=1, dry_run=False)
        row = logger.conn.execute(
            "SELECT band, mode, spot_source, rbl_mode_group FROM spots LIMIT 1"
        ).fetchone()

    assert dry_run["updated"] == 0
    assert repaired["updated"] == 1
    assert repaired["rbl_rows"] == 1
    assert repaired["ft2_rows"] == 1
    assert row == ("6m", "FT2", "rbl", "DIGI")


def test_live_rbl_spots_are_aggregated_by_call_band_mode():
    cache = []
    first = {
        "callsign": "K1ABC",
        "band": "20m",
        "mode": "CW",
        "spot_source": "rbl",
        "spotter": "OM0RX-#",
        "timestamp": 100.0,
        "comment": "CW 5dB",
    }
    second = {
        "callsign": "K1ABC",
        "band": "20m",
        "mode": "CW",
        "spot_source": "rbl",
        "spotter": "K1TTT-#",
        "timestamp": 110.0,
        "comment": "CW 14dB",
    }

    inserted, was_merged = upsert_live_spot(cache, first)
    merged, was_merged_second = upsert_live_spot(cache, second)

    assert live_spot_key(first) == "rbl:K1ABC:20M:CW"
    assert inserted is merged
    assert not was_merged
    assert was_merged_second
    assert len(cache) == 1
    assert cache[0]["aggregate_count"] == 2
    assert cache[0]["aggregate_spotter_count"] == 2
    assert cache[0]["aggregate_best_snr"] == 14
    assert cache[0]["aggregate_last_timestamp"] == 110.0


def test_local_heard_correlation_marks_matching_decoded_call():
    now = datetime.now(UTC)
    spot = {
        "callsign": "K1ABC",
        "band": "20m",
        "mode": "FT8",
        "call_status": "New Call",
        "dxcc_status": "Confirmed",
    }
    correlate_local_heard(
        spot,
        [
            {
                "timestamp": now.isoformat(),
                "message": "CQ K1ABC FN42",
                "snr": -7,
                "mode": "FT8",
            }
        ],
        mycall="OM0RX",
    )
    score, reasons = score_spot(spot)

    assert spot["local_heard"] is True
    assert spot["local_heard_snr"] == -7
    assert any("heard locally" in reason for reason in reasons)
    assert score >= 70
