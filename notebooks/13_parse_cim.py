"""
13_parse_cim.py
===============
Parses the NGED LTDS CIM file for South Wales and extracts the
network model into a set of clean DataFrames that can be used to
build a pandapower network for AC power flow and SF validation.

Extracts:
  - Buses (ConnectivityNodes + BusbarSections)
  - AC Lines (ACLineSegments with r, x, bch, length)
  - Transformers (PowerTransformers with per-end r, x, ratedU, ratedS)
  - Topology (Terminal connections between equipment and nodes)
  - Voltage levels and substations

Then cross-references against the Swansea North SF bus names to show
how much of the ANM zone network is present in the CIM.

Outputs:
  - data/cim_buses.csv
  - data/cim_lines.csv
  - data/cim_transformers.csv
  - data/cim_swansea_north_subgraph.csv  (nodes in Swansea North zone)
"""

import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
import os
import re
from collections import defaultdict

CIM_FILE    = '/Users/leonie/Documents/South_Wales_headroom_MVP/data/LTDS_SWALES_2025-02_EQ_2025-09-19_v1.0.xml'
SF_FILE     = '/Users/leonie/Documents/South_Wales_headroom_MVP/data/swansea-north_sensitivity_factors_id_315_2026.csv'
MVP_DATA_DIR = '/Users/leonie/Documents/South_Wales_headroom_MVP/data'

# CIM namespace map
NS = {
    'cim': 'http://iec.ch/TC57/CIM100#',
    'eu':  'http://iec.ch/TC57/CIM100-European#',
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'md':  'http://iec.ch/TC57/61970-552/ModelDescription/1#',
    'gb':  'http://ofgem.gov.uk/ns/CIM/LTDS/Extensions#',
}

def get_id(element):
    """Extract mRID from rdf:ID attribute."""
    raw = element.get('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}ID', '')
    return raw.lstrip('_')

def get_ref(element, tag):
    """Extract the referenced mRID from a resource attribute."""
    child = element.find(tag, NS)
    if child is None:
        return None
    raw = child.get('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource', '')
    return raw.lstrip('#_')

def get_text(element, tag):
    child = element.find(tag, NS)
    return child.text.strip() if child is not None and child.text else None

def get_float(element, tag):
    v = get_text(element, tag)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


print("Parsing CIM file...")
print(f"  {CIM_FILE}")

tree = ET.parse(CIM_FILE)
root = tree.getroot()
print(f"  Root tag: {root.tag}")
print(f"  Children: {len(list(root))}")


# ── 1. Base voltages ───────────────────────────────────────────────────────
print("\n[1] Base voltages...")
base_voltages = {}   # mRID -> kV
for bv in root.findall('cim:BaseVoltage', NS):
    mid  = get_id(bv)
    name = get_text(bv, 'cim:IdentifiedObject.name')
    kv   = get_float(bv, 'cim:BaseVoltage.nominalVoltage')
    base_voltages[mid] = kv

print(f"  Found {len(base_voltages)} base voltages: {sorted(set(base_voltages.values()))}")


# ── 2. Substations ────────────────────────────────────────────────────────
print("\n[2] Substations...")
substations = {}   # mRID -> name
for sub in root.findall('cim:Substation', NS):
    mid  = get_id(sub)
    name = get_text(sub, 'cim:IdentifiedObject.name')
    substations[mid] = name
print(f"  Found {len(substations)} substations")

# SubGeographicalRegions (GSP zones)
regions = {}
for reg in root.findall('cim:SubGeographicalRegion', NS):
    mid  = get_id(reg)
    name = get_text(reg, 'cim:IdentifiedObject.name')
    regions[mid] = name
print(f"  Found {len(regions)} SubGeographicalRegions (zones): {list(regions.values())[:8]}...")


# ── 3. Voltage levels ─────────────────────────────────────────────────────
print("\n[3] Voltage levels...")
voltage_levels = {}   # mRID -> {substation, base_voltage_kv}
for vl in root.findall('cim:VoltageLevel', NS):
    mid  = get_id(vl)
    sub_ref = get_ref(vl, 'cim:VoltageLevel.Substation')
    bv_ref  = get_ref(vl, 'cim:VoltageLevel.BaseVoltage')
    voltage_levels[mid] = {
        'substation': sub_ref,
        'kv': base_voltages.get(bv_ref),
    }
print(f"  Found {len(voltage_levels)} voltage levels")


