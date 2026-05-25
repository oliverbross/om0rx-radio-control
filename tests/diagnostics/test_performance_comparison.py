#!/usr/bin/env python
"""
Performance comparison: DuckDB vs ADIF file parsing
Tests the speed improvement of using DuckDB instead of parsing ADIF files
"""

import time
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from adif_handler import ADIFHandler

def test_adif_performance():
    """Measure ADIF file parsing performance"""
    print("=" * 60)
    print("📋 TESTING ADIF FILE PARSING")
    print("=" * 60)
    
    handler = ADIFHandler()
    
    start_time = time.time()
    qsos = handler.read_all_qsos()
    adif_elapsed = time.time() - start_time
    
    print(f"✅ Loaded {len(qsos)} QSOs from ADIF file")
    print(f"⏱️  Time: {adif_elapsed * 1000:.2f}ms ({adif_elapsed:.4f}s)")
    
    return adif_elapsed, len(qsos)


def test_duckdb_performance():
    """Measure DuckDB query performance"""
    print("\n" + "=" * 60)
    print("⚡ TESTING DUCKDB DATABASE")
    print("=" * 60)
    
    try:
        import duckdb
        
        db_path = Path(__file__).parent / "data" / "qso_log.duckdb"
        
        if not db_path.exists():
            print(f"❌ Database not found: {db_path}")
            return None, None
        
        start_time = time.time()
        
        # Connect and query
        conn = duckdb.connect(str(db_path), read_only=True)
        
        query = """
            SELECT 
                COALESCE(call, '') as call,
                COALESCE(qso_date, '') as qso_date,
                COALESCE(time_on, '') as time_on,
                COALESCE(mode, '') as mode,
                COALESCE(frequency, 0) as frequency,
                COALESCE(rst_sent, '') as rst_sent,
                COALESCE(rst_rcvd, '') as rst_rcvd,
                COALESCE(band, '') as band,
                COALESCE(name, '') as name,
                COALESCE(qth, '') as qth,
                COALESCE(gridsquare, '') as gridsquare,
                COALESCE(pota_ref, '') as pota_ref,
                COALESCE(sota_ref, '') as sota_ref,
                COALESCE(iota, '') as iota,
                COALESCE(wwff_ref, '') as wwff_ref,
                COALESCE(comment, '') as comment,
                COALESCE(country, '') as country
            FROM qso_records
            ORDER BY qso_date DESC, time_on DESC
        """
        
        result = conn.execute(query).fetchall()
        
        # Convert to dictionaries (to match ADIF handler)
        qsos = []
        for row in result:
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
                'country': row[16]
            })
        
        conn.close()
        
        duckdb_elapsed = time.time() - start_time
        
        print(f"✅ Loaded {len(qsos)} QSOs from DuckDB")
        print(f"⏱️  Time: {duckdb_elapsed * 1000:.2f}ms ({duckdb_elapsed:.4f}s)")
        
        return duckdb_elapsed, len(qsos)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return None, None


def print_comparison(adif_time, adif_count, duckdb_time, duckdb_count):
    """Print performance comparison"""
    print("\n" + "=" * 60)
    print("📊 PERFORMANCE COMPARISON")
    print("=" * 60)
    
    if adif_time is None or duckdb_time is None:
        print("⚠️  Cannot compare - one or both tests failed")
        return
    
    speedup = adif_time / duckdb_time
    improvement = ((adif_time - duckdb_time) / adif_time) * 100
    
    print(f"\n📋 ADIF Parsing:   {adif_time * 1000:.2f}ms ({adif_count} QSOs)")
    print(f"⚡ DuckDB Query:   {duckdb_time * 1000:.2f}ms ({duckdb_count} QSOs)")
    print(f"\n🚀 Speedup:       {speedup:.1f}x faster")
    print(f"📈 Improvement:   {improvement:.1f}% faster")
    print(f"💾 Time saved:    {(adif_time - duckdb_time) * 1000:.2f}ms per load")
    
    print("\n💡 IMPACT:")
    if speedup > 10:
        print(f"   🔥 DuckDB is {speedup:.0f}x faster! EXCELLENT improvement!")
    elif speedup > 5:
        print(f"   ✅ DuckDB is {speedup:.0f}x faster! Very good improvement!")
    elif speedup > 2:
        print(f"   ✅ DuckDB is {speedup:.0f}x faster! Good improvement!")
    else:
        print(f"   ✓ DuckDB is {speedup:.1f}x faster - modest improvement")


def main():
    print("\n🔬 LOCAL LOG MODAL: PERFORMANCE BENCHMARK")
    print("Comparing ADIF file parsing vs DuckDB database queries\n")
    
    # Test ADIF
    adif_time, adif_count = test_adif_performance()
    
    # Test DuckDB
    duckdb_time, duckdb_count = test_duckdb_performance()
    
    # Compare
    print_comparison(adif_time, adif_count, duckdb_time, duckdb_count)
    
    print("\n" + "=" * 60)
    print("✅ Benchmark complete!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()