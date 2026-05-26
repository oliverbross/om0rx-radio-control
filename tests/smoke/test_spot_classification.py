from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb

import _bootstrap  # noqa: F401

from radio_control import config
from radio_control.classifier_api import ClassifierAPI
from radio_control.cty_resolvers import CtyDatResolver
from radio_control.qso_status_store import DuckDBQSOStatusStore
from radio_control.spot_classification import (
    classify_dxcc_status,
    dxcc_confirmation_from_lookup,
)


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
                lotw_qsl_rcvd VARCHAR
            )
            """
        )
        conn.execute(
            "INSERT INTO qso_records VALUES (54, '17m', 'FT8', NULL, 'N')"
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
                lotw_qsl_rcvd VARCHAR
            )
            """
        )
        conn.execute(
            "INSERT INTO qso_records VALUES (54, '17m', 'FT8', NULL, 'N')"
        )
        conn.close()

        import asyncio

        assert asyncio.run(_classifier_dxcc_status(db_path)) == (True, False)


if __name__ == "__main__":
    test_cty_csv_prefix_tokens_do_not_misclassify_u_prefix()
    test_dxcc_worked_status_comes_from_local_qso_log()
    test_private_lookup_dxcc_fields_are_confirmation_only()
    test_classifier_uses_qso_log_for_dxcc_worked_status()
    print("spot classification smoke checks passed")
