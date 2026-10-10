from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import duckdb
import asyncio

import _bootstrap  # noqa: F401

from radio_control import config
from radio_control.classifier_api import ClassifierAPI
from radio_control.cty_resolvers import CtyDatResolver
from radio_control.qso_status_store import DuckDBQSOStatusStore
from radio_control.spot_classification import (
    call_bandmode_from_lookup,
    classify_call_status,
    classify_dxcc_status,
    dxcc_confirmation_from_lookup,
)
from services.digital_status import call_status_from_recent_qsos


def test_uncertain_live_spots_are_reclassified_without_a_25_row_cutoff():
    from backend.api.spots import _refresh_uncertain_spot_classifications

    class FakeClassifier:
        async def dxcc_overall(self, dxcc, **_kwargs):
            return True, True

        async def dxcc_bandmode_flags(self, dxcc, band, mode, **_kwargs):
            return False, False, True

    spots = [
        {
            "callsign": f"K{i}TEST",
            "dxcc": 291,
            "band": "30m",
            "mode": "FT8",
            "dxcc_status": "Unknown",
        }
        for i in range(30)
    ]

    asyncio.run(
        _refresh_uncertain_spot_classifications(
            SimpleNamespace(classifier=FakeClassifier(), cty_resolver=None),
            spots,
        )
    )

    assert all(spot["dxcc_status"] == "Confirmed" for spot in spots)
    assert all(spot["dxcc_status_source"] == "verified" for spot in spots)


def test_cty_csv_prefix_tokens_do_not_misclassify_u_prefix():
    resolver = CtyDatResolver(
        config.CTY_DAT_PATH,
        csv_path=config.CTY_CSV_PATH,
        ignore_suffixes=config.CTY_IGNORE_SUFFIXES,
    )

    ua3 = resolver.lookup("UA3ARC")
    ri0sp = resolver.lookup("RI0SP")

    assert ua3["country"] == "European Russia"
    assert ua3["dxcc"] == 54
    assert ua3["exact_match"] is False
    assert ri0sp["country"] == "European Russia"
    assert ri0sp["dxcc"] == 54
    assert ri0sp["exact_match"] is True


def test_cty_kg4_three_letter_suffix_is_us_not_guantanamo():
    resolver = CtyDatResolver(
        config.CTY_DAT_PATH,
        csv_path=config.CTY_CSV_PATH,
        ignore_suffixes=config.CTY_IGNORE_SUFFIXES,
    )

    us_call = resolver.lookup("KG4OJT")
    guantanamo_call = resolver.lookup("KG4AB")

    assert us_call["country"] == "United States"
    assert us_call["dxcc"] == 291
    assert us_call["prefix"] == "K"
    assert guantanamo_call["country"] == "Guantanamo Bay"
    assert guantanamo_call["dxcc"] == 105


def test_dxcc_worked_status_comes_from_local_qso_log():
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "qso_log.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE qso_records (
                dxcc INTEGER,
                band VARCHAR,
                mode VARCHAR,
                submode VARCHAR,
                lotw_qsl_rcvd VARCHAR,
                gridsquare VARCHAR
            )
            """
        )
        conn.execute(
            "INSERT INTO qso_records VALUES (54, '17m', 'FT8', NULL, 'N', 'KO85')"
        )
        conn.close()

        store = DuckDBQSOStatusStore(db_path)
        assert store.dxcc_overall(54) == (True, False)
        assert store.dxcc_bandmode_flags(54, "17m", "FT8") == (False, False, False)

        display = classify_dxcc_status(
            worked=True,
            confirmed=False,
            new_band=False,
            new_mode=False,
            bandmode_confirmed=False,
        )
        assert display.status == "Worked"
        assert display.tag == "Need LoTW"


def test_call_status_preserves_new_band_and_mode_slots():
    assert classify_call_status(False, True, True, False) == "New Call"
    assert classify_call_status(True, True, True, False) == "New Band+Mode"
    assert classify_call_status(True, True, False, False) == "New Band"
    assert classify_call_status(True, False, True, False) == "New Mode"
    assert classify_call_status(True, False, False, False) == "Worked"
    assert classify_call_status(True, True, True, True) == "Confirmed"


def test_call_status_uses_wavelog_band_mode_flags():
    worked_same_slot = {
        "call_worked_band": True,
        "call_worked_band_mode": True,
        "call_confirmed_band_mode": False,
    }
    confirmed_same_slot = {
        **worked_same_slot,
        "call_confirmed_band_mode": True,
    }
    new_mode_on_worked_band = {
        "call_worked_band": True,
        "call_worked_band_mode": False,
        "call_confirmed_band_mode": False,
    }

    assert call_bandmode_from_lookup(worked_same_slot) == (False, False, False)
    assert call_bandmode_from_lookup(confirmed_same_slot) == (False, False, True)
    assert call_bandmode_from_lookup(new_mode_on_worked_band) == (False, True, False)


def test_spot_confirmation_accepts_lotw_or_paper_but_not_eqsl():
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "qso_log.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE qso_records (
                call VARCHAR,
                dxcc INTEGER,
                band VARCHAR,
                mode VARCHAR,
                submode VARCHAR,
                lotw_qsl_rcvd VARCHAR,
                eqsl_qsl_rcvd VARCHAR,
                qsl_rcvd VARCHAR,
                gridsquare VARCHAR
            )
            """
        )
        conn.execute(
            "INSERT INTO qso_records VALUES ('HB9AA', 287, '17m', 'FT4', NULL, 'N', 'Y', 'N', 'JN47')"
        )
        conn.execute(
            "INSERT INTO qso_records VALUES ('DL1AA', 230, '20m', 'FT8', NULL, 'N', 'N', 'Y', 'JO62')"
        )
        conn.execute(
            "INSERT INTO qso_records VALUES ('K1VER', 291, '40m', 'CW', NULL, 'N', 'N', 'V', 'FN31')"
        )
        conn.close()

        store = DuckDBQSOStatusStore(db_path)
        assert store.dxcc_overall(287) == (True, False)
        assert store.dxcc_overall(230) == (True, True)
        assert store.dxcc_bandmode_flags(287, "17m", "FT4") == (False, False, False)
        assert store.call_flags("HB9AA", "17m", "FT4") == (True, False, False, False, False)
        assert store.call_flags("DL1AA", "20m", "FT8") == (True, True, False, False, True)
        assert store.call_flags("K1VER", "40m", "CW") == (True, True, False, False, True)


