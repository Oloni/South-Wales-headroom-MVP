"""
05_lifo_and_colocation.py
=========================
Adds two features to the curtailment analysis:

1. LIFO position scenarios: instead of assuming worst case (last in queue),
   compute curtailment at different queue positions to show how curtailment
   changes depending on when you connect.

2. Co-location analysis: compute curtailment for combined technologies at
   the same bus (e.g. 30MW wind + 20MW solar + 10MW BESS on one connection).

Output: 
  - data/south_wales_curtailment_lifo.csv  (position scenarios)
  - data/south_wales_curtailment_colocation.csv  (hybrid combinations)
"""

import pandas as pd
import numpy as np
import os
import glob
import time

MVP_DATA_DIR = '/Users/leonie/Documents/South_Wales_headroom_MVP/data'

FUEL_TO_PROFILE = {'Solar': 'PV', 'Wind': 'Wind', 'BESS': 'BESS Export pu', 'Other': 'Other'}

CIM_TO_NAME = {
    'AMMA': 'Ammanford', 'BRIF': 'Briton Ferry', 'CARM': 'Carmarthen',
    'GOWE': 'Gowerton East', 'HIRW': 'Hirwaun', 'LAMP': 'Lampeter',
    'LLAN': 'Llanarth', 'RHOS': 'Rhos', 'SWAN': 'Swansea North',
    'SWAW': 'Swansea West', 'TIRJ': 'Tir John', 'TROS': 'Trostre',
    'TRAV': 'Ystradgynlais',
}

# Focus on Swansea North for now (expand later)
ZONE_PREFIX = 'swansea-north'
ZONE_ID = '315'


# ============================================================
# LOAD DATA
# ============================================================
print("Loading data...")
t0 = time.time()

sf = pd.read_csv(os.path.join(MVP_DATA_DIR, f'{ZONE_PREFIX}_sensitivity_factors_id_{ZONE_ID}_2026.csv'))
pel = pd.read_csv(os.path.join(MVP_DATA_DIR, f'{ZONE_PREFIX}_pre-event_limits_id_{ZONE_ID}_2026.csv'))
profiles = pd.read_csv(os.path.join(MVP_DATA_DIR, f'{ZONE_PREFIX}_generic_generator_profiles_id_{ZONE_ID}_2026.csv'))
branch_load_original = pd.read_csv(os.path.join(MVP_DATA_DIR, f'{ZONE_PREFIX}_branch_load_id_{ZONE_ID}_2026.csv'))
cq = pd.read_csv(os.path.join(MVP_DATA_DIR, f'{ZONE_PREFIX}_connection_queue_id_{ZONE_ID}_2026.csv'))

n_halfhours = len(profiles)
print(f"Loaded in {time.time()-t0:.1f}s\n")

# Season setup
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

# BSP connection points
all_nodes = sf[['Node Number', 'Node Name']].drop_duplicates()
bsp_nodes = all_nodes[all_nodes['Node Name'].str.match(r'^[A-Z]{4}3_MAIN1$', na=False)]
bsp_points = {}
for _, row in bsp_nodes.iterrows():
    code = row['Node Name'][:4]
    name = CIM_TO_NAME.get(code, code)
    bsp_points[name] = row['Node Number']


# ============================================================
# HELPER: Project queue up to a given LIFO position
# ============================================================

def project_queue(branch_load, cq_subset):
    """Add queued generation to branch loads. Returns modified copy."""
    bl = branch_load.copy()
    
    bus_outputs = {}
    for _, p in cq_subset.iterrows():
        prof_col = FUEL_TO_PROFILE.get(p['Fuel type'], 'Other')
        if prof_col not in profiles.columns:
            continue
        output = p['Site Export Capacity (MW)'] * profiles[prof_col].values
        bus = p['Bus Number']
        if bus not in bus_outputs:
            bus_outputs[bus] = np.zeros(n_halfhours)
        bus_outputs[bus] += output
    
    for bus_num, bus_output in bus_outputs.items():
        bus_sf = sf[sf['Node Number'] == bus_num]
        for _, row in bus_sf.iterrows():
            branch_col = f"{row['From Bus Number']}_{row['To Bus Number']}_{row['Tertiary Bus Number']}_{row['Circuit ID']}"
            if branch_col in bl.columns:
                bl[branch_col] = bl[branch_col].values + bus_output * row['Sensitivity Factor MW']
    
    return bl


# ============================================================
# HELPER: Compute curtailment for a generation profile array
# ============================================================

