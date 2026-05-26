# cty_resolvers.py - Country/DXCC resolution from CTY files

import os
import re
import logging
from radio_control.config import RESOLVE_DEBUG_MISSES, CTY_IGNORE_SUFFIXES, CTY_OVERRIDES
from radio_control.config import DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME


class CtyResolver:
    """CSV-based CTY resolver with flexible column detection"""
    def __init__(self, csv_path: str, ignore_suffixes=None, overrides=None, col_override=None):
        self.rules=[]; self.prefix_set=set(); self.adif_info={}
        self.ignore_suffixes=set(ignore_suffixes or [])
        self.override_patterns=[]; self.miss_log=0
        self.debug_headers=None
        if overrides:
            import re as _re
            for patt,adif in overrides.items():
                try: self.override_patterns.append((_re.compile(patt, _re.I), int(adif)))
                except: logging.warning("Invalid override: %s -> %s", patt, adif)
        if not (csv_path and os.path.exists(csv_path)):
            logging.warning("cty.csv not found at: %s", csv_path); return

        try:
            import csv as _csv
            aliases = {
                "prefix": {"prefix","prefixes","call","callsign","px","prefix_list"},
                "entity": {"entity","country","name"},
                "adif":   {"adif","dxcc","adif_code","adifnumber"},
                "cq":     {"cq","cqz","cq_zone","zone"},
            }
            def _pick(row, keys):
                for k in row.keys():
                    if k is None: continue
                    kk = k.strip().lower()
                    if kk in keys:
                        return (k, row[k])
                return (None, "")

            def _is_commented(row):
                for v in row.values():
                    if v is None: continue
                    s = str(v).strip()
                    if not s: continue
                    return s.startswith("#")
                return False

            delims = [",",";","|","\t"]
            total = 0; added = 0
            with open(csv_path, "r", encoding="utf-8", newline="") as f:
                sample = f.read(4096); f.seek(0)
                try:
                    dialect = _csv.Sniffer().sniff(sample, delimiters="".join(delims))
                    candidates = [dialect.delimiter] + [d for d in delims if d != dialect.delimiter]
                except Exception:
                    candidates = delims[:]

                first_headers=None
                for delim in candidates:
                    f.seek(0)
                    reader = _csv.DictReader(f, delimiter=delim)
                    headers = [ (h or "").strip() for h in (reader.fieldnames or []) ]
                    if not headers:
                        continue
                    if first_headers is None: first_headers=headers
                    for row in reader:
                        total += 1
                        row = { (k or "").strip(): (v or "").strip() for k,v in row.items() }
                        if not row or _is_commented(row):
                            continue

                        if col_override:
                            pfx_val = row.get(col_override.get("prefix",""), "")
                            ent_val = row.get(col_override.get("entity",""), "")
                            adif_val= row.get(col_override.get("adif",""), "")
                            cq_val  = row.get(col_override.get("cq",""), "")
                        else:
                            pk, pfx_val = _pick(row, aliases["prefix"])
                            ek, ent_val = _pick(row, aliases["entity"])
                            ak, adif_val= _pick(row, aliases["adif"])
                            zk, cq_val  = _pick(row, aliases["cq"])

                        if not pfx_val and not adif_val:
                            continue

                        try: adif = int(adif_val) if adif_val else None
                        except: adif = None

                        if adif is not None:
                            info = self.adif_info.setdefault(adif, {})
                            if ent_val: info["entity"] = ent_val
                            if cq_val:
                                try: info["cq"] = int(cq_val)
                                except: pass

                        import re as _re
                        tokens = _re.split(r"[ ,;|\t]+", (pfx_val or "").upper())
                        tokens = [t for t in tokens if t]
                        for p in tokens:
                            self.rules.append((p, adif, ent_val, cq_val))
                            self.prefix_set.add(p)
                            added += 1

                    if added > 0:
                        break  # parsed okay with this delimiter

                self.debug_headers = first_headers

                # --- LAST-RESORT FALLBACK ---
                if added == 0 and total > 0:
                    logging.warning("CTY: falling back to heuristic parser (no headers matched).")
                    f.seek(0)
                    rdr = _csv.reader(f)
                    hdr = next(rdr, None)
                    for row in rdr:
                        total += 1
                        cells = [ (c or "").strip() for c in row ]
                        if not cells: continue
                        # pick prefix column = the cell containing letters/digits/slash/space/commas
                        pfx_candidates = [c for c in cells if re.search(r"[A-Z0-9/]{2,}", c, re.I)]
                        if not pfx_candidates: continue
                        pfx_val = pfx_candidates[0]

                        # ADIF = first integer-looking cell 1..999
                        adif = None
                        for c in cells:
                            try:
                                v=int(re.sub(r"[^\d]","",c))
                                if 1 <= v <= 999: adif=v; break
                            except: pass

                        # Country = longest alphabetic cell
                        alpha = [c for c in cells if re.search(r"[A-Za-z]{3,}", c)]
                        ent_val = max(alpha, key=len) if alpha else ""

                        # CQ zone = any 1..40 integer
                        cq = None
                        for c in cells:
                            try:
                                v=int(re.sub(r"[^\d]","",c))
                                if 1 <= v <= 40: cq=v; break
                            except: pass

                        tokens = re.split(r"[ ,;|\t]+", (pfx_val or "").upper())
                        tokens = [t for t in tokens if t]
                        for p in tokens:
                            self.rules.append((p, adif, ent_val, cq))
                            self.prefix_set.add(p)
                            added += 1

                self.rules.sort(key=lambda r: len(r[0]), reverse=True)
                logging.info("Loaded %d prefix rules from cty.csv (%d rows)", added, total)
                if self.debug_headers:
                    logging.debug("CTY headers seen: %s", self.debug_headers)

        except Exception as e:
            logging.error("Failed to load cty.csv: %s", e)

    @staticmethod
    def _norm(s:str)->str:
        s=s.upper().replace('Ø','0').replace('Ó','O').replace('Ñ','N')
        return re.sub(r'[^A-Z0-9/]','',s)

    def _strip(self, token:str)->str:
        return '' if token in self.ignore_suffixes else token

    def _cands(self, raw:str):
        call=self._norm(raw)
        for patt,adif in self.override_patterns:
            if patt.search(call): yield ('OVERRIDE',adif); return
        parts=[p for p in call.split('/') if p]
        parts_clean=[self._strip(p) for p in parts if self._strip(p)]
        yield call
        for p in sorted(parts_clean,key=len,reverse=True): yield p
        if parts_clean:
            first,last=parts_clean[0],parts_clean[-1]
            if first in self.prefix_set: yield first
            if last  in self.prefix_set: yield last
        for token in [call]+parts_clean:
            for i in range(len(token),0,-1):
                yield token[:i]

    def resolve(self, dxcall:str):
        if not self.rules:
            return None, None, None
        for cand in self._cands(dxcall):
            if isinstance(cand,tuple):
                adif=cand[1]; info=self.adif_info.get(adif,{})
                return adif, info.get("entity"), info.get("cq")
        for cand in self._cands(dxcall):
            if not isinstance(cand,str): continue
            for pfx,adif,entity,cq in self.rules:
                if cand.startswith(pfx):
                    ent = entity or self.adif_info.get(adif,{}).get("entity")
                    cqz = cq or self.adif_info.get(adif,{}).get("cq")
                    return adif, ent, cqz
        if self.miss_log < RESOLVE_DEBUG_MISSES:
            self.miss_log+=1; logging.debug("RESOLVE MISS for %s", dxcall)
        return None, None, None

    def info_for_adif(self, adif:int):
        return self.adif_info.get(adif,{})




