import sys
sys.path.insert(0, 'c:\\Projects\\om0rx-radio-control')

from radio_control.adif_handler import ADIFHandler

handler = ADIFHandler()
qsos = handler.read_recent_qsos_by_callsign('OM0AAO', 5)
print(f'Found {len(qsos)} QSOs:')
for i, qso in enumerate(qsos, 1):
    print(f'{i}. {qso}')