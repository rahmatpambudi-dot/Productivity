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
        range=f"'{sheet_name}'!A:AE"
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
    for fmt in ("%m/%d/%Y","%d/%m/%Y","%Y-%m-%d","%d-%b-%Y","%d %b %Y"):
        try:
            return datetime.datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except: pass
    # Handle M/D/YYYY or D/M/YYYY without leading zeros
    import re
    m = re.match(r'^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})$', s)
    if m:
        p1, p2, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # Assume M/D/YYYY if p1 <= 12
        if p1 <= 12:
            try: return datetime.date(year, p1, p2).strftime("%Y-%m-%d")
            except: pass
        # Try D/M/YYYY
        if p2 <= 12:
            try: return datetime.date(year, p2, p1).strftime("%Y-%m-%d")
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
        "do":    cell(r, cols["do_"]),
        "cbm":   cell(r, cols["cbm"]),
        "cap":   cell(r, cols["capArmada"]),
        "dp":    cell(r, cols["dp"]),
        "sa":    cell(r, cols["shipArea"]).upper(),
        "kat":   cell(r, cols["kategori"]).upper(),
        "tat":   cell(r, cols["tat"]),
        "od":    cell(r, cols["olfDet"]).lower() if cols["olfDet"] >= 0 else "",
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
                olf_i = next((i for i, h in enumerate(h_up) if "OLF" in h or "DETERMINE" in h), -1)
                cols["olfDet"] = olf_i

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
