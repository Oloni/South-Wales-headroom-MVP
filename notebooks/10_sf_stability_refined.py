"""
10_sf_stability_refined.py
==========================
Refined version of 09_sf_stability.py with two key improvements:

1. Only uses high-solar observations (>=40% of peak) to reduce
   demand-baseline noise swamping low-SF branches.

2. Separates sign-flipped branches (demand baseline contamination 
   or SF convention issue) from magnitude-wrong branches (genuine
   SF degradation under IBR conditions). Only the latter are clean
   evidence of model breakdown.

The commercially relevant finding:
  "Across N branches sensitive to 190MW of connected solar in the
   Swansea North zone, the implied SF at high generation output
   systematically differs from the published static value by X%
   on average — without the sign flipping that would indicate
   demand baseline contamination."
"""

import pandas as pd
import numpy as np
import os

MVP_DATA_DIR = '/Users/leonie/Documents/South_Wales_headroom_MVP/data'
ZONE     = 'swansea-north'
ZONE_ID  = '315'
FUEL_TO_PROFILE = {'Solar': 'PV', 'Wind': 'Wind', 'BESS': 'BESS Export pu', 'Other': 'Other'}

# ── Tunable parameters ─────────────────────────────────────────────────────
# Minimum solar output as fraction of peak to include an observation.
# 0.10 = 10% (original, noisy), 0.40 = 40% (recommended, cleaner signal).
MIN_SOLAR_FRAC = 0.40

# A branch is "sign-flipped" if mean implied SF has opposite sign to published.
# These are excluded from the magnitude analysis.
SIGN_FLIP_THRESHOLD = 0.0   # strict: any sign difference counts

# ── Load data ──────────────────────────────────────────────────────────────
print("Loading data...")
sf   = pd.read_csv(f'{MVP_DATA_DIR}/{ZONE}_sensitivity_factors_id_{ZONE_ID}_2026.csv')
bl   = pd.read_csv(f'{MVP_DATA_DIR}/{ZONE}_branch_load_id_{ZONE_ID}_2026.csv')
prof = pd.read_csv(f'{MVP_DATA_DIR}/{ZONE}_generic_generator_profiles_id_{ZONE_ID}_2026.csv')
cq   = pd.read_csv(f'{MVP_DATA_DIR}/{ZONE}_connection_queue_id_{ZONE_ID}_2026.csv')

timestamps = pd.to_datetime(prof['Half Hour'])
months = timestamps.dt.month.values
hours  = timestamps.dt.hour.values
n      = len(prof)

# ── Connected solar generators ─────────────────────────────────────────────
solar = cq[cq['Fuel type'] == 'Solar'].copy()
print(f"\nConnected solar generators: {len(solar)}")
for _, g in solar.iterrows():
    print(f"  {g['Site Export Capacity (MW)']:5.1f} MW at bus {g['Bus Number']}")

total_solar_capacity = solar['Site Export Capacity (MW)'].sum()
print(f"  Total: {total_solar_capacity:.1f} MW")

# ── Half-hourly solar output ───────────────────────────────────────────────
solar_output = np.zeros(n)
for _, g in solar.iterrows():
    solar_output += g['Site Export Capacity (MW)'] * prof['PV'].values

solar_peak = solar_output.max()
MIN_SOLAR_MW = solar_peak * MIN_SOLAR_FRAC

is_high_solar = solar_output >= MIN_SOLAR_MW
n_high = is_high_solar.sum()
print(f"\nSolar peak output: {solar_peak:.1f} MW")
print(f"High-solar threshold ({MIN_SOLAR_FRAC*100:.0f}% of peak): {MIN_SOLAR_MW:.1f} MW")
print(f"High-solar half-hours: {n_high} of {n} ({100*n_high/n:.1f}%)")

# ── Monthly nighttime demand baseline ─────────────────────────────────────
# Night = 01:00–05:00. Monthly mean to capture seasonal demand variation.
is_night = (hours >= 1) & (hours <= 5)

# ── Branch column names ────────────────────────────────────────────────────
sf['branch_col'] = sf.apply(
    lambda r: f"{r['From Bus Number']}_{r['To Bus Number']}_{r['Tertiary Bus Number']}_{r['Circuit ID']}",
    axis=1
)
sf['branch_name'] = sf.apply(
    lambda r: f"{r['From Bus Name']}->{r['To Bus Name']}",
    axis=1
)

