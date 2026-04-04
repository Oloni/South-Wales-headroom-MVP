"""
11_sf_variance_test.py
======================
A second-moment test of NGED sensitivity factor accuracy that is
immune to the demand baseline contamination problem that affects
the night/day implied-SF approach.

CORE IDEA
---------
If SF is correct, then within any narrow time window where demand
is approximately constant, the variance of branch flow should equal
SF² × variance of solar output:

    Var(branch_flow) ≈ SF² × Var(solar_output)

So the ratio:
    R = Var(branch_flow) / (SF² × Var(solar_output))

should be ~1.0 if the model is correct.

    R >> 1  → branch more variable than SF predicts
               (other generation or demand noise dominates — inconclusive)
    R << 1  → branch less variable than SF predicts
               (solar contribution is being overestimated by the model)
    R ≈ 1   → model consistent with data

We control for demand by grouping half-hours into narrow hour-of-day
× month bins. Within each bin, demand is roughly stable. Residual
variance then reflects solar output variation and model error.

WHAT THIS CANNOT DO
-------------------
It cannot detect a systematic bias (mean error) — only variability
mismatch. It is therefore complementary to the implied-SF approach,
not a replacement.

WHAT A RATIO << 1 MEANS COMMERCIALLY
--------------------------------------
If the model predicts that a 1 MW change in solar output moves a
branch by 0.5 MW, but empirically the branch barely moves, then
the model is overstating that generator's influence on that branch.
This means curtailment estimates for generators at that bus are
probably too high — the model is being too conservative. Conversely,
branches where R >> 1 may be understated.
"""

import pandas as pd
import numpy as np
import os

MVP_DATA_DIR = '/Users/leonie/Documents/South_Wales_headroom_MVP/data'
ZONE     = 'swansea-north'
ZONE_ID  = '315'

# ── Tunable ────────────────────────────────────────────────────────────────
# Minimum number of observations per hour×month bin to include in analysis.
# Too low = noisy variance estimates. Too high = many bins dropped.
MIN_OBS_PER_BIN = 8

# Minimum solar variance within a bin to use it.
# Bins where solar barely varies give noisy SF estimates.
MIN_SOLAR_VAR = 5.0  # MW²

# Solar output range to focus on (avoids dawn/dusk noise)
MIN_SOLAR_MW_FRAC = 0.15   # 15% of peak
MAX_SOLAR_MW_FRAC = 1.00

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

# ── Solar output ───────────────────────────────────────────────────────────
solar = cq[cq['Fuel type'] == 'Solar'].copy()
total_capacity = solar['Site Export Capacity (MW)'].sum()

solar_output = np.zeros(n)
for _, g in solar.iterrows():
    solar_output += g['Site Export Capacity (MW)'] * prof['PV'].values

solar_peak = solar_output.max()
MIN_SOLAR_MW = solar_peak * MIN_SOLAR_MW_FRAC
MAX_SOLAR_MW = solar_peak * MAX_SOLAR_MW_FRAC

print(f"Connected solar: {len(solar)} generators, {total_capacity:.1f} MW total")
print(f"Solar peak: {solar_peak:.1f} MW")
print(f"Solar range for analysis: {MIN_SOLAR_MW:.1f}–{MAX_SOLAR_MW:.1f} MW")

# ── Branch metadata ────────────────────────────────────────────────────────
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

# Aggregate weighted published SF per branch
branch_pub_sf = {}
for branch_col, group in solar_sf.groupby('branch_col'):
    contributing_mw = 0
    weighted = 0.0
    for _, row in group.iterrows():
        bus_mw = solar.loc[
            solar['Bus Number'] == row['Node Number'],
            'Site Export Capacity (MW)'
        ].sum()
        weighted      += row['Sensitivity Factor MW'] * bus_mw
        contributing_mw += bus_mw
    branch_pub_sf[branch_col] = weighted / contributing_mw if contributing_mw > 0 else 0.0

branch_names = {
    bc: solar_sf[solar_sf['branch_col'] == bc].iloc[0]['branch_name']
    for bc in branch_pub_sf
}

print(f"\nBranches to test: {len(branch_pub_sf)}")


# ── Build time index with solar filter ────────────────────────────────────
solar_mask = (solar_output >= MIN_SOLAR_MW) & (solar_output <= MAX_SOLAR_MW)
t_idx = np.where(solar_mask)[0]
print(f"Half-hours in solar range: {len(t_idx)} of {n} ({100*len(t_idx)/n:.1f}%)")


# ── Variance ratio test ────────────────────────────────────────────────────
print("\nRunning variance ratio test (hour × month bins)...")

results = []

