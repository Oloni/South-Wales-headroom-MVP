"""
04_seasonal_curtailment.py
==========================
Computes monthly and hourly curtailment breakdowns for each substation.
Uses the same methodology as 02_compute_curtailment.py but disaggregates
by month and hour-of-day to show WHEN curtailment happens.

Output: data/south_wales_curtailment_seasonal.csv

This answers Ian Dunn's question: "What does curtailment look like 
seasonally for different technologies?"
"""

import pandas as pd
import numpy as np
import os
import glob
import time

MVP_DATA_DIR = '/Users/leonie/Documents/South_Wales_headroom_MVP/data'

# ============================================================
# CONFIGURATION
# ============================================================

# Focus on BSPs from the headroom table (the ones customers care about)
# We'll compute seasonal breakdown for 20MW of each technology
TARGET_MW = 20
TECHS = ['PV', 'Wind', 'BESS']

FUEL_TO_PROFILE = {
    'Solar': 'PV', 'Wind': 'Wind', 'BESS': 'BESS Export pu', 'Other': 'Other',
}

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
# MAIN COMPUTATION
# ============================================================

def compute_seasonal_curtailment(prefix, zone_id):
    """
    For each BSP in a zone, compute half-hourly curtailment arrays
    and then aggregate by month and hour-of-day.
    """

    def zpath(filetype):
        pattern = os.path.join(MVP_DATA_DIR, f'{prefix}_{filetype}_id_{zone_id}_2026.csv')
        matches = glob.glob(pattern)
        if not matches:
            pattern2 = os.path.join(MVP_DATA_DIR, f'{prefix}*{filetype}*id_{zone_id}_2026.csv')
            matches = glob.glob(pattern2)
        return matches[0] if matches else None

    sf_path = zpath('sensitivity_factors')
    pel_path = zpath('pre-event_limits') or zpath('pre-event-limits')
    prof_path = zpath('generic_generator_profiles')
    bl_path = zpath('branch_load')
    cq_path = zpath('connection_queue')

    for name, path in [('SF', sf_path), ('PEL', pel_path), ('Profiles', prof_path), ('Branch load', bl_path)]:
        if path is None:
            print(f"  SKIPPING {prefix} — missing {name}")
            return []

    t0 = time.time()
    sf = pd.read_csv(sf_path)
    pel = pd.read_csv(pel_path)
    profiles = pd.read_csv(prof_path)
    branch_load = pd.read_csv(bl_path)
    cq = pd.read_csv(cq_path) if cq_path and os.path.exists(cq_path) else None

    n_halfhours = len(profiles)
    branch_col_set = set(branch_load.columns) - {'Half Hour'}

    # Timestamps for monthly/hourly grouping
    timestamps = pd.to_datetime(profiles['Half Hour'])
    months = timestamps.dt.month.values
    hours = timestamps.dt.hour.values

    # Season mapping for PELs
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

    # Project queue
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

        for bus_num, bus_output in bus_outputs.items():
            bus_sf = sf[sf['Node Number'] == bus_num]
            for _, row in bus_sf.iterrows():
                branch_col = f"{row['From Bus Number']}_{row['To Bus Number']}_{row['Tertiary Bus Number']}_{row['Circuit ID']}"
                if branch_col in branch_load.columns:
                    branch_load[branch_col] = branch_load[branch_col].values - bus_output * row['Sensitivity Factor MW']

    branch_col_set = set(branch_load.columns) - {'Half Hour'}

    # Find BSPs
    all_nodes = sf[['Node Number', 'Node Name']].drop_duplicates()
    bsp_nodes = all_nodes[all_nodes['Node Name'].str.match(r'^[A-Z]{4}3_MAIN1$', na=False)]
    bsp_points = {}
    for _, row in bsp_nodes.iterrows():
        code = row['Node Name'][:4]
        name = CIM_TO_NAME.get(code, code)
        bsp_points[name] = row['Node Number']

    print(f"  {prefix}: {len(bsp_points)} BSPs, loaded in {time.time()-t0:.1f}s")

    # Compute half-hourly curtailment for each BSP × tech
    results = []

    for bsp_name, bus_num in sorted(bsp_points.items()):
        bus_sf = sf[sf['Node Number'] == bus_num].copy()
        if len(bus_sf) == 0:
            continue
        bus_sf = bus_sf[bus_sf['Sensitivity Factor MW'].abs() >= 0.05].copy()
        if len(bus_sf) == 0:
            continue

        bus_sf['branch_key'] = bus_sf.apply(
            lambda r: f"{r['From Bus Number']}_{r['To Bus Number']}_{r['Circuit ID']}", axis=1
        )
        bus_sf['branch_col'] = bus_sf.apply(
            lambda r: f"{r['From Bus Number']}_{r['To Bus Number']}_{r['Tertiary Bus Number']}_{r['Circuit ID']}", axis=1
        )
        bus_sf = bus_sf[bus_sf['branch_col'].isin(branch_col_set)].copy()
        if len(bus_sf) == 0:
            continue

        for tech in TECHS:
            if tech == 'PV':
                profile = profiles['PV'].values
            elif tech == 'Wind':
                profile = profiles['Wind'].values
            elif tech == 'BESS':
                profile = profiles['BESS Export pu'].values
            else:
                continue

            gen_output = TARGET_MW * profile
            max_curtail = np.zeros(n_halfhours)

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
                new_flow = existing_flow - gen_output * sf_val

                # SF is demand convention. Generator effect = -SF × output.
                if sf_val < 0:
                    excess = np.maximum(new_flow - fwd_pel_hh, 0)
                    curtail_mw = np.minimum(excess / abs(sf_val), gen_output)
                elif sf_val > 0:
                    excess = np.maximum(rev_pel_hh - new_flow, 0)
                    curtail_mw = np.minimum(excess / sf_val, gen_output)
                else:
                    continue

                max_curtail = np.maximum(max_curtail, curtail_mw)

            # Now we have max_curtail[t] for every half-hour
            # Aggregate by month and hour

            for month in range(1, 13):
                for hour in range(24):
                    mask = (months == month) & (hours == hour)
                    if mask.sum() == 0:
                        continue

                    gen_in_window = gen_output[mask]
                    curtail_in_window = max_curtail[mask]

                    total_mwh = gen_in_window.sum() / 2
                    curtailed_mwh = curtail_in_window.sum() / 2
                    n_periods = mask.sum()
                    n_curtailed = (curtail_in_window > 0).sum()

                    curtailment_pct = 100 * curtailed_mwh / total_mwh if total_mwh > 0 else 0

                    results.append({
                        'substation': bsp_name,
                        'zone': prefix,
                        'technology': tech,
                        'capacity_mw': TARGET_MW,
                        'month': month,
                        'hour': hour,
                        'total_mwh': round(total_mwh, 1),
                        'curtailed_mwh': round(curtailed_mwh, 1),
                        'curtailment_pct': round(curtailment_pct, 1),
                        'n_periods': n_periods,
                        'n_curtailed': int(n_curtailed),
                    })

    return results