# ── 4. Connectivity nodes (buses) ─────────────────────────────────────────
print("\n[4] Connectivity nodes...")
conn_nodes = {}   # mRID -> {name, container}
for cn in root.findall('cim:ConnectivityNode', NS):
    mid  = get_id(cn)
    name = get_text(cn, 'cim:IdentifiedObject.name')
    container_ref = get_ref(cn, 'cim:ConnectivityNode.ConnectivityNodeContainer')
    conn_nodes[mid] = {
        'name':      name,
        'container': container_ref,
    }
print(f"  Found {len(conn_nodes)} connectivity nodes")


# ── 5. Terminals ──────────────────────────────────────────────────────────
print("\n[5] Terminals...")
terminals = {}   # mRID -> {equipment, connectivity_node, seq}
for t in root.findall('cim:Terminal', NS):
    mid   = get_id(t)
    eq    = get_ref(t, 'cim:Terminal.ConductingEquipment')
    cn    = get_ref(t, 'cim:Terminal.ConnectivityNode')
    seq   = get_text(t, 'cim:ACDCTerminal.sequenceNumber')
    terminals[mid] = {
        'equipment': eq,
        'node':      cn,
        'seq':       int(seq) if seq else None,
    }

# Build equipment -> terminals lookup
eq_terminals = defaultdict(list)
for tid, tdata in terminals.items():
    if tdata['equipment']:
        eq_terminals[tdata['equipment']].append((tdata['seq'], tdata['node'], tid))

# Sort by sequence number
for eq in eq_terminals:
    eq_terminals[eq].sort(key=lambda x: x[0] or 0)

print(f"  Found {len(terminals)} terminals")


# ── 6. AC Line Segments ───────────────────────────────────────────────────
print("\n[6] ACLineSegments...")
line_records = []

for seg in root.findall('cim:ACLineSegment', NS):
    mid    = get_id(seg)
    name   = get_text(seg, 'cim:IdentifiedObject.name')
    r      = get_float(seg, 'cim:ACLineSegment.r')
    x      = get_float(seg, 'cim:ACLineSegment.x')
    bch    = get_float(seg, 'cim:ACLineSegment.bch')
    length = get_float(seg, 'cim:Conductor.length')
    bv_ref = get_ref(seg, 'cim:ConductingEquipment.BaseVoltage')
    kv     = base_voltages.get(bv_ref)
    container_ref = get_ref(seg, 'cim:Equipment.EquipmentContainer')

    # Get the two terminal nodes
    term_list = eq_terminals.get(mid, [])
    from_node = term_list[0][1] if len(term_list) > 0 else None
    to_node   = term_list[1][1] if len(term_list) > 1 else None
    from_name = conn_nodes.get(from_node, {}).get('name') if from_node else None
    to_name   = conn_nodes.get(to_node, {}).get('name') if to_node else None

    line_records.append({
        'mrid':       mid,
        'name':       name,
        'from_node':  from_node,
        'to_node':    to_node,
        'from_name':  from_name,
        'to_name':    to_name,
        'r_ohm':      r,
        'x_ohm':      x,
        'bch_s':      bch,
        'length_km':  length,
        'kv':         kv,
        'container':  container_ref,
    })

df_lines = pd.DataFrame(line_records)
print(f"  Found {len(df_lines)} ACLineSegments")
print(f"  Voltage levels: {sorted(df_lines['kv'].dropna().unique())}")
print(f"  Lines with missing r/x: {df_lines['r_ohm'].isna().sum()}")


# ── 7. Power Transformers ─────────────────────────────────────────────────
print("\n[7] PowerTransformers...")
tx_ends = defaultdict(list)

for end in root.findall('cim:PowerTransformerEnd', NS):
    mid    = get_id(end)
    tx_ref = get_ref(end, 'cim:PowerTransformerEnd.PowerTransformer')
    end_no = get_text(end, 'cim:TransformerEnd.endNumber')
    r      = get_float(end, 'cim:PowerTransformerEnd.r')
    x      = get_float(end, 'cim:PowerTransformerEnd.x')
    b      = get_float(end, 'cim:PowerTransformerEnd.b')
    rated_s = get_float(end, 'cim:PowerTransformerEnd.ratedS')
    rated_u = get_float(end, 'cim:PowerTransformerEnd.ratedU')
    term_ref = get_ref(end, 'cim:TransformerEnd.Terminal')
    bv_ref   = get_ref(end, 'cim:TransformerEnd.BaseVoltage')
    kv       = base_voltages.get(bv_ref)

    # Get connectivity node from terminal
    node = terminals.get(term_ref, {}).get('node') if term_ref else None
    node_name = conn_nodes.get(node, {}).get('name') if node else None

    tx_ends[tx_ref].append({
        'end_mrid':  mid,
        'end_no':    int(end_no) if end_no else None,
        'r_ohm':     r,
        'x_ohm':     x,
        'b_s':       b,
        'rated_s_mva': rated_s,
        'rated_u_kv':  rated_u,
        'kv':          kv,
        'node':        node,
        'node_name':   node_name,
    })

