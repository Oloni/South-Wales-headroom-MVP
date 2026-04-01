"""
06_model_vs_reality.py (v2 — all zones)
========================================
Compare planning model predictions against SCADA measurements
across all zones with connected generators.

Uses the night-vs-day method: nighttime flow is demand-only,
daytime increment should match SF × gen_output. Residuals
reveal where the planning model breaks down.

Output:
  - data/model_vs_reality_residuals.csv
"""

import pandas as pd
import numpy as np
import os
import glob
import time

MVP_DATA_DIR = '/Users/leonie/Documents/South_Wales_headroom_MVP/data'
FUEL_TO_PROFILE = {'Solar': 'PV', 'Wind': 'Wind', 'BESS': 'BESS Export pu', 'Other': 'Other'}


# ============================================================
# FIND ZONES WITH CONNECTED GENERATORS
# ============================================================
print("Scanning zones for connected generators...\n")

zones_to_process = []
for f in sorted(glob.glob(os.path.join(MVP_DATA_DIR, '*_connection_queue_id_*_2026.csv'))):
    cq = pd.read_csv(f)
    connected = cq[cq['Status'] == 'Recently Connected']
    if len(connected) > 0:
        basename = os.path.basename(f)
        prefix = basename.split('_connection_queue')[0]
        zone_id = basename.split('_id_')[1].replace('_2026.csv', '')
        total_mw = connected['Site Export Capacity (MW)'].sum()
        zones_to_process.append((prefix, zone_id))
        print(f"  {prefix} (id={zone_id}): {len(connected)} generators, {total_mw:.0f} MW")

print(f"\n{len(zones_to_process)} zones to analyse\n")

t_start = time.time()
all_analysis1_results = []
all_hourly_results = []
all_branch_stats = []


