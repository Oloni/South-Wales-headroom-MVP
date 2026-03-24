"""
02_compute_curtailment.py (v4 — all South Wales zones)
======================================================
Loops through all 7 GSP zones in South Wales and computes curtailment
estimates for every BSP connection point.

Output: data/south_wales_curtailment.csv (replaces swansea_north_curtailment.csv)
"""

import pandas as pd
import numpy as np
import os
import time
import glob

MVP_DATA_DIR = '/Users/leonie/Documents/South_Wales_headroom_MVP/data'

# ============================================================
# ZONE CONFIGURATION
# ============================================================
# Each zone has files named: {prefix}_{filetype}_id_{id}_2026.csv
# Detect zones automatically from branch_load files

branch_files = glob.glob(os.path.join(MVP_DATA_DIR, '*_branch_load_id_*_2026.csv'))
zones = []
for f in sorted(branch_files):
    basename = os.path.basename(f)
    # Extract prefix and ID: e.g. "pembroke_branch_load_id_312_2026.csv" -> ("pembroke", "312")
    # Handle hyphens: "swansea-north_branch_load..." and "aberthaw-and-cardiff-east_branch..."
    parts = basename.split('_branch_load_id_')
    if len(parts) == 2:
        prefix = parts[0]
        zone_id = parts[1].replace('_2026.csv', '')
        zones.append((prefix, zone_id))

print(f"Found {len(zones)} GSP zones:")
for prefix, zid in zones:
    print(f"  {prefix} (id={zid})")

# ============================================================
# BSP CONNECTION POINTS BY ZONE
# ============================================================
# We'll auto-detect BSP 33kV main busbars from the sensitivity factor files
# Pattern: XXXX3_MAIN1 where XXXX is a 4-letter substation code

# Map known CIM codes to display names (from our substation table)
CIM_TO_NAME = {
    'ABGA': 'Abergavenny', 'AMMA': 'Ammanford', 'BREN': 'Bridgend',
    'BRIF': 'Briton Ferry', 'BARR': 'Brynhill', 'CARC': 'Cardiff Central',
    'CARE': 'Cardiff East', 'CARN': 'Cardiff North', 'CARW': 'Cardiff West',
    'CARM': 'Carmarthen', 'CRUM': 'Crumlin', 'DOWL': 'Dowlais',
    'EAST': 'East Aberthaw', 'EBBW': 'Ebbw Vale', 'GOLD': 'Golden Hill',
    'GOWE': 'Gowerton East', 'MAGA': 'Grange', 'HAVE': 'Haverfordwest',
    'HIRW': 'Hirwaun', 'LAMP': 'Lampeter', 'LLAN': 'Llanarth',
    'LLTA': 'Llantarnam', 'MIFH': 'Milford Haven', 'MOUA': 'Mountain Ash',
    'NEWS': 'Newport South', 'PANT': 'Panteg', 'PYLE': 'Pyle',
    'RHOS': 'Rhos', 'SHHK': 'South Hook', 'SUDB': 'Sudbrook',
    'SWAN': 'Swansea North', 'SWAW': 'Swansea West', 'TIRJ': 'Tir John',
    'TROS': 'Trostre', 'TRAV': 'Ystradgynlais', 'YSTR': 'Ystradgynlais',
}

# Fuel type to profile column mapping
FUEL_TO_PROFILE = {
    'Solar': 'PV', 'Wind': 'Wind', 'BESS': 'BESS Export pu', 'Other': 'Other',
}


# ============================================================
# CURTAILMENT FUNCTION (same as before)
# ============================================================