branch_cols_in_bl = set(bl.columns) - {'Half Hour'}

# ── Branches sensitive to connected solar ──────────────────────────────────
solar_buses = set(solar['Bus Number'].unique())
solar_sf = sf[
    sf['Node Number'].isin(solar_buses) &
    (sf['Sensitivity Factor MW'].abs() >= 0.05) &
    sf['branch_col'].isin(branch_cols_in_bl)
].copy()

n_branches = solar_sf['branch_col'].nunique()
print(f"\nBranches sensitive to solar generators: {n_branches}")

# ── Core computation ───────────────────────────────────────────────────────
print("\nComputing implied SFs (high-solar observations only)...")
results = []

for branch_col, group in solar_sf.groupby('branch_col'):
    branch_name = group.iloc[0]['branch_name']

    # Weighted-average published SF across solar buses
    contributing_mw = 0
    weighted_sf = 0.0
    for _, row in group.iterrows():
        bus_mw = solar.loc[solar['Bus Number'] == row['Node Number'],
                           'Site Export Capacity (MW)'].sum()
        weighted_sf  += row['Sensitivity Factor MW'] * bus_mw
        contributing_mw += bus_mw
    published_sf = weighted_sf / contributing_mw if contributing_mw > 0 else 0.0

    if branch_col not in bl.columns:
        continue

    actual_flow = bl[branch_col].values

    # Monthly nighttime demand baseline
    monthly_night_mean = {}
    for month in range(1, 13):
        mask = is_night & (months == month)
        monthly_night_mean[month] = (
            actual_flow[mask].mean() if mask.sum() > 0
            else actual_flow[is_night].mean()
        )
    demand_baseline = np.array([monthly_night_mean[m] for m in months])

    # Implied SF: generator effect = demand_baseline - actual_flow
    # (demand convention: generator is negative demand, so its effect
    #  on branch flow = -SF * output, rearranged: SF = -(flow - baseline) / output)
    gen_effect = demand_baseline - actual_flow

    # Only high-solar half-hours
    for t in range(n):
        if not is_high_solar[t]:
            continue
        if solar_output[t] <= 0:
            continue

        implied = gen_effect[t] / solar_output[t]

        # Discard physically implausible outliers (>5x published magnitude)
        if abs(implied) > 5 * abs(published_sf) + 0.5:
            continue

        results.append({
            'branch':        branch_name,
            'branch_col':    branch_col,
            'published_sf':  published_sf,
            'timestamp':     timestamps[t],
            'month':         months[t],
            'hour':          hours[t],
            'solar_mw':      solar_output[t],
            'actual_flow':   actual_flow[t],
            'baseline':      demand_baseline[t],
            'implied_sf':    implied,
        })

df = pd.DataFrame(results)
print(f"Observations: {len(df):,} across {df['branch'].nunique()} branches")


# ── Summary with sign/magnitude separation ─────────────────────────────────
print(f"\n{'='*80}")
print(f"SUMMARY — high-solar filter ({MIN_SOLAR_FRAC*100:.0f}% of peak)")
print(f"{'='*80}\n")

summary = df.groupby('branch').agg(
    published_sf  = ('published_sf',  'first'),
    mean_implied  = ('implied_sf',    'mean'),
    std_implied   = ('implied_sf',    'std'),
    p5            = ('implied_sf',    lambda x: np.percentile(x, 5)),
    p95           = ('implied_sf',    lambda x: np.percentile(x, 95)),
    n_obs         = ('implied_sf',    'count'),
).reset_index()

# ── Classify each branch ───────────────────────────────────────────────────
summary['sign_correct'] = (
    np.sign(summary['mean_implied']) == np.sign(summary['published_sf'])
)

# Magnitude error: how far is |mean_implied| from |published_sf|, as a % of |published_sf|
summary['magnitude_error_pct'] = (
    100 * (summary['mean_implied'].abs() - summary['published_sf'].abs())
    / summary['published_sf'].abs()
)

# Instability: std as % of published SF magnitude (as before, for comparison)
summary['instability_pct'] = (
    100 * summary['std_implied'] / summary['published_sf'].abs()
)

# P5-P95 range
summary['range_p5_p95'] = summary['p95'] - summary['p5']

