"""
05_lifo_and_colocation.py (v2 — all zones)
============================================
Computes LIFO position scenarios and co-location analysis
for all BSPs across all 7 South Wales GSP zones.

Output:
  - data/south_wales_curtailment_lifo.csv
  - data/south_wales_curtailment_colocation.csv
"""

import pandas as pd
import numpy as np
import os
import glob
import time

MVP_DATA_DIR = '/Users/leonie/Documents/South_Wales_headroom_MVP/data'

FUEL_TO_PROFILE = {'Solar': 'PV', 'Wind': 'Wind', 'BESS': 'BESS Export pu', 'Other': 'Other'}

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
    'TROS': 'Trostre', 'TRAV': 'Ystradgynlais',
}

COLOCATION_SCENARIOS = [
    {'name': '30MW Wind + 20MW Solar',              'wind_mw': 30, 'solar_mw': 20, 'bess_mw': 0},
    {'name': '30MW Wind + 10MW BESS',               'wind_mw': 30, 'solar_mw': 0,  'bess_mw': 10},
    {'name': '20MW Solar + 10MW BESS',              'wind_mw': 0,  'solar_mw': 20, 'bess_mw': 10},
    {'name': '30MW Wind + 20MW Solar + 10MW BESS',  'wind_mw': 30, 'solar_mw': 20, 'bess_mw': 10},
    {'name': '50MW Wind only',                      'wind_mw': 50, 'solar_mw': 0,  'bess_mw': 0},
    {'name': '50MW Solar only',                     'wind_mw': 0,  'solar_mw': 50, 'bess_mw': 0},
    {'name': '50MW BESS only',                      'wind_mw': 0,  'solar_mw': 0,  'bess_mw': 50},
]

POSITION_THRESHOLDS = [0, 50, 100, 200, 500, 1000, 9999]


# ============================================================
# ZONE DETECTION
# ============================================================
branch_files = glob.glob(os.path.join(MVP_DATA_DIR, '*_branch_load_id_*_2026.csv'))
zones = []
for f in sorted(branch_files):
    basename = os.path.basename(f)
    parts = basename.split('_branch_load_id_')
    if len(parts) == 2:
        prefix = parts[0]
        zone_id = parts[1].replace('_2026.csv', '')
        zones.append((prefix, zone_id))

print(f"Found {len(zones)} zones\n")


# ============================================================
# HELPERS
# ============================================================