def test_worked_before_date_is_latest_exact_call_band_mode_slot():
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "qso_log.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE qso_records (
                call VARCHAR,
                dxcc INTEGER,
                band VARCHAR,
                mode VARCHAR,
                submode VARCHAR,
                lotw_qsl_rcvd VARCHAR,
                eqsl_qsl_rcvd VARCHAR,
                qsl_rcvd VARCHAR,
                gridsquare VARCHAR,
                time_on TIMESTAMP
            )
            """
        )
        conn.executemany(
            "INSERT INTO qso_records VALUES (?, 150, ?, ?, ?, 'N', 'N', 'N', 'PH57', ?)",
            [
                ("VK8NSB", "20m", "DATA", "FT8", "2025-02-03 12:00:00"),
                ("vk8nsb", "20M", "DATA", "FT8", "2026-07-17 19:30:00"),
                ("VK8NSB", "20m", "SSB", None, "2026-07-18 08:00:00"),
                ("VK8NSB", "15m", "DATA", "FT8", "2026-07-18 09:00:00"),
            ],
        )
        conn.close()

        store = DuckDBQSOStatusStore(db_path)
        assert store.worked_before_date("vk8nsb", "20M", "ft8") == "20260717"
        assert store.worked_before_date("VK8NSB", "20m", "SSB") == "20260718"
        assert store.worked_before_date("VK8NSB", "15m", "FT8") == "20260718"
        assert store.worked_before_date("VK8NSB", "30m", "FT8") is None

        store.record_qso(
            {
                "callsign": "VK8NSB",
                "band": "20m",
                "mode": "FT8",
                "qso_date": "20260718",
            }
        )
        assert store.worked_before_date("VK8NSB", "20m", "FT8") == "20260718"


def test_call_confirmation_uses_local_lotw_paper_policy_not_wavelog_defaults():
    class FakeWavelogAPI:
        async def private_lookup(self, callsign, band=None, mode=None):
            return {
                "success": True,
                "data": {
                    "callsign": callsign,
                    "call_worked": True,
                    "call_confirmed": True,
                    "call_worked_band": True,
                    "call_worked_band_mode": True,
                    "call_confirmed_band_mode": True,
                },
            }

    class LotwPaperStatusStore:
        def call_flags(self, callsign, band, mode):
            return True, False, False, False, False

    classifier = ClassifierAPI(
        api_client=FakeWavelogAPI(),
        qso_status_store=LotwPaperStatusStore(),
    )

    flags = asyncio.run(classifier.call_status_flags("ZS5JY", "20m", "SSB"))
    assert flags == (True, True, False, False, False)
    assert classify_call_status(flags[0], flags[2], flags[3], flags[4]) == "Worked"


def test_special_extraction_requires_reliable_reference_patterns():
    from radio_control.spot_processor import extract_special

    assert extract_special("Walk for the Beacon 1041Z") == ""
    assert extract_special("WFF generic text without a reference") == ""
    assert extract_special("LH copy weak abbreviation") == ""
    assert extract_special("POTA K-1234") == "POTA"
    assert extract_special("WWFF VKFF-1000") == "WWFF"
    assert extract_special("SOTA OM/BA-001") == "SOTA"


def test_private_lookup_dxcc_fields_are_confirmation_only():
    confirmed, band_confirmed, bandmode_confirmed = dxcc_confirmation_from_lookup(
        {
            "dxcc_confirmed": False,
            "dxcc_confirmed_on_band": False,
            "dxcc_confirmed_on_band_mode": False,
        }
    )

    assert (confirmed, band_confirmed, bandmode_confirmed) == (False, False, False)


async def _classifier_dxcc_status(db_path: Path):
    classifier = ClassifierAPI(api_client=None, qso_status_store=DuckDBQSOStatusStore(db_path))
    return await classifier.dxcc_overall(54, callsign="RI0SP")


def test_classifier_uses_qso_log_for_dxcc_worked_status():
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "qso_log.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE qso_records (
                dxcc INTEGER,
                band VARCHAR,
                mode VARCHAR,
                submode VARCHAR,
                lotw_qsl_rcvd VARCHAR,
                gridsquare VARCHAR
            )
            """
        )
        conn.execute(
            "INSERT INTO qso_records VALUES (54, '17m', 'FT8', NULL, 'N', 'KO85')"
        )
        conn.close()

        assert asyncio.run(_classifier_dxcc_status(db_path)) == (True, False)


