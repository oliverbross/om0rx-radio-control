# PostgreSQL Migration

The app keeps `DATABASE_BACKEND=auto` by default. In auto mode it continues to
use the legacy local cache unless PostgreSQL is explicitly configured.

## Start PostgreSQL

With Docker Desktop running:

```powershell
docker compose -f docker-compose.postgres.yml up -d
```

The development DSN is:

```text
host=127.0.0.1 port=5432 dbname=om0rx_radio_control user=om0rx password=om0rx_local_dev
```

## Configure The App

Use `settings/local_secrets.json`, environment variables, or the config UI:

```json
{
  "DATABASE_BACKEND": "postgres",
  "POSTGRES_DSN": "host=127.0.0.1 port=5432 dbname=om0rx_radio_control user=om0rx password=om0rx_local_dev"
}
```

## Migrate Existing Data

Run from the project root:

```powershell
python scripts/maintenance/migrate_duckdb_to_postgres.py
```

Use `--clear` only when you intentionally want to replace PostgreSQL rows with
the current DuckDB cache contents:

```powershell
python scripts/maintenance/migrate_duckdb_to_postgres.py --clear
```

The migration copies:

- DX spots from `data/spots.duckdb`
- Wavelog QSO cache from `data/qso_log.duckdb`
- Wavelog sync metadata
- Activity Intelligence cache from `data/activity_intelligence.duckdb`

After migration, restart the backend and check `/api/service-health`. The
`Data Store` service should report `PostgreSQL`.