for branch_col, pub_sf in branch_pub_sf.items():
    if branch_col not in bl.columns:
        continue
    if abs(pub_sf) < 0.01:
        continue

    actual_flow = bl[branch_col].values

    # Expected variance contribution from solar: SF² × Var(solar)
    # We test this within each hour×month bin to control for demand
    bin_results = []

    for month in range(1, 13):
        for hour in range(6, 20):   # daytime only
            mask = solar_mask & (months == month) & (hours == hour)
            idx  = np.where(mask)[0]

            if len(idx) < MIN_OBS_PER_BIN:
                continue

            s = solar_output[idx]
            f = actual_flow[idx]

            var_solar  = np.var(s, ddof=1)
            var_flow   = np.var(f, ddof=1)
            expected_var = pub_sf**2 * var_solar

            if var_solar < MIN_SOLAR_VAR:
                continue
            if expected_var < 1e-6:
                continue

            ratio = var_flow / expected_var

            # Also compute the empirical SF from covariance
            # Cov(flow, solar) = SF × Var(solar)  (if demand is independent of solar)
            # => empirical_SF = Cov(flow, solar) / Var(solar)
            cov = np.cov(f, s)[0, 1]
            empirical_sf = cov / var_solar if var_solar > 0 else np.nan

            bin_results.append({
                'month':        month,
                'hour':         hour,
                'n':            len(idx),
                'var_solar':    var_solar,
                'var_flow':     var_flow,
                'expected_var': expected_var,
                'ratio':        ratio,
                'empirical_sf': empirical_sf,
            })

    if not bin_results:
        continue

    bin_df = pd.DataFrame(bin_results)

    # Weight bins by number of observations
    weights = bin_df['n'].values
    mean_ratio        = np.average(bin_df['ratio'],        weights=weights)
    median_ratio      = np.median(bin_df['ratio'])
    mean_empirical_sf = np.average(bin_df['empirical_sf'].dropna(),
                                   weights=weights[:len(bin_df['empirical_sf'].dropna())])
    n_bins            = len(bin_df)

    # Empirical SF sign check
    sign_correct = np.sign(mean_empirical_sf) == np.sign(pub_sf)

    # Classification
    if mean_ratio < 0.25:
        verdict = 'UNDERSTATED'   # model overestimates SF, flow barely responds
    elif mean_ratio < 0.75:
        verdict = 'LOW'
    elif mean_ratio < 1.5:
        verdict = 'CONSISTENT'
    elif mean_ratio < 4.0:
        verdict = 'HIGH'
    else:
        verdict = 'OVERSTATED'    # flow much more variable than SF predicts

    results.append({
        'branch':           branch_names[branch_col],
        'branch_col':       branch_col,
        'published_sf':     pub_sf,
        'mean_empirical_sf': mean_empirical_sf,
        'sign_correct':     sign_correct,
        'mean_ratio':       mean_ratio,
        'median_ratio':     median_ratio,
        'n_bins':           n_bins,
        'verdict':          verdict,
    })

df = pd.DataFrame(results).sort_values('mean_ratio')


# ── Results ────────────────────────────────────────────────────────────────
month_names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
               'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

print(f"\n\n{'='*90}")
print("VARIANCE RATIO TEST RESULTS")
print(f"{'='*90}")
print("""
Ratio = Var(actual branch flow) / (SF² × Var(solar output))
within hour×month bins (demand approximately constant within each bin).

  Ratio ≈ 1.0  → model consistent with observed data
  Ratio << 1   → model OVERestimates SF (solar effect smaller than predicted)
  Ratio >> 1   → model UNDERestimates SF, OR other sources dominate variance
""")

print(f"{'Branch':<42} {'Pub SF':>7} {'Emp SF':>8} {'Sign':>5} {'Ratio':>7} {'Verdict':<15} {'Bins':>5}")
print("-" * 95)

for _, r in df.iterrows():
    sign_str = '✓' if r['sign_correct'] else '✗'
    emp_sf   = f"{r['mean_empirical_sf']:.3f}" if not np.isnan(r['mean_empirical_sf']) else '  —  '
    print(
        f"{r['branch']:<42} {r['published_sf']:>7.3f} {emp_sf:>8} {sign_str:>5} "
        f"{r['mean_ratio']:>7.2f} {r['verdict']:<15} {r['n_bins']:>5}"
    )


# ── Verdict distribution ───────────────────────────────────────────────────
print(f"\n\n{'='*90}")
print("VERDICT DISTRIBUTION")
print(f"{'='*90}\n")

for verdict in ['UNDERSTATED', 'LOW', 'CONSISTENT', 'HIGH', 'OVERSTATED']:
    subset = df[df['verdict'] == verdict]
    bar    = '█' * len(subset)
    print(f"  {verdict:<12}: {len(subset):>3} branches  {bar}")

n_consistent = (df['verdict'] == 'CONSISTENT').sum()
n_understated = df['verdict'].isin(['UNDERSTATED', 'LOW']).sum()
n_overstated  = df['verdict'].isin(['HIGH', 'OVERSTATED']).sum()
print(f"\n  Model consistent (ratio 0.75–1.5): {n_consistent} of {len(df)} branches ({100*n_consistent/len(df):.0f}%)")
print(f"  SF overstated (ratio < 0.75):      {n_understated} of {len(df)} branches ({100*n_understated/len(df):.0f}%)")
print(f"  SF understated (ratio > 1.5):      {n_overstated} of {len(df)} branches ({100*n_overstated/len(df):.0f}%)")


