"""
Quick test to check QTH vs Country data in Wavelog database
"""
import pymysql
from pymysql.cursors import DictCursor
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config

# Connect to database
conn = pymysql.connect(
    host=config.DB_HOST,
    port=config.DB_PORT,
    user=config.DB_USER,
    password=config.DB_PASS,
    database=config.DB_NAME,
    charset='utf8mb4',
    cursorclass=DictCursor
)

# Query recent QSOs to see QTH vs Country
query = """
    SELECT 
        COL_CALL as callsign,
        COL_QTH as qth,
        COL_COUNTRY as country,
        COL_NAME as name
    FROM TABLE_HRD_CONTACTS_V01
    WHERE station_id = 1
    ORDER BY COL_TIME_ON DESC
    LIMIT 20
"""

with conn.cursor() as cursor:
    cursor.execute(query)
    results = cursor.fetchall()
    
    print("\n" + "="*80)
    print("CALLSIGN       | QTH FIELD                  | COUNTRY FIELD              | NAME")
    print("="*80)
    
    for row in results:
        callsign = (row['callsign'] or '').ljust(14)
        qth = (row['qth'] or '(empty)').ljust(26)
        country = (row['country'] or '(empty)').ljust(26)
        name = (row['name'] or '(empty)')
        print(f"{callsign} | {qth} | {country} | {name}")
    
    print("="*80)

conn.close()

print("\n✅ If QTH column shows country names, the database itself has wrong data.")
print("✅ If QTH column shows cities, then it's a frontend display issue.")
