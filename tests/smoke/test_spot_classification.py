from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import asyncio

import _bootstrap  # noqa: F401

from radio_control import config
from radio_control.classifier_api import ClassifierAPI
from radio_control.cty_resolvers import CtyDatResolver
from radio_control.qso_status_store import DuckDBQSOStatusStore
from radio_control.spot_classification import (
    classify_call_status,
    classify_dxcc_status,
    dxcc_confirmation_from_lookup,
)
from services.digital_status import call_status_from_recent_qsos


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


def test_dxcc_confirmed_status_accepts_eqsl_and_paper_qsl():
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
        conn.close()

        store = DuckDBQSOStatusStore(db_path)
        assert store.dxcc_overall(287) == (True, True)
        assert store.dxcc_overall(230) == (True, True)
        assert store.dxcc_bandmode_flags(287, "17m", "FT4") == (False, False, True)
        assert store.call_flags("HB9AA", "17m", "FT4") == (True, True, False, False, True)


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


if __name__ == "__main__":
    test_cty_csv_prefix_tokens_do_not_misclassify_u_prefix()
    test_dxcc_worked_status_comes_from_local_qso_log()
    test_private_lookup_dxcc_fields_are_confirmation_only()
    test_classifier_uses_qso_log_for_dxcc_worked_status()
    test_classifier_does_not_invent_atno_when_worked_cache_unavailable()
    print("spot classification smoke checks passed")
