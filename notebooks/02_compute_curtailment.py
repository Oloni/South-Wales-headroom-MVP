"""
02_compute_curtailment.py (v3 — with queue projection)
======================================================
Computes curtailment estimates for hypothetical new generators
at each BSP in the Swansea North GSP group.

KEY IMPROVEMENT: Adds the accepted connection queue onto the existing
branch loads before computing curtailment. This reflects the future
network state when queued projects build out — which is what matters
for a new connection.

Output: data/swansea_north_curtailment.csv
"""

import pandas as pd
import numpy as np
import os
import time

MVP_DATA_DIR = '/Users/leonie/Documents/South_Wales_headroom_MVP/data'

# ============================================================
# LOAD DATA
# ============================================================
print("Loading data...")
t0 = time.time()

sf = pd.read_csv(os.path.join(MVP_DATA_DIR, 'swansea-north_sensitivity_factors_id_315_2026.csv'))
pel = pd.read_csv(os.path.join(MVP_DATA_DIR, 'swansea-north_pre-event_limits_id_315_2026.csv'))
profiles = pd.read_csv(os.path.join(MVP_DATA_DIR, 'swansea-north_generic_generator_profiles_id_315_2026.csv'))
branch_load = pd.read_csv(os.path.join(MVP_DATA_DIR, 'swansea-north_branch_load_id_315_2026.csv'))
cq = pd.read_csv(os.path.join(MVP_DATA_DIR, 'swansea-north_connection_queue_id_315_2026.csv'))

print(f"  Branch loads: {branch_load.shape[0]} half-hours x {branch_load.shape[1]} columns")
print(f"  Connection queue: {len(cq)} projects, {cq['Site Export Capacity (MW)'].sum():.0f} MW total")
print(f"Data loaded in {time.time()-t0:.1f}s")

n_halfhours = len(profiles)
branch_col_set = set(branch_load.columns) - {'Half Hour'}

# ============================================================
# BUILD SEASON INDEX
# ============================================================
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
pel_fwd_by_branch = {}
pel_rev_by_branch = {}
for branch_key, group in pel.groupby('branch_key'):
    fwd = np.zeros(4)
    rev = np.zeros(4)
    for _, row in group.iterrows():
        idx = season_to_idx.get(row['Season'])
        if idx is not None:
            fwd[idx] = row['Forward PEL MW']
            rev[idx] = row['Reverse PEL MW']
    pel_fwd_by_branch[branch_key] = fwd
    pel_rev_by_branch[branch_key] = rev


# ============================================================
# STEP 1: PROJECT THE QUEUE ONTO BRANCH LOADS
# ============================================================
print("\nProjecting connection queue onto branch loads...")

fuel_to_profile = {
    'Solar': 'PV', 'Wind': 'Wind', 'BESS': 'BESS Export pu', 'Other': 'Other',
}

# Aggregate generation output by bus number
bus_outputs = {}
for _, p in cq.iterrows():
    prof_col = fuel_to_profile.get(p['Fuel type'], 'Other')
    output = p['Site Export Capacity (MW)'] * profiles[prof_col].values
    bus = p['Bus Number']
    if bus not in bus_outputs:
        bus_outputs[bus] = np.zeros(n_halfhours)
    bus_outputs[bus] += output

# Compute branch load addition from queued generation
queue_addition = {}  # branch_col -> numpy array
missing_buses = set()

for bus_num, bus_output in bus_outputs.items():
    bus_sf = sf[sf['Node Number'] == bus_num]
    if len(bus_sf) == 0:
        missing_buses.add(bus_num)
        continue
    for _, row in bus_sf.iterrows():
        branch_col = f"{row['From Bus Number']}_{row['To Bus Number']}_{row['Tertiary Bus Number']}_{row['Circuit ID']}"
        sf_val = row['Sensitivity Factor MW']
        contribution = bus_output * sf_val
        if branch_col not in queue_addition:
            queue_addition[branch_col] = np.zeros(n_halfhours)
        queue_addition[branch_col] += contribution

if missing_buses:
    print(f"  WARNING: No sensitivity factors for buses: {missing_buses}")

# Add queue projections to branch load dataframe
n_added = 0
for branch_col, addition in queue_addition.items():
    if branch_col in branch_load.columns:
        branch_load[branch_col] = branch_load[branch_col].values + addition
        n_added += 1

print(f"  Added queue generation to {n_added} branches")
print(f"  Queue projects: {len(cq)} ({cq['Site Export Capacity (MW)'].sum():.0f} MW)")

# Update branch_col_set after modifications
branch_col_set = set(branch_load.columns) - {'Half Hour'}


# ============================================================
# BSP CONNECTION POINTS
# ============================================================
bsp_connection_points = {
    'Ammanford':      536300,
    'Briton Ferry':   541400,
    'Carmarthen':     534200,
    'Gowerton East':  547100,
    'Hirwaun':        538100,
    'Lampeter':       575100,
    'Llanarth':       531300,
    'Rhos':           574500,
    'Swansea North':  547200,
    'Swansea West':   542900,
    'Tir John':       540000,
    'Trostre':        537818,
    'Ystradgynlais':  539300,
}


# ============================================================
# VECTORISED CURTAILMENT CALCULATION
# ============================================================

def compute_curtailment(bus_number, gen_mw, tech='PV'):
    """Compute annual curtailment using vectorised numpy operations."""

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
        fwd_pels = pel_fwd_by_branch.get(branch_key)
        rev_pels = pel_rev_by_branch.get(branch_key)
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


# ============================================================
# RUN FOR ALL BSPs x TECHS x SIZES
# ============================================================
print("\nComputing curtailment estimates (with queue projection)...\n")

