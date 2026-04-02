"""
03_validate_curtailment.py
==========================
Runs checks on each step of the curtailment calculation to verify
correctness. Run after 02_compute_curtailment.py.

This script doesn't compute curtailment — it validates that the
computation was done correctly by checking physical plausibility,
internal consistency, and edge cases.
"""

import pandas as pd
import numpy as np
import os
import glob

MVP_DATA_DIR = '/Users/leonie/Documents/South_Wales_headroom_MVP/data'

passed = 0
failed = 0
warnings = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  ✓ {name}")
        passed += 1
    else:
        print(f"  ✗ FAIL: {name}")
        if detail:
            print(f"    {detail}")
        failed += 1

def warn(name, detail=""):
    global warnings
    print(f"  ⚠ WARNING: {name}")
    if detail:
        print(f"    {detail}")
    warnings += 1


# Use Swansea North as the test zone (we know it best)
ZONE_PREFIX = 'swansea-north'
ZONE_ID = '315'

print("=" * 70)
print("CURTAILMENT VALIDATION — Swansea North")
print("=" * 70)


# ============================================================
# CHECK 1: Branch loading data
# ============================================================
print("\n--- CHECK 1: Branch loading data ---\n")

bl = pd.read_csv(os.path.join(MVP_DATA_DIR, f'{ZONE_PREFIX}_branch_load_id_{ZONE_ID}_2026.csv'))
n_hh = len(bl)
n_branches = len(bl.columns) - 1  # minus Half Hour column

check("Branch load has 17,568 half-hours (one year)",
      n_hh == 17568,
      f"Got {n_hh}")

check("Branch load has >100 branches",
      n_branches > 100,
      f"Got {n_branches}")

# Check for NaN
branch_cols = [c for c in bl.columns if c != 'Half Hour']
nan_count = bl[branch_cols].isna().sum().sum()
check("No NaN values in branch loading",
      nan_count == 0,
      f"Found {nan_count} NaN values")

# Check value ranges are plausible (MW should be mostly -500 to +500)
all_vals = bl[branch_cols].values.flatten()
check("Branch flows are in plausible range (-1000 to +1000 MW)",
      np.all((all_vals > -1000) & (all_vals < 1000)),
      f"Range: {all_vals.min():.0f} to {all_vals.max():.0f}")

# Check that flows vary over time (not constant)
sample_branch = branch_cols[0]
std = bl[sample_branch].std()
check(f"Branch flows vary over time (std > 0 for {sample_branch})",
      std > 0,
      f"Std = {std:.4f}")


# ============================================================
# CHECK 2: Connection queue
# ============================================================
print("\n--- CHECK 2: Connection queue ---\n")

cq = pd.read_csv(os.path.join(MVP_DATA_DIR, f'{ZONE_PREFIX}_connection_queue_id_{ZONE_ID}_2026.csv'))

check("Connection queue has projects",
      len(cq) > 0,
      f"Got {len(cq)} projects")

check("All projects have bus numbers",
      cq['Bus Number'].notna().all(),
      f"{cq['Bus Number'].isna().sum()} missing")

check("All projects have MW capacity > 0",
      (cq['Site Export Capacity (MW)'] > 0).all(),
      f"Min: {cq['Site Export Capacity (MW)'].min()}")

check("Total queue is plausible (10-2000 MW)",
      10 < cq['Site Export Capacity (MW)'].sum() < 2000,
      f"Total: {cq['Site Export Capacity (MW)'].sum():.0f} MW")

# Check bus numbers exist in sensitivity factors
sf = pd.read_csv(os.path.join(MVP_DATA_DIR, f'{ZONE_PREFIX}_sensitivity_factors_id_{ZONE_ID}_2026.csv'))
sf_buses = set(sf['Node Number'].unique())
cq_buses_matched = sum(1 for b in cq['Bus Number'] if b in sf_buses)
check("All queue bus numbers found in sensitivity factors",
      cq_buses_matched == len(cq),
      f"{cq_buses_matched}/{len(cq)} matched")


# ============================================================
# CHECK 3: Sensitivity factors
# ============================================================
print("\n--- CHECK 3: Sensitivity factors ---\n")

check("Sensitivity factors loaded",
      len(sf) > 0,
      f"{len(sf)} rows")

# Check value range
sf_vals = sf['Sensitivity Factor MW'].values
check("Sensitivity factors mostly in range [-1.5, 1.5]",
      np.percentile(np.abs(sf_vals), 99) < 1.5,
      f"99th percentile of |SF|: {np.percentile(np.abs(sf_vals), 99):.3f}")

