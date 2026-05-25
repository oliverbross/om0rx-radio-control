#!/usr/bin/env python3
"""Test if Wavelog records have last_modified"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pymysql
from pymysql.cursors import DictCursor
import config

try:
    # Connect to Wavelog
    conn = pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASS,
        database=config.DB_NAME,
        charset='utf8mb4',
        cursorclass=DictCursor
    )
    
    with conn.cursor() as cursor:
        # Get first 5 records
        cursor.execute("""
            SELECT COL_PRIMARY_KEY, COL_CALL, COL_QSO_DATE, last_modified, creation_date
            FROM TABLE_HRD_CONTACTS_V01
            WHERE station_id = %s
            ORDER BY COL_PRIMARY_KEY ASC
            LIMIT 5
        """, (config.WAVELOG_STATION_ID,))
        
        results = cursor.fetchall()
        
        print(f"📊 Sample Wavelog Records (Station ID: {config.WAVELOG_STATION_ID}):")
        print()
        
        has_null_modified = False
        for rec in results:
            print(f"🔹 ID: {rec['COL_PRIMARY_KEY']} | Call: {rec['COL_CALL']} | Date: {rec['COL_QSO_DATE']}")
            print(f"   last_modified: {rec['last_modified']}")
            print(f"   creation_date: {rec['creation_date']}")
            print()
            
            if rec['last_modified'] is None:
                has_null_modified = True
        
        # Check if ANY records have NULL last_modified
        cursor.execute("""
            SELECT COUNT(*) as total, 
                   SUM(CASE WHEN last_modified IS NULL THEN 1 ELSE 0 END) as null_count
            FROM TABLE_HRD_CONTACTS_V01
            WHERE station_id = %s
        """, (config.WAVELOG_STATION_ID,))
        
        stats = cursor.fetchone()
        print(f"📈 Statistics:")
        print(f"   Total QSOs: {stats['total']}")
        print(f"   NULL last_modified: {stats['null_count']}")
        print(f"   Valid last_modified: {stats['total'] - stats['null_count']}")
        
        if stats['null_count'] > 0:
            print(f"\n⚠️  WARNING: {stats['null_count']} records have NULL last_modified!")
            print("   This could cause sync metadata updates to fail.")
    
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