# ============================================================
# PROCESS EACH ZONE
# ============================================================
for zone_prefix, zone_id in zones_to_process:
    print(f"\n{'='*70}")
    print(f"ZONE: {zone_prefix} (id={zone_id})")
    print(f"{'='*70}")

    # Load data
    sf = pd.read_csv(os.path.join(MVP_DATA_DIR, f'{zone_prefix}_sensitivity_factors_id_{zone_id}_2026.csv'))
    profiles = pd.read_csv(os.path.join(MVP_DATA_DIR, f'{zone_prefix}_generic_generator_profiles_id_{zone_id}_2026.csv'))
    branch_load = pd.read_csv(os.path.join(MVP_DATA_DIR, f'{zone_prefix}_branch_load_id_{zone_id}_2026.csv'))
    cq = pd.read_csv(os.path.join(MVP_DATA_DIR, f'{zone_prefix}_connection_queue_id_{zone_id}_2026.csv'))

    timestamps = pd.to_datetime(profiles['Half Hour'])
    n = len(profiles)
    hours = timestamps.dt.hour.values

    connected = cq[cq['Status'] == 'Recently Connected'].copy()
    print(f"  {len(connected)} connected generators, {len(branch_load.columns)-1} branches, {n} half-hours")

    for _, g in connected.iterrows():
        prof_col = FUEL_TO_PROFILE.get(g['Fuel type'], 'Other')
        print(f"    {g['Site Export Capacity (MW)']:6.1f} MW {g['Fuel type']:<8} at bus {g['Bus Number']}")

    # Build branch column names
    sf['branch_col'] = sf.apply(
        lambda r: f"{r['From Bus Number']}_{r['To Bus Number']}_{r['Tertiary Bus Number']}_{r['Circuit ID']}", axis=1
    )
    branch_cols_in_bl = set(branch_load.columns) - {'Half Hour'}

    # Compute per-generator half-hourly output
    gen_outputs = {}
    for _, g in connected.iterrows():
        bus = g['Bus Number']
        mw = g['Site Export Capacity (MW)']
        prof_col = FUEL_TO_PROFILE.get(g['Fuel type'], 'Other')
        if prof_col not in profiles.columns:
            continue
        output = mw * profiles[prof_col].values
        if bus not in gen_outputs:
            gen_outputs[bus] = np.zeros(n)
        gen_outputs[bus] += output

    # Compute model contribution on each branch
    gen_buses = set(gen_outputs.keys())
    gen_sf = sf[sf['Node Number'].isin(gen_buses)].copy()
    gen_sf = gen_sf[gen_sf['branch_col'].isin(branch_cols_in_bl)]

    model_contribution = {}
    for branch_col, group in gen_sf.groupby('branch_col'):
        contrib = np.zeros(n)
        for _, row in group.iterrows():
            bus = row['Node Number']
            sf_val = row['Sensitivity Factor MW']
            if bus in gen_outputs:
                contrib += gen_outputs[bus] * sf_val
        model_contribution[branch_col] = contrib

    print(f"  Model contributions computed for {len(model_contribution)} branches")

    # Identify night/day based on solar (if any solar connected)
    has_solar = any(g['Fuel type'] == 'Solar' for _, g in connected.iterrows())

    if has_solar:
        solar_output = np.zeros(n)
        for _, g in connected[connected['Fuel type'] == 'Solar'].iterrows():
            solar_output += g['Site Export Capacity (MW)'] * profiles['PV'].values
        is_night = solar_output == 0
        is_day = solar_output > 0
        gen_type_label = "solar"
    else:
        # Use "Other" generators — they run flat, so use low-output hours
        # For wind: use calm periods (bottom 20% of wind output)
        wind_output = np.zeros(n)
        other_output = np.zeros(n)
        for _, g in connected.iterrows():
            prof_col = FUEL_TO_PROFILE.get(g['Fuel type'], 'Other')
            if prof_col in profiles.columns:
                if g['Fuel type'] == 'Wind':
                    wind_output += g['Site Export Capacity (MW)'] * profiles[prof_col].values
                else:
                    other_output += g['Site Export Capacity (MW)'] * profiles[prof_col].values

        total_gen = wind_output + other_output
        # For "Other" (flat profile), generation is always on
        # Use hour-of-day demand variation instead: compare peak hours vs off-peak
        # Night = 01:00-05:00, Day = 08:00-20:00
        is_night = (hours >= 1) & (hours <= 5)
        is_day = (hours >= 8) & (hours <= 20)
        gen_type_label = "all generation"

    n_night = is_night.sum()
    n_day = is_day.sum()
    print(f"  Night half-hours: {n_night}, Day half-hours: {n_day}")

    # Get branches sensitive to connected generators
    solar_buses = set(connected['Bus Number'].unique())
    sensitive_sf = sf[sf['Node Number'].isin(solar_buses)]
    sensitive_sf = sensitive_sf[sensitive_sf['Sensitivity Factor MW'].abs() >= 0.05]
    sensitive_sf = sensitive_sf[sensitive_sf['branch_col'].isin(branch_cols_in_bl)]
    sensitive_branches = sensitive_sf['branch_col'].unique()

    print(f"  Branches sensitive to connected generators: {len(sensitive_branches)}")

    # ---- ANALYSIS 1: Night vs day residuals ----
    for branch_col in sensitive_branches:
        if branch_col not in branch_load.columns:
            continue

        actual = branch_load[branch_col].values
        predicted_contrib = model_contribution.get(branch_col, np.zeros(n))

        mean_night = actual[is_night].mean()
        mean_day = actual[is_day].mean()
        mean_predicted_day = predicted_contrib[is_day].mean()
        expected_day = mean_night + mean_predicted_day
        residual = mean_day - expected_day

        branch_sf_rows = sf[sf['branch_col'] == branch_col].iloc[0]
        branch_name = f"{branch_sf_rows['From Bus Name']}->{branch_sf_rows['To Bus Name']}"

        all_analysis1_results.append({
            'zone': zone_prefix,
            'branch': branch_name,
            'branch_col': branch_col,
            'mean_night_flow': mean_night,
            'mean_day_flow': mean_day,
            'predicted_gen_effect': mean_predicted_day,
            'expected_day_flow': expected_day,
            'residual_mw': residual,
            'residual_pct_of_gen': 100 * residual / mean_predicted_day if abs(mean_predicted_day) > 0.1 else None,
        })

    # ---- ANALYSIS 2: Overall branch stats with residuals ----
    for branch_col, predicted_contrib in model_contribution.items():
        if branch_col not in branch_load.columns:
            continue
        if np.abs(predicted_contrib).max() < 0.1:
            continue

        actual = branch_load[branch_col].values
        night_mean = actual[is_night].mean()

        day_mask = is_day
        residuals_arr = actual[day_mask] - (night_mean + predicted_contrib[day_mask])

        branch_sf_rows = sf[sf['branch_col'] == branch_col].iloc[0]
        branch_name = f"{branch_sf_rows['From Bus Name']}->{branch_sf_rows['To Bus Name']}"

        all_branch_stats.append({
            'zone': zone_prefix,
            'branch': branch_name,
            'mean_residual_mw': residuals_arr.mean(),
            'std_residual_mw': residuals_arr.std(),
            'p5_residual': np.percentile(residuals_arr, 5),
            'p95_residual': np.percentile(residuals_arr, 95),
            'max_abs_residual': np.abs(residuals_arr).max(),
            'mean_gen_contribution': np.abs(predicted_contrib[day_mask]).mean(),
        })

    # ---- ANALYSIS 3: Hourly pattern for top residual branches ----
    zone_a1 = [r for r in all_analysis1_results if r['zone'] == zone_prefix]
    if zone_a1:
        sorted_a1 = sorted(zone_a1, key=lambda r: abs(r.get('residual_mw', 0)), reverse=True)
        top_branches = [r['branch_col'] for r in sorted_a1[:3]]

        for branch_col in top_branches:
            if branch_col not in branch_load.columns:
                continue

            actual = branch_load[branch_col].values
            predicted_contrib = model_contribution.get(branch_col, np.zeros(n))

            branch_sf_rows = sf[sf['branch_col'] == branch_col].iloc[0]
            branch_name = f"{branch_sf_rows['From Bus Name']}->{branch_sf_rows['To Bus Name']}"

            print(f"\n  Hourly pattern: {branch_name}")
            print(f"  {'Hour':>6} {'Actual':>10} {'Expected':>10} {'Residual':>10}")
            print(f"  {'-'*40}")

            for h in range(24):
                mask = hours == h
                act = actual[mask].mean()
                pred = predicted_contrib[mask].mean()
                night_mask = is_night & mask
                if night_mask.sum() > 0:
                    demand_proxy = actual[night_mask].mean()
                else:
                    demand_proxy = actual[is_night].mean()
                expected = demand_proxy + pred
                res = act - expected
                print(f"  {h:>6} {act:>10.1f} {expected:>10.1f} {res:>10.1f}")