# ============================================================
# RUN ALL ZONES
# ============================================================
t_start = time.time()
all_results = []

for prefix, zone_id in zones:
    zone_results = compute_seasonal_curtailment(prefix, zone_id)
    all_results.extend(zone_results)

df = pd.DataFrame(all_results)


# ============================================================
# DISPLAY: MONTHLY SUMMARY FOR INTERESTING SUBSTATIONS
# ============================================================
print(f"\n{'='*70}")
print(f"MONTHLY CURTAILMENT — 20MW Solar (selected substations)")
print(f"{'='*70}\n")

# Pick substations with non-zero curtailment
solar = df[(df['technology'] == 'PV')]
annual = solar.groupby('substation').agg(
    total=('total_mwh', 'sum'),
    curtailed=('curtailed_mwh', 'sum'),
).reset_index()
annual['pct'] = 100 * annual['curtailed'] / annual['total']
interesting = annual[annual['pct'] > 1].sort_values('pct', ascending=False).head(10)

for _, sub_row in interesting.iterrows():
    sub = sub_row['substation']
    print(f"\n  {sub} (annual: {sub_row['pct']:.1f}% curtailment)")
    print(f"  {'Month':<10} {'Generation':>12} {'Curtailed':>12} {'Curtailment':>12}")
    print(f"  {'-'*48}")

    sub_solar = solar[solar['substation'] == sub]
    monthly = sub_solar.groupby('month').agg(
        total=('total_mwh', 'sum'),
        curtailed=('curtailed_mwh', 'sum'),
    ).reset_index()
    monthly['pct'] = 100 * monthly['curtailed'] / monthly['total']
    monthly['pct'] = monthly['pct'].fillna(0)

    month_names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    for _, m in monthly.iterrows():
        print(f"  {month_names[int(m['month'])]:<10} {m['total']:>10.0f} MWh {m['curtailed']:>10.0f} MWh {m['pct']:>10.1f}%")


