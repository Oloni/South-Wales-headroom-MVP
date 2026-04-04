"""
12_sf_substation_test.py
========================
Validates NGED sensitivity factors using BSP-level substation load
data rather than derived branch load data.

WHY THIS IS CLEANER THAN BRANCH LOAD DATA
------------------------------------------
The branch load CSVs are calculated from substation loading + SFs
(see NGED guidance section 3.2.2: "derived net power flow through
each branch... calculated using the substation loading and sensitivity
factors"). They are not independent SCADA measurements — they are
partly model outputs. Worse, on ANM-controlled branches the ANM
system actively manages branch loading, suppressing the variance
that our test relies on.

The BSP transformer flow files are direct metered SCADA measurements
at the transformer itself. The ANM manages individual generator
outputs, not the aggregate BSP net flow. So the BSP net import signal
is the least ANM-contaminated data available in the open dataset.

THE TEST
--------
For a BSP with connected solar generation of capacity C MW:

  BSP_net_import(t) = Demand(t) - Gen(t)

When solar generates:
  Gen(t) = C × solar_profile(t) + other_gen(t)

So:
  BSP_net_import(t) = Demand(t) - C × solar_profile(t) - other_gen(t)

Within a narrow hour×month bin where demand and other_gen are
approximately constant, the covariance of BSP net import with
solar output should be:

  Cov(net_import, solar_output) = -C × Var(solar_profile)

Because a 1 MW increase in solar output reduces BSP net import by 1 MW
(the solar offsets grid import). This gives us a baseline: the BSP-level
relationship should be exactly -1.0 per unit of solar capacity.

We can then compare the sensitivity factor prediction for the BSP
transformer branch against this independently measured relationship.
The ratio tells us how much of the solar output actually flows through
the BSP transformer versus being absorbed locally or flowing elsewhere.

ADDITIONALLY
------------
For each BSP, we test whether the SF-predicted contribution from the
connected solar to the BSP transformer branch matches the measured
covariance — giving a direct, ANM-uncontaminated SF validation.

FILES NEEDED
------------
- BSP transformer flow CSVs (from BSP_transformer_flows_south_wales/)
  Format: columns Timestamp, Transformer, Reading Type, MW, MVAr, MVA
  Reading Types: Import, Demand, Gen
- swansea-north_sensitivity_factors_id_315_2026.csv
- swansea-north_generic_generator_profiles_id_315_2026.csv
- swansea-north_connection_queue_id_315_2026.csv
"""

import pandas as pd
import numpy as np
import os
import glob

# ── Paths ──────────────────────────────────────────────────────────────────
MVP_DATA_DIR  = '/Users/leonie/Documents/South_Wales_headroom_MVP/data'
BSP_FLOWS_DIR = '/Users/leonie/Documents/South_Wales_headroom_MVP/data/BSP_transformer_flows'
ZONE          = 'swansea-north'
ZONE_ID       = '315'

# ── Tunable ────────────────────────────────────────────────────────────────
MIN_OBS_PER_BIN = 6      # minimum half-hours per hour×month bin
MIN_SOLAR_FRAC  = 0.10   # minimum solar output as fraction of peak to include
MIN_SOLAR_VAR   = 2.0    # MW² minimum variance within a bin to use it