tx_records = []
for tx in root.findall('cim:PowerTransformer', NS):
    mid  = get_id(tx)
    name = get_text(tx, 'cim:IdentifiedObject.name')
    container_ref = get_ref(tx, 'cim:Equipment.EquipmentContainer')

    ends = sorted(tx_ends.get(mid, []), key=lambda e: e['end_no'] or 0)
    n_ends = len(ends)

    row = {
        'mrid':      mid,
        'name':      name,
        'n_windings': n_ends,
        'container': container_ref,
    }

    for i, end in enumerate(ends[:3], 1):
        row[f'end{i}_node']     = end['node']
        row[f'end{i}_name']     = end['node_name']
        row[f'end{i}_kv']       = end['rated_u_kv']
        row[f'end{i}_r']        = end['r_ohm']
        row[f'end{i}_x']        = end['x_ohm']
        row[f'end{i}_rated_s']  = end['rated_s_mva']

    tx_records.append(row)

df_tx = pd.DataFrame(tx_records)
print(f"  Found {len(df_tx)} PowerTransformers")
print(f"  2-winding: {(df_tx['n_windings']==2).sum()}")
print(f"  3-winding: {(df_tx['n_windings']==3).sum()}")
print(f"  Voltage pairs (kV): {df_tx[['end1_kv','end2_kv']].drop_duplicates().values[:8]}")


# ── 8. Cross-reference with Swansea North SF bus names ────────────────────
print("\n[8] Cross-referencing with Swansea North SF data...")

sf = pd.read_csv(SF_FILE)
sf_bus_names = set(sf['From Bus Name'].dropna()) | set(sf['To Bus Name'].dropna())
sf_bus_names = {n for n in sf_bus_names if isinstance(n, str)}

# CIM node names
cim_node_names = {v['name'] for v in conn_nodes.values() if v['name']}

# Direct matches
direct_matches = sf_bus_names & cim_node_names
print(f"\n  SF unique bus names: {len(sf_bus_names)}")
print(f"  CIM connectivity node names: {len(cim_node_names)}")
print(f"  Direct name matches: {len(direct_matches)}")

# Show matched names
print(f"\n  Matched SF bus names (sample):")
for name in sorted(direct_matches)[:20]:
    print(f"    {name}")

# Unmatched SF names
unmatched = sf_bus_names - cim_node_names
print(f"\n  Unmatched SF bus names ({len(unmatched)} total, sample):")
for name in sorted(unmatched)[:20]:
    print(f"    {name}")


# ── 9. Extract Swansea North subgraph ─────────────────────────────────────
print("\n[9] Extracting Swansea North subgraph...")

# Find all CIM lines where either endpoint matches a Swansea North SF bus name
swan_lines = df_lines[
    df_lines['from_name'].isin(sf_bus_names) |
    df_lines['to_name'].isin(sf_bus_names)
].copy()

swan_tx = df_tx[
    df_tx['end1_name'].isin(sf_bus_names) |
    df_tx['end2_name'].isin(sf_bus_names) |
    df_tx.get('end3_name', pd.Series(dtype=str)).isin(sf_bus_names)
].copy()

print(f"  Lines with at least one Swansea North endpoint: {len(swan_lines)}")
print(f"  Transformers with at least one Swansea North endpoint: {len(swan_tx)}")

# Voltage breakdown for Swansea North lines
print(f"\n  Swansea North line voltages:")
for kv, count in swan_lines['kv'].value_counts().items():
    print(f"    {kv} kV: {count} segments")

# Sample of matched lines
print(f"\n  Sample Swansea North lines:")
print(swan_lines[['name', 'from_name', 'to_name', 'r_ohm', 'x_ohm', 'kv']].head(10).to_string(index=False))