results = []
for bsp_name, bus_num in sorted(bsp_connection_points.items()):
    print(f"  {bsp_name}...", end=" ", flush=True)
    t1 = time.time()
    for tech in ['PV', 'Wind', 'BESS']:
        for mw in [5, 10, 20, 30, 50]:
            r = compute_curtailment(bus_num, mw, tech)
            if r:
                results.append({'substation': bsp_name, 'technology': tech, 'capacity_mw': mw, **r})
            else:
                results.append({
                    'substation': bsp_name, 'technology': tech, 'capacity_mw': mw,
                    'curtailment_pct': None, 'curtailed_mwh': None, 'total_mwh': None,
                    'delivered_mwh': None, 'curtailed_hours': None,
                    'binding_branch': 'No data', 'n_sensitive_branches': 0,
                })
    print(f"({time.time()-t1:.1f}s)")

df_results = pd.DataFrame(results)

# ============================================================
# DISPLAY
# ============================================================
print("\n" + "=" * 100)
print("CURTAILMENT ESTIMATES - 20MW at each BSP (Swansea North zone)")
print("With connection queue projected onto branch loads (future network state)")
print("=" * 100)

print(f"\n{'Substation':<18} {'Tech':<6} {'Curtail%':>9} {'Lost MWh':>10} {'Hours':>7} {'Binding Branch':<35}")
print("-" * 90)
for bsp_name in sorted(bsp_connection_points.keys()):
    for tech in ['PV', 'Wind', 'BESS']:
        row = df_results[
            (df_results['substation'] == bsp_name) &
            (df_results['technology'] == tech) &
            (df_results['capacity_mw'] == 20)
        ]
        if len(row) == 0 or pd.isna(row.iloc[0]['curtailment_pct']):
            print(f"{bsp_name:<18} {tech:<6}       N/A")
            continue
        r = row.iloc[0]
        print(f"{bsp_name:<18} {tech:<6} {r['curtailment_pct']:>8.1f}% {r['curtailed_mwh']:>10} {r['curtailed_hours']:>7} {r['binding_branch']:<35}")

print(f"\n\n{'SOLAR CURTAILMENT BY SIZE':=^70}")
print(f"\n{'Substation':<18} {'5MW':>7} {'10MW':>7} {'20MW':>7} {'30MW':>7} {'50MW':>7}")
print("-" * 55)
for bsp_name in sorted(bsp_connection_points.keys()):
    vals = []
    for mw in [5, 10, 20, 30, 50]:
        row = df_results[
            (df_results['substation'] == bsp_name) &
            (df_results['technology'] == 'PV') &
            (df_results['capacity_mw'] == mw)
        ]
        if len(row) > 0 and pd.notna(row.iloc[0]['curtailment_pct']):
            vals.append(f"{row.iloc[0]['curtailment_pct']:.1f}%")
        else:
            vals.append("N/A")
    print(f"{bsp_name:<18} {vals[0]:>7} {vals[1]:>7} {vals[2]:>7} {vals[3]:>7} {vals[4]:>7}")

print(f"\n\n{'WIND CURTAILMENT BY SIZE':=^70}")
print(f"\n{'Substation':<18} {'5MW':>7} {'10MW':>7} {'20MW':>7} {'30MW':>7} {'50MW':>7}")
print("-" * 55)
for bsp_name in sorted(bsp_connection_points.keys()):
    vals = []
    for mw in [5, 10, 20, 30, 50]:
        row = df_results[
            (df_results['substation'] == bsp_name) &
            (df_results['technology'] == 'Wind') &
            (df_results['capacity_mw'] == mw)
        ]
        if len(row) > 0 and pd.notna(row.iloc[0]['curtailment_pct']):
            vals.append(f"{row.iloc[0]['curtailment_pct']:.1f}%")
        else:
            vals.append("N/A")
    print(f"{bsp_name:<18} {vals[0]:>7} {vals[1]:>7} {vals[2]:>7} {vals[3]:>7} {vals[4]:>7}")

print(f"\n\n{'BESS CURTAILMENT BY SIZE':=^70}")
print(f"\n{'Substation':<18} {'5MW':>7} {'10MW':>7} {'20MW':>7} {'30MW':>7} {'50MW':>7}")
print("-" * 55)
for bsp_name in sorted(bsp_connection_points.keys()):
    vals = []
    for mw in [5, 10, 20, 30, 50]:
        row = df_results[
            (df_results['substation'] == bsp_name) &
            (df_results['technology'] == 'BESS') &
            (df_results['capacity_mw'] == mw)
        ]
        if len(row) > 0 and pd.notna(row.iloc[0]['curtailment_pct']):
            vals.append(f"{row.iloc[0]['curtailment_pct']:.1f}%")
        else:
            vals.append("N/A")
    print(f"{bsp_name:<18} {vals[0]:>7} {vals[1]:>7} {vals[2]:>7} {vals[3]:>7} {vals[4]:>7}")

# ============================================================
# SAVE
# ============================================================
output_path = os.path.join(MVP_DATA_DIR, 'swansea_north_curtailment.csv')
df_results.to_csv(output_path, index=False)
print(f"\n\nSaved {len(df_results)} estimates to {output_path}")
print(f"Total time: {time.time()-t0:.0f}s")

print("\n\nMETHODOLOGY:")
print("- Existing branch loads: actual 2024 measured data from NGED")
print("- Queue projection: all accepted + recently connected projects added")
print(f"  using generic profiles x sensitivity factors ({cq['Site Export Capacity (MW)'].sum():.0f} MW total)")
print("- New generator assumed LAST in LIFO queue (worst case for curtailment)")
print("- Seasonal PELs applied (Winter/Int Cool/Int Warm/Summer)")
print("- 5% sensitivity threshold per NGED methodology")
