#!/usr/bin/env python3
"""
Build NDC & RDC Dashboard
- Fetches all raw rows from Google Sheets API
- Saves slim data.json (only needed columns)
- Injects timestamp into HTML template
"""

import os, json, datetime, re
from google.oauth2 import service_account
from googleapiclient.discovery import build as gapi_build

SPREADSHEET_ID = "1wumoDA8SrXmaEXRkI_2lNlvof9JVtsXceeE2qhLtb7A"

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
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{sheet_name}'!A:AE",
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
    }

def parse_date_str(s):
    """Normalize date to YYYY-MM-DD string"""
    if not s: return None
    s = str(s).strip()
    # Standard formats
    for fmt in ("%m/%d/%Y","%d/%m/%Y","%Y-%m-%d","%d-%b-%Y","%d %b %Y","%m/%d/%y","%d/%m/%y"):
        try:
            return datetime.datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except: pass
    # Handle M/D/YYYY or D/M/YYYY without leading zeros (e.g. 1/1/2026)
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
    # Excel serial number
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

def slim_row(r, cols, sheet_name, site):
    """Extract only needed columns into slim dict"""
    # For CIKUPA: TAT is last TAT col, SATELITE col
    h = []  # not needed here, handled by caller
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
    }

def build():
    now_wib = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
    timestamp = now_wib.strftime("%d %b %Y %H:%M WIB")
    print(f"Building at {timestamp}")

    service = get_service()
    all_rows = []
    total = 0

    for s in SHEETS:
        print(f"  Fetching {s['name']}...")
        try:
            raw = fetch_sheet(service, s["name"])
            if not raw["headers"]:
                print(f"  ✗ {s['name']}: empty"); continue

            cols = map_cols(raw["headers"])
            h_up = [x.upper() for x in raw["headers"]]

            # For CIKUPA: override TAT col to last TAT col
            if s["name"] == "HCI CIKUPA":
                tat_cols = [i for i, h in enumerate(h_up) if h == "TAT"]
                if tat_cols: cols["tat"] = tat_cols[-1]
                sat_i = next((i for i, h in enumerate(h_up) if "SATELIT" in h), -1)
                cols["satelite"] = sat_i
                # OLF DETERMINE col - try exact then partial
                olf_i = next((i for i, h in enumerate(h_up) if "OLF DETERMINE" in h), -1)
                if olf_i < 0:
                    olf_i = next((i for i, h in enumerate(h_up) if "OLF" in h), -1)
                if olf_i < 0:
                    olf_i = next((i for i, h in enumerate(h_up) if "DETERMINE" in h), -1)
                cols["olfDet"] = olf_i
                print(f"  CIKUPA cols: tat={cols['tat']}, sat={cols['satelite']}, olfDet={cols['olfDet']}")
                if cols["olfDet"] >= 0:
                    print(f"  CIKUPA olfDet header: {raw['headers'][cols['olfDet']]}")
                    # Sample values
                    samples = [r[cols["olfDet"]] if cols["olfDet"] < len(r) else "" for r in raw["data"][:5]]
                    print(f"  CIKUPA olfDet samples: {samples}")

            # Debug: print col indices for all sheets
            print(f"  {s['name']} col indices: do={cols['do_']} cbm={cols['cbm']} cap={cols['capArmada']} dp={cols['dp']} kat={cols['kategori']}")
            if cols['capArmada'] >= 0 and cols['capArmada'] < len(raw['headers']):
                print(f"  {s['name']} cap header='{raw['headers'][cols['capArmada']]}'")
            if len(raw["data"]) > 0:
                r0 = raw["data"][0]
                cap_val = r0[cols['capArmada']] if cols['capArmada']>=0 and cols['capArmada']<len(r0) else 'OUT OF RANGE'
                print(f"  {s['name']} row0 cap='{cap_val}' len={len(r0)}")
                # Count non-empty cap values
                cap_idx = cols['capArmada']
                non_empty = sum(1 for r in raw["data"] if cap_idx>=0 and cap_idx<len(r) and r[cap_idx].strip()!='')
                print(f"  {s['name']} cap non-empty: {non_empty}/{len(raw['data'])}")
                # Sample a few rows with empty cap
                empty_samples = [r[cap_idx] if cap_idx<len(r) else 'SHORT' for r in raw["data"][1:6]]
                print(f"  {s['name']} cap samples[1:6]: {empty_samples}")

            for r in raw["data"]:
                row = slim_row(r, cols, s["name"], s["site"])
                if row["date"]:  # skip rows without date
                    all_rows.append(row)
            
            cnt = len([r for r in raw["data"] if parse_date_str(cell(r, cols["date"]))])
            total += cnt
            print(f"  ✓ {s['name']}: {cnt} rows")

        except Exception as e:
            print(f"  ✗ {s['name']}: {e}")

    print(f"\nTotal rows: {total}")

    # Save data.json
    base = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(base, '..', 'data.json')
    tpl_path  = os.path.join(base, '..', 'ndc_rdc_template.html')
    out_path  = os.path.join(base, '..', 'dashboard_ndc_rdc.html')

    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump({"timestamp": timestamp, "rows": all_rows}, f, ensure_ascii=False, separators=(',',':'))
    
    print(f"data.json: {os.path.getsize(data_path)/1024:.1f} KB")

    # Build HTML
    with open(tpl_path, 'r', encoding='utf-8') as f:
        html = f.read()
    html = html.replace('{{BUILD_TIMESTAMP}}', timestamp)
    html = html.replace('{{BUILD_DATE}}', now_wib.strftime('%Y-%m-%d'))
    # Remove embedded data placeholder if still present
    html = html.replace('// {{EMBEDDED_DATA}}', '')

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Dashboard built: {out_path}")

if __name__ == '__main__':
    build()
