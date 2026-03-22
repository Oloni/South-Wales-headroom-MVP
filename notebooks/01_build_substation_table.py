"""
01_build_substation_table.py
============================
Joins FOUR data sources into one substation-level summary table for South Wales.

Sources:
  1. LTDS Table 2a → real transformer ratings (nominal & emergency MVA)
  2. BSP transformer flow CSVs → peak/mean utilisation per substation
  3. GCR (Generation Connection Register) → queue by substation
  4. CIM file → used only for cross-referencing (ratings are placeholders)

Output: data/south_wales_substations.csv

BEFORE RUNNING: update the two paths below to match your machine.
Copy ltds-table-2a-two-winding-transformer.csv into your data/ folder.
"""

import pandas as pd
import numpy as np
import os

# ============================================================
# CONFIGURE THESE TWO PATHS
# ============================================================
BSP_FLOWS_DIR = '/Users/leonie/Documents/grid-model-experiments/BSP_transformer_flows_south_wales'
MVP_DATA_DIR = '/Users/leonie/Documents/South_Wales_headroom_MVP/data'

# ============================================================
# STEP 1: Name matching table
# ============================================================
# Rosetta Stone between four naming conventions.
# If you add new substations, add a row here.

SUBSTATION_NAMES = pd.DataFrame([
    # (flow_file,              gcr_name,                  cim_code, voltage_kv, display_name)
    ("abergavenny-66kv",       "Abergavenny",             "ABGA", 66,  "Abergavenny"),
    ("ammanford-33kv",         "Ammanford Grid",          "AMMA", 33,  "Ammanford"),
    ("bridgend-33kv",          "Bridgend Grid",           "BREN", 33,  "Bridgend"),
    ("briton-ferry-33kv",      "Briton Ferry Grid",       "BRIF", 33,  "Briton Ferry"),
    ("brynhill-33kv",          "Barry Grid",              "BARR", 33,  "Brynhill"),
    ("cardiff-central-33kv",   "Cardiff Central Grid",    "CARC", 33,  "Cardiff Central"),
    ("cardiff-east-33kv",      "Cardiff East Grid Bsp",   "CARE", 33,  "Cardiff East"),
    ("cardiff-north-33kv",     "Cardiff North Grid",      "CARN", 33,  "Cardiff North"),
    ("cardiff-west-33kv",      "Cardiff West Grid",       "CARW", 33,  "Cardiff West"),
    ("carmarthen-33kv",        "Carmarthen Grid",         "CARM", 33,  "Carmarthen"),
    ("crumlin-33kv",           "Crumlin",                 "CRUM", 33,  "Crumlin"),
    ("dowlais-33kv",           "Dowlais Grid",            "DOWL", 33,  "Dowlais"),
    ("east-aberthaw-33kv",     "East Aberthaw",           "EAST", 33,  "East Aberthaw"),
    ("ebbw-vale-33kv",         "Ebbw Vale",               "EBBW", 33,  "Ebbw Vale"),
    ("golden-hill-33kv",       "Golden Hill Grid",        "GOLD", 33,  "Golden Hill"),
    ("gowerton-east-33kv",     "Gowerton East Grid",      "GOWE", 33,  "Gowerton East"),
    ("grange-66kv",            "Grange Bsp",              "MAGA", 66,  "Grange"),
    ("haverfordwest-33kv",     "Haverfordwest Grid",      "HAVE", 33,  "Haverfordwest"),
    ("hirwaun-33kv",           "Hirwaun Grid",            "HIRW", 33,  "Hirwaun"),
    ("lampeter-33kv",          "Lampeter Grid",           "LAMP", 33,  "Lampeter"),
    ("llanarth-33kv",          "Llanarth Grid",           "LLAN", 33,  "Llanarth"),
    ("llantarnam-66kv",        "Llantarnam",              "LLTA", 66,  "Llantarnam"),
    ("milford-haven-33kv",     "Milford Haven Grid",      "MIFH", 33,  "Milford Haven"),
    ("mountain-ash-33kv",      "Mountain Ash Grid",       "MOUA", 33,  "Mountain Ash"),
    ("newport-south-33kv",     "Newport South",           "NEWS", 33,  "Newport South"),
    ("panteg-66kv",            "Panteg 132/11kV",         "PANT", 66,  "Panteg"),
    ("pyle-33kv",              "Pyle Bsp",                "PYLE", 33,  "Pyle"),
    ("rhos-33kv",              "Rhos Grid",               "RHOS", 33,  "Rhos"),
    ("sudbrook-33kv",          "Sudbrook",                "SUDB", 33,  "Sudbrook"),
    ("swansea-north-33kv",     "Swansea North Bsp",       "SWAN", 33,  "Swansea North"),
    ("swansea-west-33kv",      "Swansea West Grid",       "SWAW", 33,  "Swansea West"),
    ("tir-john-33kv",          "Tir John Power Station",  "TIRJ", 33,  "Tir John"),
    ("trostre-33kv",           "Trostre Grid",            "TROS", 33,  "Trostre"),
    ("upperboat-33kv",         "Upper Boat Bsp",          "YSTR", 33,  "Upper Boat"),
    ("ystradgynlais-33kv",     "Ystradgynlais Grid",      "YSTR", 33,  "Ystradgynlais"),
], columns=["flow_file", "gcr_name", "cim_code", "voltage_kv", "display_name"])