class CtyDatResolver:
    """
    Minimal Big CTY (cty.dat) parser focused on longest-prefix matching.
    Provides: country, cq (zone), continent, utc_offset, primary_prefix, dxcc.
    DXCC codes are extracted from cty.dat primary prefixes.
    """
    # Built from cty.dat parsing - maps primary prefix to DXCC
    PRIMARY_PREFIX_TO_DXCC = {}
    
    def __init__(self, dat_path: str, csv_path: str = None, ignore_suffixes=None):
        self.entries = []   # list of (prefix, meta, exact_match)
        self.ignore_suffixes=set(ignore_suffixes or [])
        self.miss_log=0
        self.prefix_to_dxcc = {}  # Maps prefix -> DXCC code
        
        # Load DXCC mapping from CSV first (if available)
        if csv_path and os.path.exists(csv_path):
            self._load_dxcc_from_csv(csv_path)
        
        if not (dat_path and os.path.exists(dat_path)):
            logging.warning("cty.dat not found at: %s", dat_path); return
        self._parse(dat_path)

    @staticmethod
    def _csv_prefix_tokens(prefixes_str: str) -> list[str]:
        """Return CTY-style prefix tokens without creating bogus suffix prefixes."""
        tokens = []
        for raw_token in re.split(r"[ ,;|\t]+", prefixes_str or ""):
            token = raw_token.strip().upper().lstrip("*=")
            if not token:
                continue
            token = re.sub(r"\([^)]*\)|\[[^\]]*\]|<[^>]*>", "", token).strip()
            if token:
                tokens.append(token)
        return tokens

    @staticmethod
    def _dat_prefix_token(raw_token: str) -> tuple[str, bool] | None:
        """Parse a cty.dat prefix token into a match token and exact-call flag."""
        raw = (raw_token or "").strip().upper()
        if not raw:
            return None
        exact_match = raw.startswith("=")
        token = raw.lstrip("*=")
        token = re.sub(r"\([^)]*\)|\[[^\]]*\]|<[^>]*>", "", token).strip()
        return (token, exact_match) if token else None
    
    def _load_dxcc_from_csv(self, csv_path: str):
        """Load DXCC codes from CSV to create prefix->DXCC mappings"""
        try:
            import csv as _csv
            with open(csv_path, "r", encoding="utf-8", newline="") as f:
                # Read all lines and detect format
                lines = f.readlines()
                f.seek(0)
                
                # Detect delimiter
                sample = "".join(lines[:10])
                try:
                    dialect = _csv.Sniffer().sniff(sample, delimiters=",;|\t")
                    delim = dialect.delimiter
                except Exception:
                    delim = ","
                
                # Check if first line has headers
                first_line = lines[0].strip() if lines else ""
                has_headers = any(keyword in first_line.lower() for keyword in ["prefix", "entity", "country", "adif", "dxcc"])
                
                f.seek(0)
                rdr = _csv.reader(f, delimiter=delim)
                
                # Skip header if present
                if has_headers:
                    next(rdr, None)
                
                for row in rdr:
                    if not row or len(row) < 3: continue
                    
                    # Format: primary_prefix, country, dxcc, continent, cq, itu, lat, lon, utc, prefixes
                    pfx_col = row[0].strip().upper().lstrip("*=") if row[0] else ""
                    try:
                        dxcc = int(row[2]) if len(row) > 2 and row[2].strip() else None
                    except:
                        dxcc = None
                    
                    if not pfx_col or dxcc is None: 
                        continue
                    
                    # Map primary prefix to DXCC
                    if pfx_col:
                        self.prefix_to_dxcc[pfx_col] = dxcc
                    
                    # Also map all tokenized prefixes to DXCC
                    if len(row) > 9:
                        prefixes_str = row[9].strip()
                        for tok in self._csv_prefix_tokens(prefixes_str):
                            if tok and len(tok) <= 5 and tok not in self.prefix_to_dxcc:
                                self.prefix_to_dxcc[tok] = dxcc
            
            logging.info("Loaded %d prefix-to-DXCC mappings from CSV", len(self.prefix_to_dxcc))
        except Exception as e:
            logging.warning("Failed to load DXCC mappings from CSV: %s", e)

    def _parse(self, path: str):
        """Parse cty.dat and extract DXCC codes from primary prefixes"""
        current = None
        primary_prefixes_by_adif = {}  # Map DXCC codes to their primary prefixes
        
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                
                # Country header line (starts with non-space, contains ':')
                if ':' in line and not line.startswith(' '):
                    parts = [p.strip() for p in line.split(':')]
                    if len(parts) >= 8:
                        country = parts[0].strip()
                        try: cq = int(parts[1])
                        except: cq = None
                        try: itu = int(parts[2])
                        except: itu = None
                        cont = parts[3].strip()
                        # === FIX: Extract latitude (parts[4]) and longitude (parts[5]) ===
                        try: latitude = float(parts[4])
                        except: latitude = None
                        try: longitude = float(parts[5])
                        except: longitude = None
                        try: utc = parts[6].strip()
                        except: utc = None
                        primary = parts[7].strip().lstrip("*=")  # Strip special chars
                        
                        # Extract DXCC from primary prefix - look for pattern like (230) or just get the first 3 chars
                        dxcc = None
                        if primary:
                            # Check if primary has ADIF in it like "K(6)" pattern
                            import re as _re_local
                            match = _re_local.search(r'\((\d+)\)', primary)
                            if match:
                                try: dxcc = int(match.group(1))
                                except: pass
                            # Store this mapping for later use
                            if dxcc:
                                primary_prefixes_by_adif[dxcc] = primary.split('(')[0].strip()
                        
                        current = {
                            "country": country, "cq": cq, "itu": itu, "continent": cont,
                            "latitude": latitude, "longitude": longitude,
                            "utc_offset": utc, "primary_prefix": primary, "dxcc": dxcc
                        }
                    else:
                        current = None
                        
                # Prefix lines (start with space)
                elif current is not None:
                    line_content = line.rstrip()
                    if not line_content.strip():
                        continue
                    if line_content.endswith(';'):
                        line_content = line_content[:-1]
                    
                    # Split by comma and process each prefix
                    for token in [t.strip() for t in line_content.split(',') if t.strip()]:
                        if not token:
                            continue
                        parsed = self._dat_prefix_token(token)
                        if not parsed:
                            continue
                        match_token, exact_match = parsed
                        self.entries.append((match_token, current, exact_match))
                        # Map prefix to DXCC if available
                        if current.get("dxcc"):
                            self.prefix_to_dxcc[match_token.upper()] = current.get("dxcc")
        
        self.entries.sort(key=lambda x: (len(x[0]), x[2]), reverse=True)
        logging.info("Loaded %d CTY.DAT prefixes, %d with DXCC codes", len(self.entries), len(self.prefix_to_dxcc))

    def lookup(self, callsign: str):
        """Look up callsign in cty.dat and add DXCC from prefix mapping"""
        if not callsign: return {}
        cs = callsign.upper().strip()
        ignore_suffixes = {suffix.upper() for suffix in self.ignore_suffixes}
        slash_parts = [part for part in cs.split("/") if part]
        slash_candidates = [part for part in slash_parts if part not in ignore_suffixes]
        candidates = [cs]
        candidates.extend(sorted(slash_candidates, key=len, reverse=True))

        seen = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)

            # Find matching prefix from cty.dat
            for pfx, meta, exact_match in self.entries:
                pfx_upper = pfx.upper()
                if (exact_match and candidate != pfx_upper) or (
                    not exact_match and not candidate.startswith(pfx_upper)
                ):
                    continue
                result = {
                    "country": meta.get("country"),
                    "cq": meta.get("cq"),
                    "itu": meta.get("itu"),
                    "continent": meta.get("continent"),
                    "latitude": meta.get("latitude"),  # === FIX: Include latitude ===
                    "longitude": meta.get("longitude"),  # === FIX: Include longitude ===
                    "utc_offset": meta.get("utc_offset"),
                    "primary_prefix": meta.get("primary_prefix"),
                    "prefix": pfx,
                    "matched_candidate": candidate,
                    "exact_match": exact_match,
                    "dxcc": meta.get("dxcc")
                }

                # Add DXCC from CSV mapping if available
                if not result["dxcc"]:
                    # Try longest match first from prefix_to_dxcc
                    for check_len in range(len(pfx), 0, -1):
                        check_pfx = pfx[:check_len].upper()
                        if check_pfx in self.prefix_to_dxcc:
                            result["dxcc"] = self.prefix_to_dxcc[check_pfx]
                            break

                return result
        
        self.miss_log += 1
        if self.miss_log <= 10:
            logging.debug("CTY.DAT miss: %s", callsign)
        return {}