# ── Empirical SF comparison for consistent-sign branches ──────────────────
print(f"\n\n{'='*90}")
print("EMPIRICAL vs PUBLISHED SF — sign-correct branches only")
print(f"{'='*90}")
print("""
Empirical SF = Cov(branch_flow, solar_output) / Var(solar_output)
within hour×month bins, then weighted average across bins.
This is the covariance-based estimate of how much the branch actually
responds to solar output variation, controlling for demand via binning.
""")

sign_ok = df[df['sign_correct']].copy()
sign_ok['sf_ratio'] = sign_ok['mean_empirical_sf'] / sign_ok['published_sf']
sign_ok['sf_error_pct'] = 100 * (sign_ok['mean_empirical_sf'] - sign_ok['published_sf']) / sign_ok['published_sf'].abs()

print(f"{'Branch':<42} {'Pub SF':>7} {'Emp SF':>8} {'SF ratio':>9} {'Error%':>8} {'Verdict'}")
print("-" * 90)

for _, r in sign_ok.sort_values('sf_ratio').iterrows():
    print(
        f"{r['branch']:<42} {r['published_sf']:>7.3f} {r['mean_empirical_sf']:>8.3f} "
        f"{r['sf_ratio']:>9.2f} {r['sf_error_pct']:>7.1f}%  {r['verdict']}"
    )

if len(sign_ok) > 0:
    median_ratio = sign_ok['sf_ratio'].median()
    mean_ratio   = sign_ok['sf_ratio'].mean()
    print(f"\n  Median empirical/published SF ratio: {median_ratio:.2f}")
    print(f"  Mean   empirical/published SF ratio: {mean_ratio:.2f}")
    print(f"  (1.0 = model correct, <1 = model overstates influence, >1 = understates)")


# ── Focus: branches that matter for curtailment ───────────────────────────
print(f"\n\n{'='*90}")
print("CURTAILMENT-RELEVANT BRANCHES")
print(f"{'='*90}")
print("""
Branches with |published SF| >= 0.2 are the ones most likely to be
binding constraints for new connections. These are where SF error
has the largest direct impact on curtailment estimates.
""")

high_sf = df[df['published_sf'].abs() >= 0.2].copy()
high_sf = high_sf.sort_values('mean_ratio')

print(f"{'Branch':<42} {'Pub SF':>7} {'Emp SF':>8} {'Ratio':>7} {'Verdict':<15}")
print("-" * 80)

for _, r in high_sf.iterrows():
    emp = f"{r['mean_empirical_sf']:.3f}" if not np.isnan(r['mean_empirical_sf']) else '  —  '
    sign_flag = '' if r['sign_correct'] else ' [sign flip]'
    print(
        f"{r['branch']:<42} {r['published_sf']:>7.3f} {emp:>8} "
        f"{r['mean_ratio']:>7.2f} {r['verdict']:<15}{sign_flag}"
    )


# ── The commercial finding ─────────────────────────────────────────────────
print(f"\n\n{'='*90}")
print("SUMMARY FINDING")
print(f"{'='*90}\n")

print(
    f"Variance ratio test across {len(df)} branches sensitive to\n"
    f"{total_capacity:.0f} MW of connected solar in the Swansea North ANM zone.\n"
    f"Method: within hour×month bins (demand ≈ constant), compare\n"
    f"observed branch flow variance against SF² × solar output variance.\n"
    f"\n"
    f"  Consistent with model (ratio 0.75–1.5): {n_consistent} branches ({100*n_consistent/len(df):.0f}%)\n"
    f"  SF appears overstated (ratio < 0.75):   {n_understated} branches ({100*n_understated/len(df):.0f}%)\n"
    f"  SF appears understated (ratio > 1.5):   {n_overstated} branches ({100*n_overstated/len(df):.0f}%)\n"
    f"\n"
    f"  Among sign-correct branches, median empirical/published SF ratio: "
    f"{sign_ok['sf_ratio'].median():.2f}\n"
    f"\n"
    f"  A ratio systematically below 1.0 on curtailment-relevant branches\n"
    f"  (|SF| >= 0.2) indicates the static planning model overstates the\n"
    f"  influence of connected solar on those branches — meaning curtailment\n"
    f"  estimates derived from the published SFs are likely conservative\n"
    f"  (too high). The magnitude of this bias is quantifiable from\n"
    f"  open SCADA data without requiring a full AC load flow model."
)


# ── Save ───────────────────────────────────────────────────────────────────
out = os.path.join(MVP_DATA_DIR, 'sf_variance_test.csv')
df.to_csv(out, index=False)
print(f"\nSaved → {out}")
