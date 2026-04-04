"""
09_sf_stability.py
==================
Tests whether NGED's static sensitivity factors are stable over time
by computing implied SFs from actual branch flows and known solar output.

For each branch sensitive to a connected solar generator:
  implied_SF(t) = (actual_flow(t) - demand_baseline) / solar_output(t)

If the static SF is correct, implied_SF should be constant.
Systematic variation with season or generation level indicates breakdown.
"""

import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

MVP_DATA_DIR = '/Users/leonie/Documents/South_Wales_headroom_MVP/data'
ZONE = 'swansea-north'
ZONE_ID = '315'
FUEL_TO_PROFILE = {'Solar': 'PV', 'Wind': 'Wind', 'BESS': 'BESS Export pu', 'Other': 'Other'}

# ── Load data ──────────────────────────────────────────────
sf   = pd.read_csv(f'{MVP_DATA_DIR}/{ZONE}_sensitivity_factors_id_{ZONE_ID}_2026.csv')
bl   = pd.read_csv(f'{MVP_DATA_DIR}/{ZONE}_branch_load_id_{ZONE_ID}_2026.csv')
prof = pd.read_csv(f'{MVP_DATA_DIR}/{ZONE}_generic_generator_profiles_id_{ZONE_ID}_2026.csv')
cq   = pd.read_csv(f'{MVP_DATA_DIR}/{ZONE}_connection_queue_id_{ZONE_ID}_2026.csv')

timestamps = pd.to_datetime(prof['Half Hour'])
months = timestamps.dt.month.values
hours  = timestamps.dt.hour.values
n      = len(prof)

# ── Identify connected solar generators ───────────────────
solar = cq[cq['Fuel type'] == 'Solar'].copy()
print(f"Connected solar generators: {len(solar)}")
for _, g in solar.iterrows():
    print(f"  {g['Site Export Capacity (MW)']:.1f} MW at bus {g['Bus Number']}")

# ── Compute total solar output half-hourly ─────────────────
solar_output = np.zeros(n)
for _, g in solar.iterrows():
    solar_output += g['Site Export Capacity (MW)'] * prof['PV'].values

# Mask: only use half-hours where solar is meaningfully generating
# (avoids division by near-zero at dawn/dusk)
MIN_SOLAR_MW = solar_output.max() * 0.10   # at least 10% of peak
is_solar = solar_output > MIN_SOLAR_MW

# ── Demand baseline: mean nighttime flow per branch ───────
# Night = hours 1-5, no solar, demand-only signal
is_night = (hours >= 1) & (hours <= 5)

# ── Build branch column names ──────────────────────────────
sf['branch_col'] = sf.apply(
    lambda r: f"{r['From Bus Number']}_{r['To Bus Number']}_{r['Tertiary Bus Number']}_{r['Circuit ID']}",
    axis=1
)
sf['branch_key'] = sf.apply(
    lambda r: f"{r['From Bus Number']}_{r['To Bus Number']}_{r['Circuit ID']}",
    axis=1
)
sf['branch_name'] = sf.apply(
    lambda r: f"{r['From Bus Name']}->{r['To Bus Name']}",
    axis=1
)

branch_cols_in_bl = set(bl.columns) - {'Half Hour'}

# ── Find branches sensitive to solar buses ────────────────
solar_buses = set(solar['Bus Number'].unique())
solar_sf = sf[
    sf['Node Number'].isin(solar_buses) &
    (sf['Sensitivity Factor MW'].abs() >= 0.05) &
    sf['branch_col'].isin(branch_cols_in_bl)
].copy()

print(f"\nBranches sensitive to solar generators: {solar_sf['branch_col'].nunique()}")

# ── Core computation ──────────────────────────────────────
results = []

for branch_col, group in solar_sf.groupby('branch_col'):
    branch_name = group.iloc[0]['branch_name']
    
    # Published static SF (sum contributions from all solar buses)
    # Each solar bus may have a different SF to this branch
    # We want the aggregate: total effect = sum(SF_i * output_i) / total_output
    # For simplicity, compute weighted average SF
    total_solar_at_peak = sum(
        g['Site Export Capacity (MW)'] 
        for _, g in solar.iterrows() 
        if g['Bus Number'] in group['Node Number'].values
    )
    
    weighted_sf = 0
    for _, row in group.iterrows():
        bus_mw = solar[solar['Bus Number'] == row['Node Number']]['Site Export Capacity (MW)'].sum()
        weighted_sf += row['Sensitivity Factor MW'] * (bus_mw / total_solar_at_peak if total_solar_at_peak > 0 else 0)
    
    published_sf = weighted_sf
    
    if branch_col not in bl.columns:
        continue
    
    actual_flow = bl[branch_col].values
    
    # Demand baseline: mean nighttime flow
    # Use a rolling monthly baseline to account for seasonal demand variation
    monthly_night_mean = {}
    for month in range(1, 13):
        mask = is_night & (months == month)
        if mask.sum() > 0:
            monthly_night_mean[month] = actual_flow[mask].mean()
        else:
            monthly_night_mean[month] = actual_flow[is_night].mean()
    
    demand_baseline = np.array([monthly_night_mean[m] for m in months])
    
    # Implied SF at each solar half-hour
    # actual_flow = demand_baseline + (-SF * solar_output)
    # => implied_SF = (demand_baseline - actual_flow) / solar_output
    # (negative because SF is demand convention)
    
    gen_effect = demand_baseline - actual_flow   # what the generator is doing to flow
    
    implied_sf = np.where(
        is_solar,
        gen_effect / solar_output,
        np.nan
    )
    
    # Collect results
    for t in range(n):
        if not is_solar[t] or np.isnan(implied_sf[t]):
            continue
        # Filter out physically implausible values (model noise)
        if abs(implied_sf[t]) > 3 * abs(published_sf) + 0.5:
            continue
            
        results.append({
            'branch': branch_name,
            'branch_col': branch_col,
            'published_sf': published_sf,
            'timestamp': timestamps[t],
            'month': months[t],
            'hour': hours[t],
            'solar_output_mw': solar_output[t],
            'actual_flow': actual_flow[t],
            'demand_baseline': demand_baseline[t],
            'implied_sf': implied_sf[t],
            'sf_error': implied_sf[t] - published_sf,
            'sf_error_pct': 100 * (implied_sf[t] - published_sf) / abs(published_sf) if abs(published_sf) > 0.01 else np.nan,
        })

