"""
05_lifo_and_colocation.py (v3 — proper LIFO ordering)
=====================================================
Three analyses:

1. PROPER LIFO: If you connect at queue position P, generators behind you
   (position > P) get curtailed before you. Your curtailment is lower
   because they absorb the constraint first.

2. QUEUE BUILD-OUT: What if only projects up to position X actually build?
   (Previously mislabelled as "LIFO sensitivity")

3. CO-LOCATION: Combined technology scenarios on the same connection.

Output:
  - data/south_wales_curtailment_lifo.csv      (proper LIFO by position)
  - data/south_wales_curtailment_buildout.csv   (queue build-out scenarios)
  - data/south_wales_curtailment_colocation.csv (hybrid combinations)
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

BUILDOUT_THRESHOLDS = [0, 50, 100, 200, 500, 1000, 9999]

# For proper LIFO: test "what if I'm at these positions"
LIFO_TEST_POSITIONS = [1, 10, 50, 100, 200, 500, 9999]


def get_smart_thresholds(accepted, kind='buildout'):
    """
    Generate meaningful thresholds based on the actual queue.
    For buildout: returns list of dicts with position_threshold, n_projects, queue_mw.
    For lifo: returns list of dicts with my_position, position_label, n_projects_ahead.
    """
    if len(accepted) == 0:
        return []

    sorted_acc = accepted.sort_values('Position')
    positions = sorted_acc['Position'].values
    n_total = len(positions)
    cumulative_mw = sorted_acc['Site Export Capacity (MW)'].cumsum().values

    results = []

    if kind == 'buildout':
        target_counts = set()
        target_counts.add(0)  # no accepted projects (recently connected only)
        if n_total <= 8:
            target_counts.update(range(1, n_total + 1))
        else:
            for frac in [0.2, 0.4, 0.6, 0.8]:
                target_counts.add(max(1, int(n_total * frac)))
            target_counts.add(n_total)

        for count in sorted(target_counts):
            if count == 0:
                results.append({
                    'position_threshold': 0,
                    'n_projects': 0,
                    'queue_mw': 0,
                })
            else:
                idx = min(count - 1, n_total - 1)
                results.append({
                    'position_threshold': int(positions[idx]),
                    'n_projects': count,
                    'queue_mw': round(cumulative_mw[idx]),
                })

    elif kind == 'lifo':
        target_counts = set()
        target_counts.add(1)
        if n_total <= 8:
            target_counts.update(range(1, n_total + 1))
        else:
            for frac in [0.25, 0.5, 0.75]:
                target_counts.add(max(1, int(n_total * frac)))
        target_counts.add(n_total)
        target_counts.add(n_total + 1)  # "last" = behind everyone

        for count in sorted(target_counts):
            if count > n_total:
                results.append({
                    'my_position': 9999,
                    'position_label': 'Last',
                    'n_projects_ahead': n_total,
                })
            else:
                idx = min(count - 1, n_total - 1)
                pos = int(positions[idx])
                results.append({
                    'my_position': pos,
                    'position_label': f'#{pos}',
                    'n_projects_ahead': count - 1,
                })

    return results


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

    data['pel']['branch_key'] = data['pel'].apply(
        lambda r: f"{r['From Bus Number']}_{r['To Bus Number']}_{r['Circuit ID']}", axis=1
    )
    pel_fwd, pel_rev = {}, {}
    for bk, group in data['pel'].groupby('branch_key'):
        fwd, rev = np.zeros(4), np.zeros(4)
        for _, row in group.iterrows():
            idx = season_to_idx.get(row['Season'])
            if idx is not None:
                fwd[idx] = row['Forward PEL MW']
                rev[idx] = row['Reverse PEL MW']
        pel_fwd[bk] = fwd
        pel_rev[bk] = rev
    data['pel_fwd'] = pel_fwd
    data['pel_rev'] = pel_rev

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
                bl[branch_col] = bl[branch_col].values - bus_output * row['Sensitivity Factor MW']
    return bl


def get_sensitive_branches(data, bus_number):
    """Get branches sensitive to a bus, with their data pre-loaded."""
    sf = data['sf']
    branch_col_set = set(data['branch_load'].columns) - {'Half Hour'}

    bus_sf = sf[sf['Node Number'] == bus_number].copy()
    if len(bus_sf) == 0:
        return []
    bus_sf = bus_sf[bus_sf['Sensitivity Factor MW'].abs() >= 0.05].copy()
    if len(bus_sf) == 0:
        return []

    bus_sf['branch_key'] = bus_sf.apply(
        lambda r: f"{r['From Bus Number']}_{r['To Bus Number']}_{r['Circuit ID']}", axis=1
    )
    bus_sf['branch_col'] = bus_sf.apply(
        lambda r: f"{r['From Bus Number']}_{r['To Bus Number']}_{r['Tertiary Bus Number']}_{r['Circuit ID']}", axis=1
    )
    bus_sf = bus_sf[bus_sf['branch_col'].isin(branch_col_set)].copy()
    return bus_sf


def compute_curtailment_simple(data, bus_number, gen_output_array, branch_load):
    """Simple curtailment: new generator is last, gets all curtailment."""
    bus_sf = get_sensitive_branches(data, bus_number)
    if len(bus_sf) == 0:
        return None

    pel_fwd = data['pel_fwd']
    pel_rev = data['pel_rev']
    hsi = data['halfhour_season_idx']
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
        fwd_pel_hh = fwd_pels[hsi]
        rev_pel_hh = rev_pels[hsi]
        new_flow = existing_flow - gen_output_array * sf_val

        # SF is in demand convention. Generator effect = -SF × output.
        # sf_val < 0 → generator pushes positive (forward) flow
        # sf_val > 0 → generator pushes negative (reverse) flow
        if sf_val < 0:
            excess = np.maximum(new_flow - fwd_pel_hh, 0)
            curtail_mw = np.minimum(excess / abs(sf_val), gen_output_array)
        elif sf_val > 0:
            excess = np.maximum(rev_pel_hh - new_flow, 0)
            curtail_mw = np.minimum(excess / sf_val, gen_output_array)
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


def compute_curtailment_lifo(data, bus_number, gen_mw, tech, my_position, branch_load, cq_accepted):
    """
    Proper LIFO: generators behind me (position > my_position) get curtailed
    before I do. My curtailment is only the residual after they've been
    fully curtailed.

    For each branch at each half-hour:
    1. Compute total flow = existing + all queued + my generator
    2. If overloaded, curtail in reverse position order:
       - First curtail generators with highest position (newest)
       - Then next highest, etc.
       - Only curtail me if still overloaded after all behind-me generators are curtailed
    """
    profiles = data['profiles']
    sf = data['sf']
    pel_fwd = data['pel_fwd']
    pel_rev = data['pel_rev']
    hsi = data['halfhour_season_idx']
    n = data['n_halfhours']

    prof_col = {'PV': 'PV', 'Wind': 'Wind', 'BESS': 'BESS Export pu'}.get(tech, 'Other')
    if prof_col not in profiles.columns:
        return None

    my_output = gen_mw * profiles[prof_col].values  # shape (n,)

    bus_sf = get_sensitive_branches(data, bus_number)
    if len(bus_sf) == 0:
        return None

    # Build per-project output arrays for projects BEHIND me (position > my_position)
    # sorted by position descending (highest position = curtailed first)
    behind_me = cq_accepted[cq_accepted['Position'] > my_position].sort_values('Position', ascending=False)

    behind_outputs = []  # list of (bus_number, output_array, position)
    for _, p in behind_me.iterrows():
        p_prof_col = FUEL_TO_PROFILE.get(p['Fuel type'], 'Other')
        if p_prof_col not in profiles.columns:
            continue
        p_output = p['Site Export Capacity (MW)'] * profiles[p_prof_col].values
        behind_outputs.append((p['Bus Number'], p_output, p['Position']))

    # For each branch, compute my curtailment with LIFO ordering
    max_curtail = np.zeros(n)

    for _, row in bus_sf.iterrows():
        sf_val = row['Sensitivity Factor MW']
        branch_col = row['branch_col']
        branch_key = row['branch_key']
        fwd_pels = pel_fwd.get(branch_key)
        rev_pels = pel_rev.get(branch_key)
        if fwd_pels is None or rev_pels is None:
            continue

        fwd_pel_hh = fwd_pels[hsi]
        rev_pel_hh = rev_pels[hsi]

        # Total flow with everything including me
        # SF is demand convention; generator effect = -SF × output
        total_flow = branch_load[branch_col].values - my_output * sf_val

        # Determine excess on this branch
        if sf_val < 0:
            # Generator pushes forward flow
            excess = np.maximum(total_flow - fwd_pel_hh, 0)
        elif sf_val > 0:
            # Generator pushes reverse flow
            excess = np.maximum(rev_pel_hh - total_flow, 0)
        else:
            continue

        # No excess = no curtailment from this branch
        if excess.sum() == 0:
            continue

        # Curtail behind-me generators first (LIFO order)
        remaining_excess = excess.copy()

        for behind_bus, behind_output, behind_pos in behind_outputs:
            # Get this behind-me generator's SF to this branch
            behind_sf_rows = sf[(sf['Node Number'] == behind_bus)]
            behind_sf_match = behind_sf_rows[
                behind_sf_rows.apply(
                    lambda r: f"{r['From Bus Number']}_{r['To Bus Number']}_{r['Circuit ID']}", axis=1
                ) == branch_key
            ]
            if len(behind_sf_match) == 0:
                continue
            behind_sf_val = behind_sf_match.iloc[0]['Sensitivity Factor MW']
            if abs(behind_sf_val) < 0.05:
                continue

            # How much can this behind-me generator reduce the excess?
            # Max it can contribute = its full output × |SF|
            behind_contribution = behind_output * abs(behind_sf_val)
            reduction = np.minimum(remaining_excess, behind_contribution)
            remaining_excess = np.maximum(remaining_excess - reduction, 0)

            if remaining_excess.sum() == 0:
                break

        # My curtailment = whatever excess remains after behind-me generators absorbed
        my_curtail_on_branch = np.minimum(remaining_excess / abs(sf_val), my_output)
        max_curtail = np.maximum(max_curtail, my_curtail_on_branch)

    total_mwh = my_output.sum() / 2
    curtailed_mwh = max_curtail.sum() / 2
    curtailment_pct = 100 * curtailed_mwh / total_mwh if total_mwh > 0 else 0

    return {
        'curtailment_pct': round(curtailment_pct, 2),
        'curtailed_mwh': round(curtailed_mwh),
        'total_mwh': round(total_mwh),
    }


# ============================================================
# MAIN LOOP
# ============================================================
t_start = time.time()
all_lifo = []
all_buildout = []
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

    if len(cq) > 0 and 'Status' in cq.columns and 'Position' in cq.columns:
        recently_connected = cq[cq['Status'] == 'Recently Connected']
        accepted = cq[cq['Status'] == 'Accepted not yet Connected'].sort_values('Position')
        has_queue = True
    else:
        recently_connected = pd.DataFrame()
        accepted = pd.DataFrame()
        has_queue = False

    # Full queue projection for co-location and simple curtailment
    bl_full = project_queue(data, cq) if len(cq) > 0 else data['branch_load'].copy()

    print(f"  {len(bsp_points)} BSPs, {len(cq)} queue projects")

    for bsp_name, bus_num in sorted(bsp_points.items()):

        # ==============================================================
        # PROPER LIFO: What's my curtailment at different queue positions?
        # ==============================================================
        if has_queue and len(accepted) > 0:
            lifo_thresholds = get_smart_thresholds(accepted, kind='lifo')
            for tech in ['PV', 'Wind', 'BESS']:
                for lt in lifo_thresholds:
                    r = compute_curtailment_lifo(
                        data, bus_num, 20, tech, lt['my_position'], bl_full, accepted
                    )
                    all_lifo.append({
                        'substation': bsp_name, 'zone': prefix,
                        'technology': tech,
                        'capacity_mw': 20,
                        'my_position': lt['my_position'],
                        'position_label': lt['position_label'],
                        'n_projects_ahead': lt['n_projects_ahead'],
                        'curtailment_pct': r['curtailment_pct'] if r else None,
                        'curtailed_mwh': r['curtailed_mwh'] if r else None,
                        'total_mwh': r['total_mwh'] if r else None,
                    })

        # ==============================================================
        # QUEUE BUILD-OUT: What if only some projects build?
        # ==============================================================
        if has_queue and len(accepted) > 0:
            buildout_thresholds = get_smart_thresholds(accepted, kind='buildout')
            for bt in buildout_thresholds:
                pos_threshold = bt['position_threshold']
                queue_subset = pd.concat([
                    recently_connected,
                    accepted[accepted['Position'] <= pos_threshold]
                ]) if pos_threshold > 0 else recently_connected.copy()
                queue_mw = queue_subset['Site Export Capacity (MW)'].sum()
                bl_projected = project_queue(data, queue_subset)

                row_result = {
                    'substation': bsp_name, 'zone': prefix,
                    'position_threshold': pos_threshold,
                    'n_projects': bt['n_projects'],
                    'queue_mw': round(queue_mw),
                }
                for tech, prof_col in [('PV', 'PV'), ('Wind', 'Wind'), ('BESS', 'BESS Export pu')]:
                    if prof_col not in profiles.columns:
                        row_result[f'{tech}_curtailment_pct'] = None
                        continue
                    gen_output = 20 * profiles[prof_col].values
                    r = compute_curtailment_simple(data, bus_num, gen_output, bl_projected)
                    row_result[f'{tech}_curtailment_pct'] = r['curtailment_pct'] if r else None
                all_buildout.append(row_result)

        # ==============================================================
        # CO-LOCATION
        # ==============================================================
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
            r = compute_curtailment_simple(data, bus_num, gen_output, bl_full)
            if r:
                all_coloc.append({
                    'substation': bsp_name, 'zone': prefix,
                    'scenario': scenario['name'],
                    'wind_mw': scenario['wind_mw'],
                    'solar_mw': scenario['solar_mw'],
                    'bess_mw': scenario['bess_mw'],
                    'total_mw': total_mw, **r,
                })

    print(f"  Done in {time.time()-t0:.1f}s")


# ============================================================
# SAVE
# ============================================================
df_lifo = pd.DataFrame(all_lifo)
df_buildout = pd.DataFrame(all_buildout)
df_coloc = pd.DataFrame(all_coloc)

lifo_path = os.path.join(MVP_DATA_DIR, 'south_wales_curtailment_lifo.csv')
buildout_path = os.path.join(MVP_DATA_DIR, 'south_wales_curtailment_buildout.csv')
coloc_path = os.path.join(MVP_DATA_DIR, 'south_wales_curtailment_colocation.csv')

df_lifo.to_csv(lifo_path, index=False)
df_buildout.to_csv(buildout_path, index=False)
df_coloc.to_csv(coloc_path, index=False)

print(f"\n\n{'='*60}")
print(f"SUMMARY")
print(f"{'='*60}")
print(f"LIFO (proper): {len(df_lifo)} rows ({df_lifo['substation'].nunique()} substations)")
print(f"Queue build-out: {len(df_buildout)} rows ({df_buildout['substation'].nunique()} substations)")
print(f"Co-location: {len(df_coloc)} rows ({df_coloc['substation'].nunique()} substations)")
print(f"Total time: {time.time()-t_start:.0f}s")

# Show a sample of LIFO results
print(f"\n\nSample LIFO results — 20MW Solar at Swansea West:")
sw_lifo = df_lifo[(df_lifo['substation'] == 'Swansea West') & (df_lifo['technology'] == 'PV')]
if len(sw_lifo) > 0:
    for _, r in sw_lifo.iterrows():
        label = r.get('position_label', f"pos {r['my_position']}")
        ahead = r.get('n_projects_ahead', '?')
        print(f"  {label:>10} ({ahead} projects ahead): {r['curtailment_pct']:.1f}%")

print(f"\nSample LIFO results — 20MW Wind at Swansea West:")
sw_lifo_w = df_lifo[(df_lifo['substation'] == 'Swansea West') & (df_lifo['technology'] == 'Wind')]
if len(sw_lifo_w) > 0:
    for _, r in sw_lifo_w.iterrows():
        label = r.get('position_label', f"pos {r['my_position']}")
        ahead = r.get('n_projects_ahead', '?')
        print(f"  {label:>10} ({ahead} projects ahead): {r['curtailment_pct']:.1f}%")

print(f"\nSample build-out results — 20MW Solar at Swansea West:")
sw_bo = df_buildout[df_buildout['substation'] == 'Swansea West']
if len(sw_bo) > 0:
    for _, r in sw_bo.iterrows():
        n_proj = r.get('n_projects', '?')
        pos = r['position_threshold']
        pos_label = f"≤{pos}" if pos < 9999 else "All"
        print(f"  {n_proj} projects (pos {pos_label}): {r['queue_mw']} MW → Solar {r.get('PV_curtailment_pct', '?')}%")
