# bridge_runtime.py - Main runtime loop and async functions

import asyncio
import logging
import socket
import re
import time
import argparse
import os
from collections import deque
from datetime import datetime, UTC
from radio_control.config import *
from radio_control.utils import setup_logging, band_from_khz, infer_mode, extract_special, clean_comment
from radio_control.cty_resolvers import CtyResolver, CtyHybridResolver
from radio_control.classifier import Classifier
from radio_control.flex_radio import FlexSpots
from radio_control.spot_ui import SpotUi

# DX cluster line pattern
DX_RE = re.compile(r"^DX de\s+(?P<spotter>\S+):\s+(?P<freq_khz>\d+\.\d+)\s+(?P<dxcall>[A-Z0-9/]+)\s*(?P<comment>.*)$", re.I)


class BridgeRuntime:
    def __init__(self):
        self.spots_seen=0; self.spots_sent=0; self.spots_dedup=0
        self.cluster_connected=False; self.udp_ok=False; self.flex_ok=False; self.last_spot_at=None


def _to_tk_hex(val:str) -> str:
    try:
        if not isinstance(val, str):
            return val
        s = val.strip()
        if s.startswith('#'):
            s = s[1:]
        # If ARGB (8 bytes), drop alpha
        if len(s) == 8:
            s = s[2:]
        if len(s) == 6:
            return '#' + s
    except Exception:
        pass
    return val


def color_for_tag(tag:str):
    try:
        from radio_control import config as _cfgc
        cmap = getattr(_cfgc, "COLORS", {})
        return cmap.get(tag, cmap.get("Default", COLOR_DEFAULT))
    except Exception:
        return COLOR_DEFAULT


