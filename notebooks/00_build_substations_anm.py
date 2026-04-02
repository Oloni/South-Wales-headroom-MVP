"""
00_build_substations.py (v2 — with ANM flags)
===============================================
Rebuilds south_wales_substations.csv by adding TANM/DANM flags
from the per-zone connection queue files.

This script READS the existing south_wales_substations.csv and ADDS
two new columns: has_tanm and has_danm, derived from the connection
queue files. It does NOT rebuild the entire substations table from
scratch — the existing headroom, flow, and GCR data are preserved.

Run from the South_Wales_headroom_MVP directory.
"""

import pandas as pd
import numpy as np
import os
import glob

MVP_DATA_DIR = '/Users/leonie/Documents/South_Wales_headroom_MVP/data'

# ============================================================
# LOAD EXISTING SUBSTATIONS TABLE
# ============================================================
subs_path = os.path.join(MVP_DATA_DIR, 'south_wales_substations.csv')
subs = pd.read_csv(subs_path)
print(f"Loaded {len(subs)} substations from {subs_path}")
print(f"Existing columns: {list(subs.columns)}")

# ============================================================
# MAP DISPLAY NAMES TO CIM CODES (for matching queue data)
# ============================================================
# The substations CSV uses display_name (e.g. "Swansea West")
# The connection queue uses Bus Name (e.g. "SWAW1_MAIN1")
# We need to match via the GSP zone name in the queue file

NAME_TO_CIM = {
    'Ammanford': 'AMMA', 'Briton Ferry': 'BRIF', 'Carmarthen': 'CARM',
    'Gowerton East': 'GOWE', 'Hirwaun': 'HIRW', 'Lampeter': 'LAMP',
    'Llanarth': 'LLAN', 'Rhos': 'RHOS', 'Swansea North': 'SWAN',
    'Swansea West': 'SWAW', 'Tir John': 'TIRJ', 'Trostre': 'TROS',
    'Ystradgynlais': 'TRAV', 'Abergavenny': 'ABGA', 'Bridgend': 'BREN',
    'Brynhill': 'BARR', 'Cardiff Central': 'CARC', 'Cardiff East': 'CARE',
    'Cardiff North': 'CARN', 'Cardiff West': 'CARW', 'Crumlin': 'CRUM',
    'Dowlais': 'DOWL', 'East Aberthaw': 'EAST', 'Ebbw Vale': 'EBBW',
    'Golden Hill': 'GOLD', 'Grange': 'MAGA', 'Haverfordwest': 'HAVE',
    'Llantarnam': 'LLTA', 'Milford Haven': 'MIFH', 'Mountain Ash': 'MOUA',
    'Newport South': 'NEWS', 'Panteg': 'PANT', 'Pyle': 'PYLE',
    'South Hook': 'SHHK', 'Sudbrook': 'SUDB', 'Upper Boat': 'UPPB',
}

# ============================================================
# SCAN ALL CONNECTION QUEUE FILES FOR ANM FLAGS
# ============================================================
print("\nScanning connection queue files for TANM/DANM flags...")

# Collect ANM flags per CIM code
cim_tanm = {}  # CIM code -> True/False
cim_danm = {}

queue_files = sorted(glob.glob(os.path.join(MVP_DATA_DIR, '*_connection_queue_id_*_2026.csv')))
print(f"Found {len(queue_files)} connection queue files")

for f in queue_files:
    cq = pd.read_csv(f)
    zone = os.path.basename(f).split('_connection_queue')[0]

    if 'TANM' not in cq.columns or 'DANM' not in cq.columns:
        print(f"  WARNING: {zone} has no TANM/DANM columns — skipping")
        continue

    n_tanm = (cq['TANM'] == True).sum()
    n_danm = (cq['DANM'] == True).sum()
    print(f"  {zone}: {len(cq)} projects, TANM={n_tanm}, DANM={n_danm}")

    # For each project, extract the CIM code from the bus name
    # Bus names look like: SWAW1_MAIN1, HIRW3_MAIN2, BRIF3_MAIN1, etc.
    # The CIM code is the first 4 characters
    for _, row in cq.iterrows():
        bus_name = str(row.get('Bus Name', ''))
        if len(bus_name) < 4:
            continue

        cim = bus_name[:4]

        if row.get('TANM') == True:
            cim_tanm[cim] = True
        if row.get('DANM') == True:
            cim_danm[cim] = True

print(f"\nCIM codes with TANM: {len(cim_tanm)}")
print(f"CIM codes with DANM: {len(cim_danm)}")

# ============================================================
# MAP ANM FLAGS TO SUBSTATIONS
# ============================================================
# For each substation, check if its CIM code has any TANM or DANM projects
subs['has_tanm'] = False
subs['has_danm'] = False

matched = 0
for idx, row in subs.iterrows():
    display_name = row['display_name']
    cim = NAME_TO_CIM.get(display_name)
    if cim:
        if cim in cim_tanm:
            subs.at[idx, 'has_tanm'] = True
            matched += 1
        if cim in cim_danm:
            subs.at[idx, 'has_danm'] = True

# Also check CIM codes that don't match display names directly
# (some CIM codes in the queue might map to substations via different prefixes)
for idx, row in subs.iterrows():
    display_name = row['display_name']
    cim = NAME_TO_CIM.get(display_name)
    if not cim:
        continue
    # Check all 4-char prefixes that start with the same letters
    for queue_cim in list(cim_tanm.keys()) + list(cim_danm.keys()):
        if queue_cim == cim:
            continue
        # Some substations have multiple CIM prefixes
        # e.g. SWAN (Swansea North) might have projects at SWAN1, SWAN3, SWAN4
        # We already handle this above since we take first 4 chars

print(f"\nSubstations matched to ANM flags: {matched}")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "="*60)
print("ANM STATUS BY SUBSTATION")
print("="*60)

for _, row in subs.sort_values('display_name').iterrows():
    tanm = "TANM" if row['has_tanm'] else ""
    danm = "DANM" if row['has_danm'] else ""
    anm_str = " + ".join(filter(None, [tanm, danm]))
    if anm_str:
        print(f"  {row['display_name']:<20} {anm_str}")

n_tanm = subs['has_tanm'].sum()
n_danm = subs['has_danm'].sum()
n_either = (subs['has_tanm'] | subs['has_danm']).sum()
n_neither = (~(subs['has_tanm'] | subs['has_danm'])).sum()

print(f"\n  Transmission ANM: {n_tanm} substations")
print(f"  Distribution ANM: {n_danm} substations")
print(f"  Either: {n_either} substations")
print(f"  Neither: {n_neither} substations")

# ============================================================
# SAVE
# ============================================================
subs.to_csv(subs_path, index=False)
print(f"\nSaved updated substations table to {subs_path}")
print(f"New columns added: has_tanm, has_danm")
