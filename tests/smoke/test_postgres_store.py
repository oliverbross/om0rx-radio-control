import inspect

from radio_control import config
from radio_control import postgres_store
from radio_control.postgres_store import get_postgres_dsn, get_postgres_dsn_from_values, should_use_postgres


def test_postgres_auto_mode_is_opt_in(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_BACKEND", "auto")
    monkeypatch.setattr(config, "POSTGRES_DSN", "")
    monkeypatch.setattr(config, "POSTGRES_HOST", "")
    monkeypatch.setattr(config, "POSTGRES_DB", "")
    monkeypatch.setattr(config, "POSTGRES_USER", "")

    assert get_postgres_dsn() == ""
    assert should_use_postgres() is False


def test_postgres_explicit_backend_uses_configured_dsn(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_BACKEND", "postgres")
    monkeypatch.setattr(config, "POSTGRES_DSN", "host=localhost dbname=radio user=om0rx")
    monkeypatch.setattr(config, "POSTGRES_HOST", "")
    monkeypatch.setattr(config, "POSTGRES_DB", "")
    monkeypatch.setattr(config, "POSTGRES_USER", "")

    assert get_postgres_dsn() == "host=localhost dbname=radio user=om0rx"
    assert should_use_postgres() is True


def test_postgres_dsn_can_be_built_from_unsaved_form_values():
    dsn = get_postgres_dsn_from_values(
        {
            "POSTGRES_HOST": "127.0.0.1",
            "POSTGRES_PORT": 5433,
            "POSTGRES_DB": "radio",
            "POSTGRES_USER": "om0rx",
            "POSTGRES_PASSWORD": "secret",
        }
    )

    assert dsn == "host=127.0.0.1 port=5433 dbname=radio user=om0rx password=secret"


def test_postgres_explicit_form_dsn_wins_over_split_fields():
    dsn = get_postgres_dsn_from_values(
        {
            "POSTGRES_DSN": "host=db dbname=radio user=om0rx",
            "POSTGRES_HOST": "127.0.0.1",
            "POSTGRES_DB": "ignored",
            "POSTGRES_USER": "ignored",
        }
    )

    assert dsn == "host=db dbname=radio user=om0rx"


def test_postgres_schema_includes_digital_target_queue():
    source = inspect.getsource(postgres_store.initialize_schema)

    assert "CREATE TABLE IF NOT EXISTS digital_targets" in source
    assert "key TEXT PRIMARY KEY" in source
    assert "idx_pg_digital_targets_updated" in source
    assert "idx_pg_digital_targets_band_mode" in source