# ── Map CIM codes to BSP flow file names ──────────────────────────────────
# From script 01's SUBSTATION_NAMES table
CIM_TO_FLOW_FILE = {
    'ABGA': 'abergavenny-66kv',
    'AMMA': 'ammanford-33kv',
    'BREN': 'bridgend-33kv',
    'BRIF': 'briton-ferry-33kv',
    'BARR': 'brynhill-33kv',
    'CARC': 'cardiff-central-33kv',
    'CARE': 'cardiff-east-33kv',
    'CARN': 'cardiff-north-33kv',
    'CARW': 'cardiff-west-33kv',
    'CARM': 'carmarthen-33kv',
    'CRUM': 'crumlin-33kv',
    'DOWL': 'dowlais-33kv',
    'EAST': 'east-aberthaw-33kv',
    'EBBW': 'ebbw-vale-33kv',
    'GOLD': 'golden-hill-33kv',
    'GOWE': 'gowerton-east-33kv',
    'MAGA': 'grange-66kv',
    'HAVE': 'haverfordwest-33kv',
    'HIRW': 'hirwaun-33kv',
    'LAMP': 'lampeter-33kv',
    'LLAN': 'llanarth-33kv',
    'LLTA': 'llantarnam-66kv',
    'MIFH': 'milford-haven-33kv',
    'MOUA': 'mountain-ash-33kv',
    'NEWS': 'newport-south-33kv',
    'PANT': 'panteg-66kv',
    'PYLE': 'pyle-33kv',
    'RHOS': 'rhos-33kv',
    'SUDB': 'sudbrook-33kv',
    'SWAN': 'swansea-north-33kv',
    'SWAW': 'swansea-west-33kv',
    'TIRJ': 'tir-john-33kv',
    'TROS': 'trostre-33kv',
    'YSTR': 'ystradgynlais-33kv',
}

CIM_TO_NAME = {
    'AMMA': 'Ammanford',  'BRIF': 'Briton Ferry', 'CARM': 'Carmarthen',
    'GOWE': 'Gowerton East', 'HIRW': 'Hirwaun',   'LAMP': 'Lampeter',
    'LLAN': 'Llanarth',   'RHOS': 'Rhos',         'SWAN': 'Swansea North',
    'SWAW': 'Swansea West', 'TIRJ': 'Tir John',   'TROS': 'Trostre',
    'YSTR': 'Ystradgynlais',
}


# ── Load zone data ─────────────────────────────────────────────────────────
print("Loading zone data...")
sf   = pd.read_csv(f'{MVP_DATA_DIR}/{ZONE}_sensitivity_factors_id_{ZONE_ID}_2026.csv')
prof = pd.read_csv(f'{MVP_DATA_DIR}/{ZONE}_generic_generator_profiles_id_{ZONE_ID}_2026.csv')
cq   = pd.read_csv(f'{MVP_DATA_DIR}/{ZONE}_connection_queue_id_{ZONE_ID}_2026.csv')

timestamps = pd.to_datetime(prof['Half Hour'])
months = timestamps.dt.month.values
hours  = timestamps.dt.hour.values
n      = len(prof)

# ── Solar generators ───────────────────────────────────────────────────────
solar_gens = cq[cq['Fuel type'] == 'Solar'].copy()
total_solar_mw = solar_gens['Site Export Capacity (MW)'].sum()

solar_output = np.zeros(n)
for _, g in solar_gens.iterrows():
    solar_output += g['Site Export Capacity (MW)'] * prof['PV'].values

solar_peak = solar_output.max()
MIN_SOLAR_MW = solar_peak * MIN_SOLAR_FRAC
solar_mask = solar_output >= MIN_SOLAR_MW

print(f"Connected solar: {len(solar_gens)} generators, {total_solar_mw:.1f} MW")
print(f"Solar peak: {solar_peak:.1f} MW, analysis threshold: {MIN_SOLAR_MW:.1f} MW")
print(f"Half-hours above threshold: {solar_mask.sum()} of {n}")


# ── Find BSPs in this zone from SF file ───────────────────────────────────
sf['branch_col'] = sf.apply(
    lambda r: f"{r['From Bus Number']}_{r['To Bus Number']}_{r['Tertiary Bus Number']}_{r['Circuit ID']}",
    axis=1
)

# BSP main busbars follow pattern XXXX3_MAIN1
bsp_nodes = sf[sf['Node Name'].str.match(r'^[A-Z]{4}3_MAIN1$', na=False)][
    ['Node Number', 'Node Name']
].drop_duplicates()

print(f"\nBSP nodes in zone: {len(bsp_nodes)}")
for _, row in bsp_nodes.iterrows():
    cim = row['Node Name'][:4]
    print(f"  {row['Node Name']} (bus {row['Node Number']}) → {CIM_TO_NAME.get(cim, cim)}")


