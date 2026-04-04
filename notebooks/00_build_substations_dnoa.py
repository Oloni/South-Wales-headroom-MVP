"""
00_build_substations_dnoa.py
============================
Adds DNOA (Distribution Network Options Assessment) constraint info
to south_wales_substations.csv.

Maps DNOA scheme names to our substation display names and adds:
  - dnoa_scheme: the DNOA scheme name
  - dnoa_decision: Reinforce / Reinforce with Flexibility / Flexibility / Signposting / Remove
  - dnoa_reinforce_by: earliest possible reinforcement completion year
  - dnoa_constraint_season: Winter / Summer / Winter/Summer
  - dnoa_cmz: Constraint Management Zone code (if any)
  - dnoa_flex_period: projected flexibility start-end (if any)

Run AFTER 00_build_substations_anm.py (preserves ANM flags).
"""

import pandas as pd
import os

MVP_DATA_DIR = '/Users/leonie/Documents/South_Wales_headroom_MVP/data'

subs = pd.read_csv(os.path.join(MVP_DATA_DIR, 'south_wales_substations.csv'))
dnoa = pd.read_csv(os.path.join(MVP_DATA_DIR, 'dnoa_august_2023.csv'))

print(f"Loaded {len(subs)} substations")

# Filter to South Wales, Best View scenario (avoid duplicates)
sw_dnoa = dnoa[(dnoa['Licence_area'] == 'South Wales') & (dnoa['Scenario'] == 'Best View')].copy()
print(f"South Wales DNOA entries (Best View): {len(sw_dnoa)}")

# ============================================================
# MAP DNOA SCHEME NAMES TO SUBSTATION DISPLAY NAMES
# ============================================================
# Some are direct matches, some are BSP-level constraints that
# affect multiple substations, some are circuit-level constraints
# that we map to the nearest BSP.

DNOA_TO_SUBSTATIONS = {
    'Rhos BSP': ['Rhos'],
    'Rhos - Newcastle Emlyn': ['Rhos'],  # circuit constraint near Rhos
    'Pembroke': ['Golden Hill', 'Haverfordwest', 'Milford Haven'],  # GSP-level constraint
    'Milford Haven BSP': ['Milford Haven', 'Golden Hill'],
    'Abergavenny BSP': ['Abergavenny'],
    'Abergavenny - Crickhowell': ['Abergavenny'],
    'Cardiff North': ['Cardiff North'],
    'East Aberthaw': ['East Aberthaw'],
    'Mountain Ash': ['Mountain Ash'],
    'Ashgrove': [],  # ASHG is a primary, not in our BSP list — but check
    'Haverfordwest - Brawdy': ['Haverfordwest'],
    'Newport West': ['Newport South'],  # closest BSP
    'Pantyffynnon': ['Ammanford'],  # Pantyffynnon is near Ammanford BSP
    'Trevaughan': ['Carmarthen'],  # Trevaughan is near Carmarthen
    'Ravenhill': ['Swansea North'],  # Ravenhill is in Swansea area
    'Aberaeron': ['Lampeter', 'Llanarth'],  # Aberaeron feeds from these BSPs
    'Llanfyrnach': ['Lampeter'],  # Llanfyrnach is in the Lampeter area
    'Llandrindod - Rhayader': [],  # Mid Wales, not in our South Wales BSP coverage
    'Sully Tee': ['East Aberthaw'],  # Sully is near East Aberthaw
}

# Also check if ASHG appears in the curtailment data as a primary substation
# It does — ASHG shows 9.6% solar. But it's not in our BSP headroom table.
# We'll note it in the DNOA mapping but can't add it to the substations CSV.

# ============================================================
# ADD DNOA COLUMNS
# ============================================================
subs['dnoa_scheme'] = None
subs['dnoa_decision'] = None
subs['dnoa_reinforce_by'] = None
subs['dnoa_constraint_season'] = None
subs['dnoa_cmz'] = None
subs['dnoa_flex_period'] = None

matched = 0
for _, dnoa_row in sw_dnoa.iterrows():
    scheme = dnoa_row['Scheme_name']
    target_subs = DNOA_TO_SUBSTATIONS.get(scheme, [])

    for sub_name in target_subs:
        idx = subs[subs['display_name'] == sub_name].index
        if len(idx) > 0:
            i = idx[0]
            # If already has a DNOA entry, append (some subs have multiple constraints)
            existing = subs.at[i, 'dnoa_scheme']
            if existing and str(existing) != 'nan' and str(existing) != 'None':
                subs.at[i, 'dnoa_scheme'] = f"{existing}; {scheme}"
                subs.at[i, 'dnoa_decision'] = f"{subs.at[i, 'dnoa_decision']}; {dnoa_row['DNOA_decision']}"
            else:
                subs.at[i, 'dnoa_scheme'] = scheme
                subs.at[i, 'dnoa_decision'] = dnoa_row['DNOA_decision']
                subs.at[i, 'dnoa_reinforce_by'] = dnoa_row['Earliest_possible_reinforcement_completion']
                subs.at[i, 'dnoa_constraint_season'] = dnoa_row['Constraint_season']
                cmz = dnoa_row['CMZ_Code']
                subs.at[i, 'dnoa_cmz'] = cmz if cmz != '-' else None
                flex_start = dnoa_row['Projected_flexibility_start']
                flex_end = dnoa_row['Projected_flexibility_end']
                if flex_start != '-' and flex_start != '---':
                    subs.at[i, 'dnoa_flex_period'] = f"{flex_start} to {flex_end}"
            matched += 1

print(f"\nMatched {matched} DNOA entries to substations")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "="*70)
print("DNOA CONSTRAINTS MAPPED TO SUBSTATIONS")
print("="*70)

dnoa_subs = subs[subs['dnoa_scheme'].notna() & (subs['dnoa_scheme'] != 'None')]
for _, r in dnoa_subs.sort_values('display_name').iterrows():
    print(f"  {r['display_name']:<20} Scheme: {r['dnoa_scheme']}")
    print(f"  {'':20} Decision: {r['dnoa_decision']}, Reinforce by: {r['dnoa_reinforce_by']}, Season: {r['dnoa_constraint_season']}")
    if r.get('dnoa_cmz') and str(r['dnoa_cmz']) != 'nan':
        print(f"  {'':20} CMZ: {r['dnoa_cmz']}")
    if r.get('dnoa_flex_period') and str(r['dnoa_flex_period']) != 'nan':
        print(f"  {'':20} Flexibility: {r['dnoa_flex_period']}")
    print()

n_with_dnoa = len(dnoa_subs)
n_reinforce = len(dnoa_subs[dnoa_subs['dnoa_decision'].str.contains('Reinforce', na=False)])
print(f"Substations with DNOA constraints: {n_with_dnoa}")
print(f"Substations with planned reinforcement: {n_reinforce}")

# Substations NOT in DNOA but with high curtailment
print("\nHigh-curtailment substations NOT in DNOA (potential gaps):")
# Would need curtailment data to check — just flag it
print("  (Check against curtailment results for substations like Cardiff Central, NANG, CLAS)")

# ============================================================
# SAVE
# ============================================================
subs.to_csv(os.path.join(MVP_DATA_DIR, 'south_wales_substations.csv'), index=False)
print(f"\nSaved updated substations table with DNOA columns")