async def telnet_loop(resolver, clf, udp_sock, flex: FlexSpots, ui: SpotUi, rt: BridgeRuntime, args):
    backoffs=RECONNECT_BACKOFF[:]
    while True:
        try:
            logging.info("Connecting to DXSpider %s:%s as %s", CLUSTER_HOST, CLUSTER_PORT, CLUSTER_USER)
            reader, writer = await asyncio.open_connection(CLUSTER_HOST, CLUSTER_PORT)
            await asyncio.sleep(0.2)
            writer.write((CLUSTER_USER + "\r\n").encode()); await writer.drain()
            if CLUSTER_PASS:
                await asyncio.sleep(0.1); writer.write((CLUSTER_PASS + "\r\n").encode()); await writer.drain()
            for line in LOGIN_SCRIPT:
                await asyncio.sleep(0.05); writer.write((line + "\r\n").encode()); await writer.drain()

            for _ in range(BANNER_LOG_LINES):
                s=(await reader.readline()).decode(errors="ignore")
                if not s: break

            rt.cluster_connected=True; logging.info("DXSpider connected.")
            recent=deque(maxlen=5000)

            while True:
                line=await reader.readline()
                if not line: raise ConnectionError("Cluster closed connection")
                s=line.decode(errors="ignore").strip()
                m=DX_RE.match(s)
                if not m: continue

                spotter=m.group("spotter")
                try: khz=float(m.group("freq_khz"))
                except: continue
                dxcall=m.group("dxcall").upper()
                raw_comment=m.group("comment")
                comment=clean_comment(raw_comment)
                band=band_from_khz(khz)
                emode=infer_mode(comment, band, khz)

                dxcc, entity, cq = resolver.resolve(dxcall)
                if dxcc is not None and not entity:
                    info=resolver.info_for_adif(dxcc); entity=entity or info.get("entity"); cq=cq or info.get("cq")
                country = entity or "-"
                cq_display = str(cq) if cq is not None else "-"

                dedup=(dxcall, round(khz,1), emode)
                if dedup in recent: rt.spots_dedup+=1; continue
                recent.append(dedup)

                dx_worked, dx_conf = clf.dxcc_overall(dxcc)
                dx_new_band, dx_new_mode, dx_bandmode_conf = clf.dxcc_bandmode_flags(dxcc, band, emode)
                call_worked, call_conf = clf.call_overall(dxcall)
                call_new_band, call_new_mode, call_bandmode_conf = clf.call_bandmode_flags(dxcall, band, emode)

                # Call Status precedence with W/C prefix (band+mode specific)
                # If this specific band+mode combination is new, add W/C prefix if previously worked/confirmed
                if call_new_band and call_new_mode:
                    if call_conf:
                        call_status = "C/New Band+Mode"
                    elif call_worked:
                        call_status = "W/New Band+Mode"
                    else:
                        call_status = "New Band+Mode"
                elif call_new_band:
                    if call_conf:
                        call_status = "C/New Band"
                    elif call_worked:
                        call_status = "W/New Band"
                    else:
                        call_status = "New Band"
                elif call_new_mode:
                    if call_conf:
                        call_status = "C/New Mode"
                    elif call_worked:
                        call_status = "W/New Mode"
                    else:
                        call_status = "New Mode"
                elif call_bandmode_conf:
                    call_status = "Confirmed"
                elif call_worked:
                    call_status = "Worked"
                else:
                    call_status = "New Call"

                dxcc_col = "—"
                if dxcc is not None:
                    if not dx_worked:
                        dxcc_col = "New DXCC"
                    elif dx_new_band and dx_new_mode:
                        if dx_conf:
                            dxcc_col = "C/New Band+Mode"
                        else:
                            dxcc_col = "W/New Band+Mode"
                    elif dx_new_band:
                        if dx_conf:
                            dxcc_col = "C/New Band"
                        else:
                            dxcc_col = "W/New Band"
                    elif dx_new_mode:
                        if dx_conf:
                            dxcc_col = "C/New Mode"
                        else:
                            dxcc_col = "W/New Mode"
                    elif dx_bandmode_conf:
                        dxcc_col = "Confirmed"
                    else:
                        dxcc_col = "Worked"

                tag=None
                if dxcc is not None and not dx_worked: tag="ATNO"
                elif dx_new_band and dx_new_mode: 
                    tag = "C/New Band+Mode" if dx_conf else "W/New Band+Mode"
                elif dx_new_band: 
                    tag = "C/New Band" if dx_conf else "W/New Band"
                elif dx_new_mode: 
                    tag = "C/New Mode" if dx_conf else "W/New Mode"
                elif not dx_bandmode_conf: tag="Need LoTW"
                elif dx_worked: tag="Worked"

                ts=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
                special_tag = extract_special(comment)
                ui.add((ts, band, f"{khz:.1f}", emode, dxcall, country, cq_display, spotter,
                        call_status, dxcc_col, special_tag, comment), tag)

                draw = tag is not None and tag != "Worked"
                if args.flex and flex and flex.sock and draw:
                    try:
                        flex.add_spot(rx_mhz=khz/1000.0, callsign=dxcall, mode=emode, source="cluster",
                                      spotter=spotter, comment=f"{dxcc_col} • {country} • {comment}",
                                      lifetime=3600, priority=3, color=color_for_tag(tag), ts_epoch=int(time.time()))
                        rt.flex_ok=True
                    except Exception as e:
                        logging.warning("Flex spot failed: %s", e)

                if args.udp and draw:
                    try:
                        xml = f'<?xml version="1.0" encoding="utf-8"?>\r\n<spot>\r\n  <app>N1MM</app>\r\n  <StationName>{MY_STATION}</StationName>\r\n  <dxcall>{dxcall}</dxcall>\r\n  <frequency>{khz:.1f}</frequency>\r\n  <spottercall>{spotter}</spottercall>\r\n  <timestamp>{datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")}</timestamp>\r\n  <action>add</action>\r\n  <mode>{emode}</mode>\r\n  <comment>{dxcc_col} • {country} • {comment}</comment>\r\n  <status>new qso</status>\r\n  <statuslist>new qso</statuslist>\r\n</spot>'
                        udp_sock.sendto(xml.encode("utf-8"), (args.udp_host or SDR_UDP_HOST, int(args.udp_port or SDR_UDP_PORT)))
                        rt.udp_ok=True
                    except Exception as e:
                        rt.udp_ok=False; logging.error("UDP send failed: %s", e)

                rt.spots_seen+=1
                if draw: rt.spots_sent+=1
                rt.last_spot_at=time.time()

        except Exception as e:
            if rt.cluster_connected: logging.warning("Cluster disconnected: %s", e)
            else: logging.warning("Cluster connect failed: %s", e)
            rt.cluster_connected=False
            delay=backoffs[0] if backoffs else 60
            if len(backoffs)>1: backoffs=backoffs[1:]
            await asyncio.sleep(delay); continue


