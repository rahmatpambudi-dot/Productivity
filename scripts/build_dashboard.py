#!/usr/bin/env python3
"""
Build NDC & RDC Dashboard
- Fetches all raw rows from Google Sheets API
- Saves slim data.json (only needed columns)
- Saves data_utilisasi.json (utilisasi MPP & Armada)
- Injects timestamp into HTML template
"""

import os, json, datetime, re
from collections import defaultdict
from google.oauth2 import service_account
from googleapiclient.discovery import build as gapi_build

SPREADSHEET_ID = "1wumoDA8SrXmaEXRkI_2lNlvof9JVtsXceeE2qhLtb7A"

# Master Asset roster — separate spreadsheet, one tab per month (Indonesian month names)
MASTER_ASSET_SPREADSHEET_ID = "1I20iRUWcJplXcefl_-E0li_Af-lV2vBawCaz4_Phm4I"
MASTER_ASSET_MONTHS = {
    'Januari': '01', 'Februari': '02', 'Maret': '03', 'April': '04',
    'Mei': '05', 'Juni': '06', 'Juli': '07', 'Agustus': '08',
    'September': '09', 'Oktober': '10', 'November': '11', 'Desember': '12',
}
ARMADA_TYPE_NORMALIZE = {
    'CDD': 'CDD', 'CDD LONG CHASSIS': 'CDDLC', 'CDD PICK UP': 'CDD PICKUP', 'CDD PICKUP': 'CDD PICKUP',
    'CDE': 'CDE', 'CDE LONG CHASSIS': 'CDELC', 'CDE LC': 'CDELC', 'CDELC': 'CDELC', 'CDE PICK UP': 'CDE PICKUP', 'CDE PICKUP': 'CDE PICKUP',
    'FUSO': 'FUSO', 'FUSO GENAP': 'FUSO', 'MIN VAN OPS': 'MINI VAN BOX', 'MINI VAN BOX': 'MINI VAN BOX', 'MINI VANBOX': 'MINI VAN BOX', 'MVB': 'MINI VAN BOX',
    'MOTOR BOX': 'MOTOR BOX', 'PICK UP': 'PICKUP', 'PICKUP': 'PICKUP', 'PICKUP EXTRA': 'PICKUP',
    'VAN': 'MINI VAN BOX', 'VAN BOX': 'MINI VAN BOX', 'WINGBOX': 'WINGBOX', 'WINGBOX GANJIL': 'WINGBOX',
    'BIG MAMA': 'BIG MAMA', 'CONT-40': 'CONT-40', 'TRACTOR HEAD': 'TRACTOR HEAD',
}
def norm_armada_type(t):
    v = (t or '').strip().upper()
    if not v: return 'LAINNYA'
    return ARMADA_TYPE_NORMALIZE.get(v, v)

# Utilisasi sheet — same spreadsheet, different sheet name
UTIL_SHEET_NAME = "Utilisasi"  # adjust if sheet name is different

SHEETS = [
    { "name": "AHI JABABEKA",  "site": "JABABEKA" },
    { "name": "HCI JABABEKA",  "site": "JABABEKA" },
    { "name": "KLS JABABEKA",  "site": "JABABEKA" },
    { "name": "HCI CIKUPA",    "site": "CIKUPA"   },
    { "name": "CORP SIDOARJO", "site": "SDA"      },
    { "name": "CORP TALLO",    "site": "TALLO"    },
    { "name": "CORP TAMORA",   "site": "TAMORA"   },
]

def get_service():
    creds_json = os.environ.get("GSHEET_SERVICE_ACCOUNT")
    if not creds_json:
        raise ValueError("GSHEET_SERVICE_ACCOUNT env var not set")
    creds_info = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(
        creds_info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return gapi_build("sheets", "v4", credentials=creds, cache_discovery=False)

def fetch_sheet(service, sheet_name, range_str="A:BF"):
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{sheet_name}'!{range_str}",
        valueRenderOption="FORMATTED_VALUE",
        dateTimeRenderOption="FORMATTED_STRING"
    ).execute()
    rows = result.get("values", [])
    if len(rows) < 2:
        return {"headers": [], "data": []}
    headers = [str(h).strip() for h in rows[0]]
    data = [list(r) + [""] * (len(headers) - len(r)) for r in rows[1:]]
    return {"headers": headers, "data": data}

def map_cols(headers):
    h = [x.upper() for x in headers]
    def find(*names):
        for n in names:
            for i, hh in enumerate(h):
                if n.upper() in hh: return i
        return -1
    return {
        "lc":          find("LC"),
        "owner":       find("OWNER"),
        "date":        find("DELIVERY DATE", "DELIVERY DAT"),
        "typeArmada":  find("TYPE ARMADA", "TYPE ARMAD"),
        "typeDelivery":find("TYPE DELIVERY", "TYPE DELIVER"),
        "nopol":       find("NOPOL"),
        "do_":         find("DO"),
        "cbm":         find("CBM"),
        "capArmada":   find("CAPACITY ARMADA", "CAPACITY ARM"),
        "dp":          find("DP"),
        "shipArea":    find("SHIPMENT AREA", "SHIPMENT AR"),
        "kategori":    find("KATEGORI"),
        "tat":         find("TAT"),
        "olfDet":      find("OLF DETERMINE", "OLF DET"),
        "satelite":    find("SATELITE", "SATELIT"),
        "jenisArmada": find("JENIS ARMADA", "JENIS ARM"),
        "jalur":       find("JALUR"),
        "ujp":         find("UJP"),
        "totalCost":   find("TOTAL COST"),
        "profFee":     find("PROF FEE"),
        "sewaArmada":  find("SEWA ARMADA"),
        "drvId":       find("DRIVERID", "DRIVER ID", "DRIVER_ID"),
        "crewId":      find("CREW1ID", "CREW 1 ID", "CREW1 ID", "CREW_1_ID"),
        "sla":         find("SLA CHECK IN", "SLA CHECKIN"),
    }

def parse_date_str(s):
    """Normalize date to YYYY-MM-DD string"""
    if not s: return None
    s = str(s).strip()
    for fmt in ("%m/%d/%Y","%d/%m/%Y","%Y-%m-%d","%d-%b-%Y","%d %b %Y","%m/%d/%y","%d/%m/%y"):
        try:
            return datetime.datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except: pass
    m = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})$", s)
    if m:
        p1, p2, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100: year += 2000
        if 1 <= p1 <= 12 and 1 <= p2 <= 31:
            try: return datetime.date(year, p1, p2).strftime("%Y-%m-%d")
            except: pass
        if 1 <= p2 <= 12 and 1 <= p1 <= 31:
            try: return datetime.date(year, p2, p1).strftime("%Y-%m-%d")
            except: pass
    try:
        n = int(s)
        if 40000 < n < 60000:
            d = datetime.date(1899, 12, 30) + datetime.timedelta(days=n)
            return d.strftime("%Y-%m-%d")
    except: pass
    return None

