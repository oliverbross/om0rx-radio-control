# classifier.py - QSO classification and filtering logic

import logging
from config import DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME, MY_STATION

try:
    import mysql.connector as mysql
except ImportError:
    print("Missing dependency: mysql-connector-python (pip install mysql-connector-python)")
    import sys
    sys.exit(1)


class Classifier:
    """Classify spots based on worked/confirmed status from WaveLog database"""
    def __init__(self):
        self.dxcc_worked=set(); self.dxcc_lotw=set()
        self.call_worked=set(); self.call_lotw=set()
        self.dxcc_band_worked=set(); self.dxcc_bandmode_worked=set()
        self.dxcc_mode_worked=set(); self.dxcc_mode_lotw=set()  # Track mode globally
        self.call_band_worked=set(); self.call_bandmode_worked=set()
        self.call_mode_worked=set(); self.call_mode_lotw=set()  # Track mode globally

    def load(self):
        """Load worked/confirmed data from database"""
        logging.info("Connecting to DB %s:%s/%s as %s", DB_HOST, DB_PORT, DB_NAME, DB_USER)
        con = mysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=<qrz_password> database=DB_NAME, connection_timeout=8)
        cur = con.cursor()

        cur.execute("""SELECT DISTINCT dxcc FROM vw_qsos_effective WHERE own_station=%s AND dxcc IS NOT NULL""",(MY_STATION,))
        self.dxcc_worked = {int(d) for (d,) in cur if d is not None}
        cur.execute("""SELECT DISTINCT dxcc FROM vw_qsos_effective WHERE own_station=%s AND dxcc IS NOT NULL AND lotw='Y'""",(MY_STATION,))
        self.dxcc_lotw = {int(d) for (d,) in cur if d is not None}

        cur.execute("""SELECT DISTINCT dxcall FROM vw_qsos_effective WHERE own_station=%s""",(MY_STATION,))
        self.call_worked = {c.upper() for (c,) in cur if c}
        cur.execute("""SELECT DISTINCT dxcall FROM vw_qsos_effective WHERE own_station=%s AND lotw='Y'""",(MY_STATION,))
        self.call_lotw = {c.upper() for (c,) in cur if c}

        cur.execute("""SELECT DISTINCT dxcc, band FROM vw_qsos_effective WHERE own_station=%s AND dxcc IS NOT NULL AND band<>''""",(MY_STATION,))
        self.dxcc_band_worked = {(int(d), b) for (d,b) in cur if d is not None}
        cur.execute("""SELECT DISTINCT dxcc, band, emode FROM vw_qsos_effective
                       WHERE own_station=%s AND dxcc IS NOT NULL AND band<>'' AND emode IS NOT NULL AND emode<>''""",(MY_STATION,))
        self.dxcc_bandmode_worked = {(int(d), b, m) for (d,b,m) in cur if d is not None}
        cur.execute("""SELECT DISTINCT dxcc, emode FROM vw_qsos_effective
                       WHERE own_station=%s AND dxcc IS NOT NULL AND emode IS NOT NULL AND emode<>''""",(MY_STATION,))
        self.dxcc_mode_worked = {(int(d), m) for (d,m) in cur if d is not None}
        cur.execute("""SELECT DISTINCT dxcc, emode FROM vw_qsos_effective
                       WHERE own_station=%s AND lotw='Y' AND dxcc IS NOT NULL AND emode IS NOT NULL AND emode<>''""",(MY_STATION,))
        self.dxcc_mode_lotw = {(int(d), m) for (d,m) in cur if d is not None}

        cur.execute("""SELECT DISTINCT dxcall, band FROM vw_qsos_effective WHERE own_station=%s AND band<>''""",(MY_STATION,))
        self.call_band_worked = {(c.upper(), b) for (c,b) in cur if c}
        cur.execute("""SELECT DISTINCT dxcall, band, emode FROM vw_qsos_effective
                       WHERE own_station=%s AND band<>'' AND emode IS NOT NULL AND emode<>''""",(MY_STATION,))
        self.call_bandmode_worked = {(c.upper(), b, m) for (c,b,m) in cur if c}
        cur.execute("""SELECT DISTINCT dxcall, emode FROM vw_qsos_effective
                       WHERE own_station=%s AND emode IS NOT NULL AND emode<>''""",(MY_STATION,))
        self.call_mode_worked = {(c.upper(), m) for (c,m) in cur if c}
        cur.execute("""SELECT DISTINCT dxcall, emode FROM vw_qsos_effective
                       WHERE own_station=%s AND lotw='Y' AND emode IS NOT NULL AND emode<>''""",(MY_STATION,))
        self.call_mode_lotw = {(c.upper(), m) for (c,m) in cur if c}

        cur.execute("""SELECT DISTINCT dxcc, band, emode FROM vw_qsos_effective
                       WHERE own_station=%s AND lotw='Y' AND dxcc IS NOT NULL AND band<>'' AND emode IS NOT NULL AND emode<>''""",(MY_STATION,))
        self.dxcc_bandmode_lotw = {(int(d), b, m) for (d,b,m) in cur if d is not None}
        cur.execute("""SELECT DISTINCT dxcall, band, emode FROM vw_qsos_effective
                       WHERE own_station=%s AND lotw='Y' AND band<>'' AND emode IS NOT NULL AND emode<>''""",(MY_STATION,))
        self.call_bandmode_lotw = {(c.upper(), b, m) for (c,b,m) in cur if c}

        cur.close(); con.close()
        logging.info("DB loaded: dxcc_worked=%d, dxcc_lotw=%d, dxcc_band=%d, dxcc_bandmode=%d",
                     len(self.dxcc_worked), len(self.dxcc_lotw), len(self.dxcc_band_worked), len(self.dxcc_bandmode_worked))

    def dxcc_overall(self, dxcc):
        """Check if DXCC is worked and/or confirmed"""
        worked = dxcc in self.dxcc_worked if dxcc is not None else False
        confirmed = dxcc in self.dxcc_lotw if dxcc is not None else False
        return worked, confirmed

    def dxcc_bandmode_flags(self, dxcc, band, emode):
        """Check DXCC band/mode status"""
        if dxcc is None: return False, False, False
        band_worked = (dxcc, band) in self.dxcc_band_worked
        bandmode_worked = (dxcc, band, emode) in self.dxcc_bandmode_worked
        bandmode_conf = (dxcc, band, emode) in self.dxcc_bandmode_lotw
        mode_worked = (dxcc, emode) in self.dxcc_mode_worked
        new_band = not band_worked
        new_mode = not mode_worked  # Mode has never been worked globally
        return new_band, new_mode, bandmode_conf

    def call_overall(self, call):
        """Check if call is worked and/or confirmed"""
        c=(call or "").upper()
        worked = c in self.call_worked
        confirmed = c in self.call_lotw
        return worked, confirmed

    def call_bandmode_flags(self, call, band, emode):
        """Check call band/mode status"""
        c=(call or "").upper()
        band_worked = (c, band) in self.call_band_worked
        bandmode_worked = (c, band, emode) in self.call_bandmode_worked
        bandmode_conf = (c, band, emode) in self.call_bandmode_lotw
        mode_worked = (c, emode) in self.call_mode_worked
        new_band = not band_worked
        new_mode = not mode_worked  # Mode has never been worked globally
        return new_band, new_mode, bandmode_conf


class FilterModel:
    """Filter model for spot filtering"""
    def __init__(self):
        self.bands=None; self.modes=None; self.cq=None; self.call_status=None; self.dxcc=None
        
    def match(self, row):
        """Check if row matches filter criteria"""
        # row columns: ts, band, khz, mode, callsign, country, cq, spotter, callstatus, dxcc, special, comment
        band=row[1]; mode=row[3]; cq=str(row[6]); callstatus=row[8]; dxcc=row[9]
        if self.bands and band not in self.bands: return False
        if self.modes and mode not in self.modes: return False
        if self.cq and cq not in self.cq: return False
        if self.call_status and callstatus not in self.call_status: return False
        if self.dxcc and dxcc not in self.dxcc: return False
        return True


def _parse_csv_set(s):
    """Parse comma-separated string into set"""
    items=[x.strip() for x in (s or "").split(",") if x.strip()]
    return set(items) if items else None