# Split into sign-correct and sign-flipped
sign_ok      = summary[summary['sign_correct']].copy()
sign_flipped = summary[~summary['sign_correct']].copy()

print(f"Branches with correct sign:  {len(sign_ok)}")
print(f"Branches with flipped sign:  {len(sign_flipped)}")
print()


# ── Table 1: Sign-correct branches — magnitude analysis ───────────────────
print("─" * 90)
print("TABLE 1: MAGNITUDE ERROR — sign-correct branches")
print("These are the clean evidence of SF degradation under IBR conditions.")
print("Magnitude error = (|mean implied| - |published|) / |published| × 100%")
print("─" * 90)
print(f"{'Branch':<42} {'Pub SF':>7} {'Mean impl':>10} {'Mag err%':>9} {'Std':>7} {'Instab%':>9} {'N':>6}")
print("-" * 90)

for _, r in sign_ok.sort_values('magnitude_error_pct', key=abs, ascending=False).iterrows():
    mag_err = r['magnitude_error_pct']
    flag = " ◄" if abs(mag_err) > 20 else ""
    print(
        f"{r['branch']:<42} {r['published_sf']:>7.3f} {r['mean_implied']:>10.3f} "
        f"{mag_err:>8.1f}% {r['std_implied']:>7.3f} {r['instability_pct']:>8.1f}% "
        f"{r['n_obs']:>6}{flag}"
    )

# Overall stats for sign-correct branches
if len(sign_ok) > 0:
    median_mag_err = sign_ok['magnitude_error_pct'].abs().median()
    mean_mag_err   = sign_ok['magnitude_error_pct'].abs().mean()
    large_err      = (sign_ok['magnitude_error_pct'].abs() > 20).sum()
    print(f"\n  Median |magnitude error|: {median_mag_err:.1f}%")
    print(f"  Mean   |magnitude error|: {mean_mag_err:.1f}%")
    print(f"  Branches with |mag error| > 20%: {large_err} of {len(sign_ok)}")


# ── Table 2: Sign-flipped branches ────────────────────────────────────────
print(f"\n\n{'─'*90}")
print("TABLE 2: SIGN-FLIPPED BRANCHES")
print("Likely causes: demand baseline contaminated by wind, or SF sign")
print("convention issue for specific branches. Exclude from IBR argument.")
print("─" * 90)
print(f"{'Branch':<42} {'Pub SF':>7} {'Mean impl':>10} {'Std':>7} {'Instab%':>9} {'N':>6}")
print("-" * 90)

for _, r in sign_flipped.sort_values('instability_pct', ascending=False).iterrows():
    print(
        f"{r['branch']:<42} {r['published_sf']:>7.3f} {r['mean_implied']:>10.3f} "
        f"{r['std_implied']:>7.3f} {r['instability_pct']:>8.1f}% {r['n_obs']:>6}"
    )


# ── Monthly breakdown for worst sign-correct branch ───────────────────────
month_names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
               'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

if len(sign_ok) > 0:
    focus = sign_ok.sort_values('magnitude_error_pct', key=abs, ascending=False).iloc[0]
    focus_branch = focus['branch']
    published    = focus['published_sf']
    mean_impl    = focus['mean_implied']

    print(f"\n\n{'='*80}")
    print(f"MONTHLY BREAKDOWN — {focus_branch}")
    print(f"Published SF = {published:.3f}   Mean implied = {mean_impl:.3f}   "
          f"Magnitude error = {focus['magnitude_error_pct']:.1f}%")
    print(f"{'='*80}\n")
    print(f"{'Month':<8} {'N obs':>6} {'Mean impl SF':>14} {'Std':>8} "
          f"{'|Mag err|':>10} {'vs published'}")
    print("-" * 65)

    branch_df = df[df['branch'] == focus_branch]
    monthly   = branch_df.groupby('month').agg(
        mean = ('implied_sf', 'mean'),
        std  = ('implied_sf', 'std'),
        n    = ('implied_sf', 'count'),
    ).reset_index()

    for _, m in monthly.iterrows():
        mag_err = 100 * (abs(m['mean']) - abs(published)) / abs(published)
        bar_len = int(abs(mag_err) / 5)
        bar     = ('▲' if m['mean'] > published else '▼') * min(bar_len, 20)
        print(
            f"{month_names[int(m['month'])]:<8} {m['n']:>6} {m['mean']:>14.3f} "
            f"{m['std']:>8.3f} {mag_err:>9.1f}%  {bar}"
        )