class CtyHybridResolver(CtyDatResolver):
    """
    Merge CTY.DAT prefix coverage with ADIF/DXCC codes from CSV when available.
    Matching strategy:
      1) Match DAT primary_prefix against CSV 'prefix' tokens.
      2) Fallback to normalized country-name match.
      3) If still missing, try to build a name->ADIF map from the WaveLog DB (dxcc entities) and match by name.
    """
    SYNONYMS = {
        'fed rep of germany':'germany',
        'federal republic of germany':'germany',
        'germany':'germany',
        'united states':'united states of america',
        'usa':'united states of america',
        'u s a':'united states of america',
        'england':'united kingdom',
        'scotland':'scotland',
        'wales':'wales',
        'european russia':'european russia',
        'asiatic russia':'asiatic russia'
    }
    def __init__(self, dat_path: str, csv_path: str | None, ignore_suffixes=None):
        # === LOAD CSV FIRST to populate PRIMARY_PREFIX_TO_DXCC before parsing cty.dat ===
        self.adif_info = {}
        self.rules = []  # (prefix, adif, entity, cq)

        ent_map = {}
        csv_prefix_to_dxcc = {}  # Build this from CSV to enhance CtyDatResolver
        # 3 sources to build ent_map: CSV, DB (optional), hard normalization

        def _norm(s: str) -> str:
            s = (s or "").lower()
            for ch in [",","(",")","[","]","'","`","'","–","-","  "]:
                s = s.replace(ch, " ")
            s = " ".join(s.split())
            # common synonyms
            s = s.replace("europen", "european").replace("russian federation", "russia")
            s = s.replace("kingdom of", "").replace("republic of", "").replace("islamic republic of", "")
            s = s.replace("&", "and")
            return s.strip()

        # --- CSV load (if present) - MUST be before super().__init__() ---
        if csv_path and os.path.exists(csv_path):
            try:
                import csv as _csv
                with open(csv_path, "r", encoding="utf-8", newline="") as f:
                    # Read all lines and detect format
                    lines = f.readlines()
                    f.seek(0)
                    
                    # Detect delimiter
                    sample = "".join(lines[:10])
                    try:
                        dialect = _csv.Sniffer().sniff(sample, delimiters=",;|\t")
                        delim = dialect.delimiter
                    except Exception:
                        delim = ","
                    
                    # Check if first line has headers (contains non-numeric first column or "prefix"/"entity" keywords)
                    first_line = lines[0].strip() if lines else ""
                    first_cells = first_line.split(delim) if first_line else []
                    has_headers = any(keyword in first_line.lower() for keyword in ["prefix", "entity", "country", "adif", "dxcc"])
                    
                    f.seek(0)
                    rdr = _csv.reader(f, delimiter=delim)
                    
                    # Skip header if present
                    if has_headers:
                        next(rdr, None)
                    
                    for row in rdr:
                        if not row or len(row) < 3: continue
                        
                        # Format: prefix, country, dxcc, continent, cq, itu, lat, lon, utc, prefixes
                        pfx_col = row[0].strip().upper() if row[0] else ""
                        # Strip asterisk from primary prefix (e.g., "*IT9" -> "IT9")
                        pfx_col = pfx_col.lstrip("*=")
                        name = row[1].strip() if len(row) > 1 else ""
                        try:
                            a = int(row[2]) if len(row) > 2 and row[2].strip() else None
                        except:
                            a = None
                        
                        prefixes_str = row[9].strip() if len(row) > 9 else ""
                        if not prefixes_str:
                            prefixes_str = pfx_col
                        
                        if not name or a is None: continue
                        
                        ent_map[_norm(name)] = (a, name)
                        
                        # Map primary prefix to ADIF
                        if pfx_col:
                            ent_map[pfx_col] = (a, name)
                            csv_prefix_to_dxcc[pfx_col] = a
                        
                        # Map each tokenized prefix to ADIF
                        for tok in CtyDatResolver._csv_prefix_tokens(prefixes_str):
                            if tok and len(tok) <= 5:  # Filter out invalid prefixes
                                ent_map[tok] = (a, name)
                                csv_prefix_to_dxcc[tok] = a
                        
                        self.adif_info[a] = {"entity": name}
                
                # Update CtyDatResolver's PRIMARY_PREFIX_TO_DXCC with CSV data
                CtyDatResolver.PRIMARY_PREFIX_TO_DXCC.update(csv_prefix_to_dxcc)
                logging.info("Updated PRIMARY_PREFIX_TO_DXCC with %d prefixes from CSV", len(csv_prefix_to_dxcc))
            except Exception as e:
                logging.warning("Hybrid CTY: CSV read failed: %s", e)
        
        # === NOW parse cty.dat with populated PRIMARY_PREFIX_TO_DXCC ===
        super().__init__(dat_path, ignore_suffixes=ignore_suffixes)

        # --- DB fallback (optional) ---
        if not ent_map:
            try:
                import mysql.connector as _mysql
                con = _mysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, database=DB_NAME, connection_timeout=6)
                cur = con.cursor()
                # Try common wavelog table names for entities
                for sql in [
                    "SELECT adif, name FROM dxcc_entities",
                    "SELECT adif, name FROM dxcc_entity",
                    "SELECT adif, name FROM dxcc"
                ]:
                    try:
                        cur.execute(sql)
                        rows = cur.fetchall()
                        if rows:
                            for a,name in rows:
                                try:
                                    a=int(a)
                                    ent_map[_norm(name)] = (a, name)
                                    self.adif_info[a] = {"entity": name}
                                except: pass
                            break
                    except Exception:
                        continue
                cur.close(); con.close()
            except Exception as e:
                logging.info("Hybrid CTY: DB name map not available (%s)", e)

        # --- Build rules by primary_prefix first, then name ---
        matched = 0
        self.entity_to_adif = {}  # Create reverse mapping: country_name -> ADIF
        
        for pfx, meta, _exact_match in self.entries:
            country = meta.get("country") or ""
            primary = (meta.get("primary_prefix") or "").strip().upper()
            adif = None; name = None
            if primary and primary in ent_map:
                adif, name = ent_map[primary]
            else:
                key_norm = _norm(country)
                key_norm = self.SYNONYMS.get(key_norm, key_norm)
                adif_name = ent_map.get(key_norm)
                if adif_name:
                    adif, name = adif_name
            if adif is not None:
                self.rules.append((pfx.upper(), adif, name or country, meta.get("cq")))
                # Store entity->ADIF mapping (use lowercase for case-insensitive lookup)
                entity_key = (name or country).lower()
                if entity_key and adif is not None:
                    self.entity_to_adif[entity_key] = adif
                matched += 1
        
        # Add hard-coded fallbacks for common entities that might fail resolution
        common_fallbacks = {
            'england': 223,          # England (G)
            'united kingdom': 223,   # United Kingdom
            'germany': 230,          # Germany (DL)
            'fed rep of germany': 230,
            'france': 227,           # France (F)
            'italy': 248,            # Italy (I)
            'spain': 281,            # Spain (EA)
            'european russia': 54,   # European Russia (UA)
            'asiatic russia': 15,    # Asiatic Russia
            'canada': 1,             # Canada (VE)
            'united states': 291,    # USA (K)
            'united states of america': 291,
            'usa': 291,
            'japan': 339,            # Japan (JA)
            'australia': 150,        # Australia (VK)
            'new zealand': 170,      # New Zealand (ZL)
            'argentina': 100,        # Argentina (LU)
            'brazil': 108,           # Brazil (PY)
            'mexico': 50,            # Mexico (XE)
            'slovenia': 499,         # Slovenia (S5)
            'saint helena': 278,     # Saint Helena (ZD7)
            'antarctica': 13,        # Antarctica (DP0GVN is in Antarctica)
        }
        for entity, adif_code in common_fallbacks.items():
            if entity not in self.entity_to_adif:
                self.entity_to_adif[entity] = adif_code
        
        logging.info("Hybrid CTY: %d prefixes with ADIF, %d entity mappings", matched, len(self.entity_to_adif))

    def normalize_entity(self, entity_name: str) -> str:
        """Normalize entity name for entity_to_adif lookup (mirrors _norm used at init)"""
        s = (entity_name or "").lower()
        # Handle common abbreviations
        s = s.replace("st.", "saint ").replace("st ", "saint ")
        for ch in [",","(",")","[","]","'","`","'","–","-","  "]:
            s = s.replace(ch, " ")
        s = " ".join(s.split())
        s = s.replace("europen", "european").replace("russian federation", "russia")
        s = s.replace("federal republic of", "fed rep of")
        s = s.replace("kingdom of", "").replace("republic of", "").replace("islamic republic of", "")
        s = s.replace("&", "and")
        s = self.SYNONYMS.get(s.strip(), s.strip())
        return s.strip()
    
    def resolve(self, dxcall: str):
        """Resolve callsign to DXCC, country name, and CQ zone.
        Uses CSV/DB rules first, falls back to cty.dat lookup."""
        cs=(dxcall or "").upper()
        for suf in self.ignore_suffixes:
            if cs.endswith(suf.upper()):
                cs = cs[:-len(suf)]
        
        # Try CSV/DB rules first (these have ADIF codes)
        for pfx, adif, entity, cq in sorted(self.rules, key=lambda r: len(r[0]), reverse=True):
            if cs.startswith(pfx):
                return adif, entity, cq
        
        # Fallback to cty.dat lookup
        meta = self.lookup(dxcall)
        if meta:
            country = meta.get("country")
            cq = meta.get("cq")
            dxcc = meta.get("dxcc")
            
            # If we got DXCC from cty.dat, use it
            if dxcc:
                return dxcc, country, cq
            
            # Try to find DXCC from entity mapping with normalization
            if country and hasattr(self, 'normalize_entity'):
                country_key = self.normalize_entity(country)
                if country_key in self.entity_to_adif:
                    return self.entity_to_adif[country_key], country, cq
            
            # Return country and CQ even if DXCC not found (better than None)
            return None, country, cq
        
        return None, None, None
