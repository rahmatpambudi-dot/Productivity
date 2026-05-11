#!/usr/bin/env python3
"""
Build NDC & RDC Dashboard
Fetches data from Google Sheets API using service account,
computes all metrics, and embeds data into static HTML.
"""

import os, sys, json, datetime, re
from google.oauth2 import service_account
from googleapiclient.discovery import build as gapi_build

SPREADSHEET_ID = "1w5bDjAVv_oJtGfz0sHbFLPL9j-FGZ8zCnOi7Z7N_RWg"

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

def fetch_sheet(service, sheet_name):
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=f"'{sheet_name}'!A:AE"
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
        "lc": find("LC"), "owner": find("OWNER"),
        "date": find("DELIVERY DATE","DELIVERY DAT"),
        "typeArmada": find("TYPE ARMADA","TYPE ARMAD"),
        "typeDelivery": find("TYPE DELIVERY","TYPE DELIVER"),
        "do_": find("DO"), "cbm": find("CBM"),
        "capArmada": find("CAPACITY ARMADA","CAPACITY ARM"),
        "dp": find("DP"), "shipArea": find("SHIPMENT AREA","SHIPMENT AR"),
        "kategori": find("KATEGORI"), "tat": find("TAT"),
        "olfDet": find("OLF DETERMINE","OLF DET"),
        "satelite": find("SATELITE","SATELIT"),
    }

def parse_date(s):
    if not s: return None
    s = str(s).strip()
    for fmt in ("%m/%d/%Y","%d/%m/%Y","%Y-%m-%d","%d-%b-%Y","%d %b %Y","%m-%d-%Y","%-m/%-d/%Y"):
        try: return datetime.datetime.strptime(s, fmt).date()
        except: pass
    return None

def parse_tat(val):
    if val is None or val == "": return None
    s = str(val).strip()
    m = re.match(r'^(-?\d+):(\d{2})(?::(\d{2}))?$', s)
    if m:
        h,mn,sc = int(m.group(1)),int(m.group(2)),int(m.group(3) or 0)
        return h + mn/60 + sc/3600
    try:
        n = float(s)
        if 0 < n < 2: return n * 24
    except: pass
    return None

def tat_str(hours):
    if hours is None: return "—"
    t = round(abs(hours)*3600)
    return f"{t//3600}:{(t%3600)//60:02d}:{t%60:02d}"

def avg(lst):
    lst = [x for x in lst if x is not None]
    return sum(lst)/len(lst) if lst else None

def ssum(lst): return sum(x for x in lst if x is not None)
def fmt(v,d=2): return "—" if v is None else f"{v:.{d}f}"
def fmt_pct(v): return "—" if v is None else f"{v*100:.1f}%"

def get_rows(sheet_data, cols, start, end):
    out = []
    for r in sheet_data["data"]:
        idx = cols["date"]
        d = parse_date(r[idx] if 0<=idx<len(r) else "")
        if d and start <= d <= end: out.append(r)
    return out

def cell(r, cols, key):
    idx = cols.get(key, -1)
    if idx < 0 or idx >= len(r): return ""
    return str(r[idx]).strip()