# ============================================================
# COMBINE AND SAVE
# ============================================================
df_stats = pd.DataFrame(all_branch_stats)
if len(df_stats) > 0:
    df_stats['relative_error_pct'] = 100 * df_stats['mean_residual_mw'].abs() / df_stats['mean_gen_contribution'].clip(lower=0.1)
    df_stats = df_stats.sort_values('max_abs_residual', ascending=False)

output_path = os.path.join(MVP_DATA_DIR, 'model_vs_reality_residuals.csv')
df_stats.to_csv(output_path, index=False)

print(f"\n\n{'='*70}")
print(f"SUMMARY ACROSS ALL ZONES")
print(f"{'='*70}")
print(f"Zones analysed: {len(zones_to_process)}")
print(f"Branches with residuals: {len(df_stats)}")
print(f"Saved to {output_path}")

if len(df_stats) > 0:
    print(f"\n{'Branch':<40} {'Zone':<25} {'Mean Res':>10} {'Max |Res|':>10} {'Rel Err%':>10}")
    print("-" * 100)
    for _, r in df_stats.head(25).iterrows():
        print(f"{r['branch']:<40} {r['zone']:<25} {r['mean_residual_mw']:>10.1f} {r['max_abs_residual']:>10.1f} {r['relative_error_pct']:>9.0f}%")

print(f"\nTotal time: {time.time()-t_start:.0f}s")
