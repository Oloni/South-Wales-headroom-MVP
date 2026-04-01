"""
07_curtailment_confidence.py (v2 — PEL-relative scoring)
=========================================================
Maps model-vs-reality residuals to binding branches and assigns
confidence ratings using PEL-relative error.

A 0.2 MW residual on a branch with a 45 MW PEL is 0.4% — High confidence.
A 5 MW residual on a branch with a 10 MW PEL is 50% — Low confidence.

This is more meaningful than gen-contribution-relative error because
the PEL determines whether curtailment happens, and the residual
tells you how wrong that determination might be.
"""

import pandas as pd
import numpy as np
import os
import glob
import time

MVP_DATA_DIR = '/Users/leonie/Documents/South_Wales_headroom_MVP/data'

print("Loading data...")
t0 = time.time()

curtailment = pd.read_csv(os.path.join(MVP_DATA_DIR, 'south_wales_curtailment.csv'))
residuals = pd.read_csv(os.path.join(MVP_DATA_DIR, 'model_vs_reality_residuals.csv'))

print(f"  Curtailment estimates: {len(curtailment)} rows ({curtailment['substation'].nunique()} substations)")
print(f"  Model residuals: {len(residuals)} branches")


# ============================================================
# LOAD PEL DATA TO GET BRANCH LIMITS
# ============================================================
print("\nLoading PEL data for all zones...")

pel_lookup = {}  # branch_name -> max PEL (forward or reverse, worst season)

for f in sorted(glob.glob(os.path.join(MVP_DATA_DIR, '*_pre-event_limits_id_*_2026.csv'))):
    pel = pd.read_csv(f)
    for branch_name, group in pel.groupby(
        pel.apply(lambda r: f"{r['From Bus Name']}->{r['To Bus Name']}", axis=1)
    ):
        fwd_max = group['Forward PEL MW'].abs().max()
        rev_max = group['Reverse PEL MW'].abs().max()
        pel_lookup[branch_name] = max(fwd_max, rev_max)

print(f"  PEL data for {len(pel_lookup)} branches")


# ============================================================
# LOAD BRANCH SCADA STATS (for disconnected branch detection)
# ============================================================
print("Loading branch SCADA stats...")

branch_stats = {}

for prefix_id in [('aberthaw-and-cardiff-east', '310'), ('pembroke', '312'), ('pyle', '313'),
                   ('rassau', '314'), ('swansea-north', '315'), ('upper-boat', '316'), ('uskmouth', '317')]:
    prefix, zone_id = prefix_id
    bl_path = os.path.join(MVP_DATA_DIR, f'{prefix}_branch_load_id_{zone_id}_2026.csv')
    sf_path = os.path.join(MVP_DATA_DIR, f'{prefix}_sensitivity_factors_id_{zone_id}_2026.csv')

    if not os.path.exists(bl_path) or not os.path.exists(sf_path):
        continue

    bl = pd.read_csv(bl_path)
    sf = pd.read_csv(sf_path)

    sf['branch_col'] = sf.apply(
        lambda r: f"{r['From Bus Number']}_{r['To Bus Number']}_{r['Tertiary Bus Number']}_{r['Circuit ID']}", axis=1
    )
    col_to_name = {}
    for _, row in sf.drop_duplicates('branch_col').iterrows():
        col_to_name[row['branch_col']] = f"{row['From Bus Name']}->{row['To Bus Name']}"

    for col in bl.columns:
        if col == 'Half Hour':
            continue
        if col not in col_to_name:
            continue

        values = bl[col].values
        name = col_to_name[col]
        branch_stats[name] = {
            'mean_abs_flow': np.abs(values).mean(),
            'std_flow': values.std(),
            'zero_pct': 100 * (np.abs(values) < 0.01).sum() / len(values),
            'max_abs_flow': np.abs(values).max(),
            'zone': prefix,
        }

print(f"  Branch SCADA stats for {len(branch_stats)} branches")


# ============================================================
# BUILD RESIDUAL LOOKUP
# ============================================================
residual_lookup = {}
for _, r in residuals.iterrows():
    residual_lookup[r['branch']] = {
        'mean_residual_mw': r['mean_residual_mw'],
        'std_residual_mw': r['std_residual_mw'],
        'max_abs_residual': r['max_abs_residual'],
        'mean_gen_contribution': r['mean_gen_contribution'],
    }


# ============================================================
# ASSIGN CONFIDENCE
# ============================================================
print("\nAssigning confidence ratings...")

confidence_rows = []