# ── For each BSP: load transformer flow, run covariance test ──────────────
print(f"\n{'='*80}")
print("BSP-LEVEL COVARIANCE TEST")
print(f"{'='*80}")
print("""
For each BSP with connected solar, we test:
  Cov(BSP_net_import, solar_output) within hour×month bins.

Expected: strongly negative (solar reduces grid import).
The magnitude tells us how much of solar output flows through
the BSP transformer — uncontaminated by ANM branch management.

We also compute the SF-predicted covariance for the BSP transformer
branch and compare against the measured value.
""")

results = []

for _, bsp_row in bsp_nodes.iterrows():
    bus_num  = bsp_row['Node Number']
    cim_code = bsp_row['Node Name'][:4]
    bsp_name = CIM_TO_NAME.get(cim_code, cim_code)

    # Does this BSP have solar generators connected?
    # Check which solar generators have SF to this BSP's branches
    bsp_solar_sf = sf[
        (sf['Node Number'].isin(solar_gens['Bus Number'])) &
        (sf['Node Name'] == bsp_row['Node Name'])  # SF from solar bus to BSP node
    ]

    # More useful: find the BSP transformer branch and get SFs from solar buses to it
    # BSP transformer pattern: XXXX3_#XT0 -> XXXX1_#X10
    bsp_tx_branches = sf[
        sf['From Bus Name'].str.startswith(cim_code + '3_#', na=False) &
        sf['To Bus Name'].str.startswith(cim_code + '1_#', na=False)
    ].copy()

    if len(bsp_tx_branches) == 0:
        # Try alternative pattern
        bsp_tx_branches = sf[
            sf['From Bus Name'].str.startswith(cim_code + '3', na=False) &
            sf['To Bus Name'].str.startswith(cim_code + '1', na=False)
        ].copy()

    # Get solar SFs to the BSP transformer branches
    solar_to_bsp = bsp_tx_branches[
        bsp_tx_branches['Node Number'].isin(solar_gens['Bus Number'])
    ].copy()

    # Compute weighted aggregate SF (solar → BSP transformer)
    if len(solar_to_bsp) > 0:
        agg_sf = 0.0
        total_mw = 0.0
        for _, sf_row in solar_to_bsp.iterrows():
            bus_mw = solar_gens.loc[
                solar_gens['Bus Number'] == sf_row['Node Number'],
                'Site Export Capacity (MW)'
            ].sum()
            agg_sf   += sf_row['Sensitivity Factor MW'] * bus_mw
            total_mw += bus_mw
        predicted_sf = agg_sf / total_mw if total_mw > 0 else np.nan
        solar_at_bsp_mw = total_mw
    else:
        predicted_sf    = np.nan
        solar_at_bsp_mw = 0.0

    # Load BSP transformer flow file
    flow_file_stem = CIM_TO_FLOW_FILE.get(cim_code)
    if flow_file_stem is None:
        print(f"  {bsp_name}: no flow file mapping")
        continue

    flow_path = os.path.join(
        BSP_FLOWS_DIR, f"{flow_file_stem}-transformer-flows.csv"
    )
    if not os.path.exists(flow_path):
        print(f"  {bsp_name}: flow file not found ({flow_path})")
        continue

    flow_df = pd.read_csv(flow_path)
    flow_ts  = pd.to_datetime(flow_df['Timestamp'])

    # Aggregate to net import per timestamp (sum across transformers)
    imports = flow_df[flow_df['Reading Type'] == 'Import'].groupby('Timestamp').agg(
        net_import_mw=('MW', 'sum')
    ).reset_index()
    imports['Timestamp'] = pd.to_datetime(imports['Timestamp'])

    # Align to our half-hourly index
    # Match on timestamp — both should be on HH boundaries
    ts_df = pd.DataFrame({'Timestamp': timestamps, 'idx': np.arange(n)})
    merged = ts_df.merge(imports, on='Timestamp', how='inner')

    if len(merged) < 100:
        print(f"  {bsp_name}: insufficient timestamp overlap ({len(merged)} points)")
        continue

    idx_aligned       = merged['idx'].values
    net_import_aligned = merged['net_import_mw'].values
    solar_aligned      = solar_output[idx_aligned]
    months_aligned     = months[idx_aligned]
    hours_aligned      = hours[idx_aligned]
    solar_mask_aligned = solar_mask[idx_aligned]

    # ── Run covariance test in hour×month bins ─────────────────────────
    bin_results = []

    for month in range(1, 13):
        for hour in range(6, 20):
            mask = solar_mask_aligned & (months_aligned == month) & (hours_aligned == hour)
            if mask.sum() < MIN_OBS_PER_BIN:
                continue

            s = solar_aligned[mask]
            f = net_import_aligned[mask]

            var_s = np.var(s, ddof=1)
            var_f = np.var(f, ddof=1)

            if var_s < MIN_SOLAR_VAR:
                continue

            cov_fs = np.cov(f, s)[0, 1]

            # Empirical sensitivity: how much does net_import change per MW solar?
            # Expected: -1.0 (1 MW solar → 1 MW less import)
            # In practice may differ if solar partly exported or absorbed locally
            empirical_response = cov_fs / var_s

            bin_results.append({
                'month':              month,
                'hour':               hour,
                'n':                  mask.sum(),
                'var_solar':          var_s,
                'var_import':         var_f,
                'cov':                cov_fs,
                'empirical_response': empirical_response,
            })

    if not bin_results:
        print(f"  {bsp_name}: no valid bins")
        continue

    bin_df = pd.DataFrame(bin_results)
    weights = bin_df['n'].values

    mean_response = np.average(bin_df['empirical_response'], weights=weights)
    std_response  = bin_df['empirical_response'].std()
    n_bins        = len(bin_df)

    # Fraction of solar that flows through BSP transformer
    # If mean_response = -0.7, then 70% of solar output changes BSP import
    # (the rest is absorbed by local demand or flows on other paths)
    solar_fraction = abs(mean_response)  # should be ~1.0 for a radial BSP

    # Compare against SF prediction
    # The SF predicts how a 1MW change in generation changes branch flow
    # For the BSP transformer: SF × solar_output should equal the branch flow change
    # Which should equal the import reduction (solar offsets import)
    # So: empirical_response should equal -aggregate_SF (demand convention)
    if not np.isnan(predicted_sf):
        sf_vs_empirical = abs(mean_response) / abs(predicted_sf) if abs(predicted_sf) > 0.01 else np.nan
    else:
        sf_vs_empirical = np.nan

    results.append({
        'bsp':                bsp_name,
        'cim':                cim_code,
        'solar_at_bsp_mw':   solar_at_bsp_mw,
        'predicted_sf':       predicted_sf,
        'mean_response':      mean_response,
        'std_response':       std_response,
        'solar_fraction':     solar_fraction,
        'sf_vs_empirical':    sf_vs_empirical,
        'n_bins':             n_bins,
        'n_obs':              int(bin_df['n'].sum()),
    })

    print(
        f"  {bsp_name:<18} solar={solar_at_bsp_mw:>5.0f}MW  "
        f"response={mean_response:>+7.3f}  "
        f"(expected ~-1.0 for full export)  "
        f"predicted_sf={predicted_sf:>+7.3f}  "
        f"bins={n_bins}"
    )


