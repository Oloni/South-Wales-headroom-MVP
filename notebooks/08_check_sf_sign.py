"""
08_check_sf_sign.py
===================
Diagnostic to determine whether sensitivity factors are in
demand convention (needs sign flip for generators) or
generation convention (use as-is).

Tests:
1. Rhos BSP transformer: 117 MVA of generation should push
   power FROM 33kV TO 132kV (positive direction on RHOS3→RHOS1).
   
2. Compare predicted branch flow direction against measured
   branch loading direction.

3. Check NGED's own example: "if a generator increases its
   output by 1MW and the load on a constraint increases by
   0.5MW, then SF = 0.5"
"""

import pandas as pd
import numpy as np
import os

MVP_DATA_DIR = '/Users/leonie/Documents/South_Wales_headroom_MVP/data'

sf = pd.read_csv(os.path.join(MVP_DATA_DIR, 'swansea-north_sensitivity_factors_id_315_2026.csv'))
bl = pd.read_csv(os.path.join(MVP_DATA_DIR, 'swansea-north_branch_load_id_315_2026.csv'))
profiles = pd.read_csv(os.path.join(MVP_DATA_DIR, 'swansea-north_generic_generator_profiles_id_315_2026.csv'))
cq = pd.read_csv(os.path.join(MVP_DATA_DIR, 'swansea-north_connection_queue_id_315_2026.csv'))

FUEL_TO_PROFILE = {'Solar': 'PV', 'Wind': 'Wind', 'BESS': 'BESS Export pu', 'Other': 'Other'}

print("="*70)
print("TEST 1: Physical direction at Rhos BSP transformer")
print("="*70)

# Rhos BSP transformer: RHOS3_#1T0 → RHOS1_#110
# From = 33kV side, To = 132kV side
# Generation at Rhos should push power FROM 33kV TO 132kV
# = FROM node TO node = POSITIVE flow direction

# Find this branch
rhos_tx = sf[(sf['From Bus Name'] == 'RHOS3_#1T0') & (sf['To Bus Name'] == 'RHOS1_#110')]
if len(rhos_tx) == 0:
    rhos_tx = sf[(sf['From Bus Name'].str.contains('RHOS3', na=False)) & 
                 (sf['To Bus Name'].str.contains('RHOS1', na=False))]

