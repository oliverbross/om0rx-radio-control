from services import qso_logging


def _qso(**overrides):
    value = {
        "provider": "mshv_auto_dx",
        "callsign": "UN7GGB",
        "band": "17m",
        "mode": "FT8",
        "frequency": 18.100,
        "date": "2026-10-06",
        "time_on": "08:29:01",
    }
    value.update(overrides)
    return value


def test_recent_mshv_repeat_matches_same_call_band_mode_within_ten_minutes(monkeypatch):
    monkeypatch.setattr(
        qso_logging,
        "_get_recent_qsos_from_duckdb",
        lambda call, limit: [{
            "call": call,
            "qso_date": "20261006",
            "time_on": "082800",
            "band": "17m",
            "mode": "FT8",
        }],
    )

    result = qso_logging._recent_mshv_repeat_entry(_qso())

    assert result is not None
    assert result["mshv_repeat_suppressed"] is True
    assert result["age_seconds"] == 61


def test_recent_mshv_repeat_does_not_collapse_other_band_mode_provider_or_later_qso(monkeypatch):
    monkeypatch.setattr(
        qso_logging,
        "_get_recent_qsos_from_duckdb",
        lambda call, limit: [{
            "call": call,
            "qso_date": "20261006",
            "time_on": "082800",
            "band": "17m",
            "mode": "FT8",
        }],
    )

    assert qso_logging._recent_mshv_repeat_entry(_qso(band="20m")) is None
    assert qso_logging._recent_mshv_repeat_entry(_qso(mode="FT4")) is None
    assert qso_logging._recent_mshv_repeat_entry(_qso(provider="wsjtz")) is None
    assert qso_logging._recent_mshv_repeat_entry(_qso(time_on="08:40:01")) is None


def test_recent_mshv_repeat_requires_a_canonical_cache_match(monkeypatch):
    monkeypatch.setattr(qso_logging, "_get_recent_qsos_from_duckdb", lambda call, limit: [])

    assert qso_logging._recent_mshv_repeat_entry(_qso()) is None