print(f"Substation matching table: {len(SUBSTATION_NAMES)} entries\n")


# ============================================================
# STEP 2: Extract REAL transformer ratings from LTDS Table 2a
# ============================================================
print("=== STEP 2: LTDS Transformer Ratings ===\n")

ltds_path = os.path.join(MVP_DATA_DIR, 'ltds-table-2a-two-winding-transformer.csv')
ltds = pd.read_csv(ltds_path, encoding='utf-8-sig')
sw_ltds = ltds[ltds['Licence'] == 'SWALES']

# Filter to 132/33kV and 132/66kV transformers
hv_tx = sw_ltds[
    (sw_ltds['Operating Voltage 1'] == 132) &
    (sw_ltds['Operating Voltage 2'].isin([33, 66]))
].copy()

# Extract 4-letter CIM code from Node 1
hv_tx['cim_code'] = hv_tx['Node 1'].str[:4]

# Aggregate by CIM code
ratings = hv_tx.groupby('cim_code').agg(
    n_transformers_ltds=('Nominal Rating', 'count'),
    total_nominal_mva=('Nominal Rating', 'sum'),
    total_emergency_mva=('Emergency Rating', 'sum'),
    individual_ratings=('Nominal Rating', lambda x: list(x)),
).reset_index()

# Convert individual_ratings list to a readable string for the CSV
ratings['ratings_detail'] = ratings['individual_ratings'].apply(
    lambda x: ' + '.join([f"{r:.0f}" for r in x])
)

print(f"Found ratings for {len(ratings)} substation groups:")
for _, row in ratings.iterrows():
    print(f"  {row['cim_code']}: {row['total_nominal_mva']:.0f} MVA ({row['ratings_detail']})")


# ============================================================
# STEP 3: Extract peak flows from BSP transformer CSVs
# ============================================================
print("\n\n=== STEP 3: BSP Transformer Flows ===\n")