def cell(r, idx):
    if idx < 0 or idx >= len(r): return ""
    return str(r[idx]).strip()

def to_float(s):
    """Parse float from cell, strip commas"""
    if not s: return None
    try: return float(str(s).replace(',','').replace('%','').strip())
    except: return None

def safe_float(v, default=0):
    """Like to_float but returns default instead of None, ignores #REF! and sheet errors"""
    if v is None: return default
    try: return float(str(v).replace(',','').replace('%','').strip())
    except: return default

def slim_row(r, cols, sheet_name, site):
    return {
        "sheet": sheet_name,
        "site":  site,
        "lc":    cell(r, cols["lc"]),
        "owner": cell(r, cols["owner"]),
        "date":  parse_date_str(cell(r, cols["date"])),
        "ta":    cell(r, cols["typeArmada"]).upper(),
        "td":    cell(r, cols["typeDelivery"]).lower(),
        "nopol": cell(r, cols["nopol"]),
        "do":    cell(r, cols["do_"]),
        "cbm":   cell(r, cols["cbm"]),
        "cap":   cell(r, cols["capArmada"]),
        "dp":    cell(r, cols["dp"]),
        "sa":    cell(r, cols["shipArea"]).upper(),
        "kat":   cell(r, cols["kategori"]).upper(),
        "tat":   cell(r, cols["tat"]),
        "od":    cell(r, cols["olfDet"]).strip().lower() if cols["olfDet"] >= 0 else "",
        "sat":   cell(r, cols["satelite"]).upper() if cols["satelite"] >= 0 else "",
        "ja":    cell(r, cols["jenisArmada"]).upper() if cols.get("jenisArmada", -1) >= 0 else "",
        "jalur": cell(r, cols["jalur"]).strip() if cols.get("jalur",-1) >= 0 else "",
        "ujp":   to_float(cell(r, cols["ujp"])) if cols.get("ujp",-1) >= 0 else None,
        "cost":  to_float(cell(r, cols["totalCost"])) if cols.get("totalCost",-1) >= 0 else None,
        "pf":    to_float(cell(r, cols["profFee"])) if cols.get("profFee",-1) >= 0 else None,
        "sewa":  to_float(cell(r, cols["sewaArmada"])) if cols.get("sewaArmada",-1) >= 0 else None,
        "drvId":  cell(r, cols["drvId"]).upper()  if cols.get("drvId",-1)  >= 0 else "",
        "crewId": cell(r, cols["crewId"]).upper() if cols.get("crewId",-1) >= 0 else "",
        "sla":    cell(r, cols["sla"]).strip().upper() if cols.get("sla",-1) >= 0 else "",
    }

def parse_tat_py(s):
    if not s: return None
    import re as _re
    m = _re.match(r'^(-?\d+):(\d{2})(?::(\d{2}))?$', str(s).strip())
    if m: return int(m.group(1)) + int(m.group(2))/60 + (int(m.group(3)) if m.group(3) else 0)/3600
    try:
        n = float(s)
        if 0 < n < 2: return n * 24
    except: pass
    return None

def to_num(s):
    """Parse number from cell, strip % sign if present"""
    if not s: return None
    s = str(s).strip().replace('%','').replace(',','.')
    try: return float(s)
    except: return None