# ============================================================
# DISPLAY: HOURLY PATTERN FOR SWANSEA WEST
# ============================================================
print(f"\n\n{'='*70}")
print(f"HOURLY CURTAILMENT PATTERN — 20MW at Swansea West")
print(f"{'='*70}\n")

for tech in TECHS:
    tech_name = {'PV': 'Solar', 'Wind': 'Wind', 'BESS': 'Battery'}[tech]
    sub_data = df[(df['substation'] == 'Swansea West') & (df['technology'] == tech)]
    if len(sub_data) == 0:
        print(f"  {tech_name}: no data")
        continue

    hourly = sub_data.groupby('hour').agg(
        total=('total_mwh', 'sum'),
        curtailed=('curtailed_mwh', 'sum'),
    ).reset_index()
    hourly['pct'] = 100 * hourly['curtailed'] / hourly['total']
    hourly['pct'] = hourly['pct'].fillna(0)

    print(f"  {tech_name}:")
    print(f"  {'Hour':<6} {'Curtailment':>12}")
    print(f"  {'-'*20}")
    for _, h in hourly.iterrows():
        bar = '█' * int(h['pct'] / 2)
        print(f"  {int(h['hour']):02d}:00  {h['pct']:>10.1f}% {bar}")
    print()


# ============================================================
# DISPLAY: TECHNOLOGY COMPARISON
# ============================================================
print(f"\n{'='*70}")
print(f"TECHNOLOGY COMPARISON — 20MW at selected substations")
print(f"{'='*70}\n")

print(f"{'Substation':<22} {'Solar':>8} {'Wind':>8} {'Battery':>8}")
print(f"{'-'*48}")

# Get annual curtailment per tech per substation
tech_annual = df.groupby(['substation', 'technology']).agg(
    total=('total_mwh', 'sum'),
    curtailed=('curtailed_mwh', 'sum'),
).reset_index()
tech_annual['pct'] = 100 * tech_annual['curtailed'] / tech_annual['total']

# Show substations where at least one tech has >1%
for sub in sorted(tech_annual['substation'].unique()):
    sub_data = tech_annual[tech_annual['substation'] == sub]
    if sub_data['pct'].max() < 1:
        continue

    vals = {}
    for tech in TECHS:
        row = sub_data[sub_data['technology'] == tech]
        if len(row) > 0:
            vals[tech] = f"{row.iloc[0]['pct']:.1f}%"
        else:
            vals[tech] = "—"
    print(f"{sub:<22} {vals.get('PV', '—'):>8} {vals.get('Wind', '—'):>8} {vals.get('BESS', '—'):>8}")


# ============================================================
# SAVE
# ============================================================
output_path = os.path.join(MVP_DATA_DIR, 'south_wales_curtailment_seasonal.csv')
df.to_csv(output_path, index=False)
print(f"\n\nSaved {len(df)} rows to {output_path}")
print(f"({df['substation'].nunique()} substations × {len(TECHS)} techs × 12 months × 24 hours)")
print(f"Total time: {time.time()-t_start:.0f}s")