def load_zone_data(prefix, zone_id):
    """Load all data files for a zone. Returns dict or None if missing."""
    def zpath(filetype):
        pattern = os.path.join(MVP_DATA_DIR, f'{prefix}_{filetype}_id_{zone_id}_2026.csv')
        matches = glob.glob(pattern)
        if not matches:
            pattern2 = os.path.join(MVP_DATA_DIR, f'{prefix}*{filetype}*id_{zone_id}_2026.csv')
            matches = glob.glob(pattern2)
        return matches[0] if matches else None

    paths = {
        'sf': zpath('sensitivity_factors'),
        'pel': zpath('pre-event_limits') or zpath('pre-event-limits'),
        'profiles': zpath('generic_generator_profiles'),
        'branch_load': zpath('branch_load'),
        'cq': zpath('connection_queue'),
    }

    for key in ['sf', 'pel', 'profiles', 'branch_load']:
        if paths[key] is None:
            return None

    data = {}
    data['sf'] = pd.read_csv(paths['sf'])
    data['pel'] = pd.read_csv(paths['pel'])
    data['profiles'] = pd.read_csv(paths['profiles'])
    data['branch_load'] = pd.read_csv(paths['branch_load'])
    data['cq'] = pd.read_csv(paths['cq']) if paths['cq'] and os.path.exists(paths['cq']) else pd.DataFrame()

    n = len(data['profiles'])
    timestamps = pd.to_datetime(data['profiles']['Half Hour'])
    months = timestamps.dt.month.values
    season_map = {
        1: 'Winter', 2: 'Winter', 12: 'Winter',
        3: 'Intermediate Cool', 4: 'Intermediate Cool', 11: 'Intermediate Cool',
        5: 'Intermediate Warm', 9: 'Intermediate Warm', 10: 'Intermediate Warm',
        6: 'Summer', 7: 'Summer', 8: 'Summer',
    }
    season_names = ['Winter', 'Intermediate Cool', 'Intermediate Warm', 'Summer']
    season_to_idx = {s: i for i, s in enumerate(season_names)}
    data['halfhour_season_idx'] = np.array([season_to_idx[season_map[m]] for m in months])
    data['n_halfhours'] = n

    # PEL lookup
    data['pel']['branch_key'] = data['pel'].apply(
        lambda r: f"{r['From Bus Number']}_{r['To Bus Number']}_{r['Circuit ID']}", axis=1
    )
    pel_fwd = {}
    pel_rev = {}
    for bk, group in data['pel'].groupby('branch_key'):
        fwd = np.zeros(4)
        rev = np.zeros(4)
        for _, row in group.iterrows():
            idx = season_to_idx.get(row['Season'])
            if idx is not None:
                fwd[idx] = row['Forward PEL MW']
                rev[idx] = row['Reverse PEL MW']
        pel_fwd[bk] = fwd
        pel_rev[bk] = rev
    data['pel_fwd'] = pel_fwd
    data['pel_rev'] = pel_rev

    # Find BSPs
    all_nodes = data['sf'][['Node Number', 'Node Name']].drop_duplicates()
    bsp_nodes = all_nodes[all_nodes['Node Name'].str.match(r'^[A-Z]{4}3_MAIN1$', na=False)]
    bsp_points = {}
    for _, row in bsp_nodes.iterrows():
        code = row['Node Name'][:4]
        name = CIM_TO_NAME.get(code, code)
        bsp_points[name] = row['Node Number']
    data['bsp_points'] = bsp_points

    return data


def project_queue(data, cq_subset):
    """Add queued generation to branch loads. Returns modified copy."""
    bl = data['branch_load'].copy()
    profiles = data['profiles']
    sf = data['sf']
    n = data['n_halfhours']

    bus_outputs = {}
    for _, p in cq_subset.iterrows():
        prof_col = FUEL_TO_PROFILE.get(p['Fuel type'], 'Other')
        if prof_col not in profiles.columns:
            continue
        output = p['Site Export Capacity (MW)'] * profiles[prof_col].values
        bus = p['Bus Number']
        if bus not in bus_outputs:
            bus_outputs[bus] = np.zeros(n)
        bus_outputs[bus] += output

    for bus_num, bus_output in bus_outputs.items():
        bus_sf = sf[sf['Node Number'] == bus_num]
        for _, row in bus_sf.iterrows():
            branch_col = f"{row['From Bus Number']}_{row['To Bus Number']}_{row['Tertiary Bus Number']}_{row['Circuit ID']}"
            if branch_col in bl.columns:
                bl[branch_col] = bl[branch_col].values + bus_output * row['Sensitivity Factor MW']
    return bl


def compute_curtailment(data, bus_number, gen_output_array, branch_load):
    """Compute curtailment for an arbitrary generation output array."""
    sf = data['sf']
    pel_fwd = data['pel_fwd']
    pel_rev = data['pel_rev']
    halfhour_season_idx = data['halfhour_season_idx']
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

    n = data['n_halfhours']
    max_curtail = np.zeros(n)
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
# MAIN LOOP
# ============================================================
t_start = time.time()
all_lifo = []
all_coloc = []

