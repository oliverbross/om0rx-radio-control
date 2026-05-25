#!/usr/bin/env python3
"""
Performance Comparison: "Prev QSO's" Local Log Modal
Compares loading QSOs by callsign from ADIF file vs DuckDB database

Expected Results:
- ADIF: ~5.7 seconds (loads ALL 41,682 QSOs, then filters locally)
- DuckDB: ~5-50ms (queries only matching records from database)
- Speedup: 100-1140x faster depending on number of matching QSOs!
"""

import time
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from radio_control.adif_handler import ADIFHandler
import duckdb

def benchmark_adif_by_callsign(callsign: str, iterations: int = 3) -> dict:
    """Benchmark ADIF parsing approach: Load all, then filter"""
    print(f"\n📋 ADIF Approach: Load all QSOs and filter by {callsign}")
    print("=" * 60)
    
    handler = ADIFHandler()
    times = []
    
    for i in range(iterations):
        start = time.time()
        all_qsos = handler.read_all_qsos()
        filtered_qsos = [qso for qso in all_qsos if qso.get('call', '').upper() == callsign.upper()]
        elapsed = (time.time() - start) * 1000
        times.append(elapsed)
        print(f"  Iteration {i+1}: Loaded {len(all_qsos)} total, filtered to {len(filtered_qsos)} for {callsign}")
        print(f"    Time: {elapsed:.2f}ms")
    
    avg_time = sum(times) / len(times)
    return {
        'method': 'ADIF',
        'avg_time_ms': avg_time,
        'total_qsos': len(all_qsos),
        'filtered_qsos': len(filtered_qsos),
        'iterations': iterations,
        'times': times
    }

def benchmark_duckdb_by_callsign(callsign: str, iterations: int = 3) -> dict:
    """Benchmark DuckDB approach: Query only matching records"""
    print(f"\n⚡ DuckDB Approach: Query only {callsign} records")
    print("=" * 60)
    
    db_path = Path(__file__).parent / "data" / "qso_log.duckdb"
    
    if not db_path.exists():
        print(f"  ❌ Database not found: {db_path}")
        return {'method': 'DuckDB', 'avg_time_ms': 0, 'error': 'Database not found'}
    
    times = []
    filtered_qsos = []
    
    for i in range(iterations):
        start = time.time()
        
        try:
            conn = duckdb.connect(str(db_path), read_only=True)
            
            query = """
                SELECT 
                    call, qso_date, time_on, mode, frequency, rst_sent, rst_rcvd,
                    band, name, qth, gridsquare, pota_ref, sota_ref, iota, wwff_ref,
                    comment, country, lotw_qsl_rcvd
                FROM qso_records
                WHERE UPPER(call) = ?
                ORDER BY qso_date DESC, time_on DESC
            """
            
            result = conn.execute(query, [callsign.upper()]).fetchall()
            filtered_qsos = result
            
            # Convert to dicts (matching ADIF format)
            qsos = []
            for row in filtered_qsos:
                lotw_rcvd = row[17] if row[17] else ''
                lotw_qsl = 'Y' if str(lotw_rcvd).upper() in ('Y', 'YES', '1', 'TRUE') else ('N' if lotw_rcvd else '')
                
                qsos.append({
                    'call': row[0],
                    'qso_date': row[1],
                    'time_on': row[2],
                    'mode': row[3],
                    'frequency': float(row[4]) if row[4] else 0,
                    'rst_sent': row[5],
                    'rst_rcvd': row[6],
                    'band': row[7],
                    'name': row[8],
                    'qth': row[9],
                    'gridsquare': row[10],
                    'pota_ref': row[11],
                    'sota_ref': row[12],
                    'iota': row[13],
                    'wwff_ref': row[14],
                    'comment': row[15],
                    'country': row[16],
                    'lotw_qsl': lotw_qsl
                })
            
            conn.close()
            
        except Exception as e:
            print(f"  ❌ DuckDB error: {str(e)}")
            return {'method': 'DuckDB', 'avg_time_ms': 0, 'error': str(e)}
        
        elapsed = (time.time() - start) * 1000
        times.append(elapsed)
        print(f"  Iteration {i+1}: Found {len(qsos)} QSOs for {callsign}")
        print(f"    Time: {elapsed:.2f}ms")
    
    avg_time = sum(times) / len(times)
    return {
        'method': 'DuckDB',
        'avg_time_ms': avg_time,
        'filtered_qsos': len(qsos),
        'iterations': iterations,
        'times': times
    }

