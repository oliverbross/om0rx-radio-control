import re

# Read the file
with open('c:\\Projects\\om0rx-radio-control\\logs\\qso_log.adif', 'r') as f:
    content = f.read()
    records = content.split('<EOR>')
    
    print(f"Total record segments: {len(records)}")
    
    # Find records with OM0AAO
    om0aao_count = 0
    for i, record in enumerate(records):
        if 'OM0AAO' in record:
            om0aao_count += 1
            print(f"\nRecord {i} contains OM0AAO #{om0aao_count}:")
            # Parse call field
            pattern = r'<([A-Z_]+):(\d+)>([^<]*)'
            matches = re.findall(pattern, record)
            for field_name, length, value in matches:
                print(f"  {field_name}: '{value}'")
            if om0aao_count >= 2:
                break