async def heartbeat(rt: BridgeRuntime, resolver, clf):
    while True:
        have_rules=len(resolver.rules)
        last = datetime.fromtimestamp(rt.last_spot_at, UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if rt.last_spot_at else "—"
        logging.info("HB | cluster=%s udp=%s flex=%s rules=%d seen=%d sent=%d dedup=%d last=%s",
                     "UP" if rt.cluster_connected else "DOWN",
                     "OK" if rt.udp_ok else "OFF",
                     "OK" if rt.flex_ok else "OFF",
                     have_rules, rt.spots_seen, rt.spots_sent, rt.spots_dedup, last)
        await asyncio.sleep(HEARTBEAT_SEC)


def parse_args():
    ap=argparse.ArgumentParser(description="DXSpider → WaveLog → Flex Spots (ver5.9)")
    ap.add_argument("--log-level", default=LOG_LEVEL)
    ap.add_argument("--log-file", default=None)
    ap.add_argument("--udp", dest="udp", action="store_true", default=UDP_ENABLED_DEFAULT)
    ap.add_argument("--no-udp", dest="udp", action="store_false")
    ap.add_argument("--udp-host", default=None)
    ap.add_argument("--udp-port", default=None)
    ap.add_argument("--flex", dest="flex", action="store_true", default=FLEX_ENABLED_DEFAULT)
    ap.add_argument("--no-flex", dest="flex", action="store_false")
    ap.add_argument("--flex-ip", default=None)
    ap.add_argument("--flex-port", type=int, default=None)
    ap.add_argument("--ui", action="store_true")
    ap.add_argument("--flex-test", action="store_true")
    ap.add_argument("--cty", default=None, help="Override CTY CSV path")
    ap.add_argument("--cty-cols", default=None, help="Force column mapping: prefix=...,entity=...,adif=...,cq=...")
    ap.add_argument("--cty-debug", action="store_true", help="Print header row seen for CTY CSV")
    return ap.parse_args()


async def main():
    args=parse_args()
    setup_logging(args.log_level, args.log_file)
    cty_path = args.cty or (globals().get('CTY_DAT_PATH') or CTY_CSV_PATH)
    col_override=None
    if args.cty_cols:
        try:
            parts = dict(x.split("=",1) for x in args.cty_cols.split(","))
            col_override = {k.strip(): v.strip() for k,v in parts.items()}
        except Exception:
            logging.error("Bad --cty-cols format. Use: prefix=...,entity=...,adif=...,cq=...")

    logging.info("Config: station=%s cluster=%s:%s (login=%s) db=%s@%s:%s/%s udp=%s flex=%s cty=%s",
                 MY_STATION, CLUSTER_HOST, CLUSTER_PORT, CLUSTER_USER,
                 DB_USER, DB_HOST, DB_PORT, DB_NAME, "ON" if args.udp else "OFF",
                 "ON" if args.flex else "OFF", cty_path)

    resolver = (CtyHybridResolver(cty_path, CTY_CSV_PATH, ignore_suffixes=CTY_IGNORE_SUFFIXES)
            if (cty_path and os.path.splitext(cty_path)[1].lower()=='.dat')
            else CtyResolver(cty_path, ignore_suffixes=CTY_IGNORE_SUFFIXES, overrides=CTY_OVERRIDES, col_override=col_override))
    if args.cty_debug and resolver.debug_headers:
        logging.debug("CTY header row: %s", resolver.debug_headers)
    if not resolver.rules:
        logging.error("No CTY rules loaded — Country/CQ will be blank. Check CTY file or use --cty-cols mapping.")

    clf=Classifier(); clf.load()

    udp_sock=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    flex=None
    if args.flex:
        flex=FlexSpots(args.flex_ip or FLEX_TCP_HOST, int(args.flex_port or FLEX_TCP_PORT))
        flex.connect()
        if args.flex_test:
            ok = flex.add_spot(rx_mhz=14.025, callsign="TESTDX", mode="CW", source="bridge", spotter="OM0RX",
                               comment="ver5.8 test", lifetime=120, priority=3, color="#FF00FF00", ts_epoch=int(time.time()))
            logging.info("Flex test spot sent: %s", "OK" if ok else "FAIL")
            return

    ui=SpotUi(enabled=args.ui); ui.start()
    rt=BridgeRuntime()
    await asyncio.gather(telnet_loop(resolver, clf, udp_sock, flex, ui, rt, args), heartbeat(rt, resolver, clf))


if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
