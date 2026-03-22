"""
South Wales Grid Connection Screener
=====================================
Streamlit app that displays substation-level headroom, queue data,
and measured flows for the South Wales 33kV/132kV network.

Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(
    page_title="Loom Light — Grid Connection Screener",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Force light theme
st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background-color: #ffffff; }
    [data-testid="stSidebar"] { background-color: #f8f9fa; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# LOAD DATA
# ============================================================
DATA_PATH = '../data/south_wales_substations.csv'

# Also try project root path if running from there
import os
if not os.path.exists(DATA_PATH):
    DATA_PATH = 'data/south_wales_substations.csv'

@st.cache_data
def load_data():
    df = pd.read_csv(DATA_PATH)
    
    # Add coordinates (from ECR project locations — average per BSP)
    # These are approximate: centroid of projects connected at each BSP
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
    
    # Fix: substations with no GCR match should show as 'No data' not 'Available'
    # They appear to have full headroom but really we just don't have queue info
    no_gcr = df['connected_mva'].isna() & df['accepted_mva'].isna()
    df.loc[no_gcr, 'headroom_flag'] = 'No data'
    df.loc[no_gcr, 'headroom_mva'] = np.nan
    
    return df

df = load_data()


# ============================================================
# SIDEBAR — FILTERS
# ============================================================
st.sidebar.markdown("## ⚡ Loom Light")
st.sidebar.markdown("**Grid Connection Screener**")
st.sidebar.markdown("South Wales · 132/33kV & 132/66kV BSPs")
st.sidebar.divider()

# Technology filter
tech_options = ['All'] + sorted([t for t in df['technology'].dropna().unique()])
selected_tech = st.sidebar.selectbox("Filter by technology", tech_options)

# Headroom filter
headroom_options = ['All', 'Overcommitted', 'Tight', 'Moderate', 'Available']
selected_headroom = st.sidebar.selectbox("Filter by headroom", headroom_options)

# MW input for "can I connect X MW here?"
st.sidebar.divider()
st.sidebar.markdown("### Test a connection")
test_mw = st.sidebar.number_input("Proposed capacity (MW)", min_value=0, max_value=500, value=0, step=5)
test_tech = st.sidebar.selectbox("Technology", ["Solar", "Onshore Wind", "Battery", "Other"])

# Apply filters
filtered = df.copy()
if selected_tech != 'All':
    filtered = filtered[filtered['technology'] == selected_tech]
if selected_headroom != 'All':
    filtered = filtered[filtered['headroom_flag'] == selected_headroom]


# ============================================================
# MAIN CONTENT
# ============================================================
st.markdown("# South Wales Grid Connection Screener")
st.markdown("Transformer ratings · measured flows · connection queue · headroom analysis")
st.caption("📅 Flows: Mar 2022 – Apr 2023 · Transformer ratings: Dec 2025 · Queue data: Jan 2026")

# Summary metrics
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Substations", len(filtered))
with col2:
    n_over = (filtered['headroom_flag'] == 'Overcommitted').sum()
    st.metric("Overcommitted", n_over, delta=None)
with col3:
    n_tight = (filtered['headroom_flag'] == 'Tight').sum()
    st.metric("Tight", n_tight)
with col4:
    n_avail = (filtered['headroom_flag'].isin(['Moderate', 'Available'])).sum()
    st.metric("Available / Moderate", n_avail)


# ============================================================
# MAP
# ============================================================
st.markdown("---")

map_df = filtered.dropna(subset=['lat', 'lon']).copy()

# Colour by headroom flag
def flag_to_color(flag):
    return {
        'Overcommitted': [220, 50, 50, 180],
        'Tight':         [240, 160, 30, 180],
        'Moderate':      [80, 160, 220, 180],
        'Available':     [50, 180, 80, 180],
        'No data':       [150, 150, 150, 150],
    }.get(flag, [150, 150, 150, 150])

map_df['color'] = map_df['headroom_flag'].apply(flag_to_color)

# Size by total committed capacity
map_df['size'] = np.clip(map_df['total_committed_mva'].fillna(10) * 3, 300, 8000)

# If testing a connection, recompute headroom with the proposed MW
if test_mw > 0:
    map_df['headroom_with_test'] = map_df['headroom_mva'] - test_mw
    def test_color(h):
        if pd.isna(h): return [150, 150, 150, 150]
        if h < 0: return [220, 50, 50, 180]
        if h < 20: return [240, 160, 30, 180]
        if h < 50: return [80, 160, 220, 180]
        return [50, 180, 80, 180]
    map_df['color'] = map_df['headroom_with_test'].apply(test_color)

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
        
        # Size by committed capacity
        radius = max(5, min(20, (row.get('total_committed_mva') or 10) / 10))
        
        # Build popup text
        headroom_str = f"{row['headroom_mva']:.0f}" if pd.notna(row.get('headroom_mva')) else '?'
        rating_str = f"{row['total_nominal_mva']:.0f}" if pd.notna(row.get('total_nominal_mva')) else '?'
        connected_str = f"{row['connected_mva']:.1f}" if pd.notna(row.get('connected_mva')) else '?'
        accepted_str = f"{row['accepted_mva']:.1f}" if pd.notna(row.get('accepted_mva')) else '?'
        peak_str = f"{row['peak_import_mw']:.1f}" if pd.notna(row.get('peak_import_mw')) else '?'
        tech_str = row.get('technology') or '?'
        
        popup_html = f"""
        <div style="font-family: sans-serif; font-size: 13px; min-width: 220px;">
            <b>{row['display_name']}</b> ({row['voltage_kv']}kV)<br/>
            <hr style="margin: 4px 0;">
            Rating: {rating_str} MVA<br/>
            Peak import: {peak_str} MW<br/>
            <hr style="margin: 4px 0;">
            Connected: {connected_str} MVA<br/>
            Accepted: {accepted_str} MVA<br/>
            <b>Headroom: {headroom_str} MVA</b><br/>
            <hr style="margin: 4px 0;">
            Status: <b>{row['headroom_flag']}</b><br/>
            Technology: {tech_str}
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