flow_records = []
for _, row in SUBSTATION_NAMES.iterrows():
    filepath = os.path.join(BSP_FLOWS_DIR, f"{row['flow_file']}-transformer-flows.csv")
    if not os.path.exists(filepath):
        print(f"  WARNING: not found: {row['flow_file']}")
        continue

    df = pd.read_csv(filepath)
    imports = df[df['Reading Type'] == 'Import'].copy()
    if len(imports) == 0:
        print(f"  WARNING: no Import rows in {row['flow_file']}")
        continue

    ts_agg = imports.groupby('Timestamp').agg(
        total_mw=('MW', 'sum'),
        total_mvar=('MVAr', 'sum'),
        total_mva=('MVA', 'sum'),
    ).reset_index()

    n_tx = imports['Transformer'].nunique()
    demands = df[df['Reading Type'] == 'Demand']
    demand_agg = demands.groupby('Timestamp').agg(demand_mw=('MW', 'sum')).reset_index()
    gens = df[df['Reading Type'] == 'Gen']
    gen_agg = gens.groupby('Timestamp').agg(gen_mw=('MW', 'sum')).reset_index()

    flow_records.append({
        'flow_file': row['flow_file'],
        'n_transformers_flow': n_tx,
        'peak_import_mw': ts_agg['total_mw'].max(),
        'peak_import_mva': ts_agg['total_mva'].max(),
        'mean_import_mw': ts_agg['total_mw'].mean(),
        'p95_import_mw': ts_agg['total_mw'].quantile(0.95),
        'min_import_mw': ts_agg['total_mw'].min(),
        'peak_demand_mw': demand_agg['demand_mw'].max() if len(demand_agg) > 0 else None,
        'mean_demand_mw': demand_agg['demand_mw'].mean() if len(demand_agg) > 0 else None,
        'peak_gen_mw': gen_agg['gen_mw'].max() if len(gen_agg) > 0 else None,
        'mean_gen_mw': gen_agg['gen_mw'].mean() if len(gen_agg) > 0 else None,
        'n_timestamps': len(ts_agg),
        'date_from': imports['Timestamp'].min(),
        'date_to': imports['Timestamp'].max(),
    })
    print(f"  {row['display_name']:<22} {n_tx} tx | peak {ts_agg['total_mw'].max():>6.1f} MW | mean {ts_agg['total_mw'].mean():>6.1f} MW")

flows_df = pd.DataFrame(flow_records)
print(f"\nProcessed {len(flows_df)} substations")


# ============================================================
# STEP 4: Extract queue data from GCR
# ============================================================
print("\n\n=== STEP 4: GCR Queue Data ===\n")

gcr = pd.read_csv(os.path.join(MVP_DATA_DIR, 'gcr.csv'))
sw_gcr = gcr[gcr['Licence_Area'] == 'South Wales'].copy()

gcr_agg = sw_gcr.groupby('BSP').agg(
    connected_mva=('Latest_Connected_Export_Capacity_kVA', 'sum'),
    accepted_mva=('Latest_Accepted_not_yet_Connected_Export_Capacity_kVA', 'sum'),
    offered_mva=('Latest_Offered_not_yet_Accepted_Export_Capacity_kVA', 'sum'),
    enquired_mva=('Latest_Enquired_not_yet_Offered_Export_Capacity_kVA', 'sum'),
).reset_index()

for col in ['connected_mva', 'accepted_mva', 'offered_mva', 'enquired_mva']:
    gcr_agg[col] = gcr_agg[col] / 1000

# Dominant technology per BSP (simplified)
def dominant_tech(group):
    tech_cap = group.groupby('Generator_Technology').apply(
        lambda g: g['Latest_Connected_Export_Capacity_kVA'].sum() +
                  g['Latest_Accepted_not_yet_Connected_Export_Capacity_kVA'].sum(),
        include_groups=False
    )
    return tech_cap.idxmax() if tech_cap.sum() > 0 else 'Unknown'

def simplify_tech(tech):
    t = str(tech)
    if 'Photovoltaic' in t: return 'Solar'
    if 'Onshore Wind' in t: return 'Onshore Wind'
    if 'Offshore Wind' in t: return 'Offshore Wind'
    if 'Lithium' in t or 'Battery' in t or 'Stored Energy' in t: return 'Battery'
    if 'Mixed' in t: return 'Mixed'
    if 'Fossil' in t: return 'Fossil'
    if 'Hydro' in t or 'Water' in t: return 'Hydro'
    if any(x in t for x in ['Biomass', 'Biofuel', 'Landfill', 'Sewage', 'Waste']): return 'Bio/Waste'
    return 'Other'

tech_by_bsp = sw_gcr.groupby('BSP').apply(dominant_tech, include_groups=False).reset_index()
tech_by_bsp.columns = ['BSP', 'dominant_technology']
tech_by_bsp['technology'] = tech_by_bsp['dominant_technology'].apply(simplify_tech)