# Check that BSP transformer has high SF from its own busbar
# SWAN3_MAIN1 (bus 547200) should have SF close to 1 for the SWAN3 transformer branch
swan_sf = sf[sf['Node Number'] == 547200]
if len(swan_sf) > 0:
    max_sf = swan_sf['Sensitivity Factor MW'].abs().max()
    check("Swansea North busbar has high SF to at least one branch (>0.2)",
          max_sf > 0.2,
          f"Max |SF| from SWAN3_MAIN1: {max_sf:.3f}")
else:
    warn("Could not find SWAN3_MAIN1 (bus 547200) in sensitivity factors")

# Check that remote buses have smaller SF
rhos_sf = sf[sf['Node Number'] == 574500]  # RHOS3_MAIN1
if len(rhos_sf) > 0:
    # Rhos should have high SF to Rhos transformer, lower to Swansea branches
    rhos_max = rhos_sf['Sensitivity Factor MW'].abs().max()
    check("Rhos busbar has sensitivity factors",
          rhos_max > 0,
          f"Max |SF|: {rhos_max:.3f}")


# ============================================================
# CHECK 4: Pre-event limits
# ============================================================
print("\n--- CHECK 4: Pre-event limits ---\n")

pel = pd.read_csv(os.path.join(MVP_DATA_DIR, f'{ZONE_PREFIX}_pre-event_limits_id_{ZONE_ID}_2026.csv'))

check("PEL data loaded",
      len(pel) > 0,
      f"{len(pel)} rows")

# Check seasons
seasons_found = set(pel['Season'].unique())
expected_seasons = {'Winter', 'Intermediate Cool', 'Intermediate Warm', 'Summer'}
check("All four seasons present in PELs",
      expected_seasons.issubset(seasons_found),
      f"Found: {seasons_found}")

# Check that forward PEL is positive and reverse PEL is negative
winter_pel = pel[pel['Season'] == 'Winter']
check("Forward PELs are positive",
      (winter_pel['Forward PEL MW'] > 0).all(),
      f"Min forward PEL: {winter_pel['Forward PEL MW'].min():.1f}")

check("Reverse PELs are negative",
      (winter_pel['Reverse PEL MW'] < 0).all(),
      f"Max reverse PEL: {winter_pel['Reverse PEL MW'].max():.1f}")

# Check seasonal variation (summer should generally be lower than winter)
winter_fwd = pel[pel['Season'] == 'Winter']['Forward PEL MW'].mean()
summer_fwd = pel[pel['Season'] == 'Summer']['Forward PEL MW'].mean()
check("Summer PELs are <= Winter PELs on average (thermal derating)",
      summer_fwd <= winter_fwd * 1.05,  # allow 5% tolerance
      f"Winter avg: {winter_fwd:.1f}, Summer avg: {summer_fwd:.1f}")


# ============================================================
# CHECK 5: Generic generator profiles
# ============================================================
print("\n--- CHECK 5: Generic generator profiles ---\n")

profiles = pd.read_csv(os.path.join(MVP_DATA_DIR, f'{ZONE_PREFIX}_generic_generator_profiles_id_{ZONE_ID}_2026.csv'))

check("Profiles have 17,568 half-hours",
      len(profiles) == 17568,
      f"Got {len(profiles)}")

# Solar should be 0 at night
# Find midnight rows (00:00-05:00 in winter)
timestamps = pd.to_datetime(profiles['Half Hour'])
night_mask = (timestamps.dt.hour < 5) & (timestamps.dt.month == 1)
solar_at_night = profiles.loc[night_mask, 'PV'].values
check("Solar output is 0 at night (Jan midnight-5am)",
      np.all(solar_at_night == 0),
      f"Max solar at night: {solar_at_night.max():.4f}")

# Solar should be >0 during summer midday
summer_noon = (timestamps.dt.hour == 12) & (timestamps.dt.month == 6)
solar_at_noon = profiles.loc[summer_noon, 'PV'].values
check("Solar output is >0 at summer midday",
      np.all(solar_at_noon > 0),
      f"Min solar at June noon: {solar_at_noon.min():.4f}")

# Wind should be >0 at various times (not always 0)
check("Wind has non-zero output",
      profiles['Wind'].sum() > 0,
      f"Annual sum: {profiles['Wind'].sum():.0f}")

# All profiles should be between 0 and 1 (per-unit)
for col in ['PV', 'Wind']:
    vals = profiles[col].values
    check(f"{col} profile is between 0 and 1",
          np.all((vals >= 0) & (vals <= 1.001)),
          f"Range: {vals.min():.4f} to {vals.max():.4f}")

