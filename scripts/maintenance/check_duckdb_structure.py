import duckdb
import _bootstrap  # noqa: F401
from radio_control import config

db_path = config.LOGS_DIR / 'adif_qsos.duckdb'
conn = duckdb.connect(db_path)

print("Tables in database:")
tables = conn.execute("SELECT table_name FROM information_schema.tables").fetchall()
for table in tables:
    print(f"  - {table[0]}")

# Check if qso_records exists
try:
    count = conn.execute("SELECT COUNT(*) FROM qso_records").fetchone()[0]
    print(f"\nqso_records table has {count} records")
except Exception as e:
    print(f"\nqso_records table not found: {e}")

conn.close()