# Sample of matched transformers
print(f"\n  Sample Swansea North transformers:")
tx_cols = ['name', 'end1_name', 'end2_name', 'end1_kv', 'end2_kv', 'end1_r', 'end1_x', 'end1_rated_s']
print(swan_tx[tx_cols].head(10).to_string(index=False))


# ── 10. R/X ratio analysis ────────────────────────────────────────────────
print(f"\n[10] R/X ratio analysis (why DC load flow breaks down)...")
print("""
DC load flow assumes R << X (pure inductive network).
Transmission networks: R/X ~ 0.1-0.3 (DC approx reasonable)
Distribution networks: R/X ~ 0.5-2.0 (DC approx breaks down significantly)
""")

valid_lines = df_lines[(df_lines['r_ohm'] > 0) & (df_lines['x_ohm'] > 0)].copy()
valid_lines['rx_ratio'] = valid_lines['r_ohm'] / valid_lines['x_ohm']

for kv in sorted(valid_lines['kv'].dropna().unique()):
    subset = valid_lines[valid_lines['kv'] == kv]['rx_ratio']
    if len(subset) > 0:
        print(f"  {kv:>6.1f} kV: median R/X = {subset.median():.2f}, "
              f"mean = {subset.mean():.2f}, "
              f"range = [{subset.min():.2f}, {subset.max():.2f}]  "
              f"(n={len(subset)})")

# Swansea North specifically
swan_valid = swan_lines[(swan_lines['r_ohm'] > 0) & (swan_lines['x_ohm'] > 0)].copy()
swan_valid['rx_ratio'] = swan_valid['r_ohm'] / swan_valid['x_ohm']
print(f"\n  Swansea North zone specifically:")
print(f"    Median R/X = {swan_valid['rx_ratio'].median():.2f}")
print(f"    Mean R/X   = {swan_valid['rx_ratio'].mean():.2f}")
pct_high = (swan_valid['rx_ratio'] > 0.5).sum() / len(swan_valid) * 100
print(f"    % of lines with R/X > 0.5: {pct_high:.0f}%")
print(f"\n  For context: DC load flow error scales roughly as R/X.")
print(f"  At R/X=1.0, DC SF can be wrong by 30-50% for individual branches.")


# ── 11. Save ───────────────────────────────────────────────────────────────
print("\n[11] Saving...")

df_buses = pd.DataFrame([
    {'mrid': mid, 'name': d['name'], 'container': d['container']}
    for mid, d in conn_nodes.items()
])

df_lines.to_csv(os.path.join(MVP_DATA_DIR, 'cim_lines.csv'), index=False)
df_tx.to_csv(os.path.join(MVP_DATA_DIR, 'cim_transformers.csv'), index=False)
df_buses.to_csv(os.path.join(MVP_DATA_DIR, 'cim_buses.csv'), index=False)
swan_lines.to_csv(os.path.join(MVP_DATA_DIR, 'cim_swansea_north_lines.csv'), index=False)
swan_tx.to_csv(os.path.join(MVP_DATA_DIR, 'cim_swansea_north_transformers.csv'), index=False)

print(f"  cim_buses.csv              ({len(df_buses)} rows)")
print(f"  cim_lines.csv              ({len(df_lines)} rows)")
print(f"  cim_transformers.csv       ({len(df_tx)} rows)")
print(f"  cim_swansea_north_lines.csv       ({len(swan_lines)} rows)")
print(f"  cim_swansea_north_transformers.csv ({len(swan_tx)} rows)")

print(f"""
{'='*70}
SUMMARY
{'='*70}

Network scale:
  {len(conn_nodes):>6} connectivity nodes (buses)
  {len(df_lines):>6} AC line segments
  {len(df_tx):>6} power transformers
  {len(substations):>6} substations

Swansea North zone subgraph:
  {len(direct_matches):>6} SF bus names matched directly in CIM
  {len(swan_lines):>6} CIM lines with Swansea North endpoints
  {len(swan_tx):>6} CIM transformers with Swansea North endpoints

Key finding:
  33kV distribution network median R/X = {swan_valid['rx_ratio'].median():.2f}
  This is {swan_valid['rx_ratio'].median() / 0.15:.0f}x higher than typical 132kV transmission (R/X~0.15)
  DC load flow error scales with R/X — this is the root cause of
  SF inaccuracy in distribution networks under IBR conditions.

Next step: run 14_build_pandapower.py to build the AC power flow model.
""")