def compute_jababeka(raw, start, end):
    main_sheets = ["AHI JABABEKA","HCI JABABEKA"]
    all_sheets  = ["AHI JABABEKA","HCI JABABEKA","KLS JABABEKA"]
    rit_vals = []
    for sn in all_sheets:
        if sn not in raw: continue
        cols = map_cols(raw[sn]["headers"])
        rows = [r for r in get_rows(raw[sn],cols,start,end) if cell(r,cols,"typeDelivery").lower()!="satelite"]
        by_d = {}
        for r in rows:
            dk = str(parse_date(cell(r,cols,"date")))
            if dk not in by_d: by_d[dk] = {"t":set(),"d":[]}
            by_d[dk]["t"].add(cell(r,cols,"lc")); by_d[dk]["d"].append(cell(r,cols,"do_"))
        for v in by_d.values():
            dc = len([x for x in v["d"] if x!=""])
            if dc>0: rit_vals.append(len(v["t"])/dc)
    oL=oM=0; dp_st,dp_mx,dp_nr,dp_rg,do_tr=[],[],[],[],[]
    do_dp_k=do_dp_n=0; tat_d,tat_s=[],[]
    for sn in main_sheets:
        if sn not in raw: continue
        cols=map_cols(raw[sn]["headers"]); rows=get_rows(raw[sn],cols,start,end)
        for r in rows:
            td=cell(r,cols,"typeDelivery").lower(); own=cell(r,cols,"owner").upper()
            kat=cell(r,cols,"kategori").upper(); ta=cell(r,cols,"typeArmada").upper()
            sa=cell(r,cols,"shipArea").upper(); t=parse_tat(cell(r,cols,"tat"))
            dp=float(cell(r,cols,"dp") or 0); do=float(cell(r,cols,"do_") or 0)
            cbm=float(cell(r,cols,"cbm") or 0); cap=float(cell(r,cols,"capArmada") or 0)
            if td=="store" and own!="FBI" and kat=="REGULAR":
                oL+=cbm; oM+=cap; dp_st.append(dp)
            if td=="customer" and own!="FBI": dp_mx.append(dp)
            if td=="customer" and own!="FBI" and kat=="NON REGULAR": dp_nr.append(dp)
            if td=="customer" and own!="FBI" and ta!="PICKUP" and kat=="REGULAR":
                dp_rg.append(dp); do_tr.append(do); do_dp_k+=do; do_dp_n+=dp
            if td=="customer" and kat=="REGULAR" and "DALAM KOTA" in sa and t is not None and 0<=t<=24: tat_d.append(t)
            if td=="store" and kat=="REGULAR" and "DALAM KOTA" in sa and t is not None and 0<=t<=24: tat_s.append(t)
    return {"site":"JABABEKA","ritase":avg(rit_vals),"olf":oL/oM if oM>0 else None,
            "dpStore":avg(dp_st),"dpMix":avg(dp_mx),"dpNonReg":avg(dp_nr),"dpReg":avg(dp_rg),
            "doTrip":avg(do_tr),"doDp":do_dp_k/do_dp_n if do_dp_n>0 else None,
            "tatDirect":avg(tat_d),"tatStore":avg(tat_s)}

def compute_cikupa(raw, start, end):
    sn="HCI CIKUPA"
    if sn not in raw: return None
    headers=raw[sn]["headers"]; cols=map_cols(headers)
    h_up=[x.upper() for x in headers]
    tat_cols=[i for i,h in enumerate(h_up) if h=="TAT"]
    tat_col=tat_cols[-1] if tat_cols else cols["tat"]
    sat_col=next((i for i,h in enumerate(h_up) if "SATELIT" in h),-1)
    olf_det_col=next((i for i,h in enumerate(h_up) if "OLF" in h or "DETERMINE" in h),-1)
    rows=get_rows(raw[sn],cols,start,end)
    rit_rows=[r for r in rows if cell(r,cols,"typeDelivery").lower() not in ("satelite","min van ops")]
    by_d={}
    for r in rit_rows:
        dk=str(parse_date(cell(r,cols,"date")))
        if dk not in by_d: by_d[dk]={"t":set(),"d":[]}
        by_d[dk]["t"].add(cell(r,cols,"lc")); by_d[dk]["d"].append(cell(r,cols,"do_"))
    rit_vals=[]
    for v in by_d.values():
        dc=len([x for x in v["d"] if x!=""])
        if dc>0: rit_vals.append(len(v["t"])/dc)
    olf_r=[r for r in rows if cell(r,cols,"typeDelivery").lower()=="store"
           and olf_det_col>=0 and "non cikande" in str(r[olf_det_col] if olf_det_col<len(r) else "").lower()]
    oL=ssum([float(cell(r,cols,"cbm") or 0) for r in olf_r])
    oM=ssum([float(cell(r,cols,"capArmada") or 0) for r in olf_r])
    dp_st=[float(cell(r,cols,"dp") or 0) for r in olf_r]
    dp_mx=[float(cell(r,cols,"dp") or 0) for r in rows if cell(r,cols,"typeDelivery").lower()=="customer"]
    dp_nr=[float(cell(r,cols,"dp") or 0) for r in rows if cell(r,cols,"typeDelivery").lower()=="customer" and cell(r,cols,"kategori").upper()=="NON REGULAR"]
    def is_nonsat(r): return sat_col>=0 and sat_col<len(r) and "NON SATELIT" in str(r[sat_col]).upper()
    dr=[r for r in rows if cell(r,cols,"typeDelivery").lower()=="customer" and cell(r,cols,"typeArmada").upper()!="PICKUP" and cell(r,cols,"kategori").upper()=="REGULAR" and is_nonsat(r)]
    dp_rg=[float(cell(r,cols,"dp") or 0) for r in dr]
    do_tr=[float(cell(r,cols,"do_") or 0) for r in dr]
    do_dp_k=ssum([float(cell(r,cols,"do_") or 0) for r in dr])
    do_dp_n=ssum([float(cell(r,cols,"dp") or 0) for r in dr])
    def gt(r): v=r[tat_col] if tat_col<len(r) else ""; return parse_tat(v)
    tat_d=[t for r in rows if cell(r,cols,"typeDelivery").lower()=="customer" and cell(r,cols,"kategori").upper()=="REGULAR" and is_nonsat(r) for t in [gt(r)] if t is not None and 0<=t<=24]
    tat_s=[t for r in rows if cell(r,cols,"typeDelivery").lower()=="store" and cell(r,cols,"kategori").upper()=="REGULAR" and is_nonsat(r) for t in [gt(r)] if t is not None and 0<=t<=24]
    return {"site":"CIKUPA","ritase":avg(rit_vals),"olf":oL/oM if oM>0 else None,
            "dpStore":avg(dp_st),"dpMix":avg(dp_mx),"dpNonReg":avg(dp_nr),"dpReg":avg(dp_rg),
            "doTrip":avg(do_tr),"doDp":do_dp_k/do_dp_n if do_dp_n>0 else None,
            "tatDirect":avg(tat_d),"tatStore":avg(tat_s)}