# Legend
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
    st.info(f"Map shows headroom **after** adding {test_mw} MW of {test_tech}. Colours updated accordingly.")


# ============================================================
# SUBSTATION DETAIL TABLE
# ============================================================
st.markdown("---")
st.markdown("## Substation Details")

# Let user select a substation
selected_sub = st.selectbox(
    "Select a substation for detail view",
    options=['(Overview table)'] + sorted(filtered['display_name'].tolist()),
)

if selected_sub == '(Overview table)':
    # Show summary table
    display_cols = [
        'display_name', 'voltage_kv', 'total_nominal_mva', 'peak_import_mw',
        'utilisation_pct', 'connected_mva', 'accepted_mva', 'offered_mva',
        'headroom_mva', 'headroom_flag', 'technology', 'net_exporter',
    ]
    
    rename = {
        'display_name': 'Substation',
        'voltage_kv': 'kV',
        'total_nominal_mva': 'Rating (MVA)',
        'peak_import_mw': 'Peak Import (MW)',
        'utilisation_pct': 'Utilisation %',
        'connected_mva': 'Connected (MVA)',
        'accepted_mva': 'Accepted (MVA)',
        'offered_mva': 'Offered (MVA)',
        'headroom_mva': 'Headroom (MVA)',
        'headroom_flag': 'Status',
        'technology': 'Dominant Tech',
        'net_exporter': 'Net Exporter',
    }
    
    table_df = filtered[display_cols].rename(columns=rename).sort_values('Headroom (MVA)')
    
    # Style: highlight overcommitted rows
    def color_headroom(val):
        if pd.isna(val): return ''
        if val < 0: return 'background-color: #ffcccc'
        if val < 20: return 'background-color: #fff3cd'
        return ''
    
    styled = table_df.style.map(color_headroom, subset=['Headroom (MVA)'])
    st.dataframe(styled, use_container_width=True, height=600)

else:
    # Detail view for selected substation
    row = filtered[filtered['display_name'] == selected_sub].iloc[0]
    
    st.markdown(f"### {row['display_name']} ({row['voltage_kv']}kV)")
    
    # Key metrics in columns
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
        mean = row.get('mean_import_mw')
        util = row.get('utilisation_pct')
        
        st.metric("Peak Import", f"{peak:.1f} MW" if pd.notna(peak) else "?")
        st.metric("Mean Import", f"{mean:.1f} MW" if pd.notna(mean) else "?")
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
    
    # Test connection
    if test_mw > 0:
        st.markdown("---")
        st.markdown(f"#### What if: {test_mw} MW {test_tech} connects here?")
        new_headroom = headroom - test_mw if pd.notna(headroom) else None
        if new_headroom is not None:
            if new_headroom < 0:
                st.error(f"Would push headroom to **{new_headroom:.0f} MVA** — overcommitted")
            elif new_headroom < 20:
                st.warning(f"Would leave **{new_headroom:.0f} MVA** headroom — tight")
            else:
                st.success(f"Would leave **{new_headroom:.0f} MVA** headroom — feasible")
    
    # Data quality note
    st.markdown("---")
    st.caption(f"Flow data: {row.get('date_from', '?')} to {row.get('date_to', '?')} | {row.get('n_timestamps', '?')} timestamps")
    st.caption("Headroom = nominal transformer rating − (connected + accepted generation). Negative means overcommitted on paper.")
    st.caption("This does not account for diversity, curtailment arrangements, or queue attrition.")


# ============================================================
# FOOTER
# ============================================================
st.markdown("---")
st.caption("**Loom Light** — Grid Connection Intelligence")
st.caption("Data sources: NGED LTDS Table 2a (transformer ratings), NGED BSP transformer flows (Mar 2022–Apr 2023), NGED Generation Connection Register (Jan 2026)")
st.caption("⚠️ Prototype — not for investment decisions. Headroom calculations do not account for diversity, curtailment, demand, or planned reinforcements.")
