"""
12b_timestamp_diagnostic.py
===========================
Quick check of timestamp formats across the two data sources
before running the full substation test.
"""

import pandas as pd
import os

MVP_DATA_DIR  = '/Users/leonie/Documents/South_Wales_headroom_MVP/data'
BSP_FLOWS_DIR = '/Users/leonie/Documents/South_Wales_headroom_MVP/data/BSP_transformer_flows'
ZONE          = 'swansea-north'
ZONE_ID       = '315'

# ── Profile timestamps ─────────────────────────────────────────────────────
prof = pd.read_csv(f'{MVP_DATA_DIR}/{ZONE}_generic_generator_profiles_id_{ZONE_ID}_2026.csv')
print("=== PROFILE TIMESTAMPS ===")
print(f"Column name: '{prof.columns[0]}'")
print(f"First 5 raw values:")
for v in prof['Half Hour'].head():
    print(f"  {repr(v)}")
prof_ts = pd.to_datetime(prof['Half Hour'])
print(f"Parsed first 5:")
for v in prof_ts.head():
    print(f"  {v}  (tz={v.tzinfo})")
print(f"Range: {prof_ts.min()} → {prof_ts.max()}")

# ── BSP flow timestamps ────────────────────────────────────────────────────
# Try a few BSP files
test_files = [
    'swansea-north-33kv-transformer-flows.csv',
    'swansea-west-33kv-transformer-flows.csv',
    'rhos-33kv-transformer-flows.csv',
    'trostre-33kv-transformer-flows.csv',
]

for fname in test_files:
    fpath = os.path.join(BSP_FLOWS_DIR, fname)
    if not os.path.exists(fpath):
        print(f"\n  NOT FOUND: {fname}")
        continue

    print(f"\n=== {fname} ===")
    df = pd.read_csv(fpath)
    print(f"Columns: {list(df.columns)}")
    print(f"Reading Types: {df['Reading Type'].unique()}")
    print(f"First 3 raw timestamps:")
    for v in df['Timestamp'].head(3):
        print(f"  {repr(v)}")

    # Try parsing
    ts = pd.to_datetime(df['Timestamp'], utc=False)
    print(f"Parsed first 3:")
    for v in ts.head(3):
        print(f"  {v}  (tz={v.tzinfo})")
    print(f"Range: {ts.min()} → {ts.max()}")
    print(f"Total rows: {len(df)}, unique timestamps: {df['Timestamp'].nunique()}")

    # Check overlap with profile
    imports = df[df['Reading Type'] == 'Import'].copy()
    imports['ts_parsed'] = pd.to_datetime(imports['Timestamp'])
    prof_ts_set = set(prof_ts.astype(str))
    import_ts_set = set(imports['ts_parsed'].astype(str))
    overlap = prof_ts_set & import_ts_set
    print(f"Timestamp overlap with profile: {len(overlap)} of {len(import_ts_set)}")
    if len(overlap) == 0:
        # Show a sample from each to spot the format difference
        print(f"  Profile sample: {list(prof_ts_set)[:3]}")
        print(f"  Flow file sample: {list(import_ts_set)[:3]}")