# ── Summary table ──────────────────────────────────────────────────────────
if not results:
    print("\nNo results — check that BSP flow files exist in BSP_FLOWS_DIR")
else:
    df = pd.DataFrame(results)

    print(f"\n\n{'='*90}")
    print("SUMMARY: BSP-LEVEL SOLAR RESPONSE vs SF PREDICTION")
    print(f"{'='*90}")
    print(f"""
Column definitions:
  Solar MW      — capacity of solar connected at this BSP (from connection queue)
  Pred SF       — SF-weighted aggregate sensitivity factor (solar → BSP transformer)
  Empirical     — measured Cov(import, solar)/Var(solar) from SCADA (unmanaged)
  Solar frac    — |empirical response|: fraction of solar that changes BSP import
                  ~1.0 = all solar flows through BSP tx, <1.0 = partly absorbed locally
  SF ratio      — |empirical| / |predicted SF|: how well the model matches reality
                  1.0 = consistent, <1 = SF overstated, >1 = SF understated
""")

    print(f"{'BSP':<20} {'Solar MW':>9} {'Pred SF':>9} {'Empirical':>10} "
          f"{'Solar frac':>11} {'SF ratio':>9} {'N bins':>7} {'N obs':>7}")
    print("-" * 90)

    for _, r in df.sort_values('solar_at_bsp_mw', ascending=False).iterrows():
        pred   = f"{r['predicted_sf']:>+9.3f}" if not np.isnan(r['predicted_sf']) else "       —"
        ratio  = f"{r['sf_vs_empirical']:>9.2f}"  if not np.isnan(r['sf_vs_empirical']) else "       —"
        print(
            f"{r['bsp']:<20} {r['solar_at_bsp_mw']:>9.1f} {pred} "
            f"{r['mean_response']:>+10.3f} {r['solar_fraction']:>11.3f} "
            f"{ratio} {r['n_bins']:>7} {r['n_obs']:>7}"
        )

    # ── Interpretation ─────────────────────────────────────────────────
    print(f"\n\n{'='*90}")
    print("INTERPRETATION")
    print(f"{'='*90}\n")

    good = df[df['solar_fraction'] > 0.5]
    poor = df[df['solar_fraction'] <= 0.5]

    print(f"BSPs where solar clearly reduces BSP import (fraction > 0.5): {len(good)}")
    print(f"BSPs where solar signal is weak or absent (fraction <= 0.5):  {len(poor)}\n")

    if len(poor) > 0:
        print("Weak signal BSPs (possible explanations):")
        for _, r in poor.iterrows():
            print(f"  {r['bsp']}: response={r['mean_response']:+.3f}")
            if r['solar_at_bsp_mw'] == 0:
                print(f"    → No solar in connection queue at this BSP bus")
            elif abs(r['mean_response']) < 0.1:
                print(f"    → Solar may be on a different bus than BSP main busbar")
                print(f"    → Or ANM curtailment is active even at BSP level")
            else:
                print(f"    → Moderate signal, may be noisy")

    print()

    # ── Compare with branch load test ─────────────────────────────────
    print(f"{'='*90}")
    print("KEY COMPARISON: BSP-level vs branch-level signal")
    print(f"{'='*90}\n")
    print(
        "If BSP-level responses are closer to the expected -1.0 than the\n"
        "branch-level variance ratios were (which mostly showed 0.0-0.15),\n"
        "this confirms that ANM management of branch flows — not SF error —\n"
        "was driving the branch-level test results.\n"
        "\n"
        "If BSP-level responses are also near zero, the explanation is either:\n"
        "  (a) Solar is being curtailed heavily enough to suppress even BSP-level signal\n"
        "  (b) Solar buses are not co-located with BSP main busbars in the model\n"
        "  (c) Significant local demand is absorbing the solar output\n"
    )

    if len(df) > 0:
        median_frac = df['solar_fraction'].median()
        print(f"Median solar fraction across BSPs: {median_frac:.2f}")
        print(f"(Branch-level test gave median variance ratio of ~0.02-0.15)")
        print()
        if median_frac > 0.3:
            print("→ BSP-level signal is substantially stronger than branch-level.")
            print("  This supports the ANM contamination hypothesis.")
            print("  The SFs may be more accurate than the branch-level test suggested.")
        else:
            print("→ BSP-level signal is also weak.")
            print("  ANM contamination alone does not explain the branch-level results.")
            print("  Consider: heavy curtailment of solar, or bus location mismatch.")

    # ── Save ───────────────────────────────────────────────────────────
    out = os.path.join(MVP_DATA_DIR, 'sf_substation_test.csv')
    df.to_csv(out, index=False)
    print(f"\nSaved → {out}")