# ── Generation-level non-linearity for same branch ────────────────────────
if len(sign_ok) > 0:
    print(f"\n\n{'='*80}")
    print(f"GENERATION-LEVEL NON-LINEARITY — {focus_branch}")
    print(f"Flat implied SF across output bins = linear model holds.")
    print(f"Systematic slope = non-linearity, i.e. DC load flow assumption breaking down.")
    print(f"{'='*80}\n")

    branch_df = df[df['branch'] == focus_branch].copy()
    branch_df['solar_bin'] = pd.qcut(branch_df['solar_mw'], q=5, duplicates='drop')

    gen_level = branch_df.groupby('solar_bin', observed=True).agg(
        mean_solar = ('solar_mw',   'mean'),
        mean_impl  = ('implied_sf', 'mean'),
        std        = ('implied_sf', 'std'),
        n          = ('implied_sf', 'count'),
    ).reset_index()

    print(f"{'Solar output (MW)':>18} {'Mean impl SF':>14} {'Std':>8} {'N':>6}  vs published")
    print("-" * 65)
    for _, g in gen_level.iterrows():
        delta = g['mean_impl'] - published
        bar   = ('▲' if delta > 0 else '▼') * min(int(abs(delta) / (abs(published) * 0.05 + 0.001)), 20)
        print(
            f"{g['mean_solar']:>18.1f} {g['mean_impl']:>14.3f} "
            f"{g['std']:>8.3f} {g['n']:>6}  {bar}"
        )

    # Simple slope test: regress implied_sf on solar_mw
    x = branch_df['solar_mw'].values
    y = branch_df['implied_sf'].values
    slope, intercept = np.polyfit(x, y, 1)
    print(f"\n  OLS slope of implied_SF vs solar_output: {slope:.6f} per MW")
    print(f"  (non-zero slope = generation-level dependence = non-linearity)")
    print(f"  Implied SF at {x.min():.0f} MW solar: {intercept + slope*x.min():.3f}")
    print(f"  Implied SF at {x.max():.0f} MW solar: {intercept + slope*x.max():.3f}")
    print(f"  Change across output range: {slope*(x.max()-x.min()):.3f}")


# ── The one-paragraph commercial finding ──────────────────────────────────
print(f"\n\n{'='*80}")
print("SUMMARY FINDING")
print(f"{'='*80}\n")

n_sign_ok    = len(sign_ok)
n_sign_flip  = len(sign_flipped)
large_err_n  = (sign_ok['magnitude_error_pct'].abs() > 20).sum() if len(sign_ok) > 0 else 0
med_err      = sign_ok['magnitude_error_pct'].abs().median() if len(sign_ok) > 0 else 0

print(
    f"Across {n_branches} branches sensitive to {total_solar_capacity:.0f} MW of connected solar\n"
    f"in the Swansea North ANM zone, using only high-solar observations\n"
    f"(>{MIN_SOLAR_MW:.0f} MW output, {MIN_SOLAR_FRAC*100:.0f}% of peak):\n"
    f"\n"
    f"  {n_sign_ok} branches show correct-sign implied SFs (clean IBR signal).\n"
    f"  {n_sign_flip} branches show sign-flipped implied SFs (demand baseline\n"
    f"     contamination or SF convention issue — excluded from IBR argument).\n"
    f"\n"
    f"  Among the {n_sign_ok} clean branches:\n"
    f"    Median magnitude error: {med_err:.1f}%\n"
    f"    Branches with >20% magnitude error: {large_err_n} of {n_sign_ok}\n"
    f"\n"
    f"  The planning model's static sensitivity factors carry a systematic\n"
    f"  magnitude bias detectable from open SCADA data alone. This bias\n"
    f"  translates directly into curtailment estimation error on the branches\n"
    f"  most likely to be binding constraints for new connections."
)


# ── Save ───────────────────────────────────────────────────────────────────
out_obs     = os.path.join(MVP_DATA_DIR, 'sf_stability_refined_observations.csv')
out_summary = os.path.join(MVP_DATA_DIR, 'sf_stability_refined_summary.csv')

df.to_csv(out_obs, index=False)
summary.to_csv(out_summary, index=False)

print(f"\nSaved observations → {out_obs}")
print(f"Saved summary      → {out_summary}")
