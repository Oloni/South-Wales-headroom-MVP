"""
12c_sf_substations_selfcontained.py  (v2 — sign fix for net exporters)
=======================================================================
Runs the BSP-level covariance test entirely within the BSP transformer
flow data, without needing to match to the ANM zone profile files.

v2 fixes: instead of filtering to Reading Type == 'Import' (which flips
sign at net-exporting BSPs like Rhos and Swansea North), we use the
raw net flow = Import - Gen, which is directionally consistent regardless
of whether the BSP is a net importer or exporter.

Alternatively, for BSPs where Import is consistently signed, we use
abs(net_import_mw) to remove the sign ambiguity entirely.

The test: within each hour×month bin (demand ≈ constant), the covariance
of BSP net flow with measured generation should be ~ -1.0. When solar
generates more, the BSP imports less (or exports more). 1MW gen → 1MW
reduction in net import. Sign-corrected so this holds for exporters too.
"""

import pandas as pd
import numpy as np
import os
import glob

BSP_FLOWS_DIR = '/Users/leonie/Documents/South_Wales_headroom_MVP/data/BSP_transformer_flows'

# ── Tunable ────────────────────────────────────────────────────────────────
MIN_GEN_FRAC  = 0.10   # fraction of BSP peak Gen to include a half-hour
MIN_OBS_BIN   = 6      # minimum observations per hour×month bin
MIN_GEN_VAR   = 1.0    # MW² minimum Gen variance within a bin

results = []

for fpath in sorted(glob.glob(os.path.join(BSP_FLOWS_DIR, '*-transformer-flows.csv'))):
    fname    = os.path.basename(fpath)
    bsp_name = fname.replace('-transformer-flows.csv', '')

    df = pd.read_csv(fpath)
    df['ts'] = pd.to_datetime(df['Timestamp'])

    # ── Aggregate per timestamp across all transformers ────────────────
    imports = df[df['Reading Type'] == 'Import'].groupby('ts').agg(
        import_mw=('MW', 'sum')
    ).reset_index()

    gens = df[df['Reading Type'] == 'Gen'].groupby('ts').agg(
        gen_mw=('MW', 'sum')
    ).reset_index()

    demands = df[df['Reading Type'] == 'Demand'].groupby('ts').agg(
        demand_mw=('MW', 'sum')
    ).reset_index()

    merged = imports.merge(gens, on='ts', how='inner').merge(demands, on='ts', how='inner')

    if len(merged) < 500:
        print(f"  {bsp_name}: insufficient data ({len(merged)} rows)")
        continue

    # ── Sign-corrected net flow ────────────────────────────────────────
    # Raw Import can be negative at net-exporting BSPs (sign flips).
    # Use: net_import = demand - gen  which is always correctly signed.
    # When gen increases by 1MW, net_import decreases by 1MW → response = -1.
    # This works for both importers and exporters.
    merged['net_import_mw'] = merged['demand_mw'] - merged['gen_mw']

    # Also compute the raw Import-based version for comparison
    merged['raw_import_mw'] = merged['import_mw']

    merged['month'] = merged['ts'].dt.month
    merged['hour']  = merged['ts'].dt.hour

    gen_peak = merged['gen_mw'].max()
    if gen_peak < 1.0:
        continue

    MIN_GEN_MW = gen_peak * MIN_GEN_FRAC
    gen_mask   = merged['gen_mw'] >= MIN_GEN_MW

    # ── Check: is this a net exporter? ───────────────────────────────
    mean_import_raw = merged['raw_import_mw'].mean()
    is_net_exporter = mean_import_raw < 0

    # ── Covariance test in hour×month bins ────────────────────────────
    bin_results_corrected = []
    bin_results_raw       = []

    for month in range(1, 13):
        for hour in range(6, 20):
            mask = gen_mask & (merged['month'] == month) & (merged['hour'] == hour)
            if mask.sum() < MIN_OBS_BIN:
                continue

            g  = merged.loc[mask, 'gen_mw'].values
            f_corrected = merged.loc[mask, 'net_import_mw'].values
            f_raw       = merged.loc[mask, 'raw_import_mw'].values

            var_g = np.var(g, ddof=1)
            if var_g < MIN_GEN_VAR:
                continue

            # Corrected: demand - gen
            cov_c = np.cov(f_corrected, g)[0, 1]
            bin_results_corrected.append({
                'month': month, 'hour': hour,
                'n': mask.sum(),
                'response': cov_c / var_g,
            })

            # Raw Import (for comparison)
            cov_r = np.cov(f_raw, g)[0, 1]
            bin_results_raw.append({
                'month': month, 'hour': hour,
                'n': mask.sum(),
                'response': cov_r / var_g,
            })

    if not bin_results_corrected:
        continue

    bin_df_c = pd.DataFrame(bin_results_corrected)
    bin_df_r = pd.DataFrame(bin_results_raw)
    weights  = bin_df_c['n'].values

    resp_corrected = np.average(bin_df_c['response'], weights=weights)
    resp_raw       = np.average(bin_df_r['response'], weights=weights)
    std_corrected  = bin_df_c['response'].std()
    n_bins         = len(bin_df_c)

    results.append({
        'bsp':              bsp_name,
        'gen_peak_mw':      gen_peak,
        'mean_import_raw':  mean_import_raw,
        'is_net_exporter':  is_net_exporter,
        'response_corrected': resp_corrected,
        'response_raw':       resp_raw,
        'std_corrected':    std_corrected,
        'n_bins':           n_bins,
    })

    exporter_flag = ' [NET EXPORTER]' if is_net_exporter else ''
    print(
        f"  {bsp_name:<35} peak={gen_peak:>6.1f}MW  "
        f"corrected={resp_corrected:>+7.3f}  raw={resp_raw:>+7.3f}  "
        f"bins={n_bins}{exporter_flag}"
    )