# Check capacity factors are plausible
solar_cf = profiles['PV'].mean()
wind_cf = profiles['Wind'].mean()
check(f"Solar capacity factor is plausible (10-20%): {solar_cf:.1%}",
      0.08 < solar_cf < 0.22)
check(f"Wind capacity factor is plausible (20-35%): {wind_cf:.1%}",
      0.15 < wind_cf < 0.40)


# ============================================================
# CHECK 6: Queue projection
# ============================================================
print("\n--- CHECK 6: Queue projection onto branch loads ---\n")

# Reload branch load WITHOUT queue projection
bl_original = pd.read_csv(os.path.join(MVP_DATA_DIR, f'{ZONE_PREFIX}_branch_load_id_{ZONE_ID}_2026.csv'))

# Project queue manually and compare
FUEL_TO_PROFILE = {'Solar': 'PV', 'Wind': 'Wind', 'BESS': 'BESS Export pu', 'Other': 'Other'}

bus_outputs = {}
for _, p in cq.iterrows():
    prof_col = FUEL_TO_PROFILE.get(p['Fuel type'], 'Other')
    if prof_col not in profiles.columns:
        continue
    output = p['Site Export Capacity (MW)'] * profiles[prof_col].values
    bus = p['Bus Number']
    if bus not in bus_outputs:
        bus_outputs[bus] = np.zeros(17568)
    bus_outputs[bus] += output

# Pick a branch we know is affected: SWAW transformer
# SWAW1_MAIN1 (bus 554000) has 44MW solar + 44MW BESS queued
swaw_bus = 554000
swaw_sf_rows = sf[sf['Node Number'] == swaw_bus]

if len(swaw_sf_rows) > 0 and swaw_bus in bus_outputs:
    # Find a branch with high sensitivity from SWAW
    top_branch = swaw_sf_rows.loc[swaw_sf_rows['Sensitivity Factor MW'].abs().idxmax()]
    branch_col = f"{top_branch['From Bus Number']}_{top_branch['To Bus Number']}_{top_branch['Tertiary Bus Number']}_{top_branch['Circuit ID']}"
    
    if branch_col in bl_original.columns:
        original_peak = bl_original[branch_col].max()
        
        # Compute what the projected peak should be
        # SF is demand convention; generator effect = -SF × output
        addition = -bus_outputs[swaw_bus] * top_branch['Sensitivity Factor MW']
        projected = bl_original[branch_col].values + addition
        projected_peak = projected.max()
        
        check(f"Queue projection increases peak flow on SWAW branch",
              abs(projected_peak) > abs(original_peak),
              f"Original peak: {original_peak:.1f}, Projected peak: {projected_peak:.1f}")
        
        check("Queue addition is non-trivial (>1 MW peak change)",
              abs(projected_peak - original_peak) > 1,
              f"Peak change: {abs(projected_peak - original_peak):.1f} MW")
    else:
        warn(f"Branch column {branch_col} not found in branch load file")
else:
    warn("Could not test SWAW queue projection")


# ============================================================
# CHECK 7: Curtailment output consistency
# ============================================================
print("\n--- CHECK 7: Curtailment output consistency ---\n")

curt = pd.read_csv(os.path.join(MVP_DATA_DIR, 'south_wales_curtailment.csv'))

check("Curtailment output file exists and has data",
      len(curt) > 0,
      f"{len(curt)} rows")

# Filter to Swansea North
sw_curt = curt[curt['zone'].str.contains('swansea', case=False, na=False)]
check("Swansea North results present",
      len(sw_curt) > 0,
      f"{len(sw_curt)} rows")

# Curtailment should be between 0% and 100%
valid_curt = curt[curt['curtailment_pct'].notna()]
check("All curtailment values are between 0% and 100%",
      (valid_curt['curtailment_pct'] >= 0).all() and (valid_curt['curtailment_pct'] <= 100.1).all(),
      f"Range: {valid_curt['curtailment_pct'].min():.1f}% to {valid_curt['curtailment_pct'].max():.1f}%")

# Curtailed MWh should not exceed total MWh
check("Curtailed MWh never exceeds total MWh",
      (valid_curt['curtailed_mwh'] <= valid_curt['total_mwh'] + 1).all(),
      "Some curtailed > total!")

# Delivered = total - curtailed
check("Delivered MWh = total - curtailed (within rounding)",
      np.allclose(
          valid_curt['delivered_mwh'].values,
          valid_curt['total_mwh'].values - valid_curt['curtailed_mwh'].values,
          atol=2
      ))

