from radio_control import config
from radio_control.postgres_store import get_postgres_dsn, should_use_postgres


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