def compute_curtailment(bus_number, gen_output_array, branch_load):
    """
    Compute curtailment given an arbitrary generation output array.
    gen_output_array: numpy array of shape (n_halfhours,) — MW output at each half-hour.
    """
    branch_col_set = set(branch_load.columns) - {'Half Hour'}
    
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
        new_flow = existing_flow + gen_output_array * sf_val
        
        if sf_val > 0:
            excess = np.maximum(new_flow - fwd_pel_hh, 0)
            curtail_mw = np.minimum(excess / sf_val, gen_output_array)
        elif sf_val < 0:
            excess = np.maximum(rev_pel_hh - new_flow, 0)
            curtail_mw = np.minimum(excess / abs(sf_val), gen_output_array)
        else:
            continue
        
        new_binding = curtail_mw > max_curtail
        if new_binding.any():
            binding_counts[branch_key] = binding_counts.get(branch_key, 0) + int(new_binding.sum())
        max_curtail = np.maximum(max_curtail, curtail_mw)
    
    total_mwh = gen_output_array.sum() / 2
    curtailed_mwh = max_curtail.sum() / 2
    curtailment_pct = 100 * curtailed_mwh / total_mwh if total_mwh > 0 else 0
    
    binding_name = 'None'
    if binding_counts:
        top_key = max(binding_counts, key=binding_counts.get)
        info = bus_sf[bus_sf['branch_key'] == top_key].iloc[0]
        binding_name = f"{info['From Bus Name']}->{info['To Bus Name']}"
    
    return {
        'curtailment_pct': round(curtailment_pct, 2),
        'curtailed_mwh': round(curtailed_mwh),
        'total_mwh': round(total_mwh),
        'binding_branch': binding_name,
    }


# ============================================================
# PART 1: LIFO POSITION SCENARIOS
# ============================================================
print("=" * 70)
print("PART 1: LIFO POSITION SCENARIOS")
print("=" * 70)
print("\nFor each substation, compute curtailment at different queue positions.")
print("Lower position = fewer projects ahead = less curtailment.\n")

# Define position thresholds to test
# Recently connected (pos=0) are always included
recently_connected = cq[cq['Status'] == 'Recently Connected']
accepted = cq[cq['Status'] == 'Accepted not yet Connected'].sort_values('Position')

# Position scenarios: "what if only projects up to position X are built?"
position_thresholds = [0, 50, 100, 200, 500, 1000, 9999]

lifo_results = []

for bsp_name in ['Swansea West', 'Hirwaun', 'Llanarth', 'Swansea North', 'Rhos', 'Lampeter']:
    if bsp_name not in bsp_points:
        continue
    bus_num = bsp_points[bsp_name]
    
    print(f"\n  {bsp_name}:")
    print(f"  {'Position':<12} {'Queue MW':>10} {'Solar 20MW':>12} {'Wind 20MW':>12} {'BESS 20MW':>12}")
    print(f"  {'-'*60}")
    
    for pos_threshold in position_thresholds:
        # Build queue subset: recently connected + accepted up to this position
        queue_subset = pd.concat([
            recently_connected,
            accepted[accepted['Position'] <= pos_threshold]
        ])
        queue_mw = queue_subset['Site Export Capacity (MW)'].sum()
        
        # Project this queue onto branch loads
        bl_projected = project_queue(branch_load_original, queue_subset)
        
        # Compute curtailment for each tech
        results_line = {'substation': bsp_name, 'position_threshold': pos_threshold, 'queue_mw': round(queue_mw)}
        
        for tech, prof_col in [('PV', 'PV'), ('Wind', 'Wind'), ('BESS', 'BESS Export pu')]:
            gen_output = 20 * profiles[prof_col].values
            r = compute_curtailment(bus_num, gen_output, bl_projected)
            if r:
                results_line[f'{tech}_curtailment_pct'] = r['curtailment_pct']
                results_line[f'{tech}_binding'] = r['binding_branch']
            else:
                results_line[f'{tech}_curtailment_pct'] = None
                results_line[f'{tech}_binding'] = 'No data'
        
        lifo_results.append(results_line)
        
        pv_pct = results_line.get('PV_curtailment_pct', 0) or 0
        wind_pct = results_line.get('Wind_curtailment_pct', 0) or 0
        bess_pct = results_line.get('BESS_curtailment_pct', 0) or 0
        label = f"pos≤{pos_threshold}" if pos_threshold < 9999 else "all"
        print(f"  {label:<12} {queue_mw:>8.0f} MW {pv_pct:>10.1f}% {wind_pct:>10.1f}% {bess_pct:>10.1f}%")

df_lifo = pd.DataFrame(lifo_results)
lifo_path = os.path.join(MVP_DATA_DIR, 'south_wales_curtailment_lifo.csv')
df_lifo.to_csv(lifo_path, index=False)
print(f"\nSaved LIFO scenarios to {lifo_path}")


# ============================================================
# PART 2: CO-LOCATION ANALYSIS
# ============================================================
print(f"\n\n{'='*70}")
print("PART 2: CO-LOCATION ANALYSIS")
print("=" * 70)
print("\nWhat if you combine technologies on the same connection?")
print("e.g. 30MW wind + 20MW solar, or 20MW solar + 10MW BESS\n")

# Use full queue projection for co-location analysis
bl_full = project_queue(branch_load_original, cq)

