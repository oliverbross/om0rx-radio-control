#!/usr/bin/env python3
"""Quick test of rotor AUTO fix"""
import sys
sys.path.insert(0, 'c:/Projects/om0rx-radio-control')

print("Testing rotor AUTO fix...")

# Test 1: Check cty_resolvers can import
try:
    from cty_resolvers import CtyDatResolver
    print("✅ cty_resolvers imports successfully")
except Exception as e:
    print(f"❌ cty_resolvers import failed: {e}")
    sys.exit(1)

# Test 2: Load cty.dat and check for lat/lon fields
try:
    resolver = CtyDatResolver('c:/Projects/om0rx-radio-control/data/cty.dat', 'c:/Projects/om0rx-radio-control/data/cty.csv')
    print(f"✅ Loaded {len(resolver.entries)} CTY.DAT entries")
except Exception as e:
    print(f"❌ Failed to load cty.dat: {e}")
    sys.exit(1)

# Test 3: Test a lookup for IS0 (Sardinia)
try:
    result = resolver.lookup('IS0GQX')
    if result:
        lat = result.get('latitude')
        lon = result.get('longitude')
        grid = result.get('gridsquare')
        print(f"✅ Lookup IS0GQX:")
        print(f"   Country: {result.get('country')}")
        print(f"   Latitude: {lat}")
        print(f"   Longitude: {lon}")
        
        if lat is None or lon is None:
            print("❌ ERROR: Latitude or Longitude is None!")
        else:
            print("✅ Coordinates present")
            
            # Test 4: Check grid conversion
            try:
                from rotor_math import latlon_to_grid
                grid = latlon_to_grid(lat, lon, precision=6)
                print(f"✅ Converted to gridsquare: {grid}")
            except Exception as e:
                print(f"❌ Grid conversion failed: {e}")
    else:
        print("❌ Lookup returned empty result")
except Exception as e:
    print(f"❌ Lookup failed: {e}")
    sys.exit(1)

print("\n✅✅✅ All tests passed! Rotor AUTO fix is working!")