for prefix, zone_id in zones:
    print(f"\n{'='*60}")
    print(f"ZONE: {prefix} (id={zone_id})")
    print(f"{'='*60}")

    data = load_zone_data(prefix, zone_id)
    if data is None:
        print("  SKIPPING — missing files")
        continue

    t0 = time.time()
    profiles = data['profiles']
    cq = data['cq']
    bsp_points = data['bsp_points']

    # Separate recently connected and accepted
    if len(cq) > 0 and 'Status' in cq.columns and 'Position' in cq.columns:
        recently_connected = cq[cq['Status'] == 'Recently Connected']
        accepted = cq[cq['Status'] == 'Accepted not yet Connected'].sort_values('Position')
        has_queue = True
    else:
        recently_connected = pd.DataFrame()
        accepted = pd.DataFrame()
        has_queue = False

    # Full queue projection for co-location
    bl_full = project_queue(data, cq) if len(cq) > 0 else data['branch_load'].copy()

    print(f"  {len(bsp_points)} BSPs, {len(cq)} queue projects")

    for bsp_name, bus_num in sorted(bsp_points.items()):

        # ============================================================
        # LIFO POSITION SCENARIOS
        # ============================================================
        if has_queue and len(accepted) > 0:
            for pos_threshold in POSITION_THRESHOLDS:
                queue_subset = pd.concat([
                    recently_connected,
                    accepted[accepted['Position'] <= pos_threshold]
                ])
                queue_mw = queue_subset['Site Export Capacity (MW)'].sum()

                bl_projected = project_queue(data, queue_subset)

                row_result = {
                    'substation': bsp_name, 'zone': prefix,
                    'position_threshold': pos_threshold,
                    'queue_mw': round(queue_mw),
                }

                for tech, prof_col in [('PV', 'PV'), ('Wind', 'Wind'), ('BESS', 'BESS Export pu')]:
                    if prof_col not in profiles.columns:
                        row_result[f'{tech}_curtailment_pct'] = None
                        continue
                    gen_output = 20 * profiles[prof_col].values
                    r = compute_curtailment(data, bus_num, gen_output, bl_projected)
                    row_result[f'{tech}_curtailment_pct'] = r['curtailment_pct'] if r else None

                all_lifo.append(row_result)

        # ============================================================
        # CO-LOCATION SCENARIOS
        # ============================================================
        for scenario in COLOCATION_SCENARIOS:
            gen_parts = []
            if scenario['wind_mw'] > 0 and 'Wind' in profiles.columns:
                gen_parts.append(scenario['wind_mw'] * profiles['Wind'].values)
            if scenario['solar_mw'] > 0 and 'PV' in profiles.columns:
                gen_parts.append(scenario['solar_mw'] * profiles['PV'].values)
            if scenario['bess_mw'] > 0 and 'BESS Export pu' in profiles.columns:
                gen_parts.append(scenario['bess_mw'] * profiles['BESS Export pu'].values)

            if not gen_parts:
                continue

            gen_output = sum(gen_parts)
            total_mw = scenario['wind_mw'] + scenario['solar_mw'] + scenario['bess_mw']

            r = compute_curtailment(data, bus_num, gen_output, bl_full)
            if r:
                all_coloc.append({
                    'substation': bsp_name, 'zone': prefix,
                    'scenario': scenario['name'],
                    'wind_mw': scenario['wind_mw'],
                    'solar_mw': scenario['solar_mw'],
                    'bess_mw': scenario['bess_mw'],
                    'total_mw': total_mw,
                    **r,
                })

    print(f"  Done in {time.time()-t0:.1f}s")


# ============================================================
# SAVE
# ============================================================
df_lifo = pd.DataFrame(all_lifo)
df_coloc = pd.DataFrame(all_coloc)

lifo_path = os.path.join(MVP_DATA_DIR, 'south_wales_curtailment_lifo.csv')
coloc_path = os.path.join(MVP_DATA_DIR, 'south_wales_curtailment_colocation.csv')

df_lifo.to_csv(lifo_path, index=False)
df_coloc.to_csv(coloc_path, index=False)

print(f"\n\n{'='*60}")
print(f"SUMMARY")
print(f"{'='*60}")
print(f"LIFO: {len(df_lifo)} rows ({df_lifo['substation'].nunique()} substations)")
print(f"Co-location: {len(df_coloc)} rows ({df_coloc['substation'].nunique()} substations)")
print(f"Total time: {time.time()-t_start:.0f}s")
print(f"\nSaved to:")
print(f"  {lifo_path}")
print(f"  {coloc_path}")