if len(rhos_tx) > 0:
    row = rhos_tx.iloc[0]
    branch_col = f"{row['From Bus Number']}_{row['To Bus Number']}_{row['Tertiary Bus Number']}_{row['Circuit ID']}"
    
    print(f"\nBranch: {row['From Bus Name']} → {row['To Bus Name']}")
    print(f"  From = 33kV (RHOS3), To = 132kV (RHOS1)")
    print(f"  Branch column: {branch_col}")
    
    # Get SF from Rhos main busbar to this branch
    rhos_bus = 574500  # RHOS3_MAIN1
    rhos_sf = rhos_tx[rhos_tx['Node Number'] == rhos_bus]
    if len(rhos_sf) > 0:
        sf_val = rhos_sf.iloc[0]['Sensitivity Factor MW']
        print(f"\n  SF from RHOS3_MAIN1 to this branch: {sf_val:.3f}")
        
        print(f"\n  INTERPRETATION:")
        print(f"  If SF is in GENERATION convention (your code uses +SF):")
        print(f"    Generator at Rhos → branch flow changes by +1MW × {sf_val:.3f} = {sf_val:.3f} MW")
        if sf_val < 0:
            print(f"    = NEGATIVE flow = To→From = 132kV→33kV")
            print(f"    ❌ WRONG: generation should push power FROM 33kV TO 132kV (positive)")
        else:
            print(f"    = POSITIVE flow = From→To = 33kV→132kV")
            print(f"    ✓ CORRECT: generation pushes power from 33kV to 132kV")
        
        print(f"\n  If SF is in DEMAND convention (needs sign flip, use -SF):")
        print(f"    Generator at Rhos → branch flow changes by +1MW × {-sf_val:.3f} = {-sf_val:.3f} MW")
        if -sf_val > 0:
            print(f"    = POSITIVE flow = From→To = 33kV→132kV")
            print(f"    ✓ CORRECT: generation pushes power from 33kV to 132kV")
        else:
            print(f"    = NEGATIVE flow = To→From = 132kV→33kV")
            print(f"    ❌ WRONG")
    
    # Check actual measured flow on this branch
    if branch_col in bl.columns:
        actual = bl[branch_col].values
        print(f"\n  MEASURED BRANCH LOADING (SCADA):")
        print(f"    Mean flow: {actual.mean():.1f} MW")
        print(f"    Peak flow: {actual.max():.1f} MW")
        print(f"    Min flow:  {actual.min():.1f} MW")
        print(f"    % of time positive (From→To = 33kV→132kV): {100*(actual>0).sum()/len(actual):.0f}%")
        print(f"    % of time negative (To→From = 132kV→33kV): {100*(actual<0).sum()/len(actual):.0f}%")
        
        # Rhos has 39.2 MVA connected generation
        # If generation dominates, flow should be NEGATIVE (export from 33kV to 132kV... wait)
        # Actually: From=33kV, To=132kV. Power flowing from 33kV to 132kV = FROM→TO = POSITIVE
        # So if Rhos is a net exporter (mean import = -8.3 MW), the BSP transformer should show
        # positive flow (33kV → 132kV = export to grid)
        if actual.mean() > 0:
            print(f"    → Mean flow is POSITIVE (33kV→132kV = exporting to grid)")
            print(f"    → Consistent with Rhos being a net exporter (-8.3 MW mean import)")
        else:
            print(f"    → Mean flow is NEGATIVE (132kV→33kV = importing from grid)")
            print(f"    → This would mean Rhos is a net IMPORTER, but substation data says -8.3 MW (exporter)")
            print(f"    → Check: does the substation data measure at a different point?")
else:
    print("  Rhos BSP transformer not found in SF data")


print("\n\n" + "="*70)
print("TEST 2: Swansea West BSP transformer")
print("="*70)

# SWAW3_#2T0 → SWAW1_213 (the binding constraint from our curtailment)
swaw_tx = sf[(sf['From Bus Name'].str.contains('SWAW3', na=False)) & 
             (sf['To Bus Name'].str.contains('SWAW1', na=False))]

swaw_buses = sf[sf['Node Name'].str.startswith('SWAW', na=False)][['Node Number', 'Node Name']].drop_duplicates()
print(f"\nSWAW nodes: {swaw_buses.to_string(index=False)}")

for _, row in swaw_tx.drop_duplicates(subset=['From Bus Name', 'To Bus Name']).iterrows():
    branch_col = f"{row['From Bus Number']}_{row['To Bus Number']}_{row['Tertiary Bus Number']}_{row['Circuit ID']}"
    
    print(f"\nBranch: {row['From Bus Name']} → {row['To Bus Name']}")
    
    # Get SF from SWAW main busbar
    for swaw_bus_row in swaw_buses.itertuples():
        bus_sf = sf[(sf['Node Number'] == swaw_bus_row[1]) & 
                    (sf['From Bus Name'] == row['From Bus Name']) &
                    (sf['To Bus Name'] == row['To Bus Name'])]
        if len(bus_sf) > 0:
            sv = bus_sf.iloc[0]['Sensitivity Factor MW']
            print(f"  SF from {swaw_bus_row[2]} (bus {swaw_bus_row[1]}): {sv:.3f}")
    
    if branch_col in bl.columns:
        actual = bl[branch_col].values
        print(f"  Measured: mean={actual.mean():.1f} MW, range=[{actual.min():.1f}, {actual.max():.1f}]")
        print(f"  % positive: {100*(actual>0).sum()/len(actual):.0f}%")


print("\n\n" + "="*70)
print("TEST 3: Queue projection direction check")
print("="*70)

# Take the Rhos BSP transformer
# Project the connected generation (30MW solar at bus 2905 is in this zone)
# and check: does the projected flow go in the physically correct direction?