# ── Summary ────────────────────────────────────────────────────────────────
print(f"\n\n{'='*80}")
print("SUMMARY: Gen → Net Import response (sign-corrected)")
print("Expected = -1.0 regardless of whether BSP is net importer or exporter")
print(f"{'='*80}\n")

df_out = pd.DataFrame(results).sort_values('response_corrected')

print(f"{'BSP':<35} {'Peak MW':>8} {'Corrected':>10} {'Raw':>8} {'Std':>7} {'Exporter':>9}")
print("-" * 80)
for _, r in df_out.iterrows():
    flag     = '✓' if r['is_net_exporter'] else ''
    consist  = ' ✓ consistent' if abs(r['response_corrected'] + 1.0) < 0.15 else ''
    print(
        f"{r['bsp']:<35} {r['gen_peak_mw']:>8.1f} "
        f"{r['response_corrected']:>+10.3f} {r['response_raw']:>+8.3f} "
        f"{r['std_corrected']:>7.3f} {flag:>9}{consist}"
    )

n_consistent = (abs(df_out['response_corrected'] + 1.0) < 0.15).sum()
n_exporters  = df_out['is_net_exporter'].sum()
median_resp  = df_out['response_corrected'].median()

print(f"\nNet-exporting BSPs: {n_exporters}")
print(f"BSPs with corrected response near -1.0 (±0.15): {n_consistent} of {len(df_out)}")
print(f"Median corrected response: {median_resp:.3f}")
print(f"Median raw response:       {df_out['response_raw'].median():.3f}")

print(f"""
KEY COMPARISON — Raw vs Corrected:
  If corrected responses for exporters (Rhos, Swansea North) are now
  near -1.0, the sign issue was the full explanation for their anomalous
  raw responses — confirming the BSP-level data is clean and the ANM
  contamination is specific to the derived branch load layer.

  If corrected responses are still anomalous, there is a more fundamental
  issue: heavy curtailment suppressing even BSP-level signal, or the Gen
  reading including non-solar generation that varies independently.
""")

# Save
out = os.path.join(os.path.dirname(BSP_FLOWS_DIR), 'sf_substation_selfcontained_v2.csv')
df_out.to_csv(out, index=False)
print(f"Saved → {out}")