def compute_simple(raw, sn, site_name, start, end, has_fbi):
    if sn not in raw: return None
    cols=map_cols(raw[sn]["headers"]); rows=get_rows(raw[sn],cols,start,end)
    by_d={}
    for r in rows:
        d=parse_date(cell(r,cols,"date"))
        if not d: continue
        dk=str(d)
        if dk not in by_d: by_d[dk]={"t":set(),"d":[]}
        by_d[dk]["t"].add(cell(r,cols,"lc")); by_d[dk]["d"].append(cell(r,cols,"do_"))
    rit_vals=[]
    for v in by_d.values():
        dc=len([x for x in v["d"] if x!=""])
        if dc>0: rit_vals.append(len(v["t"])/dc)
    def ok(r): return not has_fbi or cell(r,cols,"owner").upper()!="FBI"
    olf_r=[r for r in rows if cell(r,cols,"typeDelivery").lower()=="store" and cell(r,cols,"kategori").upper()=="REGULAR" and ok(r)]
    oL=ssum([float(cell(r,cols,"cbm") or 0) for r in olf_r])
    oM=ssum([float(cell(r,cols,"capArmada") or 0) for r in olf_r])
    dp_st=[float(cell(r,cols,"dp") or 0) for r in olf_r]
    dp_mx=[float(cell(r,cols,"dp") or 0) for r in rows if cell(r,cols,"typeDelivery").lower()=="customer" and ok(r)]
    dp_nr=[float(cell(r,cols,"dp") or 0) for r in rows if cell(r,cols,"typeDelivery").lower()=="customer" and cell(r,cols,"kategori").upper()=="NON REGULAR" and ok(r)]
    dr=[r for r in rows if cell(r,cols,"typeDelivery").lower()=="customer" and cell(r,cols,"typeArmada").upper()!="PICKUP" and cell(r,cols,"kategori").upper()=="REGULAR" and ok(r)]
    dp_rg=[float(cell(r,cols,"dp") or 0) for r in dr]
    do_tr=[float(cell(r,cols,"do_") or 0) for r in dr]
    do_dp_k=ssum([float(cell(r,cols,"do_") or 0) for r in dr])
    do_dp_n=ssum([float(cell(r,cols,"dp") or 0) for r in dr])
    tat_d=[t for r in rows if cell(r,cols,"typeDelivery").lower()=="customer" and cell(r,cols,"kategori").upper()=="REGULAR" and "DALAM KOTA" in cell(r,cols,"shipArea").upper() for t in [parse_tat(cell(r,cols,"tat"))] if t is not None and 0<=t<=24]
    tat_s=[t for r in rows if cell(r,cols,"typeDelivery").lower()=="store" and cell(r,cols,"kategori").upper()=="REGULAR" and "DALAM KOTA" in cell(r,cols,"shipArea").upper() for t in [parse_tat(cell(r,cols,"tat"))] if t is not None and 0<=t<=24]
    return {"site":site_name,"ritase":avg(rit_vals),"olf":oL/oM if oM>0 else None,
            "dpStore":avg(dp_st),"dpMix":avg(dp_mx),"dpNonReg":avg(dp_nr),"dpReg":avg(dp_rg),
            "doTrip":avg(do_tr),"doDp":do_dp_k/do_dp_n if do_dp_n>0 else None,
            "tatDirect":avg(tat_d),"tatStore":avg(tat_s)}