def test_grid_worked_status_comes_from_local_qso_log():
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "qso_log.duckdb"
        conn = duckdb.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE qso_records (
                dxcc INTEGER,
                band VARCHAR,
                mode VARCHAR,
                submode VARCHAR,
                lotw_qsl_rcvd VARCHAR,
                gridsquare VARCHAR
            )
            """
        )
        conn.execute("INSERT INTO qso_records VALUES (NULL, '20m', 'FT8', NULL, 'N', 'JN88TQ')")
        conn.close()

        store = DuckDBQSOStatusStore(db_path)
        assert store.grid_flags("JN88AA", "20m", "FT8") == (False, False, False)
        assert store.grid_flags("JN88AA", "15m", "FT8") == (False, True, False)
        assert store.grid_flags("JO70", "20m", "FT8") == (True, True, True)


def test_qso_status_store_records_new_logged_qso_in_memory():
    store = DuckDBQSOStatusStore()

    changed = store.record_qso({
        "callsign": " ea1aa ",
        "band": "20m",
        "mode": "FT8",
        "gridsquare": "IN80aa",
        "dxcc": 281,
    })

    assert changed is True
    assert store.call_flags("EA1AA", "20m", "FT8") == (True, False, False, False, False)
    assert ("EA1AA", "20m", "FT8") in store.call_bandmode_worked
    assert store.dxcc_overall(281) == (True, False)
    assert store.dxcc_bandmode_flags(281, "20m", "FT8") == (False, False, False)
    assert store.grid_flags("IN80ZZ", "20m", "FT8") == (False, False, False)


class _UnavailableStatusStore:
    def dxcc_overall(self, dxcc):
        return None

    def dxcc_bandmode_flags(self, dxcc, band, mode):
        return None


def test_classifier_does_not_invent_atno_when_worked_cache_unavailable():
    classifier = ClassifierAPI(api_client=None, qso_status_store=_UnavailableStatusStore())

    assert asyncio.run(
        classifier.dxcc_overall(279, callsign="MM3WYM", allow_unconfirmed_fallback=False)
    ) is None
    assert asyncio.run(
        classifier.dxcc_bandmode_flags(
            279,
            "20m",
            "FT8",
            callsign="MM3WYM",
            allow_unconfirmed_fallback=False,
        )
    ) is None


def test_digital_status_recent_qso_is_band_and_mode_slot_aware(monkeypatch):
    import services.qso_logging as qlog

    def fake_wavelog_db(callsign, limit):
        return [
            {
                "call": callsign,
                "band": "20m",
                "mode": "FT8",
                "lotw_qsl": "N",
            }
        ]

    monkeypatch.setattr(qlog, "_get_recent_qsos_from_wavelog_db", fake_wavelog_db)

    assert asyncio.run(call_status_from_recent_qsos("IT9FJE", "20m", "FT8")) == "Worked"
    assert asyncio.run(call_status_from_recent_qsos("IT9FJE", "20m", "SSB")) == "New Mode"
    assert asyncio.run(call_status_from_recent_qsos("IT9FJE", "15m", "FT8")) == "New Band"
    assert asyncio.run(call_status_from_recent_qsos("IT9FJE", "15m", "SSB")) == "New Band+Mode"


def test_digital_status_accepts_paper_qsl_confirmation(monkeypatch):
    import services.qso_logging as qlog

    monkeypatch.setattr(
        qlog,
        "_get_recent_qsos_from_wavelog_db",
        lambda callsign, limit: [
            {
                "call": callsign,
                "band": "20m",
                "mode": "SSB",
                "lotw_qsl": "N",
                "qsl_rcvd": "Y",
                "eqsl_qsl_rcvd": "N",
            }
        ],
    )

    assert asyncio.run(call_status_from_recent_qsos("ZS5JY", "20m", "SSB")) == "Confirmed"


if __name__ == "__main__":
    test_cty_csv_prefix_tokens_do_not_misclassify_u_prefix()
    test_dxcc_worked_status_comes_from_local_qso_log()
    test_private_lookup_dxcc_fields_are_confirmation_only()
    test_classifier_uses_qso_log_for_dxcc_worked_status()
    test_classifier_does_not_invent_atno_when_worked_cache_unavailable()
    print("spot classification smoke checks passed")