# Define co-location scenarios
colocation_scenarios = [
    {'name': '30MW Wind + 20MW Solar',     'wind_mw': 30, 'solar_mw': 20, 'bess_mw': 0},
    {'name': '30MW Wind + 10MW BESS',      'wind_mw': 30, 'solar_mw': 0,  'bess_mw': 10},
    {'name': '20MW Solar + 10MW BESS',     'wind_mw': 0,  'solar_mw': 20, 'bess_mw': 10},
    {'name': '30MW Wind + 20MW Solar + 10MW BESS', 'wind_mw': 30, 'solar_mw': 20, 'bess_mw': 10},
    {'name': '50MW Wind only',             'wind_mw': 50, 'solar_mw': 0,  'bess_mw': 0},
    {'name': '50MW Solar only',            'wind_mw': 0,  'solar_mw': 50, 'bess_mw': 0},
    {'name': '50MW BESS only',             'wind_mw': 0,  'solar_mw': 0,  'bess_mw': 50},
]

colocation_results = []

for bsp_name in ['Swansea West', 'Hirwaun', 'Llanarth', 'Swansea North', 'Rhos', 'Lampeter']:
    if bsp_name not in bsp_points:
        continue
    bus_num = bsp_points[bsp_name]
    
    print(f"\n  {bsp_name}:")
    print(f"  {'Scenario':<40} {'Total MW':>10} {'Curtail%':>10} {'Lost MWh':>10} {'Binding':<30}")
    print(f"  {'-'*105}")
    
    for scenario in colocation_scenarios:
        # Combined output: sum of all technologies at each half-hour
        gen_output = (
            scenario['wind_mw'] * profiles['Wind'].values +
            scenario['solar_mw'] * profiles['PV'].values +
            scenario['bess_mw'] * profiles['BESS Export pu'].values
        )
        total_mw = scenario['wind_mw'] + scenario['solar_mw'] + scenario['bess_mw']
        
        r = compute_curtailment(bus_num, gen_output, bl_full)
        
        if r:
            colocation_results.append({
                'substation': bsp_name,
                'scenario': scenario['name'],
                'wind_mw': scenario['wind_mw'],
                'solar_mw': scenario['solar_mw'],
                'bess_mw': scenario['bess_mw'],
                'total_mw': total_mw,
                **r,
            })
            print(f"  {scenario['name']:<40} {total_mw:>8} MW {r['curtailment_pct']:>9.1f}% {r['curtailed_mwh']:>10} {r['binding_branch']:<30}")
        else:
            print(f"  {scenario['name']:<40} {total_mw:>8} MW       N/A")

df_coloc = pd.DataFrame(colocation_results)
coloc_path = os.path.join(MVP_DATA_DIR, 'south_wales_curtailment_colocation.csv')
df_coloc.to_csv(coloc_path, index=False)
print(f"\nSaved co-location analysis to {coloc_path}")


# ============================================================
# INSIGHT: Hybridisation benefit
# ============================================================
print(f"\n\n{'='*70}")
print("HYBRIDISATION INSIGHT")
print("=" * 70)
print("\nCompare: 50MW of one technology vs split across two")
print("This answers Ian's question: 'How can I use the 70% of the grid")
print("that my wind farm isn't using?'\n")

for bsp_name in ['Swansea West', 'Hirwaun', 'Llanarth']:
    if bsp_name not in bsp_points:
        continue
    bus_num = bsp_points[bsp_name]
    
    print(f"  {bsp_name}:")
    
    # 50MW wind only
    wind_only = compute_curtailment(bus_num, 50 * profiles['Wind'].values, bl_full)
    # 50MW solar only
    solar_only = compute_curtailment(bus_num, 50 * profiles['PV'].values, bl_full)
    # 30MW wind + 20MW solar (same total connection)
    hybrid = compute_curtailment(
        bus_num, 
        30 * profiles['Wind'].values + 20 * profiles['PV'].values,
        bl_full
    )
    
    if wind_only and solar_only and hybrid:
        print(f"    50MW Wind only:           {wind_only['curtailment_pct']:>5.1f}% ({wind_only['curtailed_mwh']} MWh lost)")
        print(f"    50MW Solar only:          {solar_only['curtailment_pct']:>5.1f}% ({solar_only['curtailed_mwh']} MWh lost)")
        print(f"    30MW Wind + 20MW Solar:   {hybrid['curtailment_pct']:>5.1f}% ({hybrid['curtailed_mwh']} MWh lost)")
        
        # Show the benefit
        wind_delivered = wind_only['total_mwh'] - wind_only['curtailed_mwh']
        solar_delivered = solar_only['total_mwh'] - solar_only['curtailed_mwh']
        hybrid_delivered = hybrid['total_mwh'] - hybrid['curtailed_mwh']
        
        print(f"    → Hybrid delivers {hybrid_delivered:,.0f} MWh vs {wind_delivered:,.0f} MWh (wind) or {solar_delivered:,.0f} MWh (solar)")
    print()

print(f"\nTotal time: {time.time()-t0:.0f}s")
