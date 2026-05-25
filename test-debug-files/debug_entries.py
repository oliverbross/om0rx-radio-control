import sys
sys.path.insert(0, '.')

from cty_resolvers import CtyHybridResolver

resolver = CtyHybridResolver(
    'C:\\Projects\\om0rx-radio-control\\data\\cty.dat',
    'C:\\Projects\\om0rx-radio-control\\data\\cty.csv',
    ignore_suffixes=['P','M','MM','AM','QRP','QRPP','A','B','QTH']
)

# Check the internal entries for N
print("Checking entries for specific prefixes:\n")
count = 0
for pfx, meta in resolver.entries:
    if pfx in ['N', 'K', 'W', 'LU', 'NO']:
        print(f'Prefix: {repr(pfx)}')
        print(f'  Country: {meta.get("country")}')
        print(f'  DXCC: {meta.get("dxcc")}')
        print()
        count += 1
        if count >= 10:
            break

# Now test resolve for USA calls
print("\nTesting USA call resolution:")
for call in ['N', 'K', 'W', 'N0CALL', 'K1TEST', 'W5XYZ']:
    dxcc, country, cq = resolver.resolve(call)
    print(f'{call:15} -> DXCC: {dxcc:5} Country: {country}')