# ── UTILISASI ──────────────────────────────────────────────────
def fetch_utilisasi(service, timestamp):
    """
    Fetch sheet Utilisasi (multi-header: row1=group, row2=sub-col).
    Expected structure (same as CSV):
      Col A  : Site Origin
      Col B  : TANGGAL
      Col C  : CAPACITY MPP (DRIVER) > Assets
      Col D  : Plan
      Col E  : Aktual
      Col F  : GAP
      Col G  : Kehadiran
      Col H  : Utilize
      Col I  : CAPACITY MPP (AST. DRIVER) > Assets
      Col J  : Plan
      Col K  : Aktual
      Col L  : GAP
      Col M  : Kehadiran
      Col N  : Utilize
      Col O  : CAPACITY MPP (STAFF UP) > Assets  (skipped — not needed)
      Col P  : Plan
      Col Q  : Aktual
      Col R  : GAP
      Col S  : Utilize
      Col T  : CAPACITY ARMADA > Assets
      Col U  : Availibility
      Col V  : Utilisasi
      Col W  : Ritase  (skipped)
      Col X  : Service (skipped)
      Col Y  : Idle    (skipped)
      Col Z  : Other Delivery (skipped)
    """
    print(f"  Fetching {UTIL_SHEET_NAME}...")
    try:
        raw = fetch_sheet(service, UTIL_SHEET_NAME, range_str="A:Z")
    except Exception as e:
        print(f"  ✗ {UTIL_SHEET_NAME}: {e}")
        return [], {}

    rows = raw["data"]
    if len(rows) < 2:
        print(f"  ✗ {UTIL_SHEET_NAME}: not enough rows")
        return [], {}

    # Row 0 = group headers, Row 1 = sub-col headers, data starts row 2
    # But fetch_sheet already consumed row[0] as headers and rows[1:] as data
    # So raw["data"][0] is actually the sub-header row, data starts raw["data"][1]
    sub_headers = [str(x).strip().upper() for x in rows[0]]
    data_rows   = rows[1:]

    # Fixed column indices based on known structure
    # (robust: find by sub-header name)
    # Fixed column indices based on actual sheet structure:
    # A=0 Site, B=1 Tanggal
    # DRIVER: C=2 Assets, D=3 Plan, E=4 Aktual, F=5 GAP, G=6 Kehadiran, H=7 Utilize
    # AST.DRV: I=8 Assets, J=9 Plan, K=10 Aktual, L=11 GAP, M=12 Kehadiran, N=13 Utilize
    # STAFF UP: O=14 Assets, P=15 Plan, Q=16 Aktual, R=17 GAP, S=18 Utilize
    # ARMADA:  T=19 Assets, U=20 Availibility, V=21 Utilisasi, W=22 Ritase, X=23 Service, Y=24 Idle, Z=25 Other
    IDX = {
        'site':       0,
        'date':       1,
        'drv_plan':      3,   # DRIVER Plan
        'drv_aktual':    4,   # DRIVER Aktual
        'drv_kehadiran': 6,   # DRIVER Kehadiran
        'drv_utilize':   7,   # DRIVER Utilize
        'ast_plan':      9,   # AST.DRIVER Plan
        'ast_aktual':    10,  # AST.DRIVER Aktual
        'ast_kehadiran': 12,  # AST.DRIVER Kehadiran
        'ast_utilize':   13,  # AST.DRIVER Utilize
        'arm_assets': 19,  # ARMADA Assets
        'arm_avail':  20,  # ARMADA Availibility
        'arm_util':   21,  # ARMADA Utilisasi
        'arm_service':23,  # ARMADA Service
        'arm_idle':   24,  # ARMADA Idle
    }
    print(f"  Utilisasi col indices (hardcoded): {IDX}")

    debug_util = {"sub_headers": sub_headers}

    util_rows = []
    for r in data_rows:
        site = cell(r, IDX['site'])
        date = parse_date_str(cell(r, IDX['date']))
        if not site or not date:
            continue

        drv_plan      = to_num(cell(r, IDX['drv_plan']))
        drv_aktual    = to_num(cell(r, IDX['drv_aktual']))
        drv_kehadiran = to_num(cell(r, IDX['drv_kehadiran']))
        drv_utilize   = to_num(cell(r, IDX['drv_utilize']))
        ast_plan      = to_num(cell(r, IDX['ast_plan']))
        ast_aktual    = to_num(cell(r, IDX['ast_aktual']))
        ast_kehadiran = to_num(cell(r, IDX['ast_kehadiran']))
        ast_utilize   = to_num(cell(r, IDX['ast_utilize']))
        arm_assets = to_num(cell(r, IDX['arm_assets']))
        arm_avail  = to_num(cell(r, IDX['arm_avail']))
        arm_util   = to_num(cell(r, IDX['arm_util']))
        arm_service= to_num(cell(r, IDX['arm_service']))
        arm_idle   = to_num(cell(r, IDX['arm_idle']))

        util_rows.append({
            'site':       site,
            'date':       date,
            'drv_plan':      drv_plan,
            'drv_aktual':    drv_aktual,
            'drv_kehadiran': drv_kehadiran,
            'drv_utilize':   drv_utilize,
            'ast_plan':      ast_plan,
            'ast_aktual':    ast_aktual,
            'ast_kehadiran': ast_kehadiran,
            'ast_utilize':   ast_utilize,
            'arm_assets': arm_assets,
            'arm_avail':  arm_avail,
            'arm_util':   arm_util,
            'arm_service':arm_service,
            'arm_idle':   arm_idle,
        })

    print(f"  ✓ {UTIL_SHEET_NAME}: {len(util_rows)} rows")
    return util_rows, debug_util


def compute_ritase_by_site_date(all_rows):
    """
    Compute per-site per-date:
      ritase_armada = unique LC / unique Nopol
      ritase_mpp    = unique LC / unique DriverId (non-empty)
    Returns dict: { (site, date): {'ritase_armada': float, 'ritase_mpp': float} }
    Site mapping aligns with UTIL_SITE_MAP (same as Sheets sheet names).
    """
    SHEET_TO_UTIL_SITE = {
        'AHI JABABEKA':  'AHI JABABEKA',
        'HCI JABABEKA':  'HCI JABABEKA',
        'KLS JABABEKA':  None,           # KLS excluded from utilisasi
        'HCI CIKUPA':    'HCI CIKUPA',
        'CORP SIDOARJO': 'CORP SIDOARJO',
        'CORP TALLO':    'CORP TALLO',
        'CORP TAMORA':   'CORP TAMORA',
    }
    from collections import defaultdict
    # bucket: (util_site, date) -> {lc, nopol, drvid}
    buckets = defaultdict(lambda: {'lc': set(), 'nopol': set(), 'drvid': set()})

    for r in all_rows:
        util_site = SHEET_TO_UTIL_SITE.get(r.get('sheet'))
        if not util_site: continue
        date = r.get('date')
        if not date: continue
        td = (r.get('td') or '').lower()
        if td == 'satelite': continue  # same exclusion as existing ritase logic

        lc    = r.get('lc', '')
        nopol = r.get('nopol', '')
        drvid = r.get('drvId', '')

        key = (util_site, date)
        if lc:    buckets[key]['lc'].add(lc)
        if nopol: buckets[key]['nopol'].add(nopol)
        if drvid: buckets[key]['drvid'].add(drvid)

    result = {}
    for (util_site, date), v in buckets.items():
        lc_cnt    = len(v['lc'])
        nopol_cnt = len(v['nopol'])
        drvid_cnt = len(v['drvid'])
        result[(util_site, date)] = {
            'ritase_armada': round(lc_cnt / nopol_cnt, 4) if nopol_cnt > 0 else None,
            'ritase_mpp':    round(lc_cnt / drvid_cnt, 4) if drvid_cnt > 0 else None,
        }
    return result