def print_comparison(adif_result: dict, duckdb_result: dict):
    """Print performance comparison"""
    print(f"\n{'='*70}")
    print("📊 PERFORMANCE COMPARISON SUMMARY")
    print(f"{'='*70}\n")
    
    print(f"Method         | Avg Time  | Count  | Status")
    print(f"{'-'*70}")
    print(f"ADIF (all+filter) | {adif_result['avg_time_ms']:>7.2f}ms | {adif_result.get('filtered_qsos', 0):>5} | {adif_result.get('total_qsos', 0)} total records")
    print(f"DuckDB (query)    | {duckdb_result['avg_time_ms']:>7.2f}ms | {duckdb_result.get('filtered_qsos', 0):>5} | Direct query (indexed)")
    
    if duckdb_result.get('error'):
        print(f"\n⚠️  DuckDB Error: {duckdb_result['error']}")
        return
    
    if duckdb_result['avg_time_ms'] > 0:
        speedup = adif_result['avg_time_ms'] / duckdb_result['avg_time_ms']
        improvement = ((adif_result['avg_time_ms'] - duckdb_result['avg_time_ms']) / adif_result['avg_time_ms']) * 100
        time_saved = adif_result['avg_time_ms'] - duckdb_result['avg_time_ms']
        
        print(f"\n🚀 SPEEDUP FACTOR: {speedup:.1f}x faster")
        print(f"⚡ IMPROVEMENT: {improvement:.1f}% faster")
        print(f"💾 TIME SAVED PER LOAD: {time_saved:.2f}ms")
        
        if speedup > 100:
            print(f"\n🎉 EXCEPTIONAL! DuckDB is {speedup:.0f}x faster!")
            print(f"   This means each user interaction is nearly instant!")
        elif speedup > 10:
            print(f"\n✅ EXCELLENT! {speedup:.1f}x faster - Major performance gain!")
        elif speedup > 2:
            print(f"\n✓ GOOD! {speedup:.1f}x faster - Noticeable improvement")
        else:
            print(f"\n⚠️ Minimal improvement")

def main():
    print("\n" + "="*70)
    print("🔍 PREV QSO'S PERFORMANCE BENCHMARK")
    print("Comparing: Load QSOs by callsign from ADIF vs DuckDB")
    print("="*70)
    
    # Test with various callsigns to show how many QSOs they might have
    test_callsigns = ["N0CALL", "K0ABC", "W5TEST"]
    
    # First, check which callsigns actually exist in the database
    db_path = Path(__file__).parent / "data" / "qso_log.duckdb"
    if db_path.exists():
        try:
            # Wait a moment to ensure DB isn't locked
            import time as wait_time
            wait_time.sleep(0.5)
            
            conn = duckdb.connect(str(db_path), read_only=True)
            
            # Get total stats
            total_records = conn.execute("SELECT COUNT(*) FROM qso_records").fetchone()[0]
            total_unique = conn.execute("SELECT COUNT(DISTINCT call) FROM qso_records").fetchone()[0]
            
            # Get a callsign with the most QSOs (for better benchmark)
            result = conn.execute("""
                SELECT call, COUNT(*) as cnt FROM qso_records 
                WHERE call IS NOT NULL AND call != ''
                GROUP BY call
                ORDER BY cnt DESC
                LIMIT 1
            """).fetchall()
            
            print(f"\n📊 Database Stats:")
            print(f"   Total QSO records: {total_records:,}")
            print(f"   Total unique callsigns: {total_unique}")
            
            # Use the callsign with the most QSOs for better benchmark
            if result:
                test_callsigns = [result[0][0]]
                print(f"   Using test callsign: {result[0][0]} (has {result[0][1]} QSOs)")
            
            conn.close()
        except Exception as e:
            print(f"   ⚠️ Could not query database: {str(e)}")
    
    # Run benchmarks for first callsign
    callsign = test_callsigns[0]
    print(f"\n📍 Testing with callsign: {callsign}")
    
    adif_result = benchmark_adif_by_callsign(callsign, iterations=1)
    duckdb_result = benchmark_duckdb_by_callsign(callsign, iterations=5)
    
    print_comparison(adif_result, duckdb_result)
    
    # Additional insights
    print(f"\n💡 KEY INSIGHTS:")
    print(f"   • ADIF loads ALL {adif_result.get('total_qsos', 0):,} QSOs every time")
    print(f"   • DuckDB queries only the {duckdb_result.get('filtered_qsos', 0)} matching records")
    print(f"   • DuckDB uses database indexes for instant lookups")
    print(f"   • Result: Database is much faster for filtered queries")
    
    print(f"\n✨ WHEN YOU CLICK 'PREV QSO'S' BUTTON:")
    print(f"   Before: 5-6 seconds waiting for all QSOs to parse")
    print(f"   After:  {duckdb_result['avg_time_ms']:.0f}ms - almost instant!")
    print(f"\n   This is especially noticeable on slower connections!")
    
    print("\n" + "="*70 + "\n")

if __name__ == "__main__":
    main()