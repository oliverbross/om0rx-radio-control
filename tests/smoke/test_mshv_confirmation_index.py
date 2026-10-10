import json

from radio_control.qso_status_store import DuckDBQSOStatusStore


def test_confirmation_index_uses_spots_wavelog_facts(monkeypatch):
    store = DuckDBQSOStatusStore()
    monkeypatch.setattr(store, "_ensure_loaded", lambda: True)
    store.dxcc_confirmed = {291, 390}
    store.call_confirmed = {"TA3XEE"}
    store.dxcc_bandmode_confirmed = {(390, "20m", "FT8")}
    store.call_bandmode_confirmed = {("TA3XEE", "20m", "FT8")}

    lines = store.mshv_confirmation_index()

    assert "DXCC|291" in lines
    assert "DXCC_BAND_MODE|390|8|FT8" in lines
    assert "CALL|TA3XEE" in lines
    assert "CALL_BAND_MODE|TA3XEE|8|FT8" in lines


def test_confirmation_index_fails_closed_without_wavelog(monkeypatch):
    store = DuckDBQSOStatusStore()
    monkeypatch.setattr(store, "_ensure_loaded", lambda: False)
    assert store.mshv_confirmation_index() is None


def test_us_state_index_pools_ft8_ft4_and_preserves_confirmation(monkeypatch, tmp_path):
    import radio_control.qso_status_store as status_store

    store = DuckDBQSOStatusStore()
    monkeypatch.setattr(store, "_ensure_loaded", lambda: True)
    monkeypatch.setattr(status_store.config, "DATA_DIR", tmp_path)
    store.us_state_by_call = {"K1AAA": "MA", "K1BBB": "MA"}
    store.us_state_band_worked_calls = {("MA", "20m"): {"K1AAA", "K1BBB"}}
    store.us_state_band_confirmed_calls = {("MA", "20m"): {"K1AAA"}}

    lines = store.mshv_us_state_index()

    assert "CALL|K1AAA|MA|0|291" in lines
    assert "CALL|K1BBB|MA|0|291" in lines
    assert "WORKED|K1AAA|MA|8|1|291" in lines
    assert "WORKED|K1BBB|MA|8|0|291" in lines


def test_us_state_index_rejects_foreign_qrz_state_abbreviations(monkeypatch, tmp_path):
    import radio_control.qso_status_store as status_store

    store = DuckDBQSOStatusStore()
    monkeypatch.setattr(store, "_ensure_loaded", lambda: True)
    monkeypatch.setattr(status_store.config, "DATA_DIR", tmp_path)
    (tmp_path / "qrz_profile_cache.json").write_text(json.dumps({
        "IU7UTX": {"profile": {"country": "Italy", "state": "MT", "lotw": "1"}},
        "K1AAA": {"profile": {"country": "United States", "state": "MA", "lotw": "1"}},
    }), encoding="utf-8")

    lines = store.mshv_us_state_index()

    assert not any("IU7UTX" in line for line in lines)
    assert "CALL|K1AAA|MA|1|291" in lines