def compute_fbi_kls_util_by_date(all_rows):
    """
    Compute daily MPP & Armada metrics for JAB_FBI, JAB_KLS, SDA_HCI, SDA_AHI, SDA_FBI
    from trip data using fixed nopol lists.
    """
    import datetime

    FBI_NOPOL = {
        'A8012ZV','A8607WX','A8386VX','A8976XA','B9015SCF','B9018SCF',
        'A8157ZC','A8232ZC','B9747SCE','A8710ZE','A8711ZE','A8709ZE',
        'A8541ZE','A8506ZD','A8088VC',
    }
    KLS_NOPOL = {
        'A8437ZH','A8481ZH','A8801XZ','A8537ZF','A8721VB','A8717VB',
        'A8757VB','A8759VB','A8912VB','A8910VB','A8020VC','A8542XB',
        'A8237VD','B9044BRO','B9068BEN','A8876ZX','A8002XW','A8503ZX',
        'A8048ZX','A8288YX','A8976XY','A8908XY','B9190SDB','B9642SCE',
        'A8098ZH','A8504ZX','A8339ZS','A8432ZS','A8159ZC','B9320SCE',
        'A8721ZV','A8553VB','A8961VB','A8983VB','A8017VC','A8373VC',
        'A8304VC','A8476VC','A8486VC','A8505VC','A8520VC',
    }
    HCI_SDA_NOPOL = {
        'B9059BEN','B9057BEN','W8528PC','W8890NU','W8894NU','W8551PV',
        'W8911PS','W8746PV','W8745PV','W8906PS','W8847QD','W8851QD',
        'W8478QD','W8581QD','W8582QD','W8518QE','W8520QE','A8064ZV',
        'W8150PC','A8524VB','W8194QA','W8195QA','W8910PS','W8081QB',
        'W8082QB','W8108QB','W8265QC','W8264QC',
    }
    AHI_SDA_NOPOL = {
        'B9056BEN','A8572ZE','W8819QB','W8850QD','W8656QE','W8907PS',
        'W8908PS','W8479QD','W8555QC','W8744PV','A8653ZF','W8519QE',
        'W8342QA','W8224QB','W8225QB','W8776NU','W8262QC',
    }
    FBI_SDA_NOPOL = {
        'W8909PS','W8773NU','W8263QC',
    }
    HCI_TAMORA_NOPOL = {
        'BK8136LM','BK8022LM','BK8031LM','BK8009MI','BK8815MG',
        'BK8805MH','BK8806MH','BK8807MH','BK8803MH','BK8804MH',
        'BK8047MQ','BK8073MQ','BK8075MQ','BK8696MS','BK8871MS',
    }
    AHI_TAMORA_NOPOL = {
        'BK8299MH','BK8172LM','BK8135LM','BK8146LM','BK8192MQ',
        'BK8074MQ','BK8309MS','BK8646MS','BK8141LM','BK8647MS',
    }
    FBI_TAMORA_NOPOL = {
        'A8330VX','BK8099LM',
    }
    KLS_TAMORA_NOPOL = {
        'BK8191MQ','BK8633MS',
    }
    HCI_TALLO_NOPOL = {
        'A8348VA','DD8283SY','A8997ZD','DD8634RG','DD8632RG',
        'DD8987RG','DD8986RG','DD8705RM','DD8199SJ','DD8195AK',
        'DD8328KJ','DD8194AK','DD8394KL','DD8389QW',
    }
    AHI_TALLO_NOPOL = {
        'DD8173RV','DD8165UE','DD8633RG','DD8797SZ','DD8772UF','DD8140AK',
    }
    FBI_TALLO_NOPOL = {
        'A8609ZF',
    }

    # Libur nasional 2026
    HOLIDAYS = {
        '2026-01-01','2026-01-16','2026-02-17','2026-03-19',
        '2026-03-21','2026-03-22','2026-04-03','2026-04-05',
        '2026-05-01','2026-05-14','2026-05-27','2026-05-31',
        '2026-06-01','2026-06-16','2026-08-17','2026-08-25','2026-12-25',
    }
    KLS_CUTI = {
        '2026-03-20','2026-03-23','2026-03-24',
        '2026-06-02','2026-06-03','2026-06-04',
        '2026-06-05','2026-06-08',
    }
    KLS_EXCLUDE = HOLIDAYS | KLS_CUTI

    buckets = defaultdict(lambda: {'drvid': set(), 'nopol': set(), 'crewid': set()})

    for r in all_rows:
        date  = r.get('date')
        if not date: continue
        if (r.get('td') or '').lower() == 'satelite': continue

        nopol  = (r.get('nopol') or '').strip().upper()
        drvid  = r.get('drvId', '')
        crewid = r.get('crewId', '')

        if nopol in FBI_NOPOL:         bu = 'JAB_FBI'
        elif nopol in KLS_NOPOL:       bu = 'JAB_KLS'
        elif nopol in HCI_SDA_NOPOL:   bu = 'SDA_HCI'
        elif nopol in AHI_SDA_NOPOL:   bu = 'SDA_AHI'
        elif nopol in FBI_SDA_NOPOL:      bu = 'SDA_FBI'
        elif nopol in HCI_TAMORA_NOPOL:    bu = 'TAMORA_HCI'
        elif nopol in AHI_TAMORA_NOPOL:    bu = 'TAMORA_AHI'
        elif nopol in FBI_TAMORA_NOPOL:    bu = 'TAMORA_FBI'
        elif nopol in KLS_TAMORA_NOPOL:    bu = 'TAMORA_KLS'
        elif nopol in HCI_TALLO_NOPOL:     bu = 'TALLO_HCI'
        elif nopol in AHI_TALLO_NOPOL:     bu = 'TALLO_AHI'
        elif nopol in FBI_TALLO_NOPOL:     bu = 'TALLO_FBI'
        else: continue

        try:
            dow = datetime.date.fromisoformat(date).weekday()
        except: continue

        # Day exclusions
        if bu in ('JAB_FBI','SDA_FBI','TAMORA_FBI','TALLO_FBI'):
            if dow == 6: continue
            if date in HOLIDAYS: continue
        elif bu == 'JAB_KLS':
            if dow >= 5: continue
            if date in KLS_EXCLUDE: continue
        elif bu == 'TAMORA_KLS':
            if dow >= 5: continue
            if date in KLS_EXCLUDE: continue
        elif bu in ('SDA_HCI','SDA_AHI','TAMORA_HCI','TAMORA_AHI','TALLO_HCI','TALLO_AHI'):
            if dow == 6: continue
            if date in HOLIDAYS: continue

        if nopol: buckets[(bu, date)]['nopol'].add(nopol)
        if drvid: buckets[(bu, date)]['drvid'].add(drvid)
        if crewid: buckets[(bu, date)]['crewid'].add(crewid)

    result = {}
    for (bu, date), v in buckets.items():
        drv_cnt   = len(v['drvid'])
        nopol_cnt = len(v['nopol'])
        crew_cnt  = len(v['crewid'])
        result[(bu, date)] = {
            'drv_aktual':   drv_cnt,
            'drv_plan':     drv_cnt,
            'nopol_aktual': nopol_cnt,
            'crew_aktual':  crew_cnt if bu not in ('JAB_FBI','SDA_FBI','TAMORA_FBI','TALLO_FBI') else 0,
        }
    return result