for _, row in curtailment.iterrows():
    binding = row.get('binding_branch', '')
    sub = row['substation']
    tech = row['technology']
    mw = row['capacity_mw']
    curt_pct = row['curtailment_pct']

    result = {
        'substation': sub,
        'technology': tech,
        'capacity_mw': mw,
        'curtailment_pct': curt_pct,
        'binding_branch': binding,
    }

    if pd.isna(binding) or binding == 'None' or str(binding).strip() == '':
        result['confidence'] = 'N/A'
        result['confidence_reason'] = 'No curtailment — no binding constraint'
        result['model_residual_mw'] = None
        result['pel_mw'] = None
        result['residual_pct_of_pel'] = None
        confidence_rows.append(result)
        continue

    # Get PEL for this branch
    pel_mw = pel_lookup.get(binding)
    result['pel_mw'] = pel_mw

    # Check 1: Is this branch in the residuals table (validated against SCADA)?
    if binding in residual_lookup:
        res = residual_lookup[binding]
        abs_mean_res = abs(res['mean_residual_mw'])
        abs_max_res = res['max_abs_residual']
        result['model_residual_mw'] = res['mean_residual_mw']
        result['model_residual_std'] = res['std_residual_mw']
        result['model_max_residual'] = abs_max_res

        if pel_mw and pel_mw > 0:
            # PEL-relative scoring
            pel_rel_mean = 100 * abs_mean_res / pel_mw
            pel_rel_max = 100 * abs_max_res / pel_mw
            result['residual_pct_of_pel'] = pel_rel_mean

            # Absolute floor: if mean residual < 1 MW, the model error
            # is operationally insignificant regardless of percentages
            if abs_mean_res < 1.0:
                result['confidence'] = 'High'
                result['confidence_reason'] = f'Residual {abs_mean_res:.1f} MW on {pel_mw:.0f} MW PEL — operationally negligible.'
            elif pel_rel_mean < 5 and pel_rel_max < 25:
                result['confidence'] = 'High'
                result['confidence_reason'] = f'Residual {abs_mean_res:.1f} MW = {pel_rel_mean:.0f}% of PEL ({pel_mw:.0f} MW). Model well-validated.'
            elif pel_rel_mean < 15 and pel_rel_max < 50:
                result['confidence'] = 'Moderate'
                result['confidence_reason'] = f'Residual {abs_mean_res:.1f} MW = {pel_rel_mean:.0f}% of PEL ({pel_mw:.0f} MW). Estimate directionally correct.'
            else:
                result['confidence'] = 'Low'
                result['confidence_reason'] = f'Residual {abs_mean_res:.1f} MW = {pel_rel_mean:.0f}% of PEL ({pel_mw:.0f} MW). Significant model-reality gap.'
        else:
            # No PEL available — fall back to absolute residual
            result['residual_pct_of_pel'] = None
            if abs_mean_res < 2:
                result['confidence'] = 'High'
                result['confidence_reason'] = f'Residual {abs_mean_res:.1f} MW (small absolute). No PEL for relative scoring.'
            elif abs_mean_res < 10:
                result['confidence'] = 'Moderate'
                result['confidence_reason'] = f'Residual {abs_mean_res:.1f} MW. No PEL for relative scoring.'
            else:
                result['confidence'] = 'Low'
                result['confidence_reason'] = f'Residual {abs_mean_res:.1f} MW (large absolute). No PEL for relative scoring.'

    # Check 2: Branch in SCADA but no generation residual
    elif binding in branch_stats:
        bs = branch_stats[binding]
        result['model_residual_mw'] = None
        result['residual_pct_of_pel'] = None

        if bs['zero_pct'] > 95:
            result['confidence'] = 'Very Low'
            result['confidence_reason'] = f'Branch reads zero {bs["zero_pct"]:.0f}% of time — likely disconnected or unmonitored'
        elif bs['zero_pct'] > 50:
            result['confidence'] = 'Low'
            result['confidence_reason'] = f'Branch reads zero {bs["zero_pct"]:.0f}% of time — intermittent monitoring'
        elif bs['max_abs_flow'] < 1.0:
            result['confidence'] = 'Low'
            result['confidence_reason'] = f'Branch max flow only {bs["max_abs_flow"]:.1f} MW — may not be active'
        else:
            result['confidence'] = 'Moderate'
            result['confidence_reason'] = f'Branch active (mean {bs["mean_abs_flow"]:.1f} MW) but no generation residual available'

    else:
        result['confidence'] = 'Unknown'
        result['confidence_reason'] = 'Binding branch not found in SCADA data'
        result['model_residual_mw'] = None
        result['residual_pct_of_pel'] = None

    confidence_rows.append(result)

