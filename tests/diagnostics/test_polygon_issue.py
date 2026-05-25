import json

with open('c:\\Projects\\om0rx-radio-control\\data\\countries-110m.json', 'r') as f:
    topo = json.load(f)

countries = topo['objects']['countries']['geometries']
for i, geom in enumerate(countries):
    props = geom.get('properties', {})
    if props.get('name') == 'Poland':
        print('Found Poland at index', i)
        print('Geometry type:', geom.get('type'))
        print('Properties:', props)
        print('Has arcs:', 'arcs' in geom)
        if 'arcs' in geom:
            print('Arcs length:', len(geom['arcs']))
            print('First few arcs:', geom['arcs'][:3])
        break