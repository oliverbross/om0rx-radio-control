#!/usr/bin/env python3
"""Debug the sync issue - check what wavelog_ids are in DuckDB vs being fetched"""

import pymysql
from config import WAVELOG_CONFIG

def check_sync_issue():
    """Check what's happening with the sync"""
    
    # Connect to Wavelog
    wavelog_conn = pymysql.connect(**WAVELOG_CONFIG)
    
    print("\n=== WAVELOG DATABASE CHECK ===")
    with wavelog_conn.cursor() as cursor:
        # Get total QSOs
        cursor.execute("SELECT COUNT(*) FROM TABLE_HRD_CONTACTS_V01 WHERE station_id = 1")
        total = cursor.fetchone()[0]
        print(f"Total QSOs in Wavelog: {total}")
        
        # Get min/max wavelog IDs
        cursor.execute("SELECT MIN(COL_PRIMARY_KEY), MAX(COL_PRIMARY_KEY) FROM TABLE_HRD_CONTACTS_V01 WHERE station_id = 1")
        min_id, max_id = cursor.fetchone()
        print(f"Wavelog ID range: {min_id} - {max_id}")
        
        # Check records at offset 3000 (what's currently being fetched)
        cursor.execute("""
            SELECT COL_PRIMARY_KEY, COL_CALL, COL_QSO_DATE, COL_TIME_ON
            FROM TABLE_HRD_CONTACTS_V01
            WHERE station_id = 1
            ORDER BY last_modified ASC, COL_PRIMARY_KEY ASC
            LIMIT 10 OFFSET 3000
        """)
        
        print("\n📥 Records at offset 3000 (what sync is trying to fetch):")
        for row in cursor.fetchall():
            print(f"  wavelog_id={row[0]}, call={row[1]}, date={row[2]}, time={row[3]}")
    
    wavelog_conn.close()
    
    print("\n=== DUCKDB CHECK (via HTTP API) ===")
    import requests
    try:
        # Query through the API to avoid locking issues
        response = requests.get("http://localhost:8000/api/qso/query", params={
            "limit": 10,
            "sort": "wavelog_id",
            "order": "desc"
        }, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            print(f"Total QSOs in DuckDB (from API): {data.get('total', 'N/A')}")
            print("\n📊 Last 10 wavelog_ids in DuckDB:")
            for qso in data.get('qsos', [])[:10]:
                print(f"  wavelog_id={qso.get('wavelog_id')}, call={qso.get('call')}")
        else:
            print(f"❌ API returned status {response.status_code}")
    except Exception as e:
        print(f"❌ Could not query API: {e}")
        print("\n💡 Make sure backend is running on http://localhost:8000")

if __name__ == "__main__":
    check_sync_issue()