def aggregate_monthly(all_rows, timestamp):
    """Pre-compute all metrics per site per month for data_monthly.json"""
    SITES = ['JABABEKA','CIKUPA','SDA','TALLO','TAMORA']
    SL = {'JABABEKA':'Jababeka','CIKUPA':'Cikupa','SDA':'Sidoarjo','TALLO':'Tallo','TAMORA':'Tamora'}

    buckets = defaultdict(list)
    for r in all_rows:
        if r.get('date') and r.get('site'):
            buckets[(r['site'], r['date'][:7])].append(r)

    months = sorted(set(mo for _, mo in buckets.keys()))
    result = []

    for mo in months:
        for site in SITES:
            sr = buckets.get((site, mo), [])
            if not sr: continue
            isJAB = site == 'JABABEKA'
            isCIK = site == 'CIKUPA'
            isSDA = site == 'SDA'
            srMain = [r for r in sr if r.get('sheet') != 'KLS JABABEKA'] if isJAB else sr

            olf_r = [r for r in srMain if r.get('td')=='store' and r.get('kat')=='REGULAR'
                     and not (isJAB and r.get('sheet')=='AHI JABABEKA' and r.get('owner')=='FBI')
                     and not (isSDA and r.get('owner')=='FBI')
                     and (not isCIK or 'non cikande' in (r.get('od') or ''))]
            oL = sum(safe_float(r.get('cbm')) for r in olf_r)
            oM = sum(safe_float(r.get('cap')) for r in olf_r)

            dpMx_r = [r for r in srMain if r.get('td')=='customer'
                      and not ((isJAB or isSDA) and r.get('owner')=='FBI')]
            dpNR_r = [r for r in dpMx_r if r.get('kat')=='NON REGULAR']
            drR = [r for r in srMain if r.get('td')=='customer' and r.get('ta')!='PICKUP'
                   and r.get('kat')=='REGULAR'
                   and not ((isJAB or isSDA) and r.get('owner')=='FBI')
                   and (not isCIK or 'NON SATELIT' in (r.get('sat') or ''))]

            cbmT = sum(safe_float(r.get('cbm')) for r in drR)
            doN  = sum(safe_float(r.get('do') ) for r in drR)
            dpN  = sum(safe_float(r.get('dp') ) for r in drR)

            daily = defaultdict(lambda: {'lc': set(), 'np': set()})
            for r in sr:
                td = r.get('td','')
                if td == 'satelite': continue
                if isCIK and (r.get('ja') or '').upper() == 'MIN VAN OPS': continue
                if r.get('date'): daily[r['date']]['lc'].add(r.get('lc','')); daily[r['date']]['np'].add(r.get('nopol',''))
            rit_vals = [len(v['lc'])/len(v['np']) for v in daily.values() if len(v['np'])>0]

            tatD_r = [r for r in srMain if r.get('td')=='customer' and r.get('kat')=='REGULAR'
                      and (not isCIK or 'NON SATELIT' in (r.get('sat') or ''))
                      and (isCIK or 'DALAM KOTA' in (r.get('sa') or ''))]
            tatD_v = [t for r in tatD_r if (t:=parse_tat_py(r.get('tat'))) is not None and 0<=t<=24]
            tatS_r = [r for r in srMain if r.get('td')=='store' and r.get('kat')=='REGULAR'
                      and (not isCIK or 'NON SATELIT' in (r.get('sat') or ''))
                      and (isCIK or 'DALAM KOTA' in (r.get('sa') or ''))]
            cutoff = 12 if isCIK else 24
            tatS_v = [t for r in tatS_r if (t:=parse_tat_py(r.get('tat'))) is not None and 0<=t<=cutoff]

            def _avg(lst): lst=[x for x in lst if x is not None]; return round(sum(lst)/len(lst),4) if lst else None
            def _avg_list(lst): return round(sum(lst)/len(lst),4) if lst else None

            result.append({
                'site': site, 'label': SL[site], 'month': mo,
                'ritase':   _avg(rit_vals),
                'olf':      round(oL/oM,4) if oM>0 else None,
                'dpStore':  _avg_list([safe_float(r.get('dp')) for r in olf_r]),
                'dpMix':    _avg_list([safe_float(r.get('dp')) for r in dpMx_r]),
                'dpNonReg': _avg_list([safe_float(r.get('dp')) for r in dpNR_r]),
                'dpReg':    _avg_list([safe_float(r.get('dp')) for r in drR]),
                'doTrip':   _avg_list([safe_float(r.get('do')) for r in drR]),
                'doDp':     round(doN/dpN,4) if dpN>0 else None,
                'cbmDo':    round(cbmT/doN,4) if doN>0 else None,
                'cbmDp':    round(cbmT/dpN,4) if dpN>0 else None,
                'tatDirect':_avg(tatD_v),
                'tatStore': _avg(tatS_v),
            })
    return {'timestamp': timestamp, 'monthly': result}


def fetch_master_asset(service):
    """Fetch Master Asset roster (one tab per month) from the separate Master Asset spreadsheet.
    Returns { 'YYYY-MM': { site: { normalized_type: [nopol,...] } } }"""
    try:
        meta = service.spreadsheets().get(spreadsheetId=MASTER_ASSET_SPREADSHEET_ID).execute()
        tab_names = [s['properties']['title'] for s in meta.get('sheets', [])]
    except Exception as e:
        print(f"  ✗ Master Asset: cannot list tabs: {e}")
        return {}

    months_out = {}
    for tab in tab_names:
        month_num = MASTER_ASSET_MONTHS.get(tab.strip())
        if not month_num:
            continue  # skip non-month tabs
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=MASTER_ASSET_SPREADSHEET_ID,
                range=f"'{tab}'!A:K",
                valueRenderOption="FORMATTED_VALUE",
            ).execute()
            rows = result.get("values", [])
        except Exception as e:
            print(f"  ✗ Master Asset tab {tab}: {e}")
            continue
        if len(rows) < 2:
            continue
        headers = [str(h).strip().upper() for h in rows[0]]
        def col(*names):
            for n in names:
                for i, hh in enumerate(headers):
                    if n in hh: return i
            return -1
        i_nopol = col('NOPOL')
        i_type  = col('TYPE')
        i_site  = col('SITE')
        if i_nopol < 0 or i_type < 0 or i_site < 0:
            print(f"  ✗ Master Asset tab {tab}: missing NOPOL/Type/Site column")
            continue

        by_site_type = defaultdict(lambda: defaultdict(list))
        for r in rows[1:]:
            if len(r) <= max(i_nopol, i_type, i_site): continue
            nopol = (r[i_nopol] or '').strip().upper()
            typ   = norm_armada_type(r[i_type] if i_type < len(r) else '')
            site  = (r[i_site] or '').strip()
            if not nopol or not site: continue
            # Tamora master sheet: 'CDE' entries are a data-entry shorthand for 'CDE LC'
            # (CDELC), not a genuinely separate short-chassis fleet like at other sites.
            if 'TAMORA' in site.upper() and typ == 'CDE':
                typ = 'CDELC'
            by_site_type[site][typ].append(nopol)

        month_key = f"2026-{month_num}"
        months_out[month_key] = {s: dict(t) for s, t in by_site_type.items()}
        total_nopol = sum(len(v) for t in by_site_type.values() for v in t.values())
        print(f"  ✓ Master Asset {tab} ({month_key}): {total_nopol} nopol, {len(by_site_type)} site")

    return months_out