# Monotonicity: curtailment % should increase with MW for same substation/tech
print("\n  Monotonicity checks (curtailment should increase with MW):")
violations = 0
for sub in curt['substation'].unique():
    for tech in ['PV', 'Wind', 'BESS']:
        rows = curt[
            (curt['substation'] == sub) &
            (curt['technology'] == tech) &
            (curt['curtailment_pct'].notna())
        ].sort_values('capacity_mw')
        
        if len(rows) < 2:
            continue
        
        pcts = rows['curtailment_pct'].values
        for i in range(1, len(pcts)):
            if pcts[i] < pcts[i-1] - 0.1:  # allow tiny rounding tolerance
                violations += 1
                if violations <= 3:
                    warn(f"Non-monotonic: {sub} {tech} — {rows['capacity_mw'].values[i-1]}MW={pcts[i-1]:.1f}% > {rows['capacity_mw'].values[i]}MW={pcts[i]:.1f}%")

check(f"Curtailment is monotonically increasing with MW (violations: {violations})",
      violations == 0)


# ============================================================
# CHECK 8: Edge cases
# ============================================================
print("\n--- CHECK 8: Edge cases ---\n")

# Substations with 0% at all sizes should have 'None' as binding branch
zero_all = curt.groupby(['substation', 'technology']).agg(
    max_curt=('curtailment_pct', 'max')
).reset_index()
zero_subs = zero_all[zero_all['max_curt'] == 0]
if len(zero_subs) > 0:
    sample = curt[
        (curt['substation'] == zero_subs.iloc[0]['substation']) &
        (curt['technology'] == zero_subs.iloc[0]['technology']) &
        (curt['capacity_mw'] == 50)
    ]
    if len(sample) > 0:
        check("0% curtailment substations have 'None' binding branch",
              sample.iloc[0]['binding_branch'] == 'None')

# Total MWh should scale linearly with MW (same tech, same substation)
# 20MW solar should have ~2x the total_mwh of 10MW solar
for sub in ['Swansea North', 'Rhos', 'Hirwaun']:
    t10 = curt[(curt['substation'] == sub) & (curt['technology'] == 'PV') & (curt['capacity_mw'] == 10)]
    t20 = curt[(curt['substation'] == sub) & (curt['technology'] == 'PV') & (curt['capacity_mw'] == 20)]
    if len(t10) > 0 and len(t20) > 0:
        if pd.notna(t10.iloc[0]['total_mwh']) and pd.notna(t20.iloc[0]['total_mwh']):
            ratio = t20.iloc[0]['total_mwh'] / t10.iloc[0]['total_mwh']
            check(f"Total MWh scales with MW at {sub} (20MW/10MW ratio ≈ 2.0)",
                  1.95 < ratio < 2.05,
                  f"Ratio: {ratio:.3f}")


# ============================================================
# CHECK 9: Cross-check against headroom table
# ============================================================
print("\n--- CHECK 9: Cross-check with headroom table ---\n")

subs = pd.read_csv(os.path.join(MVP_DATA_DIR, 'south_wales_substations.csv'))

# Substations that are heavily overcommitted should generally show higher curtailment
overcommitted = subs[subs['headroom_mva'] < -50]['display_name'].tolist()
if overcommitted:
    for sub in overcommitted[:3]:
        curt_row = curt[
            (curt['substation'] == sub) &
            (curt['technology'] == 'PV') &
            (curt['capacity_mw'] == 20)
        ]
        if len(curt_row) > 0 and pd.notna(curt_row.iloc[0]['curtailment_pct']):
            pct = curt_row.iloc[0]['curtailment_pct']
            # Overcommitted substations MIGHT still show low curtailment because
            # the branch load file reflects today's network (less loaded than the
            # queue suggests). This is a known limitation.
            if pct > 1:
                print(f"  ✓ {sub} (heavily overcommitted): {pct:.1f}% curtailment — consistent")
            else:
                warn(f"{sub} is overcommitted but shows {pct:.1f}% curtailment",
                     "This may be because the branch load data is from 2024 "
                     "and the queue hasn't built out yet, OR because the BSP-level "
                     "overcommitment doesn't translate to branch-level overload "
                     "(different data granularity)")


# ============================================================
# SUMMARY
# ============================================================
print(f"\n{'='*70}")
print(f"VALIDATION SUMMARY")
print(f"{'='*70}")
print(f"  Passed:   {passed}")
print(f"  Failed:   {failed}")
print(f"  Warnings: {warnings}")

if failed == 0:
    print("\n  All checks passed. ✓")
else:
    print(f"\n  {failed} checks failed — review the issues above.")

if warnings > 0:
    print(f"  {warnings} warnings — worth investigating but not necessarily errors.")