def make_summary(results):
    keys=["ritase","olf","dpStore","dpMix","dpNonReg","dpReg","doTrip","doDp","tatDirect","tatStore"]
    return {"site":"NDC & RDC",**{k:avg([r[k] for r in results]) for k in keys}}

def build():
    now_wib=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
    timestamp=now_wib.strftime("%d %b %Y %H:%M WIB")
    print(f"Building dashboard at {timestamp}")
    service=get_service()
    raw={}
    for s in SHEETS:
        print(f"  Fetching {s['name']}...")
        try:
            raw[s["name"]]=fetch_sheet(service,s["name"])
            print(f"  OK {s['name']}: {len(raw[s['name']]['data'])} rows")
        except Exception as e:
            print(f"  ERR {s['name']}: {e}"); raw[s["name"]]={"headers":[],"data":[]}

    periods=[]
    for year in [2026]:
        for month in range(1,13):
            start=datetime.date(year,month,1)
            end=datetime.date(year,month+1,1)-datetime.timedelta(days=1) if month<12 else datetime.date(year,12,31)
            if start > now_wib.date(): break
            if end > now_wib.date(): end=now_wib.date()
            results=[compute_jababeka(raw,start,end),compute_cikupa(raw,start,end),
                     compute_simple(raw,"CORP SIDOARJO","SDA",start,end,True),
                     compute_simple(raw,"CORP TALLO","TALLO",start,end,False),
                     compute_simple(raw,"CORP TAMORA","TAMORA",start,end,False)]
            results=[r for r in results if r]
            if not any(r["ritase"] for r in results): continue
            summary=make_summary(results)
            try: label=datetime.date(year,month,1).strftime("%B %Y")
            except: label=f"{month}/{year}"
            periods.append({"period":f"{year}-{month:02d}","label":label,"sites":results,"summary":summary})
            print(f"  {label}: OLF={fmt_pct(summary['olf'])} Ritase={fmt(summary['ritase'])} TAT_D={tat_str(summary['tatDirect'])}")

    def clean(obj):
        if isinstance(obj,dict): return {k:clean(v) for k,v in obj.items()}
        if isinstance(obj,list): return [clean(x) for x in obj]
        if isinstance(obj,float): return None if obj!=obj else round(obj,6)
        return obj

    data_json=json.dumps(clean(periods),ensure_ascii=False)
    base=os.path.dirname(os.path.abspath(__file__))
    tpl=os.path.join(base,'..','ndc_rdc_template.html')
    out=os.path.join(base,'..','dashboard_ndc_rdc.html')
    with open(tpl,'r',encoding='utf-8') as f: html=f.read()
    html=html.replace('{{BUILD_TIMESTAMP}}',timestamp)
    html=html.replace('{{BUILD_DATE}}',now_wib.strftime('%Y-%m-%d'))
    html=html.replace('// {{EMBEDDED_DATA}}',f'const EMBEDDED_DATA = {data_json};')
    with open(out,'w',encoding='utf-8') as f: f.write(html)
    print(f"\nDashboard built: {out} ({len(periods)} periods)")

if __name__=='__main__':
    build()
