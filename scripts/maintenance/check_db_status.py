#!/usr/bin/env python3
"""Quick check of DuckDB sync status"""

import duckdb
import time
from pathlib import Path

db_path = Path(__file__).resolve().parent / 'data' / 'qso_log.duckdb'

# Try to open with read-only access
try:
    # Open in read-only mode
    conn = duckdb.connect(db_path, read_only=True)
    
    # Check if table exists
    try:
        result = conn.execute("SELECT COUNT(*) as count FROM qso_records").fetchall()
        count = result[0][0] if result else 0
        print(f"✅ Total records in qso_records: {count}")
        
        # Show recent records
        recent = conn.execute("SELECT call, qso_date, qso_datetime FROM qso_records LIMIT 5").fetchall()
        print(f"\n📝 Recent records:")
        for call, date, dt in recent:
            print(f"   {call} - {date} {dt}")
            
        # Check for 9Y4DG
        result_9y4dg = conn.execute("SELECT COUNT(*) FROM qso_records WHERE call = '9Y4DG'").fetchall()
        count_9y4dg = result_9y4dg[0][0] if result_9y4dg else 0
        print(f"\n🔍 Records for 9Y4DG: {count_9y4dg}")
        
        # Check for OM0AAO
        result_om0aao = conn.execute("SELECT COUNT(*) FROM qso_records WHERE call = 'OM0AAO'").fetchall()
        count_om0aao = result_om0aao[0][0] if result_om0aao else 0
        print(f"🔍 Records for OM0AAO: {count_om0aao}")
        
    except Exception as e:
        print(f"❌ Table error: {e}")
    
    conn.close()
    
except Exception as e:
    print(f"❌ Cannot open database: {e}")
    print("   Database is locked - backend may be writing to it")