def build():
    now_wib = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
    timestamp = now_wib.strftime("%d %b %Y %H:%M WIB")
    print(f"Building at {timestamp}")

    service = get_service()
    all_rows = []
    total = 0

    # TEMP DEBUG — diagnosing why HCI JABABEKA / KLS JABABEKA yield 0 rows.
    # Captured per-sheet and written to debug_build.json so we can inspect it
    # without needing GitHub Actions log access (Azure Blob redirect issue).
    import traceback
    debug_info = []

    for s in SHEETS:
        print(f"  Fetching {s['name']}...")
        sheet_debug = {"name": s["name"], "site": s["site"]}
        try:
            raw = fetch_sheet(service, s["name"])
            sheet_debug["raw_data_rows"] = len(raw["data"])
            sheet_debug["headers"] = raw["headers"]
            if not raw["headers"]:
                print(f"  ✗ {s['name']}: empty")
                sheet_debug["status"] = "empty_headers"
                debug_info.append(sheet_debug)
                continue

            cols = map_cols(raw["headers"])
            sheet_debug["cols"] = cols
            h_up = [x.upper() for x in raw["headers"]]

            if s["name"] == "HCI CIKUPA":
                tat_cols = [i for i, h in enumerate(h_up) if h == "TAT"]
                if tat_cols: cols["tat"] = tat_cols[-1]
                sat_i = next((i for i, h in enumerate(h_up) if "SATELIT" in h), -1)
                cols["satelite"] = sat_i
                olf_i = next((i for i, h in enumerate(h_up) if "OLF DETERMINE" in h), -1)
                if olf_i < 0: olf_i = next((i for i, h in enumerate(h_up) if "OLF" in h), -1)
                if olf_i < 0: olf_i = next((i for i, h in enumerate(h_up) if "DETERMINE" in h), -1)
                cols["olfDet"] = olf_i
                sa_cols = [i for i, h in enumerate(h_up) if "SHIPMENT" in h]
                if sa_cols: cols["shipArea"] = sa_cols[-1]
                print(f"  CIKUPA cols: tat={cols['tat']}, sat={cols['satelite']}, olfDet={cols['olfDet']}, shipArea={cols['shipArea']}")

            print(f"  {s['name']} col indices: do={cols['do_']} cbm={cols['cbm']} cap={cols['capArmada']} dp={cols['dp']} kat={cols['kategori']}")

            # sample first 3 raw date cells (before parsing) to catch format issues
            sheet_debug["sample_date_cells"] = [cell(r, cols["date"]) for r in raw["data"][:3]]
            sheet_debug["sample_parsed_dates"] = [parse_date_str(cell(r, cols["date"])) for r in raw["data"][:3]]

            for r in raw["data"]:
                row = slim_row(r, cols, s["name"], s["site"])
                if row["date"]:
                    all_rows.append(row)

            cnt = len([r for r in raw["data"] if parse_date_str(cell(r, cols["date"]))])
            total += cnt
            print(f"  ✓ {s['name']}: {cnt} rows")
            sheet_debug["status"] = "ok"
            sheet_debug["parsed_rows"] = cnt

        except Exception as e:
            print(f"  ✗ {s['name']}: {e}")
            sheet_debug["status"] = "exception"
            sheet_debug["error"] = str(e)
            sheet_debug["traceback"] = traceback.format_exc()

        debug_info.append(sheet_debug)

    try:
        _dbg_base = os.path.dirname(os.path.abspath(__file__))
        _dbg_path = os.path.join(_dbg_base, '..', 'debug_build.json')
        with open(_dbg_path, 'w', encoding='utf-8') as _dbgf:
            json.dump({"timestamp": timestamp, "sheets": debug_info}, _dbgf, ensure_ascii=False, indent=2)
        print(f"debug_build.json written: {len(debug_info)} sheets")
    except Exception as _e:
        print(f"  ✗ failed writing debug_build.json: {_e}")

    print(f"\nTotal rows: {total}")

    print("  Fetching Master Asset roster...")
    try:
        master_asset = fetch_master_asset(service)
    except Exception as e:
        print(f"  ✗ Master Asset: {e}")
        master_asset = {}

    base = os.path.dirname(os.path.abspath(__file__))
    data_path     = os.path.join(base, '..', 'data.json')
    monthly_path  = os.path.join(base, '..', 'data_monthly.json')
    util_path     = os.path.join(base, '..', 'data_utilisasi.json')
    master_asset_path = os.path.join(base, '..', 'data_master_asset.json')
    tpl_path      = os.path.join(base, '..', 'ndc_rdc_template.html')
    out_path      = os.path.join(base, '..', 'dashboard_ndc_rdc.html')

    with open(master_asset_path, 'w', encoding='utf-8') as f:
        json.dump({"timestamp": timestamp, "months": master_asset}, f, ensure_ascii=False, separators=(',',':'))
    print(f"data_master_asset.json: {os.path.getsize(master_asset_path)/1024:.1f} KB, {len(master_asset)} bulan")

    # Encode string fields to integer codes to reduce file size
    ENCODE_FIELDS = ['sheet','site','td','kat','ta','sa','owner','nopol','jalur','ja','sat','od','drvId','crewId','sla']
    
    # Build encoding maps from all rows
    enc_maps = {}
    for f in ENCODE_FIELDS:
        vals = sorted(set(str(r.get(f,'') or '') for r in all_rows))
        enc_maps[f] = {v: i for i, v in enumerate(vals)}
    dec_maps = {f: list(m.keys()) for f, m in enc_maps.items()}

    def encode_row(r):
        er = {}
        for k, v in r.items():
            if k in enc_maps and v is not None:
                er[k] = enc_maps[k].get(str(v) if v is not None else '', 0)
            else:
                er[k] = v
        return er

    # Split per site + encode
    from collections import defaultdict
    by_site = defaultdict(list)
    for r in all_rows:
        by_site[r.get('site','')].append(encode_row(r))

    SITES_LIST = ['JABABEKA','CIKUPA','SDA','TALLO','TAMORA']
    total_kb = 0
    for site in SITES_LIST:
        site_rows = by_site.get(site, [])
        site_path = os.path.join(base, '..', f'data_{site}.json')
        with open(site_path, 'w', encoding='utf-8') as f:
            json.dump({'timestamp': timestamp, 'maps': dec_maps, 'rows': site_rows}, f, ensure_ascii=False, separators=(',',':'))
        kb = os.path.getsize(site_path)/1024
        total_kb += kb
        print(f"data_{site}.json: {kb:.0f} KB ({len(site_rows)} rows)")

    # Keep data.json as combined encoded (for backward compat / ALL site filter)
    all_encoded = []
    for site in SITES_LIST:
        all_encoded.extend(by_site.get(site, []))
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump({'timestamp': timestamp, 'maps': dec_maps, 'rows': all_encoded}, f, ensure_ascii=False, separators=(',',':'))
    print(f"data.json (combined): {os.path.getsize(data_path)/1024:.0f} KB")

    # data_utilisasi.json — fetch FIRST so debug_util is available for data_monthly.json below
    util_rows, debug_util = fetch_utilisasi(service, timestamp)
    # Inject ritase_armada & ritase_mpp per site per date from raw trip data
    ritase_map = compute_ritase_by_site_date(all_rows)
    for row in util_rows:
        key = (row['site'], row['date'])
        r = ritase_map.get(key, {})
        row['ritase_armada'] = r.get('ritase_armada')
        row['ritase_mpp']    = r.get('ritase_mpp')

    # data_monthly.json
    monthly = aggregate_monthly(all_rows, timestamp)
    monthly["_debug_build"] = debug_info  # TEMP — remove after diagnosing HCI/KLS JABABEKA 0-row issue
    monthly["_debug_util"] = debug_util  # TEMP — verify Utilisasi sheet column indices (arm_avail>arm_assets check)
    with open(monthly_path, 'w', encoding='utf-8') as f:
        json.dump(monthly, f, ensure_ascii=False, separators=(',',':'))
    print(f"data_monthly.json: {os.path.getsize(monthly_path)/1024:.1f} KB")

    # Inject synthetic rows for JAB_FBI (assets=15) & JAB_KLS (assets=41)
    FBI_ASSETS = 15
    KLS_ASSETS = 41
    HCI_SDA_ASSETS = 28
    AHI_SDA_ASSETS = 17
    FBI_SDA_ASSETS = 3
    FBI_NOPOL = {
        'A8012ZV','A8607WX','A8386VX','A8976XA','B9015SCF','B9018SCF',
        'A8157ZC','A8232ZC','B9747SCE','A8710ZE','A8711ZE','A8709ZE',
        'A8541ZE','A8506ZD','A8088VC',
    }
    KLS_NOPOL = {
        'A8437ZH','A8481ZH','A8801XZ','A8537ZF','A8721VB','A8717VB',
        'A8757VB','A8759VB','A8912VB','A8910VB','A8020VC','A8542XB',
        'A8237VD','B9044BRO','B9068BEN','A8876ZX','A8002XW','A8503ZX',
        'A8048ZX','A8288YX','A8976XY','A8908XY','B9190SDB','B9642SCE',
        'A8098ZH','A8504ZX','A8339ZS','A8432ZS','A8159ZC','B9320SCE',
        'A8721ZV','A8553VB','A8961VB','A8983VB','A8017VC','A8373VC',
        'A8304VC','A8476VC','A8486VC','A8505VC','A8520VC',
    }
    HCI_SDA_NOPOL = {
        'B9059BEN','B9057BEN','W8528PC','W8890NU','W8894NU','W8551PV',
        'W8911PS','W8746PV','W8745PV','W8906PS','W8847QD','W8851QD',
        'W8478QD','W8581QD','W8582QD','W8518QE','W8520QE','A8064ZV',
        'W8150PC','A8524VB','W8194QA','W8195QA','W8910PS','W8081QB',
        'W8082QB','W8108QB','W8265QC','W8264QC',
    }
    AHI_SDA_NOPOL = {
        'B9056BEN','A8572ZE','W8819QB','W8850QD','W8656QE','W8907PS',
        'W8908PS','W8479QD','W8555QC','W8744PV','A8653ZF','W8519QE',
        'W8342QA','W8224QB','W8225QB','W8776NU','W8262QC',
    }
    FBI_SDA_NOPOL = {
        'W8909PS','W8773NU','W8263QC',
    }
    HCI_TAMORA_NOPOL = {
        'BK8136LM','BK8022LM','BK8031LM','BK8009MI','BK8815MG',
        'BK8805MH','BK8806MH','BK8807MH','BK8803MH','BK8804MH',
        'BK8047MQ','BK8073MQ','BK8075MQ','BK8696MS','BK8871MS',
    }
    AHI_TAMORA_NOPOL = {
        'BK8299MH','BK8172LM','BK8135LM','BK8146LM','BK8192MQ',
        'BK8074MQ','BK8309MS','BK8646MS','BK8141LM','BK8647MS',
    }
    FBI_TAMORA_NOPOL = {
        'A8330VX','BK8099LM',
    }
    KLS_TAMORA_NOPOL = {
        'BK8191MQ','BK8633MS',
    }
    HCI_TALLO_NOPOL = {
        'A8348VA','DD8283SY','A8997ZD','DD8634RG','DD8632RG',
        'DD8987RG','DD8986RG','DD8705RM','DD8199SJ','DD8195AK',
        'DD8328KJ','DD8194AK','DD8394KL','DD8389QW',
    }
    AHI_TALLO_NOPOL = {
        'DD8173RV','DD8165UE','DD8633RG','DD8797SZ','DD8772UF','DD8140AK',
    }
    FBI_TALLO_NOPOL = {
        'A8609ZF',
    }
    HCI_TAMORA_NOPOL2 = {
        'BK8136LM','BK8022LM','BK8031LM','BK8009MI','BK8815MG',
        'BK8805MH','BK8806MH','BK8807MH','BK8803MH','BK8804MH',
        'BK8047MQ','BK8073MQ','BK8075MQ','BK8696MS','BK8871MS',
    }
    AHI_TAMORA_NOPOL2 = {
        'BK8299MH','BK8172LM','BK8135LM','BK8146LM','BK8192MQ',
        'BK8074MQ','BK8309MS','BK8646MS','BK8141LM','BK8647MS',
    }
    FBI_TAMORA_NOPOL2 = {'A8330VX','BK8099LM'}
    KLS_TAMORA_NOPOL2 = {'BK8191MQ','BK8633MS'}
    HCI_TALLO_NOPOL2 = {
        'A8348VA','DD8283SY','A8997ZD','DD8634RG','DD8632RG',
        'DD8987RG','DD8986RG','DD8705RM','DD8199SJ','DD8195AK',
        'DD8328KJ','DD8194AK','DD8394KL','DD8389QW',
    }
    AHI_TALLO_NOPOL2 = {'DD8173RV','DD8165UE','DD8633RG','DD8797SZ','DD8772UF','DD8140AK'}
    FBI_TALLO_NOPOL2 = {'A8609ZF'}
    ALL_NOPOL_MAP = {
        'JAB_FBI': FBI_NOPOL, 'JAB_KLS': KLS_NOPOL,
        'SDA_HCI': HCI_SDA_NOPOL, 'SDA_AHI': AHI_SDA_NOPOL, 'SDA_FBI': FBI_SDA_NOPOL,
        'TAMORA_HCI': HCI_TAMORA_NOPOL2, 'TAMORA_AHI': AHI_TAMORA_NOPOL2,
        'TAMORA_FBI': FBI_TAMORA_NOPOL2, 'TAMORA_KLS': KLS_TAMORA_NOPOL2,
        'TALLO_HCI': HCI_TALLO_NOPOL2, 'TALLO_AHI': AHI_TALLO_NOPOL2,
        'TALLO_FBI': FBI_TALLO_NOPOL2,
    }
    ASSETS_MAP = {
        'JAB_FBI': FBI_ASSETS, 'JAB_KLS': KLS_ASSETS,
        'SDA_HCI': HCI_SDA_ASSETS, 'SDA_AHI': AHI_SDA_ASSETS, 'SDA_FBI': FBI_SDA_ASSETS,
        'TAMORA_HCI': 15, 'TAMORA_AHI': 10, 'TAMORA_FBI': 2, 'TAMORA_KLS': 2,
        'TALLO_HCI': 14, 'TALLO_AHI': 6, 'TALLO_FBI': 1,
    }
    fbi_kls_map = compute_fbi_kls_util_by_date(all_rows)
    # Build per-BU ritase
    HOLIDAYS_2026 = {
        '2026-01-01','2026-01-16','2026-02-17','2026-03-19',
        '2026-03-21','2026-03-22','2026-04-03','2026-04-05',
        '2026-05-01','2026-05-14','2026-05-27','2026-05-31',
        '2026-06-01','2026-06-16','2026-08-17','2026-08-25','2026-12-25',
    }
    KLS_CUTI = {
        '2026-03-20','2026-03-23','2026-03-24',
        '2026-06-02','2026-06-03','2026-06-04','2026-06-05','2026-06-08',
    }
    KLS_EXCLUDE = HOLIDAYS_2026 | KLS_CUTI
    fbi_buckets = defaultdict(lambda: {'lc': set(), 'nopol': set(), 'drvid': set(), 'crewid': set()})
    for r in all_rows:
        date  = r.get('date')
        if not date: continue
        if (r.get('td') or '').lower() == 'satelite': continue
        nopol = (r.get('nopol') or '').strip().upper()
        bu = None
        for _bu, _nopols in ALL_NOPOL_MAP.items():
            if nopol in _nopols:
                bu = _bu; break
        if not bu: continue
        try:
            dow = datetime.date.fromisoformat(date).weekday()
        except: continue
        if bu in ('JAB_FBI','SDA_FBI','SDA_HCI','SDA_AHI'):
            if dow == 6: continue
            if date in HOLIDAYS_2026: continue
        elif bu == 'JAB_KLS':
            if dow >= 5: continue
            if date in KLS_EXCLUDE: continue
        lc = r.get('lc',''); drvid = r.get('drvId',''); crewid = r.get('crewId','')
        if lc:     fbi_buckets[(bu,date)]['lc'].add(lc)
        if nopol:  fbi_buckets[(bu,date)]['nopol'].add(nopol)
        if drvid:  fbi_buckets[(bu,date)]['drvid'].add(drvid)
        if crewid: fbi_buckets[(bu,date)]['crewid'].add(crewid)

    fbi_ritase = {}
    for (bu, date), v in fbi_buckets.items():
        lc_cnt = len(v['lc']); np_cnt = len(v['nopol']); dr_cnt = len(v['drvid'])
        fbi_ritase[(bu,date)] = {
            'ritase_armada': round(lc_cnt/np_cnt,4) if np_cnt>0 else None,
            'ritase_mpp':    round(lc_cnt/dr_cnt,4) if dr_cnt>0 else None,
        }

    for (bu, date), v in fbi_kls_map.items():
        assets = ASSETS_MAP.get(bu, 0)
        nopol_cnt = v['nopol_aktual']
        crew      = v.get('crew_aktual', 0)
        rit       = fbi_ritase.get((bu,date), {})
        util_rows.append({
            'site':          bu,
            'date':          date,
            'drv_plan':      v['drv_plan'],
            'drv_aktual':    v['drv_aktual'],
            'ast_plan':      crew if bu == 'JAB_KLS' else None,  # plan = aktual
            'ast_aktual':    crew if bu == 'JAB_KLS' else None,
            'arm_assets':    assets,
            'arm_avail':     nopol_cnt,
            'arm_util':      nopol_cnt,
            'ritase_armada': rit.get('ritase_armada'),
            'ritase_mpp':    rit.get('ritase_mpp'),
        })
    bu_counts = {}
    for k in fbi_kls_map: bu_counts[k[0]] = bu_counts.get(k[0],0)+1
    print(f"  + synthetic util rows: {bu_counts}")

    with open(util_path, 'w', encoding='utf-8') as f:
        json.dump({"timestamp": timestamp, "rows": util_rows}, f, ensure_ascii=False, separators=(',',':'))
    print(f"data_utilisasi.json: {os.path.getsize(util_path)/1024:.1f} KB, {len(util_rows)} rows")

    # Build HTML
    with open(tpl_path, 'r', encoding='utf-8') as f:
        html = f.read()
    html = html.replace('{{BUILD_TIMESTAMP}}', timestamp)
    html = html.replace('{{BUILD_DATE}}', now_wib.strftime('%Y-%m-%d'))
    html = html.replace('// {{EMBEDDED_DATA}}', '')

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Dashboard built: {out_path}")


if __name__ == '__main__':
    build()
