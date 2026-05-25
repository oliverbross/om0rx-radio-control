#!/usr/bin/env python3
import sqlite3
import json
import _bootstrap  # noqa: F401
from radio_control import config

db_path = config.DATA_DIR / 'wavelog.db'
try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sync_status")
    row = cursor.fetchone()
    if row:
        print("Sync Status:")
        print(f"  Row: {row}")
        cursor.execute("PRAGMA table_info(sync_status)")
        columns = cursor.fetchall()
        print(f"\n  Columns:")
        for col in columns:
            print(f"    {col[1]}: {col[2]}")
    conn.close()
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
