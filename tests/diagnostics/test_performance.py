#!/usr/bin/env python3
"""Test filtered search performance after optimization"""

import urllib.request
import json
import time

print("=" * 60)
print("Testing Filtered Search Performance - Database Optimized")
print("=" * 60)

# Test 1: Empty search (all spots)
print("\n1️⃣ Empty filter (all spots, limit 100):")
times = []
for i in range(3):
    try:
        start = time.time()
        req = urllib.request.Request(
            'http://localhost:8000/api/spots/filtered-search',
            data=json.dumps({'limit': 100}).encode(),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
            elapsed = time.time() - start
            times.append(elapsed)
            count = len(data.get('spots', []))
            print(f"   Run {i+1}: {elapsed:.3f}s - {count} spots")
            
            if i == 0 and count > 0:
                s = data['spots'][0]
                print(f"   Sample: {s.get('callsign')} [{s.get('call_status')} / {s.get('dxcc_status')}]")
    except Exception as e:
        print(f"   Error: {e}")

if times:
    avg = sum(times) / len(times)
    print(f"   ✅ Average response time: {avg:.3f}s")
    if avg < 1.0:
        print("   ✅ PERFORMANCE GOOD - Response time < 1 second")
    else:
        print(f"   ⚠️ PERFORMANCE SLOW - Response time {avg:.3f}s (should be < 1s)")

# Test 2: Callsign filter
print("\n2️⃣ Callsign filter (e.g., 6o3t):")
try:
    start = time.time()
    req = urllib.request.Request(
        'http://localhost:8000/api/spots/filtered-search',
        data=json.dumps({'callsign': '6o3t', 'limit': 100}).encode(),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
        elapsed = time.time() - start
        count = len(data.get('spots', []))
        print(f"   Response: {elapsed:.3f}s - {count} spots found")
        if count > 0:
            s = data['spots'][0]
            print(f"   Sample: {s.get('callsign')} [{s.get('call_status')} / {s.get('dxcc_status')}]")
except Exception as e:
    print(f"   Error: {e}")

# Test 3: Band filter
print("\n3️⃣ Band filter (20m):")
try:
    start = time.time()
    req = urllib.request.Request(
        'http://localhost:8000/api/spots/filtered-search',
        data=json.dumps({'bands': ['20m'], 'limit': 50}).encode(),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
        elapsed = time.time() - start
        count = len(data.get('spots', []))
        print(f"   Response: {elapsed:.3f}s - {count} spots found")
except Exception as e:
    print(f"   Error: {e}")

print("\n" + "=" * 60)
print("✅ Optimization testing complete!")
print("=" * 60)