gcr_agg = gcr_agg.merge(tech_by_bsp[['BSP', 'technology']], on='BSP', how='left')
print(f"GCR: {len(gcr_agg)} South Wales BSPs")


# ============================================================
# STEP 5: Join everything
# ============================================================
print("\n=== STEP 5: Joining ===\n")

result = SUBSTATION_NAMES.copy()
result = result.merge(ratings.drop(columns=['individual_ratings']), on='cim_code', how='left')
result = result.merge(flows_df, on='flow_file', how='left')
result = result.merge(gcr_agg.rename(columns={'BSP': 'gcr_name'}), on='gcr_name', how='left')


# ============================================================
# STEP 6: Compute headroom
# ============================================================

result['total_committed_mva'] = result['connected_mva'].fillna(0) + result['accepted_mva'].fillna(0)
result['headroom_mva'] = result['total_nominal_mva'] - result['total_committed_mva']
result['utilisation_pct'] = (result['peak_import_mw'] / result['total_nominal_mva'] * 100).round(1)
result['net_exporter'] = result['mean_import_mw'] < 0

def headroom_flag(row):
    if pd.isna(row.get('headroom_mva')): return 'No data'
    if row['headroom_mva'] < 0: return 'Overcommitted'
    if row['headroom_mva'] < 20: return 'Tight'
    if row['headroom_mva'] < 50: return 'Moderate'
    return 'Available'

result['headroom_flag'] = result.apply(headroom_flag, axis=1)


# ============================================================
# DISPLAY
# ============================================================
print("\n=== SOUTH WALES SUBSTATION SUMMARY ===\n")
print(f"{'Substation':<22} {'kV':>3} {'Rating':>7} {'Peak MW':>8} {'Util%':>6} {'Conn':>6} {'Accpt':>6} {'Headrm':>7}  {'Flag':<15} {'Tech'}")
print("-" * 115)

for _, row in result.sort_values('headroom_mva').iterrows():
    r = lambda col, fmt='.0f': f"{row[col]:{fmt}}" if pd.notna(row.get(col)) else '?'
    exp = ' [EXPORT]' if row.get('net_exporter') else ''
    print(f"{row['display_name']:<22} {row['voltage_kv']:>3} {r('total_nominal_mva'):>7} {r('peak_import_mw', '.1f'):>8} {r('utilisation_pct', '.0f')+'%':>6} {r('connected_mva', '.1f'):>6} {r('accepted_mva', '.1f'):>6} {r('headroom_mva', '.1f'):>7}  {row['headroom_flag']:<15} {row.get('technology') or '?'}{exp}")


# ============================================================
# SAVE
# ============================================================
output_path = os.path.join(MVP_DATA_DIR, 'south_wales_substations.csv')
result.to_csv(output_path, index=False)
print(f"\n\nSaved to {output_path}")

print(f"\nTotal substations: {len(result)}")
print(f"  With ratings:    {result['total_nominal_mva'].notna().sum()}")
print(f"  With flow data:  {result['peak_import_mw'].notna().sum()}")
print(f"  With GCR data:   {result['connected_mva'].notna().sum()}")

print(f"\nHeadroom breakdown:")
for flag in ['Overcommitted', 'Tight', 'Moderate', 'Available', 'No data']:
    n = (result['headroom_flag'] == flag).sum()
    if n: print(f"  {flag}: {n}")

print("\n=== TOP 10 MOST OVERCOMMITTED ===\n")
for _, row in result.nsmallest(10, 'headroom_mva').iterrows():
    print(f"  {row['display_name']:<22} Rating: {row['total_nominal_mva']:>6.0f} MVA | Committed: {row['total_committed_mva']:>6.0f} MVA | Headroom: {row['headroom_mva']:>7.1f} MVA")

print("\n\nNOTE: Negative headroom means committed generation exceeds transformer rating.")
print("This doesn't mean the network fails — diversity, curtailment, and queue")
print("attrition mean not everything runs at full output simultaneously.")
print("But it IS the signal that connection risk is high at these substations.")