def compute_curtailment_for_zone(prefix, zone_id):
    """Load data for one zone, project queue, compute curtailment for all BSPs."""
    
    print(f"\n{'='*60}")
    print(f"ZONE: {prefix} (id={zone_id})")
    print(f"{'='*60}")
    
    # Build file paths
    def zpath(filetype):
        # Handle both hyphenated and underscored prefixes
        pattern = os.path.join(MVP_DATA_DIR, f'{prefix}_{filetype}_id_{zone_id}_2026.csv')
        matches = glob.glob(pattern)
        if not matches:
            # Try with hyphens replaced
            pattern2 = os.path.join(MVP_DATA_DIR, f'{prefix}*{filetype}*id_{zone_id}_2026.csv')
            matches = glob.glob(pattern2)
        return matches[0] if matches else None
    
    # Load data
    sf_path = zpath('sensitivity_factors')
    pel_path = zpath('pre-event_limits') or zpath('pre-event-limits')
    prof_path = zpath('generic_generator_profiles')
    bl_path = zpath('branch_load')
    cq_path = zpath('connection_queue')
    
    missing = []
    for name, path in [('SF', sf_path), ('PEL', pel_path), ('Profiles', prof_path), ('Branch load', bl_path)]:
        if path is None:
            missing.append(name)
    
    if missing:
        print(f"  SKIPPING — missing files: {missing}")
        return []
    
    t0 = time.time()
    sf = pd.read_csv(sf_path)
    pel = pd.read_csv(pel_path)
    profiles = pd.read_csv(prof_path)
    branch_load = pd.read_csv(bl_path)
    
    cq = pd.read_csv(cq_path) if cq_path and os.path.exists(cq_path) else None
    
    n_halfhours = len(profiles)
    branch_col_set = set(branch_load.columns) - {'Half Hour'}
    
    print(f"  Loaded in {time.time()-t0:.1f}s: {len(sf)} SF rows, {branch_load.shape[1]} branches, {n_halfhours} half-hours")
    if cq is not None:
        print(f"  Connection queue: {len(cq)} projects, {cq['Site Export Capacity (MW)'].sum():.0f} MW")
    
    # Season index
    timestamps = pd.to_datetime(profiles['Half Hour'])
    months = timestamps.dt.month.values
    season_map = {
        1: 'Winter', 2: 'Winter', 12: 'Winter',
        3: 'Intermediate Cool', 4: 'Intermediate Cool', 11: 'Intermediate Cool',
        5: 'Intermediate Warm', 9: 'Intermediate Warm', 10: 'Intermediate Warm',
        6: 'Summer', 7: 'Summer', 8: 'Summer',
    }
    season_names = ['Winter', 'Intermediate Cool', 'Intermediate Warm', 'Summer']
    season_to_idx = {s: i for i, s in enumerate(season_names)}
    halfhour_season_idx = np.array([season_to_idx[season_map[m]] for m in months])
    
    # PEL lookup
    pel['branch_key'] = pel.apply(
        lambda r: f"{r['From Bus Number']}_{r['To Bus Number']}_{r['Circuit ID']}", axis=1
    )
    pel_fwd = {}
    pel_rev = {}
    for bk, group in pel.groupby('branch_key'):
        fwd = np.zeros(4)
        rev = np.zeros(4)
        for _, row in group.iterrows():
            idx = season_to_idx.get(row['Season'])
            if idx is not None:
                fwd[idx] = row['Forward PEL MW']
                rev[idx] = row['Reverse PEL MW']
        pel_fwd[bk] = fwd
        pel_rev[bk] = rev
    
    # Project queue onto branch loads
    if cq is not None and len(cq) > 0:
        bus_outputs = {}
        for _, p in cq.iterrows():
            prof_col = FUEL_TO_PROFILE.get(p['Fuel type'], 'Other')
            if prof_col not in profiles.columns:
                continue
            output = p['Site Export Capacity (MW)'] * profiles[prof_col].values
            bus = p['Bus Number']
            if bus not in bus_outputs:
                bus_outputs[bus] = np.zeros(n_halfhours)
            bus_outputs[bus] += output
        
        n_added = 0
        for bus_num, bus_output in bus_outputs.items():
            bus_sf = sf[sf['Node Number'] == bus_num]
            for _, row in bus_sf.iterrows():
                branch_col = f"{row['From Bus Number']}_{row['To Bus Number']}_{row['Tertiary Bus Number']}_{row['Circuit ID']}"
                if branch_col in branch_load.columns:
                    branch_load[branch_col] = branch_load[branch_col].values + bus_output * row['Sensitivity Factor MW']
                    n_added += 1
        print(f"  Queue projected onto {n_added} branch-columns")
    
    # Update branch_col_set
    branch_col_set = set(branch_load.columns) - {'Half Hour'}
    
    # Find BSP connection points in this zone
    all_nodes = sf[['Node Number', 'Node Name']].drop_duplicates()
    bsp_nodes = all_nodes[all_nodes['Node Name'].str.match(r'^[A-Z]{4}3_MAIN1$', na=False)]
    
    bsp_points = {}
    for _, row in bsp_nodes.iterrows():
        code = row['Node Name'][:4]
        name = CIM_TO_NAME.get(code, code)
        bsp_points[name] = row['Node Number']
    
    print(f"  BSP connection points found: {len(bsp_points)}")
    
    # Compute curtailment for each BSP
    def compute_curtailment(bus_number, gen_mw, tech='PV'):
        if tech == 'PV':
            profile = profiles['PV'].values
        elif tech == 'Wind':
            profile = profiles['Wind'].values
        elif tech == 'BESS':
            profile = profiles['BESS Export pu'].values
        else:
            profile = profiles['Other'].values
        
        gen_output = gen_mw * profile
        
        bus_sf = sf[sf['Node Number'] == bus_number].copy()
        if len(bus_sf) == 0:
            return None
        bus_sf = bus_sf[bus_sf['Sensitivity Factor MW'].abs() >= 0.05].copy()
        if len(bus_sf) == 0:
            return None
        
        bus_sf['branch_key'] = bus_sf.apply(
            lambda r: f"{r['From Bus Number']}_{r['To Bus Number']}_{r['Circuit ID']}", axis=1
        )
        bus_sf['branch_col'] = bus_sf.apply(
            lambda r: f"{r['From Bus Number']}_{r['To Bus Number']}_{r['Tertiary Bus Number']}_{r['Circuit ID']}", axis=1
        )
        bus_sf = bus_sf[bus_sf['branch_col'].isin(branch_col_set)].copy()
        if len(bus_sf) == 0:
            return None
        
        max_curtail = np.zeros(n_halfhours)
        binding_counts = {}
        
        for _, row in bus_sf.iterrows():
            sf_val = row['Sensitivity Factor MW']
            branch_col = row['branch_col']
            branch_key = row['branch_key']
            
            existing_flow = branch_load[branch_col].values
            fwd_pels = pel_fwd.get(branch_key)
            rev_pels = pel_rev.get(branch_key)
            if fwd_pels is None or rev_pels is None:
                continue
            
            fwd_pel_hh = fwd_pels[halfhour_season_idx]
            rev_pel_hh = rev_pels[halfhour_season_idx]
            new_flow = existing_flow + gen_output * sf_val
            
            if sf_val > 0:
                excess = np.maximum(new_flow - fwd_pel_hh, 0)
                curtail_mw = np.minimum(excess / sf_val, gen_output)
            elif sf_val < 0:
                excess = np.maximum(rev_pel_hh - new_flow, 0)
                curtail_mw = np.minimum(excess / abs(sf_val), gen_output)
            else:
                continue
            
            new_binding = curtail_mw > max_curtail
            if new_binding.any():
                binding_counts[branch_key] = binding_counts.get(branch_key, 0) + int(new_binding.sum())
            max_curtail = np.maximum(max_curtail, curtail_mw)
        
        total_mwh = gen_output.sum() / 2
        curtailed_mwh = max_curtail.sum() / 2
        curtailed_hours = int((max_curtail > 0).sum())
        curtailment_pct = 100 * curtailed_mwh / total_mwh if total_mwh > 0 else 0
        
        if binding_counts:
            top_key = max(binding_counts, key=binding_counts.get)
            info = bus_sf[bus_sf['branch_key'] == top_key].iloc[0]
            binding_name = f"{info['From Bus Name']}->{info['To Bus Name']}"
        else:
            binding_name = 'None'
        
        return {
            'curtailment_pct': round(curtailment_pct, 2),
            'curtailed_mwh': round(curtailed_mwh),
            'total_mwh': round(total_mwh),
            'delivered_mwh': round(total_mwh - curtailed_mwh),
            'curtailed_hours': curtailed_hours,
            'binding_branch': binding_name,
            'n_sensitive_branches': len(bus_sf),
        }
    
    # Run for all BSPs in this zone
    results = []
    for bsp_name, bus_num in sorted(bsp_points.items()):
        for tech in ['PV', 'Wind', 'BESS']:
            for mw in [5, 10, 20, 30, 50]:
                r = compute_curtailment(bus_num, mw, tech)
                if r:
                    results.append({
                        'substation': bsp_name, 'zone': prefix, 'technology': tech,
                        'capacity_mw': mw, **r
                    })
                else:
                    results.append({
                        'substation': bsp_name, 'zone': prefix, 'technology': tech,
                        'capacity_mw': mw, 'curtailment_pct': None, 'curtailed_mwh': None,
                        'total_mwh': None, 'delivered_mwh': None, 'curtailed_hours': None,
                        'binding_branch': 'No data', 'n_sensitive_branches': 0,
                    })
    
    print(f"  Computed {len(results)} estimates for {len(bsp_points)} BSPs")
    return results