rhos_tx_rows = sf[(sf['From Bus Name'].str.contains('RHOS3_#1T0', na=False)) & 
                  (sf['To Bus Name'].str.contains('RHOS1_#110', na=False))]

if len(rhos_tx_rows) > 0:
    row = rhos_tx_rows.iloc[0]
    branch_col = f"{row['From Bus Number']}_{row['To Bus Number']}_{row['Tertiary Bus Number']}_{row['Circuit ID']}"
    
    if branch_col in bl.columns:
        original_flow = bl[branch_col].values.copy()
        
        # Get all connected generators in this zone
        connected = cq[cq['Status'] == 'Recently Connected']
        print(f"\nConnected generators in Swansea North:")
        for _, g in connected.iterrows():
            print(f"  {g['Site Export Capacity (MW)']:.1f} MW {g['Fuel type']} at bus {g['Bus Number']}")
            
            # Get this generator's SF to the Rhos transformer
            gen_sf = sf[(sf['Node Number'] == g['Bus Number']) & 
                       (sf['From Bus Name'] == row['From Bus Name']) &
                       (sf['To Bus Name'] == row['To Bus Name'])]
            if len(gen_sf) > 0:
                sv = gen_sf.iloc[0]['Sensitivity Factor MW']
                print(f"    SF to Rhos transformer: {sv:.3f}")
                print(f"    With CURRENT code (+SF): flow change = {g['Site Export Capacity (MW)']:.0f} × profile × {sv:.3f}")
                print(f"    With FLIPPED code (-SF): flow change = {g['Site Export Capacity (MW)']:.0f} × profile × {-sv:.3f}")
            else:
                print(f"    No SF to Rhos transformer (too remote)")
        
        # Now check: Rhos has its own generators. What SF does RHOS3_MAIN1 have?
        rhos_own_sf = sf[(sf['Node Number'] == 574500) &
                        (sf['From Bus Name'] == row['From Bus Name']) &
                        (sf['To Bus Name'] == row['To Bus Name'])]
        if len(rhos_own_sf) > 0:
            sv = rhos_own_sf.iloc[0]['Sensitivity Factor MW']
            print(f"\n  RHOS3_MAIN1 SF to its own transformer: {sv:.3f}")
            print(f"  If a 10MW generator connects at Rhos:")
            print(f"    Current code: flow += 10 × {sv:.3f} = {10*sv:.1f} MW")
            print(f"    Flipped code: flow -= 10 × {sv:.3f} = {-10*sv:.1f} MW")
            print(f"    (Positive = 33kV→132kV = export to grid)")
            print(f"    A generator at Rhos SHOULD increase export (positive flow)")
            if sv < 0:
                print(f"    Current code gives NEGATIVE change → WRONG (reduces export)")
                print(f"    Flipped code gives POSITIVE change → CORRECT (increases export)")
                print(f"\n    ⚠️  CONCLUSION: SF is in DEMAND convention. Code needs sign flip.")
            else:
                print(f"    Current code gives POSITIVE change → CORRECT (increases export)")
                print(f"\n    ✓  CONCLUSION: SF is in GENERATION convention. Code is correct.")


print("\n\n" + "="*70)
print("TEST 4: Cross-check with NGED guidance Section 3.4.1")  
print("="*70)
print("""
NGED defines SF as: ΔPower flow at branch / ΔLoad at node

"Load" in NGED terminology = demand (HV to LV = positive).
See Section 3.2.1: "The sign associated to this load is based on 
the convention of power flow direction of positive for demand 
i.e. HV to LV."

So: SF = ΔBranch flow / ΔDemand

A generator DECREASES demand (or equivalently, is negative demand).
Therefore: Generator effect on branch = -SF × gen_output

BUT Section 3.4.2 says: "if a generator increases its output by 
1MW and the load on a constraint increases by 0.5MW, then the 
sensitivity factor for a generator at that point on the network 
to that branch will be 0.5"

This example uses "load on a constraint" which could mean branch 
loading (which increases when the generator exports more through it),
not demand. If so, the SF might already be in generation convention.

The physical test above resolves this ambiguity.
""")