df = pd.DataFrame(results)
print(f"\nComputed {len(df)} implied SF observations across {df['branch'].nunique()} branches")


# ── Summary statistics ─────────────────────────────────────
print(f"\n{'='*70}")
print("SF STABILITY SUMMARY")
print(f"{'='*70}\n")

summary = df.groupby('branch').agg(
    published_sf=('published_sf', 'first'),
    mean_implied=('implied_sf', 'mean'),
    std_implied=('implied_sf', 'std'),
    p5=('implied_sf', lambda x: np.percentile(x, 5)),
    p95=('implied_sf', lambda x: np.percentile(x, 95)),
    n_obs=('implied_sf', 'count'),
).reset_index()

summary['range_p5_p95'] = summary['p95'] - summary['p5']
summary['instability_pct'] = 100 * summary['std_implied'] / summary['published_sf'].abs()

print(f"{'Branch':<40} {'Published SF':>12} {'Mean implied':>12} {'Std':>8} {'P5–P95 range':>14} {'Instability':>12}")
print("-" * 100)
for _, r in summary.sort_values('instability_pct', ascending=False).iterrows():
    print(f"{r['branch']:<40} {r['published_sf']:>12.3f} {r['mean_implied']:>12.3f} "
          f"{r['std_implied']:>8.3f} {r['range_p5_p95']:>14.3f} {r['instability_pct']:>11.0f}%")


# ── Monthly breakdown ──────────────────────────────────────
print(f"\n\n{'='*70}")
print("MONTHLY VARIATION IN IMPLIED SF")
print(f"{'='*70}\n")

month_names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
               'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# Pick the branch with highest instability
top_branch = summary.sort_values('instability_pct', ascending=False).iloc[0]['branch']
top_col    = summary.sort_values('instability_pct', ascending=False).iloc[0]['branch']

branch_df = df[df['branch'] == top_branch]
published  = branch_df['published_sf'].iloc[0]

print(f"Branch: {top_branch}  (published SF = {published:.3f})\n")
print(f"{'Month':<8} {'Mean implied SF':>15} {'Std':>8} {'Deviation from published':>25}")
print("-" * 60)

monthly = branch_df.groupby('month').agg(
    mean=('implied_sf', 'mean'),
    std=('implied_sf', 'std'),
).reset_index()

for _, r in monthly.iterrows():
    deviation = r['mean'] - published
    bar = '█' * int(abs(deviation) / (abs(published) * 0.05 + 0.001))
    sign = '+' if deviation > 0 else '-'
    print(f"{month_names[int(r['month'])]:<8} {r['mean']:>15.3f} {r['std']:>8.3f}   {sign}{abs(deviation):.3f}  {bar}")


# ── Generation-level dependence ───────────────────────────
print(f"\n\n{'='*70}")
print("GENERATION-LEVEL DEPENDENCE (non-linearity test)")
print(f"{'='*70}\n")
print("If SF is truly linear, implied SF should be flat across output levels.")
print(f"Branch: {top_branch}\n")

branch_df = df[df['branch'] == top_branch].copy()
branch_df['solar_bin'] = pd.cut(branch_df['solar_output_mw'], bins=5)

gen_level = branch_df.groupby('solar_bin', observed=True).agg(
    mean_implied=('implied_sf', 'mean'),
    std=('implied_sf', 'std'),
    n=('implied_sf', 'count'),
).reset_index()

print(f"{'Solar output bin':<25} {'Mean implied SF':>15} {'Std':>8} {'N':>6}")
print("-" * 58)
for _, r in gen_level.iterrows():
    print(f"{str(r['solar_bin']):<25} {r['mean_implied']:>15.3f} {r['std']:>8.3f} {r['n']:>6}")


# ── Save ───────────────────────────────────────────────────
output_path = os.path.join(MVP_DATA_DIR, 'sf_stability_analysis.csv')
df.to_csv(output_path, index=False)
print(f"\n\nSaved {len(df)} observations to {output_path}")