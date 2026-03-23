"""
South Wales Grid Connection Screener
=====================================
Streamlit app with headroom analysis AND curtailment estimates.

Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import os

st.set_page_config(
    page_title="Loom Light — Grid Connection Screener",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# LOAD DATA
# ============================================================
DATA_PATH = '../data/south_wales_substations.csv'
CURTAILMENT_PATH = '../data/swansea_north_curtailment.csv'

if not os.path.exists(DATA_PATH):
    DATA_PATH = 'data/south_wales_substations.csv'
    CURTAILMENT_PATH = 'data/swansea_north_curtailment.csv'

@st.cache_data
def load_data():
    df = pd.read_csv(DATA_PATH)
    
    coords = {
        'Abergavenny':    (51.82, -3.02),
        'Ammanford':      (51.80, -3.92),
        'Bridgend':       (51.51, -3.58),
        'Briton Ferry':   (51.63, -3.82),
        'Brynhill':       (51.44, -3.33),
        'Cardiff Central':(51.48, -3.18),
        'Cardiff East':   (51.52, -3.13),
        'Cardiff North':  (51.52, -3.19),
        'Cardiff West':   (51.48, -3.23),
        'Carmarthen':     (51.86, -4.30),
        'Crumlin':        (51.68, -3.13),
        'Dowlais':        (51.75, -3.35),
        'East Aberthaw':  (51.41, -3.39),
        'Ebbw Vale':      (51.78, -3.21),
        'Golden Hill':    (51.70, -4.97),
        'Gowerton East':  (51.66, -4.00),
        'Grange':         (51.55, -3.75),
        'Haverfordwest':  (51.80, -4.97),
        'Hirwaun':        (51.73, -3.47),
        'Lampeter':       (52.12, -4.08),
        'Llanarth':       (52.21, -4.35),
        'Llantarnam':     (51.65, -3.02),
        'Milford Haven':  (51.72, -5.03),
        'Mountain Ash':   (51.68, -3.38),
        'Newport South':  (51.58, -2.97),
        'Panteg':         (51.70, -3.01),
        'Pyle':           (51.53, -3.70),
        'Rhos':           (52.03, -4.45),
        'Sudbrook':       (51.58, -2.72),
        'Swansea North':  (51.67, -3.94),
        'Swansea West':   (51.63, -3.96),
        'Tir John':       (51.63, -3.92),
        'Trostre':        (51.69, -4.15),
        'Upper Boat':     (51.55, -3.35),
        'Ystradgynlais':  (51.77, -3.79),
    }
    
    df['lat'] = df['display_name'].map(lambda x: coords.get(x, (None, None))[0])
    df['lon'] = df['display_name'].map(lambda x: coords.get(x, (None, None))[1])
    
    # Fix: substations with no GCR match should show as 'No data'
    no_gcr = df['connected_mva'].isna() & df['accepted_mva'].isna()
    df.loc[no_gcr, 'headroom_flag'] = 'No data'
    df.loc[no_gcr, 'headroom_mva'] = np.nan
    
    return df

@st.cache_data
def load_curtailment():
    if os.path.exists(CURTAILMENT_PATH):
        return pd.read_csv(CURTAILMENT_PATH)
    return None

df = load_data()
curtailment_df = load_curtailment()


# ============================================================
# SIDEBAR
# ============================================================
st.sidebar.markdown("## ⚡ Loom Light")
st.sidebar.markdown("**Grid Connection Screener**")
st.sidebar.markdown("South Wales · 132/33kV & 132/66kV BSPs")
st.sidebar.divider()

tech_options = ['All'] + sorted([t for t in df['technology'].dropna().unique()])
selected_tech = st.sidebar.selectbox("Filter by technology", tech_options)

headroom_options = ['All', 'Overcommitted', 'Tight', 'Moderate', 'Available']
selected_headroom = st.sidebar.selectbox("Filter by headroom", headroom_options)

st.sidebar.divider()
st.sidebar.markdown("### Test a connection")
test_mw = st.sidebar.number_input("Proposed capacity (MW)", min_value=0, max_value=500, value=0, step=5)
test_tech = st.sidebar.selectbox("Technology", ["Solar", "Onshore Wind", "Battery", "Other"])

# Map sidebar tech names to curtailment CSV tech names
tech_map = {"Solar": "PV", "Onshore Wind": "Wind", "Battery": "BESS", "Other": "Other"}

filtered = df.copy()
if selected_tech != 'All':
    filtered = filtered[filtered['technology'] == selected_tech]
if selected_headroom != 'All':
    filtered = filtered[filtered['headroom_flag'] == selected_headroom]


# ============================================================
# HEADER
# ============================================================
st.markdown("# South Wales Grid Connection Screener")
st.markdown("Transformer ratings · measured flows · connection queue · headroom · curtailment estimates")
st.caption("📅 Flows: Mar 2022 – Apr 2023 · Ratings: Dec 2025 · Queue: Jan 2026 · Curtailment: Mar 2026 (Swansea North zone)")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Substations", len(filtered))
with col2:
    st.metric("Overcommitted", (filtered['headroom_flag'] == 'Overcommitted').sum())
with col3:
    st.metric("Tight", (filtered['headroom_flag'] == 'Tight').sum())
with col4:
    st.metric("Available / Moderate", filtered['headroom_flag'].isin(['Moderate', 'Available']).sum())


# ============================================================
# MAP
# ============================================================
st.markdown("---")

map_df = filtered.dropna(subset=['lat', 'lon']).copy()

# If testing a connection and curtailment data available, add curtailment to tooltip
if test_mw > 0 and curtailment_df is not None:
    curt_tech = tech_map.get(test_tech, 'PV')
    # Find closest MW in curtailment data
    available_mws = sorted(curtailment_df['capacity_mw'].unique())
    closest_mw = min(available_mws, key=lambda x: abs(x - test_mw))
    
    curt_slice = curtailment_df[
        (curtailment_df['technology'] == curt_tech) &
        (curtailment_df['capacity_mw'] == closest_mw)
    ][['substation', 'curtailment_pct', 'binding_branch']].copy()
    curt_slice = curt_slice.rename(columns={'substation': 'display_name'})
    map_df = map_df.merge(curt_slice, on='display_name', how='left')

try:
    import folium
    from streamlit_folium import st_folium
    
    m = folium.Map(location=[51.65, -3.6], zoom_start=8, tiles='CartoDB positron')
    
    flag_colors = {
        'Overcommitted': '#dc3545',
        'Tight':         '#f0a028',
        'Moderate':      '#50a0dc',
        'Available':     '#32b450',
        'No data':       '#999999',
    }
    
    for _, row in map_df.iterrows():
        color = flag_colors.get(row['headroom_flag'], '#999999')
        radius = max(5, min(20, (row.get('total_committed_mva') or 10) / 10))
        
        headroom_str = f"{row['headroom_mva']:.0f}" if pd.notna(row.get('headroom_mva')) else '?'
        rating_str = f"{row['total_nominal_mva']:.0f}" if pd.notna(row.get('total_nominal_mva')) else '?'
        connected_str = f"{row['connected_mva']:.1f}" if pd.notna(row.get('connected_mva')) else '?'
        accepted_str = f"{row['accepted_mva']:.1f}" if pd.notna(row.get('accepted_mva')) else '?'
        peak_str = f"{row['peak_import_mw']:.1f}" if pd.notna(row.get('peak_import_mw')) else '?'
        tech_str = row.get('technology') or '?'
        
        # Add curtailment to popup if available
        curt_html = ""
        if 'curtailment_pct' in row.index and pd.notna(row.get('curtailment_pct')):
            curt_pct = row['curtailment_pct']
            binding = row.get('binding_branch', '?')
            curt_html = f"""
            <hr style="margin: 4px 0;">
            <b style="color: {'#dc3545' if curt_pct > 5 else '#f0a028' if curt_pct > 1 else '#32b450'}">
            Curtailment ({test_mw}MW {test_tech}): {curt_pct:.1f}%</b><br/>
            Binding: {binding}
            """
        
        popup_html = f"""
        <div style="font-family: sans-serif; font-size: 13px; min-width: 220px;">
            <b>{row['display_name']}</b> ({row['voltage_kv']}kV)<br/>
            <hr style="margin: 4px 0;">
            Rating: {rating_str} MVA | Peak: {peak_str} MW<br/>
            <hr style="margin: 4px 0;">
            Connected: {connected_str} MVA<br/>
            Accepted: {accepted_str} MVA<br/>
            <b>Headroom: {headroom_str} MVA</b><br/>
            Status: <b>{row['headroom_flag']}</b><br/>
            Technology: {tech_str}
            {curt_html}
        </div>
        """
        
        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=radius,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            weight=2,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{row['display_name']}: {headroom_str} MVA headroom",
        ).add_to(m)
    
    st_folium(m, width=None, height=500, use_container_width=True)
    
except ImportError:
    st.warning("Install folium and streamlit-folium for the map: `pip install folium streamlit-folium`")
    st.map(map_df, latitude='lat', longitude='lon')

leg1, leg2, leg3, leg4 = st.columns(4)
with leg1:
    st.markdown("🔴 **Overcommitted** — committed > rating")
with leg2:
    st.markdown("🟡 **Tight** — <20 MVA headroom")
with leg3:
    st.markdown("🔵 **Moderate** — 20-50 MVA headroom")
with leg4:
    st.markdown("🟢 **Available** — >50 MVA headroom")

if test_mw > 0:
    st.info(f"Popups show curtailment estimate for **{test_mw} MW {test_tech}** (Swansea North zone only). Click a substation to see details.")


# ============================================================
# SUBSTATION DETAIL
# ============================================================
st.markdown("---")
st.markdown("## Substation Details")

selected_sub = st.selectbox(
    "Select a substation for detail view",
    options=['(Overview table)'] + sorted(filtered['display_name'].tolist()),
)

if selected_sub == '(Overview table)':
    display_cols = [
        'display_name', 'voltage_kv', 'total_nominal_mva', 'peak_import_mw',
        'utilisation_pct', 'connected_mva', 'accepted_mva', 'offered_mva',
        'headroom_mva', 'headroom_flag', 'technology', 'net_exporter',
    ]
    rename = {
        'display_name': 'Substation', 'voltage_kv': 'kV',
        'total_nominal_mva': 'Rating (MVA)', 'peak_import_mw': 'Peak Import (MW)',
        'utilisation_pct': 'Utilisation %', 'connected_mva': 'Connected (MVA)',
        'accepted_mva': 'Accepted (MVA)', 'offered_mva': 'Offered (MVA)',
        'headroom_mva': 'Headroom (MVA)', 'headroom_flag': 'Status',
        'technology': 'Dominant Tech', 'net_exporter': 'Net Exporter',
    }
    table_df = filtered[display_cols].rename(columns=rename).sort_values('Headroom (MVA)')
    
    def color_headroom(val):
        if pd.isna(val): return ''
        if val < 0: return 'background-color: #ffcccc'
        if val < 20: return 'background-color: #fff3cd'
        return ''
    
    styled = table_df.style.map(color_headroom, subset=['Headroom (MVA)'])
    st.dataframe(styled, use_container_width=True, height=600)

else:
    row = filtered[filtered['display_name'] == selected_sub].iloc[0]
    
    st.markdown(f"### {row['display_name']} ({row['voltage_kv']}kV)")
    
    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.markdown("#### Transformer")
        rating = row.get('total_nominal_mva')
        emergency = row.get('total_emergency_mva')
        n_tx = row.get('n_transformers_ltds')
        ratings_detail = row.get('ratings_detail', '')
        st.metric("Nominal Rating", f"{rating:.0f} MVA" if pd.notna(rating) else "Unknown")
        if pd.notna(emergency):
            st.metric("Emergency Rating", f"{emergency:.0f} MVA")
        if pd.notna(n_tx):
            st.caption(f"{int(n_tx)} transformers: {ratings_detail} MVA")
    
    with c2:
        st.markdown("#### Measured Flows")
        peak = row.get('peak_import_mw')
        mean_imp = row.get('mean_import_mw')
        util = row.get('utilisation_pct')
        st.metric("Peak Import", f"{peak:.1f} MW" if pd.notna(peak) else "?")
        st.metric("Mean Import", f"{mean_imp:.1f} MW" if pd.notna(mean_imp) else "?")
        if pd.notna(util):
            st.caption(f"Utilisation: {util:.0f}% of nominal rating")
        if row.get('net_exporter'):
            st.warning("⚡ Net exporter on average — more generation than demand")
    
    with c3:
        st.markdown("#### Connection Queue")
        st.metric("Connected", f"{row.get('connected_mva', 0):.1f} MVA")
        st.metric("Accepted (not built)", f"{row.get('accepted_mva', 0):.1f} MVA")
        offered = row.get('offered_mva', 0)
        enquired = row.get('enquired_mva', 0)
        if pd.notna(offered) and offered > 0:
            st.caption(f"Offered: {offered:.1f} MVA")
        if pd.notna(enquired) and enquired > 0:
            st.caption(f"Enquired: {enquired:.1f} MVA")
        st.caption(f"Dominant technology: {row.get('technology', '?')}")
    
    # Headroom assessment
    st.markdown("---")
    headroom = row.get('headroom_mva')
    flag = row.get('headroom_flag', 'No data')
    
    if flag == 'Overcommitted':
        st.error(f"**{flag}**: Committed generation ({row.get('total_committed_mva', 0):.0f} MVA) exceeds transformer rating ({rating:.0f} MVA) by {abs(headroom):.0f} MVA")
    elif flag == 'Tight':
        st.warning(f"**{flag}**: Only {headroom:.0f} MVA of headroom remaining")
    elif flag in ['Moderate', 'Available']:
        st.success(f"**{flag}**: {headroom:.0f} MVA of headroom available")
    
    # ============================================================
    # CURTAILMENT SECTION (new)
    # ============================================================
    if curtailment_df is not None:
        sub_curt = curtailment_df[curtailment_df['substation'] == selected_sub]
        
        if len(sub_curt) > 0 and sub_curt['curtailment_pct'].notna().any():
            st.markdown("---")
            st.markdown("#### Curtailment Estimates")
            st.caption("Estimated annual curtailment for a new generator at this substation, assuming all accepted projects in the queue are built. Based on NGED sensitivity factors, branch loading, and pre-event limits.")
            
            # Show curtailment table by tech and size
            pivot = sub_curt.pivot_table(
                index='technology', columns='capacity_mw',
                values='curtailment_pct', aggfunc='first'
            )
            
            # Rename for display
            pivot.index = pivot.index.map({'PV': 'Solar', 'Wind': 'Wind', 'BESS': 'Battery'})
            pivot.columns = [f"{int(c)} MW" for c in pivot.columns]
            
            # Format as percentages
            styled_curt = pivot.style.format("{:.1f}%", na_rep="—").background_gradient(
                cmap='RdYlGn_r', vmin=0, vmax=20
            )
            st.dataframe(styled_curt, use_container_width=True)
            
            # Show binding constraint
            binding_info = sub_curt[sub_curt['capacity_mw'] == 20].groupby('technology')['binding_branch'].first()
            if len(binding_info) > 0:
                bindings = [f"{tech}: {branch}" for tech, branch in binding_info.items() if branch != 'None']
                if bindings:
                    st.caption(f"Binding constraints (20MW): {' · '.join(bindings)}")
            
            # If test MW entered, show specific estimate
            if test_mw > 0:
                curt_tech = tech_map.get(test_tech, 'PV')
                available_mws = sorted(sub_curt['capacity_mw'].unique())
                closest_mw = min(available_mws, key=lambda x: abs(x - test_mw))
                
                estimate = sub_curt[
                    (sub_curt['technology'] == curt_tech) &
                    (sub_curt['capacity_mw'] == closest_mw)
                ]
                
                if len(estimate) > 0:
                    e = estimate.iloc[0]
                    if pd.notna(e['curtailment_pct']):
                        curt_pct = e['curtailment_pct']
                        if curt_pct > 5:
                            st.error(f"**{test_mw} MW {test_tech}**: estimated {curt_pct:.1f}% curtailment ({e['curtailed_mwh']:.0f} MWh/year lost)")
                        elif curt_pct > 1:
                            st.warning(f"**{test_mw} MW {test_tech}**: estimated {curt_pct:.1f}% curtailment ({e['curtailed_mwh']:.0f} MWh/year lost)")
                        elif curt_pct > 0:
                            st.info(f"**{test_mw} MW {test_tech}**: estimated {curt_pct:.1f}% curtailment ({e['curtailed_mwh']:.0f} MWh/year lost)")
                        else:
                            st.success(f"**{test_mw} MW {test_tech}**: no curtailment estimated")
                        
                        if e['binding_branch'] != 'None':
                            st.caption(f"Binding constraint: {e['binding_branch']}")
                        
                        if closest_mw != test_mw:
                            st.caption(f"Note: estimate shown for {closest_mw} MW (closest available).")
        else:
            st.markdown("---")
            st.info("Curtailment data not available for this substation. Currently computed for Swansea North GSP group only.")
    
    # Data quality note
    st.markdown("---")
    st.caption(f"Flow data: {row.get('date_from', '?')} to {row.get('date_to', '?')} | {row.get('n_timestamps', '?')} timestamps")
    st.caption("Headroom = nominal transformer rating − (connected + accepted generation). Negative means overcommitted on paper.")
    st.caption("Curtailment estimates use NGED's published sensitivity factors, 2024 branch loading, seasonal PELs, and generic generator profiles. Queue projected using all accepted projects.")


# ============================================================
# FOOTER
# ============================================================
st.markdown("---")
st.caption("**Loom Light** — Grid Connection Intelligence")
st.caption("Data: NGED LTDS Table 2a (ratings), BSP transformer flows (2022-23), Generation Connection Register (Jan 2026), Curtailment analysis data (Mar 2026)")
st.caption("⚠️ Prototype — not for investment decisions. Estimates do not account for LIFO queue position detail, abnormal running, ANM interactions, or demand growth.")
