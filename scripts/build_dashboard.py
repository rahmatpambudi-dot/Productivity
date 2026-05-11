#!/usr/bin/env python3
"""
Build NDC & RDC Dashboard
Fetches CSV data from Google Sheets and injects last-updated timestamp into HTML
"""

import urllib.request
import json
import datetime
import os
import sys

SHEETS = [
    { "name": "AHI JABABEKA",  "site": "JABABEKA", "gid": "111957912" },
    { "name": "HCI JABABEKA",  "site": "JABABEKA", "gid": "1129886851" },
    { "name": "KLS JABABEKA",  "site": "JABABEKA", "gid": "197682446" },
    { "name": "HCI CIKUPA",    "site": "CIKUPA",   "gid": "1019046386" },
    { "name": "CORP SIDOARJO", "site": "SDA",      "gid": "1111207228" },
    { "name": "CORP TALLO",    "site": "TALLO",    "gid": "1950770306" },
    { "name": "CORP TAMORA",   "site": "TAMORA",   "gid": "1447314605" },
]

BASE_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQUlleuAjGsHyROuTEp5e7G8P4_Yr4EvdOpsSEkfB9gIfg6esYzw0PYN0MMQ4lkzvoOOvva5Ly48K1o/pub"

def check_sheets_accessible():
    """Verify at least one sheet is accessible"""
    test_url = f"{BASE_URL}?gid={SHEETS[0]['gid']}&single=true&output=csv"
    try:
        req = urllib.request.Request(test_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read(100)
            return len(data) > 0
    except Exception as e:
        print(f"Warning: Could not verify sheet access: {e}")
        return False

def build():
    now_utc = datetime.datetime.utcnow()
    now_wib = now_utc + datetime.timedelta(hours=7)
    timestamp = now_wib.strftime("%d %b %Y %H:%M WIB")
    
    print(f"Building dashboard at {timestamp}")
    
    accessible = check_sheets_accessible()
    if not accessible:
        print("Warning: Sheets may not be accessible, dashboard will fetch client-side")
    
    # Read template
    template_path = os.path.join(os.path.dirname(__file__), '..', 'ndc_rdc_template.html')
    output_path = os.path.join(os.path.dirname(__file__), '..', 'dashboard_ndc_rdc.html')
    
    with open(template_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # Inject build timestamp
    html = html.replace('{{BUILD_TIMESTAMP}}', timestamp)
    html = html.replace('{{BUILD_DATE}}', now_wib.strftime('%Y-%m-%d'))
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"Dashboard built successfully: {output_path}")
    print(f"Timestamp: {timestamp}")

if __name__ == '__main__':
    build()