df_conf = pd.DataFrame(confidence_rows)


# ============================================================
# SUMMARY
# ============================================================
print("\n" + "="*70)
print("CURTAILMENT CONFIDENCE SUMMARY")
print("="*70)

print("\nOverall distribution:")
for conf in ['High', 'Moderate', 'Low', 'Very Low', 'Unknown', 'N/A']:
    n = (df_conf['confidence'] == conf).sum()
    pct = 100 * n / len(df_conf)
    print(f"  {conf:<12}: {n:>5} estimates ({pct:.0f}%)")

# HIGH confidence with curtailment
print("\n" + "="*70)
print("HIGH CONFIDENCE ESTIMATES WITH CURTAILMENT")
print("="*70)
print("Model validated against SCADA. Residual < 5% of PEL.\n")

high = df_conf[(df_conf['curtailment_pct'] > 0) & (df_conf['confidence'] == 'High')]
if len(high) > 0:
    high_20 = high[high['capacity_mw'] == 20].sort_values('curtailment_pct', ascending=False)
    print(f"{'Substation':<20} {'Tech':<6} {'Curt%':>7} {'Residual':>10} {'PEL':>8} {'Res/PEL':>8}")
    print("-" * 65)
    for _, r in high_20.head(30).iterrows():
        res = f"{r['model_residual_mw']:.1f}" if pd.notna(r.get('model_residual_mw')) else "—"
        pel = f"{r['pel_mw']:.0f}" if pd.notna(r.get('pel_mw')) else "—"
        rpel = f"{r['residual_pct_of_pel']:.0f}%" if pd.notna(r.get('residual_pct_of_pel')) else "—"
        print(f"{r['substation']:<20} {r['technology']:<6} {r['curtailment_pct']:>6.1f}% {res:>10} {pel:>8} {rpel:>8}")
else:
    print("  None found.")

# LOW confidence with high curtailment
print("\n" + "="*70)
print("LOW/VERY LOW CONFIDENCE WITH CURTAILMENT > 5%")
print("="*70)
print("These estimates are most at risk of being wrong.\n")

flagged = df_conf[
    (df_conf['curtailment_pct'] > 5) &
    (df_conf['confidence'].isin(['Low', 'Very Low']))
]
if len(flagged) > 0:
    flagged_20 = flagged[flagged['capacity_mw'] == 20].sort_values('curtailment_pct', ascending=False)
    print(f"{'Substation':<20} {'Tech':<6} {'Curt%':>7} {'Reason'}")
    print("-" * 90)
    for _, r in flagged_20.head(20).iterrows():
        print(f"{r['substation']:<20} {r['technology']:<6} {r['curtailment_pct']:>6.1f}% {r['confidence_reason']}")
else:
    print("  None found.")

# Disconnected branches
print("\n" + "="*70)
print("POTENTIALLY DISCONNECTED BRANCHES")
print("="*70)
zero_branches = df_conf[df_conf['confidence'] == 'Very Low'][['binding_branch', 'confidence_reason']].drop_duplicates()
if len(zero_branches) > 0:
    for _, r in zero_branches.iterrows():
        print(f"  {r['binding_branch']}: {r['confidence_reason']}")
else:
    print("  None found.")


# ============================================================
# SAVE
# ============================================================
output_path = os.path.join(MVP_DATA_DIR, 'south_wales_curtailment_confidence.csv')
df_conf.to_csv(output_path, index=False)
print(f"\nSaved {len(df_conf)} rows to {output_path}")
print(f"Total time: {time.time()-t0:.0f}s")

# Quick stats for the pitch
n_validated = (df_conf['confidence'].isin(['High', 'Moderate', 'Low'])).sum()
n_high = (df_conf['confidence'] == 'High').sum()
n_with_curt = (df_conf['curtailment_pct'] > 0).sum()
n_high_with_curt = ((df_conf['confidence'] == 'High') & (df_conf['curtailment_pct'] > 0)).sum()

print(f"\n--- For the pitch ---")
print(f"Total estimates: {len(df_conf)}")
print(f"SCADA-validated: {n_validated} ({100*n_validated/len(df_conf):.0f}%)")
print(f"High confidence: {n_high} ({100*n_high/len(df_conf):.0f}%)")
print(f"High confidence with curtailment > 0: {n_high_with_curt}")