# ============================================================
# RUN ALL ZONES
# ============================================================
t_start = time.time()
all_results = []

for prefix, zone_id in zones:
    zone_results = compute_curtailment_for_zone(prefix, zone_id)
    all_results.extend(zone_results)

df_all = pd.DataFrame(all_results)

# ============================================================
# DISPLAY SUMMARY
# ============================================================
print(f"\n\n{'='*100}")
print(f"SOUTH WALES CURTAILMENT SUMMARY — 20MW Solar at each BSP")
print(f"{'='*100}")

solar_20 = df_all[(df_all['technology'] == 'PV') & (df_all['capacity_mw'] == 20)].copy()
solar_20 = solar_20.sort_values('curtailment_pct', ascending=False)

print(f"\n{'Substation':<22} {'Zone':<30} {'Curtail%':>9} {'Lost MWh':>10} {'Binding Branch':<35}")
print("-" * 110)
for _, row in solar_20.iterrows():
    if pd.notna(row['curtailment_pct']):
        print(f"{row['substation']:<22} {row['zone']:<30} {row['curtailment_pct']:>8.1f}% {row['curtailed_mwh']:>10} {row['binding_branch']:<35}")

# Substations with >1% curtailment
high_curt = solar_20[solar_20['curtailment_pct'] > 1]
print(f"\n\nSubstations with >1% solar curtailment at 20MW: {len(high_curt)}")

# Substations with 0%
zero_curt = solar_20[solar_20['curtailment_pct'] == 0]
print(f"Substations with 0% solar curtailment at 20MW: {len(zero_curt)}")

# ============================================================
# SAVE
# ============================================================
# Save as south_wales_curtailment.csv (not just swansea_north)
output_path = os.path.join(MVP_DATA_DIR, 'south_wales_curtailment.csv')
df_all.to_csv(output_path, index=False)

# Also keep backward compatibility
swansea_only = df_all[df_all['zone'].str.contains('swansea', case=False)]
swansea_path = os.path.join(MVP_DATA_DIR, 'swansea_north_curtailment.csv')
swansea_only.to_csv(swansea_path, index=False)

print(f"\n\nSaved {len(df_all)} estimates to {output_path}")
print(f"Zones processed: {len(zones)}")
print(f"Unique substations: {df_all['substation'].nunique()}")
print(f"Total time: {time.time()-t_start:.0f}s")
