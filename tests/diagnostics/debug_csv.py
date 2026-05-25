import sys
sys.path.insert(0, '.')
import csv

# Read CSV directly to see what's there for USA
with open('C:\\Projects\\om0rx-radio-control\\data\\cty.csv', 'r') as f:
    lines = f.readlines()
    
    # Find USA entry
    for i, line in enumerate(lines):
        if 'United States' in line or ',K,' in line or ',N,' in line or ',W,' in line:
            print(f"Line {i}: {line.strip()}")
            if i > 100:  # Only look at first ~150 lines for USA
                break

print("\n\nNow checking if CSV is being parsed correctly:")

# Simulate the CSV parsing
from cty_resolvers import CtyHybridResolver

csv_prefix_to_dxcc = {}

with open('C:\\Projects\\om0rx-radio-control\\data\\cty.csv', 'r') as f:
    lines = f.readlines()
    f.seek(0)
    
    reader = csv.reader(f, delimiter=',')
    for row in reader:
        if not row or len(row) < 3: 
            continue
        
        pfx_col = row[0].strip().upper() if row[0] else ""
        pfx_col = pfx_col.lstrip("*=")
        name = row[1].strip() if len(row) > 1 else ""
        try:
            a = int(row[2]) if len(row) > 2 and row[2].strip() else None
        except:
            a = None
        
        if not name or a is None: 
            continue
        
        # Track K, N, W
        if pfx_col in ['K', 'N', 'W']:
            print(f"Found {pfx_col}: Country={name}, DXCC={a}")
            csv_prefix_to_dxcc[pfx_col] = a
        
        # Also check for LU
        if pfx_col == 'LU':
            print(f"Found {pfx_col}: Country={name}, DXCC={a}")
            csv_prefix_to_dxcc[pfx_col] = a

print(f"\nFinal csv_prefix_to_dxcc: {csv_prefix_to_dxcc}")